import math
import pytest
from pydantic import ValidationError
from prism_dynasense import Scenario,Study,Variable


@pytest.mark.parametrize("updates",[
    {"initial_pressure_pa":float("nan")},{"radiant_fraction":float("inf")},
    {"hole_diameter_m":0.},{"isolation_time_s":-1.},{"receptor_distance_m":0.},
    {"fluid":"Ammonia"},{"unknown":1.},{"time_step_s":41.},
    {"time_step_s":.00001},{"discharge_coefficient":1.1},{"temperature_k":23.},
])
def test_invalid_scenarios_are_rejected(updates):
    with pytest.raises(ValidationError):Scenario(**updates)


def test_required_variable_identity_and_baseline_bounds():
    with pytest.raises(ValidationError):Variable(name="made_up",lower=0.,upper=1.)
    with pytest.raises(ValidationError):Variable(name="radiant_fraction",lower=.2,upper=.1)
    with pytest.raises(ValidationError):Study(variables=[Variable(name="radiant_fraction",lower=.2,upper=.3)])


def test_duplicate_and_infeasible_designs_rejected():
    v=Variable(name="radiant_fraction",lower=.05,upper=.15)
    with pytest.raises(ValidationError):Study(variables=[v,v])
    with pytest.raises(ValidationError):Study(variables=[Variable(name="radiant_fraction",lower=-.1,upper=.2)])


def test_sample_dimensions_and_range():
    s=Study()
    with pytest.raises(ValueError):s.with_values([.1])
    with pytest.raises(ValueError):s.with_values([float("nan")]*5)
    assert s.with_values([getattr(s.scenario,v.name) for v in s.variables])==s.scenario


def test_json_roundtrip():
    study=Study()
    assert Study.model_validate_json(study.model_dump_json())==study

