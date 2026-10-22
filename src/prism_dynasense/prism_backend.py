"""Small adapter to installed PRISM 0.6.8, never a copied private runtime."""
from __future__ import annotations

import hashlib
import inspect
import math
from importlib.metadata import version

import numpy as np

SUPPORTED_PRISM = "0.6.8"


def check_backend() -> dict:
    installed = version("prism-risk")
    if installed != SUPPORTED_PRISM:
        raise RuntimeError(f"PRISM {SUPPORTED_PRISM} required; installed {installed}")
    from lh2_tno.risk import thermal_dose
    from prism_qra.risk import ThermalProbit, probit_to_probability
    modules = (inspect.getmodule(thermal_dose), inspect.getmodule(ThermalProbit))
    hashes = {}
    for module in modules:
        with open(module.__file__, "rb") as stream:
            hashes[module.__name__] = hashlib.sha256(stream.read()).hexdigest()
    return {"package": "prism-risk", "version": installed, "module_sha256": hashes,
            "functions": ["lh2_tno.risk.thermal_dose", "prism_qra.risk.ThermalProbit",
                          "prism_qra.risk.probit_to_probability"]}


def prism_thermal_dose(time_s, flux_w_m2) -> float:
    """PRISM's analytic integral of piecewise-linear heat-flux samples."""
    from lh2_tno.risk import FluxStep, thermal_dose
    steps = tuple(FluxStep(time_s=float(t), heat_flux_w_m2=float(q))
                  for t, q in zip(time_s, flux_w_m2, strict=True))
    return float(thermal_dose(steps)["dose"])


def harm_probability(dose):
    """Conditional unprotected thermal-fatality model, not annual risk."""
    from prism_qra.risk import ThermalProbit, probit_to_probability
    values = np.asarray(dose, dtype=float)
    if np.any(~np.isfinite(values)) or np.any(values < 0):
        raise ValueError("finite nonnegative thermal dose required")
    model = ThermalProbit()
    flat = [0.0 if x == 0 else probit_to_probability(model.a + model.b * math.log(x))
            for x in values.ravel()]
    result = np.asarray(flat).reshape(values.shape)
    return float(result) if values.ndim == 0 else result

