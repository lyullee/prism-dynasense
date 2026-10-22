"""Small command line application; computations are local and explicit."""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .contracts import Study
from .io import dump_json,export_sensitivity,export_simulation,fingerprint,load_study
from .prism_backend import check_backend
from .simulation import simulate
from .sensitivity import local_sensitivity,run_sensitivity


def parser():
    p=argparse.ArgumentParser(prog="prism-dynasense",description="PRISM-DynaSense: 동적 사고위험·민감도 분석기")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="배포 PRISM과 의존성 확인")
    template=sub.add_parser("template",help="편집 가능한 입력 예제 생성")
    template.add_argument("path")
    for name in ("run","sensitivity","demo"):
        command=sub.add_parser(name)
        if name!="demo":command.add_argument("input",help="입력 JSON 경로")
        command.add_argument("--out",default="dynasense-result")
        command.add_argument("--open",action="store_true",help="완료 후 결과 화면 열기")
        if name!="run":
            command.add_argument("--levels",type=int,nargs="+",default=[64,128,256])
            command.add_argument("--resamples",type=int,default=300)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=="doctor":
            import json
            print(json.dumps(check_backend(),indent=2));return 0
        if args.command=="template":
            if Path(args.path).exists():raise ValueError("input file exists; choose a new path")
            dump_json(args.path,Study().model_dump());print(args.path);return 0
        study=Study() if args.command=="demo" else load_study(args.input)
        out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
        dump_json(out/"input.json",study.model_dump())
        baseline=simulate(study.scenario)
        export_simulation(out,baseline)
        result=None
        if args.command in ("sensitivity","demo"):
            print("민감도 계산: 실제 사고모델을 표본별로 실행합니다.",flush=True)
            def progress(n,done,total):print(f"N={n}: {done}/{total}",flush=True)
            result=run_sensitivity(study,levels=tuple(args.levels),resamples=args.resamples,progress=progress)
            export_sensitivity(out,result)
            dump_json(out/"local_sensitivity.json",local_sensitivity(study))
        dump_json(out/"reproducibility.json",fingerprint(study))
        from .report import build_report
        build_report(out,study,baseline,result)
        print(f"결과: {out/'report.html'}",flush=True)
        if result:print(f"수렴 기준 통과: {result['convergence_passed']}/{result['output_count']} · 실패 표본: {result['failed_unique_evaluations']}")
        if args.open:webbrowser.open((out/"report.html").as_uri())
        return 2 if result and result["failed_unique_evaluations"] else 0
    except (ValueError,RuntimeError,OSError,ImportError) as exc:
        print(f"실행 실패: {exc}",file=sys.stderr);return 2


if __name__=="__main__":raise SystemExit(main())

