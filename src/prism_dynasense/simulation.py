"""Finite-inventory gas release and conditional point-source thermal exposure.

Original isothermal ideal-gas screening model. A connected upstream reservoir
is isolated at a declared time; gas remaining downstream continues to leak.
Radiation is quasi-steady with an explicitly supplied radiant fraction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from .contracts import Scenario
from .prism_backend import check_backend, harm_probability, prism_thermal_dose

R_SPECIFIC = 8.31446261815324 / 0.00201588
GAMMA = 1.4
AMBIENT_PA = 101325.0
H2_LHV_J_KG = 120_000_000.0

OUTPUT_LABELS = {
    "released_mass_kg": "기록 구간 누출질량", "peak_release_kg_s": "최대 누출률",
    "peak_heat_flux_w_m2": "최대 열유속", "thermal_dose": "누적 열노출량",
    "conditional_harm_probability": "조건부 피해확률",
    "dose_at_25pct": "평가시간 25%의 누적 열노출량",
    "dose_at_50pct": "평가시간 50%의 누적 열노출량",
    "dose_at_75pct": "평가시간 75%의 누적 열노출량",
}
OUTPUT_UNITS = {"released_mass_kg": "kg", "peak_release_kg_s": "kg/s", "peak_heat_flux_w_m2": "W/m²",
                "thermal_dose": "(W/m²)^(4/3)·s", "conditional_harm_probability": "1",
                "dose_at_25pct": "(W/m²)^(4/3)·s", "dose_at_50pct": "(W/m²)^(4/3)·s", "dose_at_75pct": "(W/m²)^(4/3)·s"}


def gas_release_rate(pressure_pa: float, temperature_k: float, hole_m: float, cd: float) -> float:
    """Ideal-gas isentropic nozzle, choked and unchoked regimes (SI)."""
    if not all(math.isfinite(x) for x in (pressure_pa, temperature_k, hole_m, cd)):
        raise ValueError("finite nozzle inputs required")
    if pressure_pa <= 0 or temperature_k <= 0 or hole_m <= 0 or not 0 < cd <= 1:
        raise ValueError("positive nozzle state and Cd in (0,1] required")
    if pressure_pa <= AMBIENT_PA:
        return 0.0
    ratio = AMBIENT_PA / pressure_pa
    critical = (2.0 / (GAMMA + 1.0)) ** (GAMMA / (GAMMA - 1.0))
    if ratio <= critical:
        factor = math.sqrt(GAMMA) * (2.0 / (GAMMA + 1)) ** ((GAMMA + 1) / (2 * (GAMMA - 1)))
    else:
        factor = math.sqrt(max(0.0, 2 * GAMMA / (GAMMA - 1) * (ratio ** (2 / GAMMA) - ratio ** ((GAMMA + 1) / GAMMA))))
    return cd * math.pi * hole_m**2 / 4 * pressure_pa / math.sqrt(R_SPECIFIC * temperature_k) * factor


def power_segment_integrals(time_s, flux_w_m2, exponent=4.0 / 3.0):
    """Analytic integral for linear flux segments; stable near equal endpoints."""
    t, q = np.asarray(time_s, float), np.asarray(flux_w_m2, float)
    if t.ndim != 1 or q.shape != t.shape or len(t) < 2 or np.any(np.diff(t) <= 0):
        raise ValueError("matched increasing histories required")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(q)) or np.any(q < 0):
        raise ValueError("finite nonnegative heat flux required")
    a, b = q[:-1], q[1:]
    equal = np.isclose(a, b, rtol=1e-7, atol=1e-16)
    mean = np.empty_like(a)
    mean[equal] = (a[equal]**exponent + 4*((a[equal]+b[equal])/2)**exponent + b[equal]**exponent)/6
    mean[~equal] = (b[~equal]**(exponent+1)-a[~equal]**(exponent+1))/((exponent+1)*(b[~equal]-a[~equal]))
    return mean * np.diff(t)


@dataclass
class Simulation:
    scenario: Scenario
    time_s: np.ndarray
    pressure_pa: np.ndarray
    release_kg_s: np.ndarray
    released_kg: np.ndarray
    remaining_kg: np.ndarray
    trapped_upstream_kg: np.ndarray
    heat_flux_w_m2: np.ndarray
    cumulative_dose: np.ndarray
    conditional_probability: np.ndarray
    outputs: dict[str, float]
    audit: dict

    def history(self) -> dict:
        return {"time_s": self.time_s.tolist(), "pressure_pa": self.pressure_pa.tolist(),
                "release_kg_s": self.release_kg_s.tolist(), "released_kg": self.released_kg.tolist(),
                "remaining_kg": self.remaining_kg.tolist(), "trapped_upstream_kg": self.trapped_upstream_kg.tolist(),
                "heat_flux_w_m2": self.heat_flux_w_m2.tolist(), "cumulative_dose": self.cumulative_dose.tolist(),
                "conditional_probability": self.conditional_probability.tolist()}


def _pressure_solution(scenario, volume, start, end, initial_pressure):
    if start >= end:
        return lambda x: np.full_like(np.asarray(x, dtype=float), initial_pressure)
    def rhs(t, p):
        q = gas_release_rate(max(AMBIENT_PA, float(p[0])), scenario.temperature_k,
                             scenario.hole_diameter_m, scenario.discharge_coefficient)
        return [-R_SPECIFIC * scenario.temperature_k / volume * q]
    def ambient(t, p):
        return p[0] - AMBIENT_PA
    ambient.terminal = True
    ambient.direction = -1
    solution = solve_ivp(rhs, (start, end), [initial_pressure], rtol=1e-8, atol=1e-4,
                         dense_output=True, events=ambient)
    if not solution.success:
        raise RuntimeError("pressure integration failed: " + solution.message)
    stop = float(solution.t[-1])
    def evaluate(t):
        tt = np.asarray(t, dtype=float)
        return np.maximum(AMBIENT_PA, np.where(tt <= stop, solution.sol(np.minimum(tt, stop))[0], AMBIENT_PA))
    return evaluate


def simulate(scenario: Scenario, *, backend_check=True) -> Simulation:
    """Execute one complete recorded scenario; retain residual inventory."""
    if not isinstance(scenario, Scenario):
        raise TypeError("a validated Scenario is required")
    if backend_check:
        check_backend()
    s = scenario
    times = np.linspace(0.0, s.horizon_s, int(math.ceil(s.horizon_s/s.time_step_s))+1)
    marks = [s.isolation_time_s, s.ignition_time_s, .25*s.horizon_s, .5*s.horizon_s, .75*s.horizon_s]
    t = np.unique(np.r_[times, [x for x in marks if 0 <= x <= s.horizon_s]])
    combined_volume = s.upstream_volume_m3 + s.isolated_volume_m3
    rt = R_SPECIFIC * s.temperature_k
    initial_mass = s.initial_pressure_pa * combined_volume / rt
    cut = min(s.isolation_time_s, s.horizon_s)
    connected = _pressure_solution(s, combined_volume, 0., cut, s.initial_pressure_pa)
    p_cut = float(connected(np.array([cut]))[0])
    tail = _pressure_solution(s, s.isolated_volume_m3, cut, s.horizon_s, p_cut)
    p = np.empty_like(t)
    before = t <= cut
    p[before] = connected(t[before])
    p[~before] = tail(t[~before])
    separated = t >= s.isolation_time_s
    trapped = np.where(separated, p_cut*s.upstream_volume_m3/rt, 0.)
    remaining = np.where(separated, trapped + p*s.isolated_volume_m3/rt, p*combined_volume/rt)
    released = initial_mass - remaining
    q = np.array([gas_release_rate(float(pp), s.temperature_k, s.hole_diameter_m, s.discharge_coefficient) for pp in p])
    radiation = s.radiant_fraction * H2_LHV_J_KG * q * s.atmospheric_transmissivity / (4*math.pi*s.receptor_distance_m**2)
    flux = np.where(t >= s.ignition_time_s, radiation, 0.)
    dose = np.zeros_like(t)
    active = t >= s.ignition_time_s
    prism_dose = 0.
    if np.count_nonzero(active) >= 2:
        dose[active] = np.r_[0., np.cumsum(power_segment_integrals(t[active], radiation[active]))]
        prism_dose = prism_thermal_dose(t[active], radiation[active])
    pd = harm_probability(dose)
    outputs = {"released_mass_kg": float(released[-1]), "peak_release_kg_s": float(q.max()),
               "peak_heat_flux_w_m2": float(flux.max()), "thermal_dose": float(dose[-1]),
               "conditional_harm_probability": float(pd[-1]),
               "dose_at_25pct": float(dose[np.searchsorted(t,.25*s.horizon_s)]),
               "dose_at_50pct": float(dose[np.searchsorted(t,.5*s.horizon_s)]),
               "dose_at_75pct": float(dose[np.searchsorted(t,.75*s.horizon_s)])}
    closure = float(np.max(np.abs(initial_mass-remaining-released)))
    integral_mass = float(np.trapezoid(q, t))
    if not all(math.isfinite(v) for v in outputs.values()):
        raise RuntimeError("nonfinite model output; result withheld")
    if not math.isclose(outputs["thermal_dose"], prism_dose, rel_tol=1e-8, abs_tol=1e-8):
        raise RuntimeError("independent accumulation and PRISM dose disagree")
    audit = {"model":"hydrogen-ideal-isothermal-isolated-segment/v1", "initial_inventory_kg":initial_mass,
             "mass_closure_residual_kg":closure, "sampled_rate_integral_kg":integral_mass,
             "sampled_rate_integral_error_kg":integral_mass-outputs["released_mass_kg"],
             "prism_thermal_dose":prism_dose, "assessment_horizon_s":s.horizon_s,
             "leak_ended_within_record":bool(p[-1] <= AMBIENT_PA*(1+1e-7)),
             "remaining_inventory_kg":float(remaining[-1]),
             "radiation_model":"quasi-steady point-source; supplied radiant fraction and transmissivity",
             "source_assumptions":["ideal hydrogen gas", "isothermal", "fixed volumes", "instantaneous upstream isolation; downstream inventory retained"],
             "conditioning":"declared release and ignition scenario; unprotected thermal exposure",
             "full_event_exposure_claimed":False, "annual_risk_claimed":False,
             "independent_physical_validation":False}
    return Simulation(s,t,p,q,released,remaining,trapped,flux,dose,pd,outputs,audit)
