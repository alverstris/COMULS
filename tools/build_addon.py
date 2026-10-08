"""Build a reproducible .ankiaddon without shipping tests or source vocabularies."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def build():
    src = ROOT / "addon"
    required = ["__init__.py", "core.py", "templates.py", "collection.py", "ui.py", "reviewer.py", "data/tester.json"]
    missing = [name for name in required if not (src / name).is_file()]
    if missing:
        raise SystemExit("Missing package files: " + ", ".join(missing))
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    target = out / "comuls-tester.ankiaddon"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(src.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or "user_files" in path.parts:
                continue
            entry = zipfile.ZipInfo(path.relative_to(src).as_posix(), date_time=(2026, 10, 8, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, path.read_bytes())
        manifest_entry = zipfile.ZipInfo("manifest.json", date_time=(2026, 10, 8, 0, 0, 0))
        manifest_entry.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(manifest_entry, json.dumps({"package": "comuls_tester", "name": "COMULS tester", "min_point_version": 260903}))
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(checksum + "  " + target.name + "\n", encoding="utf-8")
    print(f"Built {target.name}: {target.stat().st_size} bytes; sha256 {checksum}")
    return target

if __name__ == "__main__":
    build()
