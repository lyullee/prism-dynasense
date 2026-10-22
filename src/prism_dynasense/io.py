"""Versioned input, strict JSON/CSV exports and reproducibility fingerprints."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
from importlib.metadata import version
from pathlib import Path

from . import __version__
from .contracts import Study


def load_study(path) -> Study:
    return Study.model_validate_json(Path(path).read_text(encoding="utf-8-sig"))


def dump_json(path, value):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def fingerprint(study):
    encoded=json.dumps(study.model_dump(mode="json"),sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    root=Path(__file__).resolve().parent
    return {"software":"PRISM-DynaSense","version":__version__,"python":platform.python_version(),
            "input_sha256":hashlib.sha256(encoded).hexdigest(),
            "dependencies":{name:version(name) for name in ("prism-risk","numpy","scipy","SALib","pydantic")},
            "source_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob("*.py"))},
            "reproduction":"same validated input, source hashes, dependency versions, seed and sampling levels"}


def export_simulation(directory, simulation):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    history=simulation.history()
    with (out/"history.csv").open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.writer(f);writer.writerow(history)
        writer.writerows(zip(*history.values(),strict=True))
    dump_json(out/"simulation.json",{"scenario":simulation.scenario.model_dump(),"outputs":simulation.outputs,
                                    "audit":simulation.audit,"history":history})


def export_sensitivity(directory, result):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True)
    dump_json(out/"sensitivity.json",result)
    design=result["largest_design"]
    with (out/"samples_and_outputs.csv").open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f);w.writerow(["sample_id"]+design["input_names"]+design["output_names"])
        w.writerows([i]+x+y for i,(x,y) in enumerate(zip(design["samples"],design["values"],strict=True)))
    final=result["levels"][str(result["base_sample_levels"][-1])]["outputs"]
    with (out/"sobol_indices.csv").open("w",encoding="utf-8-sig",newline="") as f:
        columns=["output","input","S1","ST","S1_ci_half_width","ST_ci_half_width","convergence_status"]
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for name,row in final.items():
            for index in row["indices"]:
                w.writerow({"output":name,**index,"convergence_status":result["convergence"][name]["status"]})

