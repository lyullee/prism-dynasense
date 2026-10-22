import json
from pathlib import Path
from prism_dynasense import Scenario,Study,simulate
from prism_dynasense.cli import main
from prism_dynasense.io import fingerprint,load_study
from prism_dynasense.report import build_report


def test_template_run_doctor_and_version(tmp_path,capsys):
    file=tmp_path/"study.json"
    assert main(["template",str(file)])==0
    assert main(["template",str(file)])==2
    assert load_study(file)==Study()
    assert main(["doctor"])==0
    out=tmp_path/"case"
    assert main(["run",str(file),"--out",str(out)])==0
    assert (out/"report.html").exists()
    assert (out/"history.csv").read_text(encoding="utf-8-sig").startswith("time_s,pressure_pa")
    result=json.loads((out/"simulation.json").read_text(encoding="utf-8"))
    assert result["outputs"]["released_mass_kg"]>0


def test_bad_inputs_return_nonzero_exit(tmp_path):
    file=tmp_path/"bad.json";file.write_text('{"scenario":{"hole_diameter_m":-1}}')
    assert main(["run",str(file),"--out",str(tmp_path/"case")])==2


def test_report_embeds_real_data_and_escapes_script_injection(tmp_path):
    s=Scenario(name="<script>alert('x')</script>")
    r=simulate(s);study=Study(scenario=s)
    path=build_report(tmp_path,study,r)
    html=path.read_text(encoding="utf-8")
    assert "<script>alert('x')</script>" not in html
    assert "\\u003cscript" in html
    assert str(r.outputs["released_mass_kg"]) in html
    assert "__DATA_JSON__" not in html
    assert 'https://cdn' not in html


def test_input_fingerprint_changes_with_model_input():
    a=fingerprint(Study())
    b=fingerprint(Study(scenario=Scenario(isolation_time_s=11.)))
    assert a["input_sha256"]!=b["input_sha256"]
    assert len(a["source_sha256"])>=6
    assert a["dependencies"]["prism-risk"]=="0.6.8"
