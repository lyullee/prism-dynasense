"""Direct-model Sobol and local analysis with missing-output and convergence gates."""
from __future__ import annotations

import math
from time import perf_counter
from typing import Callable

import numpy as np
from SALib.analyze import sobol as sobol_analyze
from SALib.sample import sobol as sobol_sample

from .contracts import Study
from .prism_backend import check_backend
from .simulation import OUTPUT_LABELS, OUTPUT_UNITS, simulate


def make_design(names, bounds, base_samples, seed):
    if isinstance(base_samples, bool) or not isinstance(base_samples, int) or base_samples < 16 or base_samples > 16384 or base_samples & (base_samples-1):
        raise ValueError("base_samples must be a power of two between 16 and 16384")
    if not names or len(set(names)) != len(names) or len(bounds) != len(names):
        raise ValueError("unique names and matching bounds required")
    if any(len(b)!=2 or not all(math.isfinite(x) for x in b) or b[0]>=b[1] for b in bounds):
        raise ValueError("finite increasing bounds required")
    problem = {"num_vars":len(names), "names":list(names), "bounds":[list(b) for b in bounds]}
    sample = sobol_sample.sample(problem,base_samples,calc_second_order=False,scramble=True,seed=seed)
    return problem,sample


def analyze_sobol(problem, values, *, seed=20261022, resamples=300):
    """Analyze a complete Saltelli-ordered array; never drop individual rows."""
    y = np.asarray(values, dtype=float)
    d = int(problem["num_vars"])
    if y.ndim != 1 or len(y) < 16*(d+2) or len(y) % (d+2):
        raise ValueError("a complete first/total-order Sobol design is required")
    if not np.all(np.isfinite(y)):
        return {"status":"WITHHELD_INVALID_EVALUATIONS", "indices":[], "reason":"missing/nonfinite output; no zero filling or row dropping"}
    if np.ptp(y) <= 1e-12*max(float(np.max(np.abs(y))),1e-100):
        return {"status":"UNDEFINED_CONSTANT_OUTPUT", "indices":[], "reason":"output variance is zero or numerically negligible"}
    result = sobol_analyze.analyze(problem,y,calc_second_order=False,num_resamples=resamples,
                                   conf_level=.95,seed=seed,print_to_console=False)
    rows = [{"input":name,"S1":float(result["S1"][i]),"ST":float(result["ST"][i]),
             "S1_ci_half_width":float(result["S1_conf"][i]),"ST_ci_half_width":float(result["ST_conf"][i])}
            for i,name in enumerate(problem["names"])]
    if any(not math.isfinite(value) for row in rows for key,value in row.items() if key!="input"):
        return {"status":"WITHHELD_NUMERICAL_INDICES","indices":[],"reason":"nonfinite index or confidence interval"}
    rows.sort(key=lambda r:r["ST"],reverse=True)
    return {"status":"ESTIMATED", "indices":rows, "top3":[r["input"] for r in rows[:min(3,d)]]}


def convergence_gate(previous, current, *, st_tolerance=.05, ci_tolerance=.10):
    if previous["status"]!="ESTIMATED" or current["status"]!="ESTIMATED":
        return {"status":"WITHHELD", "reason":"both estimates must be finite and nonconstant"}
    old={r["input"]:r for r in previous["indices"]}
    if set(old)!={r["input"] for r in current["indices"]}:
        raise ValueError("input identities differ between convergence levels")
    change=max(abs(r["ST"]-old[r["input"]]["ST"]) for r in current["indices"])
    width=max(r["ST_ci_half_width"] for r in current["indices"])
    stable=set(previous["top3"])==set(current["top3"])
    passed=change<=st_tolerance and width<=ci_tolerance and stable
    return {"status":"PASS" if passed else "WITHHELD", "max_ST_change":change,
            "max_ST_ci_half_width":width,"top3_set_stable":stable,
            "criteria":{"max_ST_change":st_tolerance,"max_ST_ci_half_width":ci_tolerance,"top3_set_stable":True}}


def local_sensitivity(study: Study):
    """Baseline and individual range endpoints; not a causal global ranking."""
    baseline=simulate(study.scenario,backend_check=False).outputs
    rows=[]
    for variable in study.variables:
        samples={}
        for label,value in (("lower",variable.lower),("upper",variable.upper)):
            scenario=type(study.scenario).model_validate(study.scenario.model_dump()|{variable.name:value})
            samples[label]=simulate(scenario,backend_check=False).outputs
        rows.append({"input":variable.name,"lower":variable.lower,"upper":variable.upper,
                     "outputs_at_lower":samples["lower"],"outputs_at_upper":samples["upper"]})
    return {"baseline":baseline,"rows":rows,"interpretation":"one-at-a-time declared endpoints; interactions are not represented"}


def run_sensitivity(study: Study, *, levels=(128,256,512), resamples=300, progress: Callable|None=None):
    """Re-execute each unique physical case; no fitted surrogate is substituted."""
    backend=check_backend()
    levels=tuple(levels)
    if len(levels)<2 or tuple(sorted(set(levels)))!=levels:
        raise ValueError("at least two strictly increasing base sample levels required")
    if not isinstance(resamples,int) or isinstance(resamples,bool) or resamples<50:
        raise ValueError("at least 50 bootstrap resamples required")
    names=[v.name for v in study.variables]
    bounds=[[v.lower,v.upper] for v in study.variables]
    cache={}
    studies={}
    failures=[]
    started=perf_counter()
    largest_samples=[]
    largest_values=[]
    for n in levels:
        problem,x=make_design(names,bounds,n,study.seed)
        matrix=np.full((len(x),len(OUTPUT_LABELS)),np.nan)
        for i,values in enumerate(x):
            key=tuple(float(v) for v in values)
            if key not in cache:
                try:
                    outputs=simulate(study.with_values(values),backend_check=False).outputs
                    cache[key]=[outputs[k] for k in OUTPUT_LABELS]
                except Exception as exc:
                    cache[key]=[float("nan")]*len(OUTPUT_LABELS)
                    failures.append({"input":list(key),"error_type":type(exc).__name__,"message":str(exc)[:300]})
            matrix[i]=cache[key]
            if progress and (i+1)%max(1,len(x)//10)==0:
                progress(n,i+1,len(x))
        summary={}
        for j,output in enumerate(OUTPUT_LABELS):
            si=analyze_sobol(problem,matrix[:,j],seed=study.seed,resamples=resamples)
            si.update({"label":OUTPUT_LABELS[output],"unit":OUTPUT_UNITS[output]})
            if np.all(np.isfinite(matrix[:,j])):
                si["p05_p50_p95"]=np.quantile(matrix[:,j],[.05,.5,.95]).tolist()
            summary[output]=si
        studies[str(n)]={"design_rows":len(x),"outputs":summary}
        largest_samples=x.tolist()
        largest_values=[[float(v) if math.isfinite(v) else None for v in row] for row in matrix]
    previous,current=studies[str(levels[-2])]["outputs"],studies[str(levels[-1])]["outputs"]
    gates={o:convergence_gate(previous[o],current[o]) for o in OUTPUT_LABELS}
    return {"schema":"prism-dynasense/sensitivity/v1","method":"scrambled Sobol / Saltelli; first and total order; direct model",
            "input_distribution":"independent uniform ranges; no plant-population probability claim",
            "seed":study.seed,"base_sample_levels":list(levels),"bootstrap_resamples":resamples,
            "uncertainty":"bootstrap 95% half-width; model-form uncertainty not included",
            "backend":backend,"levels":studies,"convergence":gates,
            "convergence_passed":sum(r["status"]=="PASS" for r in gates.values()),
            "output_count":len(gates),"unique_model_evaluations":len(cache),
            "failed_unique_evaluations":len(failures),"failures":failures,
            "duration_seconds":perf_counter()-started,
            "largest_design":{"input_names":names,"output_names":list(OUTPUT_LABELS),"samples":largest_samples,"values":largest_values},
            "limits":["finite recorded horizon", "isothermal ideal hydrogen gas", "quasi-steady point-source radiation",
                      "conditional unprotected thermal harm; no annual risk", "convergence does not prove physical validity"]}

