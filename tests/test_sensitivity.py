import numpy as np
import pytest
from prism_dynasense import Study,Scenario,Variable
from prism_dynasense.sensitivity import analyze_sobol,convergence_gate,make_design,run_sensitivity


@pytest.mark.parametrize("n",[0,12,True,65536])
def test_invalid_sample_counts(n):
    with pytest.raises(ValueError):make_design(["x"],[[0,1]],n,1)


def test_additive_model_indices_and_reproducible_design():
    p,x=make_design(["x","y"],[[0,1],[0,1]],4096,12)
    _,xx=make_design(["x","y"],[[0,1],[0,1]],4096,12)
    np.testing.assert_array_equal(x,xx)
    y=x[:,0]+2*x[:,1]
    result=analyze_sobol(p,y,seed=12)
    rows={r["input"]:r for r in result["indices"]}
    assert rows["x"]["ST"]==pytest.approx(.2,abs=.015)
    assert rows["y"]["ST"]==pytest.approx(.8,abs=.015)


def test_ishigami_interaction_benchmark():
    p,x=make_design(["x1","x2","x3"],[[-np.pi,np.pi]]*3,4096,912)
    y=np.sin(x[:,0])+7*np.sin(x[:,1])**2+.1*x[:,2]**4*np.sin(x[:,0])
    result=analyze_sobol(p,y,seed=912)
    rows={r["input"]:r for r in result["indices"]}
    for name,expected in {"x1":.5576,"x2":.4424,"x3":.2437}.items():
        assert rows[name]["ST"]==pytest.approx(expected,abs=.04)
    assert rows["x3"]["S1"]==pytest.approx(0,abs=.04)


def test_constant_and_invalid_outputs_are_not_zero_indices():
    p,x=make_design(["x"],[[0,1]],32,1)
    r=analyze_sobol(p,np.ones(len(x)))
    assert r["status"]=="UNDEFINED_CONSTANT_OUTPUT" and r["indices"]==[]
    y=x[:,0].copy();y[3]=np.nan
    assert analyze_sobol(p,y)["status"]=="WITHHELD_INVALID_EVALUATIONS"
    with pytest.raises(ValueError):analyze_sobol(p,y[:-1])


def test_convergence_checks_all_inputs_not_only_top_one():
    a={"status":"ESTIMATED","indices":[{"input":"x","ST":.7,"ST_ci_half_width":.02},{"input":"y","ST":.3,"ST_ci_half_width":.01}],"top3":["x","y"]}
    b={"status":"ESTIMATED","indices":[{"input":"x","ST":.7,"ST_ci_half_width":.02},{"input":"y","ST":.4,"ST_ci_half_width":.01}],"top3":["x","y"]}
    assert convergence_gate(a,a)["status"]=="PASS"
    assert convergence_gate(a,b)["status"]=="WITHHELD"


def test_direct_model_campaign_and_undefined_early_time_output():
    study=Study(scenario=Scenario(horizon_s=2.,time_step_s=.5,ignition_time_s=1.9),variables=[Variable(name="radiant_fraction",lower=.05,upper=.15)])
    r=run_sensitivity(study,levels=(16,32),resamples=50)
    assert r["failed_unique_evaluations"]==0
    assert r["unique_model_evaluations"]<=16*3+32*3
    assert r["levels"]["32"]["outputs"]["dose_at_25pct"]["status"]=="UNDEFINED_CONSTANT_OUTPUT"
    assert r["convergence"]["dose_at_25pct"]["status"]=="WITHHELD"


def test_failed_model_evaluations_withhold_the_complete_output(monkeypatch):
    import prism_dynasense.sensitivity as module
    def broken(*args,**kwargs):raise ValueError("deliberate unavailable model")
    monkeypatch.setattr(module,"simulate",broken)
    study=Study(variables=[Variable(name="radiant_fraction",lower=.05,upper=.15)])
    r=run_sensitivity(study,levels=(16,32),resamples=50)
    assert r["failed_unique_evaluations"]>0
    assert all(o["status"]=="WITHHELD_INVALID_EVALUATIONS" for o in r["levels"]["32"]["outputs"].values())
    assert all(v is None for row in r["largest_design"]["values"] for v in row)

