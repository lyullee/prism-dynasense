"""Check the actual wheel contents before publishing a release."""
from pathlib import Path
import zipfile


def main():
    root = Path(__file__).resolve().parents[1]
    wheel = next((root / "dist").glob("*.whl"))
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        required = ["prism_dynasense/cli.py", "prism_dynasense/templates/dashboard.html", "prism_dynasense/data/example.json"]
        for name in required:
            if name not in names: raise RuntimeError(f"wheel is missing {name}")
        if not any(name.endswith("/licenses/THIRD_PARTY_NOTICES.md") for name in names):
            raise RuntimeError("third-party notices missing from wheel")
        if any(".venv" in name or "__pycache__" in name for name in names):
            raise RuntimeError("development environment leaked into wheel")
    print(f"Wheel verified: {wheel.name} ({len(names)} files)")


if __name__ == "__main__": main()
