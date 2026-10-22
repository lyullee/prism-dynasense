import math
import numpy as np
import pytest
from prism_dynasense import Scenario,simulate
from prism_dynasense.simulation import AMBIENT_PA,R_SPECIFIC,gas_release_rate,power_segment_integrals
from prism_dynasense.prism_backend import check_backend,harm_probability,prism_thermal_dose


def test_published_prism_backend_is_real_and_pinned():
    r=check_backend()
    assert r["version"]=="0.6.8"
    assert len(r["module_sha256"])==2


@pytest.mark.parametrize("pressure",[1.,101325.])
def test_no_outflow_below_ambient(pressure):
    assert gas_release_rate(pressure,293.15,.004,.8)==0.


def test_nozzle_choked_area_scaling_and_critical_continuity():
    q=gas_release_rate(2e6,293.15,.004,.8)
    assert gas_release_rate(2e6,293.15,.008,.8)==pytest.approx(4*q)
    critical=AMBIENT_PA/((2/2.4)**(1.4/.4))
    a=gas_release_rate(critical*(1-1e-8),293.15,.004,.8)
    b=gas_release_rate(critical*(1+1e-8),293.15,.004,.8)
    assert a==pytest.approx(b,rel=1e-6)


def test_pre_isolation_pressure_matches_analytic_choked_isothermal_decay():
    s=Scenario(horizon_s=2.,time_step_s=.1,isolation_time_s=20.)
    r=simulate(s)
    q0=gas_release_rate(s.initial_pressure_pa,s.temperature_k,s.hole_diameter_m,s.discharge_coefficient)
    k=q0/s.initial_pressure_pa*R_SPECIFIC*s.temperature_k/(s.upstream_volume_m3+s.isolated_volume_m3)
    expected=s.initial_pressure_pa*np.exp(-k*r.time_s)
    np.testing.assert_allclose(r.pressure_pa,expected,rtol=1e-7)


def test_mass_closure_and_residual_release_after_upstream_isolation():
    r=simulate(Scenario())
    initial=r.audit["initial_inventory_kg"]
    np.testing.assert_allclose(r.remaining_kg+r.released_kg,initial,atol=1e-12)
    i=np.searchsorted(r.time_s,r.scenario.isolation_time_s)
    assert r.release_kg_s[i]>0
    assert r.released_kg[-1]>r.released_kg[i]
    assert r.trapped_upstream_kg[-1]>0
    assert r.audit["remaining_inventory_kg"]>0
    assert not r.audit["annual_risk_claimed"]
    assert not r.audit["independent_physical_validation"]


def test_initial_isolation_keeps_only_downstream_inventory_available():
    s=Scenario(isolation_time_s=0.)
    r=simulate(s)
    maximum=s.initial_pressure_pa*s.isolated_volume_m3/(R_SPECIFIC*s.temperature_k)
    assert 0 < r.released_kg[-1] < maximum


def test_no_ignition_means_zero_thermal_outputs_but_nonzero_release():
    r=simulate(Scenario(ignition_time_s=100.))
    assert r.outputs["thermal_dose"]==0.
    assert r.outputs["conditional_harm_probability"]==0.
    assert r.outputs["released_mass_kg"]>0


def test_ignition_discontinuity_does_not_leak_dose_into_previous_interval():
    r=simulate(Scenario(ignition_time_s=1.37))
    assert 1.37 in r.time_s
    assert np.all(r.cumulative_dose[r.time_s<=1.37]==0)
    assert np.all(r.heat_flux_w_m2[r.time_s<1.37]==0)
    assert r.heat_flux_w_m2[np.searchsorted(r.time_s,1.37)]>0


def test_point_source_distance_scaling_and_cumulative_probability():
    a=simulate(Scenario())
    b=simulate(Scenario(receptor_distance_m=2.))
    np.testing.assert_allclose(b.heat_flux_w_m2,a.heat_flux_w_m2/4)
    assert b.outputs["thermal_dose"]==pytest.approx(a.outputs["thermal_dose"]/4**(4/3))
    assert np.all(np.diff(a.conditional_probability)>=0)
    assert 0<a.outputs["conditional_harm_probability"]<1


def test_prism_integration_matches_exact_linear_ramp():
    t=np.array([0.,12.]);q=np.array([0.,3000.])
    expected=12*3000**(4/3)/(7/3)
    assert prism_thermal_dose(t,q)==pytest.approx(expected)
    assert sum(power_segment_integrals(t,q))==pytest.approx(expected)


def test_constant_flux_prism_probability_and_zero_boundary():
    from prism_qra.risk import ThermalProbit,probit_to_probability
    dose=prism_thermal_dose([0,10],[5000,5000])
    expected=probit_to_probability(ThermalProbit().probit(5000,10))
    assert harm_probability(dose)==pytest.approx(expected)
    assert harm_probability(0.)==0.
    with pytest.raises(ValueError):harm_probability(float("nan"))


def test_time_step_refinement_separate_from_sobol_convergence():
    results=[simulate(Scenario(time_step_s=dt)) for dt in (1.,.5,.25)]
    coarse,medium,fine=[r.outputs["thermal_dose"] for r in results]
    assert abs(medium-fine)/fine<.005
    assert abs(medium-fine)<abs(coarse-fine)
    assert abs(results[-1].audit["sampled_rate_integral_error_kg"])<abs(results[0].audit["sampled_rate_integral_error_kg"])


def test_deterministic_histories():
    a,b=simulate(Scenario()),simulate(Scenario())
    assert a.outputs==b.outputs
    np.testing.assert_array_equal(a.release_kg_s,b.release_kg_s)

