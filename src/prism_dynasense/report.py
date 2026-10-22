"""Self-contained dashboard and publication-friendly real-calculation plots."""
from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from . import __version__
from .contracts import VARIABLE_LABELS
from .simulation import OUTPUT_LABELS,OUTPUT_UNITS


def build_report(directory,study,baseline,sensitivity=None):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    final={}
    if sensitivity:
        final=sensitivity["levels"][str(sensitivity["base_sample_levels"][-1])]["outputs"]
    payload={"version":__version__,"study":study.model_dump(),"history":baseline.history(),
             "outputs":baseline.outputs,"audit":baseline.audit,
             "sensitivity":final,"gates":sensitivity["convergence"] if sensitivity else {},
             "sampling":{k:sensitivity[k] for k in ("seed","base_sample_levels","unique_model_evaluations","failed_unique_evaluations","method","duration_seconds")} if sensitivity else None,
             "variable_labels":VARIABLE_LABELS,"output_labels":OUTPUT_LABELS,"output_units":OUTPUT_UNITS}
    template=files("prism_dynasense").joinpath("templates/dashboard.html").read_text(encoding="utf-8")
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace("<","\\u003c").replace("\u2028","\\u2028").replace("\u2029","\\u2029")
    (out/"report.html").write_text(template.replace("__DATA_JSON__",encoded),encoding="utf-8")
    export_figures(out,baseline,final,sensitivity["convergence"] if sensitivity else {})
    return out/"report.html"


def export_figures(out,baseline,final,gates):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t=baseline.time_s
    fig,axes=plt.subplots(2,2,figsize=(11,7),constrained_layout=True)
    charts=[(baseline.release_kg_s,"Release rate (kg/s)"),(baseline.heat_flux_w_m2/1000,"Heat flux (kW/m²)"),
            (baseline.cumulative_dose,"Thermal dose ((W/m²)^(4/3) s)"),(baseline.conditional_probability,"Conditional thermal harm probability")]
    for ax,(y,label) in zip(axes.ravel(),charts):
        plot_t,plot_y=t,y
        if label.startswith("Heat flux") and 0 < baseline.scenario.ignition_time_s <= baseline.scenario.horizon_s:
            import numpy as np
            ignition_index=int(np.searchsorted(t,baseline.scenario.ignition_time_s))
            plot_t=np.insert(t,ignition_index,baseline.scenario.ignition_time_s)
            plot_y=np.insert(y,ignition_index,0.)
        ax.plot(plot_t,plot_y,color="#146b59",lw=2)
        ax.set(xlabel="Time (s)",ylabel=label)
        ax.axvline(baseline.scenario.ignition_time_s,color="#b0782d",ls=":",lw=1,label="Ignition")
        ax.axvline(baseline.scenario.isolation_time_s,color="#617182",ls="--",lw=1,label="Upstream isolation")
        ax.grid(alpha=.2)
        ax.tick_params(labelsize=10)
    axes[0,0].legend(fontsize=9)
    fig.suptitle("PRISM-DynaSense | Actual screening-model calculation\nIdeal isothermal H2; quasi-steady point-source radiation; finite horizon",fontsize=13)
    for extension in ("png","svg"):
        fig.savefig(out/f"time_history.{extension}",dpi=180)
    plt.close(fig)
    if not final:return
    row=final.get("thermal_dose",{})
    if not row.get("indices"):return
    ordered=list(reversed(row["indices"]))
    fig,ax=plt.subplots(figsize=(9,4.5),constrained_layout=True)
    labels=[r["input"].replace("_"," ") for r in ordered]
    ax.errorbar([r["ST"] for r in ordered],labels,xerr=[r["ST_ci_half_width"] for r in ordered],fmt="o",color="#146b59",capsize=4)
    ax.axvline(0,color="#71807d",lw=.8)
    ax.set_xlabel("Total-order Sobol index ST (bootstrap 95% half-width)")
    ax.set_title("Thermal-dose sensitivity | Convergence: "+gates["thermal_dose"]["status"])
    ax.grid(axis="x",alpha=.2)
    for extension in ("png","svg"):fig.savefig(out/f"sobol_thermal_dose.{extension}",dpi=180)
    plt.close(fig)

