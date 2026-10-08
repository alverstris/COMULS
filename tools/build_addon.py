"""Build reproducible Imperial B1/B2 Anki add-ons with bundled audio.

All three installers share one package identity, so replacing a cohort
installer preserves COMULS's user_files and native note/card identities.
The cohort hint affects only the first unconfirmed course selection.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = (2026, 10, 8, 0, 0, 0)


def archive_entry(archive, name, content):
    entry = zipfile.ZipInfo(name, date_time=STAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, content)


def build():
    src = ROOT / "addon"
    required = ["__init__.py", "core.py", "templates.py", "collection.py", "ui.py", "reviewer.py",
                "bridge.py", "media.py", "course.py", "evidence.py", "placement.py", "data/media_manifest.json", "data/imperial_b1.json", "data/imperial_b2.json"]
    missing = [name for name in required if not (src / name).is_file()]
    if missing:
        raise SystemExit("Missing package files: " + ", ".join(missing))
    packs = [json.loads((src/name).read_text(encoding="utf-8")) for name in
             ("data/imperial_b1.json", "data/imperial_b2.json")]
    audio_files = {e["audio_file"] for pack in packs for e in pack["exercises"] if e.get("audio_file")}
    if not audio_files:
        raise SystemExit("Imperial listening content must include bundled recording filenames")
    media_paths = {p.name: p for p in (src/"data"/"media").rglob("*") if p.is_file()}
    missing = sorted(audio_files-media_paths.keys())
    if missing:
        raise SystemExit("Run the verified audio build before packaging; missing recordings: "+", ".join(missing[:8]))
    model_files = [p for p in src.rglob("*") if p.is_file() and p.suffix in (".onnx", ".pt", ".pth")]
    if model_files:
        raise SystemExit("Voice-model caches must remain outside the distributable add-on")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    files = [p for p in sorted(src.rglob("*")) if p.is_file()
             and not any(part in ("__pycache__", "user_files") for part in p.relative_to(src).parts)
             and p.suffix not in (".pyc", ".pyo")
             and p.name not in ("manifest.json", "course_profile.json")]
    variants = [(None, "comuls-imperial-demo.ankiaddon"),
                ("B1", "comuls-imperial-b1.ankiaddon"), ("B2", "comuls-imperial-b2.ankiaddon")]
    results = []
    for cohort, filename in variants:
        target = out / filename
        manifest = {"package": "comuls_tester", "name": "COMULS — Imperial "+(cohort or "French")+" course demo",
                    "min_point_version": 260903}
        profile = {"cohort": cohort, "project": "Imperial French course demo"}
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive_entry(archive, path.relative_to(src).as_posix(), path.read_bytes())
            archive_entry(archive, "course_profile.json", json.dumps(profile, ensure_ascii=False, indent=2)+"\n")
            archive_entry(archive, "manifest.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True)+"\n")
        results.append({"file": filename, "cohort": cohort, "bytes": target.stat().st_size,
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    legacy = out/"comuls-tester.ankiaddon"
    shutil.copyfile(out/variants[0][1], legacy)
    results.append(dict(results[0], file=legacy.name))
    (out/"SHA256SUMS").write_text("".join(item["sha256"]+"  "+item["file"]+"\n" for item in results), encoding="utf-8")
    (out/"build_manifest.json").write_text(json.dumps({
        "schema_version": 1, "package": "comuls_tester", "installers": results,
        "included_cohorts": {p["pack_id"]: len(p["exercises"]) for p in packs},
        "primary_recordings": len(audio_files), "packaged_files": len(files)+2,
        "cohort_behavior": "Initial suggestion only; existing course selection and progress are preserved."
    }, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    for result in results:
        print(f"Built {result['file']}: {result['bytes']} bytes; sha256 {result['sha256']}")
    return out/variants[0][1]


if __name__ == "__main__":
    build()
