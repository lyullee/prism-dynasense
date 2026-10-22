"""PRISM-DynaSense: transient accident screening with explicit assumptions."""

__version__ = "0.1.0"

from .contracts import Scenario, Study, Variable
from .simulation import simulate
from .sensitivity import local_sensitivity, run_sensitivity

__all__ = ["Scenario", "Study", "Variable", "simulate", "local_sensitivity", "run_sensitivity", "__version__"]

