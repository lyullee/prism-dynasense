"""Assemble original-source inventory and a registration preparation archive.

No external library source, credentials, virtual environments or private data
are copied. This script prepares evidence; it does not submit a registration.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    out = ROOT / "artifacts" / "registration"
    out.mkdir(parents=True, exist_ok=True)
    original = []
    for folder, category in (("src", "application"), ("tests", "tests"), ("tools", "supporting-tool")):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".html", ".json", ".cjs"} and "__pycache__" not in path.parts:
                original.append({"path": path.relative_to(ROOT).as_posix(), "category": category,
                                 "bytes": path.stat().st_size, "lines": len(path.read_text(encoding="utf-8").splitlines()),
                                 "sha256": sha256(path)})
    inventory = {"program": "PRISM-DynaSense", "version": VERSION,
                 "ownership_status": "rights holder, applicant and employment ownership require human confirmation",
                 "third_party_source_included": False, "files": original,
                 "totals": {"files": len(original), "lines": sum(p["lines"] for p in original), "bytes": sum(p["bytes"] for p in original)}}
    write_json(out / "source_inventory.json", inventory)

    candidates = [ROOT / name for name in ("README.md", "README_ko.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", "CITATION.cff", "pyproject.toml", "MANIFEST.in", "requirements-lock.txt")]
    for folder in ("src", "tests", "tools", "docs", "examples"):
        candidates.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and p.suffix in {".py", ".cjs", ".md", ".json", ".html", ".csv", ".png", ".svg"} and "__pycache__" not in p.parts)
    candidates.extend(p for p in (ROOT / "dist").glob("*") if p.suffix in {".whl", ".gz"})
    test_report = ROOT / "artifacts" / "test-results.xml"
    if test_report.exists(): candidates.append(test_report)
    browser_report = ROOT / "artifacts" / "browser-qa.json"
    if browser_report.exists(): candidates.append(browser_report)
    smoke_report = ROOT / "artifacts" / "wheel-smoke.json"
    if smoke_report.exists(): candidates.append(smoke_report)
    candidates.append(out / "source_inventory.json")
    unique = sorted(set(p for p in candidates if p.exists()))
    manifest = {"program": "PRISM-DynaSense", "version": VERSION, "purpose": "registration preparation, not a registration certificate",
                "files": [{"path": p.relative_to(ROOT).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)} for p in unique]}
    write_json(out / "release_manifest.json", manifest)
    archive = out / f"PRISM-DynaSense_{VERSION}_registration-preparation.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in unique + [out / "release_manifest.json"]:
            z.write(path, path.relative_to(ROOT).as_posix())
    checks = [archive, out / "source_inventory.json", out / "release_manifest.json"] + sorted((ROOT / "dist").glob("*"))
    (out / "SHA256SUMS.txt").write_text("".join(f"{sha256(p)}  {p.name}\n" for p in checks if p.is_file()), encoding="utf-8")
    print(json.dumps({"archive": str(archive), "files": len(unique)+1, "original_source_files": len(original), "sha256": sha256(archive)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
