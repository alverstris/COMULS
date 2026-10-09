"""Build reproducible, provenance-bearing Imperial B1/B2 Anki installers.

All installers keep the comuls_tester identity. Cohort selection is a fresh-
profile hint, so replacing an installer retains existing progress/user_files.
Release builds require a clean Git checkout and verified committed media.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import types
import zipfile

ROOT = Path(__file__).resolve().parents[1]
STAMP = (2026, 10, 9, 0, 0, 0)
PACKAGE = "comuls_tester"


def sha256(content):
    return hashlib.sha256(content).hexdigest()


def archive_entry(archive, name, content):
    entry = zipfile.ZipInfo(name, date_time=STAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o100644 << 16
    archive.writestr(entry, content)


def source_provenance(root, files, require_clean=False):
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    status = subprocess.check_output([
        "git", "status", "--porcelain", "--untracked-files=all", "--", "addon", "tools", "tests", ".github", "docs"
    ], cwd=root, text=True).strip()
    if require_clean and status:
        raise ValueError("Release source is not a clean Git commit; commit the implementation and verification first")
    digests = {str(path.relative_to(root / "addon").as_posix()): sha256(path.read_bytes()) for path in files}
    digest = sha256(json.dumps(digests, sort_keys=True, separators=(",", ":")).encode())
    return {"schema_version": 1, "source_commit": commit, "source_dirty": bool(status),
            "source_tree_sha256": digest, "source_files": digests}


def addon_module(root, name):
    # Import validators without importing addon's Qt startup side effects.
    package_name = "comuls_build_validation"
    package = types.ModuleType(package_name)
    package.__path__ = [str(root / "addon")]
    sys.modules[package_name] = package
    spec = importlib.util.spec_from_file_location(package_name + "." + name, root / "addon" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def addon_version(src):
    for node in ast.parse((src / "version.py").read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "VERSION" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Missing add-on VERSION")


def build(*, require_clean=False):
    src = ROOT / "addon"
    required = ["__init__.py", "core.py", "templates.py", "collection.py", "ui.py", "reviewer.py",
                "bridge.py", "media.py", "course.py", "version.py", "evidence.py", "placement.py", "pack_install.py",
                "data/media_manifest.json", "data/imperial_b1.json", "data/imperial_b2.json"]
    missing = [name for name in required if not (src / name).is_file()]
    if missing:
        raise ValueError("Missing package files: " + ", ".join(missing))
    core = addon_module(ROOT, "core")
    packs = [core.load_pack(src / name) for name in ("data/imperial_b1.json", "data/imperial_b2.json")]
    media = addon_module(ROOT, "media")
    assets = {}
    for cohort, pack in zip(("B1", "B2"), packs):
        if not pack["exercises"] or {e["type"] for e in pack["exercises"]} != set(core.EXERCISE_TYPES):
            raise ValueError(cohort + " must include all thirteen exercise formats")
        if any(e.get("cohort", e.get("origin_entry_level")) != cohort for e in pack["exercises"]):
            raise ValueError(cohort + " pack contains an exercise assigned to a different cohort")
        assets.update(media.validate_pack_media(pack, src))
    if not assets:
        raise ValueError("Imperial listening content must include bundled recordings")
    files = []
    for path in sorted(src.rglob("*")):
        if path.is_symlink():
            raise ValueError("Distributable source must not contain symlinks: " + str(path))
        if not path.is_file() or any(part in ("__pycache__", "user_files") for part in path.relative_to(src).parts):
            continue
        if path.suffix in (".onnx", ".pt", ".pth"):
            raise ValueError("Voice model caches must remain outside the distributable add-on")
        if path.suffix in (".pyc", ".pyo") or path.name in ("manifest.json", "course_profile.json", "provenance.json"):
            continue
        files.append(path)
    provenance = source_provenance(ROOT, files, require_clean)
    version = addon_version(src)
    provenance.update(addon_version=version, package=PACKAGE)
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    variants = [(None, "comuls-imperial-demo.ankiaddon"),
                ("B1", "comuls-imperial-b1.ankiaddon"), ("B2", "comuls-imperial-b2.ankiaddon")]
    results = []
    for cohort, filename in variants:
        target = out / filename
        manifest = {"package": PACKAGE, "name": "COMULS — Imperial " + (cohort or "French") + " course demo",
                    "min_point_version": 260903}
        profile = {"cohort": cohort, "project": "Imperial French course demo"}
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive_entry(archive, path.relative_to(src).as_posix(), path.read_bytes())
            for name, value in (("course_profile.json", profile), ("manifest.json", manifest), ("provenance.json", provenance)):
                archive_entry(archive, name, json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        results.append({"file": filename, "cohort": cohort, "bytes": target.stat().st_size,
                        "sha256": sha256(target.read_bytes())})
    legacy = out / "comuls-tester.ankiaddon"
    shutil.copyfile(out / variants[0][1], legacy)
    results.append(dict(results[0], file=legacy.name))
    (out / "SHA256SUMS").write_text("".join(item["sha256"] + "  " + item["file"] + "\n" for item in results), encoding="utf-8")
    (out / "build_manifest.json").write_text(json.dumps({
        "schema_version": 1, "package": PACKAGE, "addon_version": version,
        "source_commit": provenance["source_commit"], "source_dirty": provenance["source_dirty"],
        "source_tree_sha256": provenance["source_tree_sha256"], "installers": results,
        "included_cohorts": {p["pack_id"]: len(p["exercises"]) for p in packs},
        "bundled_recordings": len(assets), "packaged_files": len(files) + 3,
        "cohort_behavior": "Initial suggestion only; existing course selection and progress are preserved."
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for result in results:
        print(f"Built {result['file']}: {result['bytes']} bytes; sha256 {result['sha256']}")
    return out / variants[0][1]


def verify_release(dist, source_commit):
    """Fail closed unless published bytes have matching exact-commit native evidence."""
    manifest = json.loads((dist / "build_manifest.json").read_text(encoding="utf-8"))
    if manifest["source_commit"] != source_commit or manifest["source_dirty"]:
        raise ValueError("Release manifest does not identify the clean requested source commit")
    installers = {item["file"]: item for item in manifest["installers"]}
    for item in installers.values():
        if sha256((dist / item["file"]).read_bytes()) != item["sha256"]:
            raise ValueError("Installer changed after verification: " + item["file"])
    expected_types = set(addon_module(ROOT, "core").EXERCISE_TYPES)
    expected = (("general", "comuls-imperial-demo.ankiaddon", "full"),
                ("b1-installer", "comuls-imperial-b1.ankiaddon", "smoke"),
                ("b2-installer", "comuls-imperial-b2.ankiaddon", "smoke"))
    for folder, package, mode in expected:
        report = json.loads((dist / "native-verification" / (folder + ".json")).read_text(encoding="utf-8"))
        if not report.get("passed") or report.get("verification_mode") != mode:
            raise ValueError("Required native application verification did not pass: " + folder)
        if report["source_commit"] != source_commit or report["source_dirty"]:
            raise ValueError("Native application evidence identifies another source commit")
        if report["package_sha256"] != installers[package]["sha256"]:
            raise ValueError("Native application evidence identifies another installer")
        if report["source_tree_sha256"] != manifest["source_tree_sha256"]:
            raise ValueError("Native application evidence identifies another source tree")
        if not report.get("runs") or any(not run.get("passed") for run in report["runs"]):
            raise ValueError("Missing or failed native application scenarios")
        if mode == "full":
            for stage in ("B1", "B2"):
                formats = {review["type"] for run in report["runs"] if run.get("stage") == stage
                           for review in run.get("reviews", [])}
                if formats != expected_types:
                    raise ValueError("Native application must review all thirteen formats for " + stage)
    print("Release evidence matches clean source " + source_commit)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-clean", action="store_true", help="Refuse a release build from uncommitted source")
    parser.add_argument("--verify-release", type=Path, help="Check installer hashes against native reports in this dist directory")
    parser.add_argument("--source-commit", help="Exact source commit required by --verify-release")
    args = parser.parse_args()
    if args.verify_release:
        if not args.source_commit:
            parser.error("--verify-release requires --source-commit")
        verify_release(args.verify_release, args.source_commit)
    else:
        build(require_clean=args.require_clean)
