"""Run the packaged COMULS add-on inside the real Anki Desktop application.

Requires a display (CI: xvfb-run), mpv, and a working/null audio sink.
The driver uses real widgets, QWebEngine DOM events, native reviewer buttons,
collection operations, and profile shutdown. No aqt objects are replaced.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def read_package(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        imperial = ["data/imperial_b1.json", "data/imperial_b2.json"]
        names = [name for name in imperial if name in archive.namelist()]
        if not names:
            names = ["data/tester.json"]
        exercises = []
        for name in names:
            exercises.extend(json.loads(archive.read(name))["exercises"])
        profile = json.loads(archive.read("course_profile.json")) if "course_profile.json" in archive.namelist() else {}
        return manifest, exercises, profile


def batches_for(stage, exercises):
    spec = importlib.util.spec_from_file_location("e2e_core", ROOT / "addon" / "core.py")
    core = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = core
    spec.loader.exec_module(core)
    groups = []
    for kind in core.EXERCISE_TYPES:
        candidates = [e for e in exercises if e["type"] == kind and core.level_eligible(e, stage)
                      and e.get("qa", {}).get("ready") and not e.get("prerequisites")]
        candidates.sort(key=lambda e: (e.get("origin_entry_level") != stage, e["id"]))
        if not candidates:
            raise ValueError(f"No independently admissible {stage} {kind} in packaged content")
        item = candidates[0]
        unit, linked = item["unit_id"], set(item.get("exposure_groups", []))
        preview = any(core.LEVELS.index(item.get(key) or item["level"]) > core.LEVELS.index(stage)
                      for key in ("level", "target_level", "carrier_level", "construction_level"))
        for group in groups:
            if (len(group["types"]) < 6 and unit not in group["units"]
                    and not linked.intersection(group["linked"]) and not (preview and group["preview"])):
                break
        else:
            group = {"types": [], "units": set(), "linked": set(), "preview": False}
            groups.append(group)
        group["types"].append(kind)
        group["units"].add(unit)
        group["linked"].update(linked)
        group["preview"] = group["preview"] or preview
    return [g["types"] for g in groups]


def seed_profiles(base, profiles):
    # Official ProfileManager creates Anki's actual preferences database.
    import anki.lang
    from aqt.profiles import ProfileManager, VideoDriver
    anki.lang.set_lang("en")
    pm = ProfileManager(ProfileManager.get_created_base_folder(str(base)))
    pm.setupMeta()
    pm.meta.update(defaultLang="en", firstRun=False, updates=False, suppressUpdate=True)
    pm.set_video_driver(VideoDriver.Software)
    for name in profiles:
        pm.create(name)
        pm.load(name)
        pm.profile["autoSync"] = False
        pm.profile["numBackups"] = 0
        pm.save()
    pm.db.close()


def child(base, profile, config):
    os.environ["COMULS_E2E_CONFIG"] = str(config)
    sys.argv = ["anki", "-b", str(base), "-p", profile, "-l", "en"]
    import aqt
    aqt.run()


def invoke(base, profile, config, output, timeout):
    config_path = output / f"{config['run_id']}.config.json"
    report_path = output / f"{config['run_id']}.json"
    config["report_path"] = str(report_path)
    config["artifact_dir"] = str(output)
    config_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    command = [sys.executable, str(Path(__file__).resolve()), "--child", str(base), profile, str(config_path)]
    log_path = output / f"{config['run_id']}.log"
    with log_path.open("w", encoding="utf-8") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if not report_path.exists():
        raise RuntimeError(f"{config['run_id']}: Anki exited {result.returncode} without a driver report; see {log_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if result.returncode or not report.get("passed"):
        raise RuntimeError(f"{config['run_id']}: {report.get('error', 'Anki process failed')}; see {log_path}")
    print(f"PASS {config['run_id']}: {len(report.get('reviews', []))} native reviews", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--addon", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "anki-e2e")
    parser.add_argument("--smoke", action="store_true", help="Verify cohort-package selection and two formats, without repeating the full format sweep")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--stages", nargs="+", choices=["B1", "B2"], default=["B1", "B2"])
    parser.add_argument("--child", nargs=3, metavar=("BASE", "PROFILE", "CONFIG"))
    args = parser.parse_args()
    if args.child:
        child(Path(args.child[0]), args.child[1], Path(args.child[2]))
        return
    if not args.addon or not args.addon.is_file():
        parser.error("--addon must point to the built .ankiaddon")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    addon = args.addon.resolve()
    manifest, exercises, profile = read_package(addon)
    plans = ([(stage, ["meaning_recall", "sound_discrimination"]) for stage in args.stages] if args.smoke
             else [(stage, kinds) for stage in args.stages for kinds in batches_for(stage, exercises)])
    profiles = ["E2E install"] + [f"E2E {stage} {i+1}" for i, (stage, _) in enumerate(plans)]
    summary = {"package": addon.name, "package_sha256": hashlib.sha256(addon.read_bytes()).hexdigest(),
               "anki": "26.09.3", "display": os.environ.get("DISPLAY"), "runs": [], "passed": False,
               "scope": "Real Anki Desktop with packaged add-on; automated interactions do not assess French pronunciation quality."}
    summary_path = output / "summary.json"
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    try:
        with tempfile.TemporaryDirectory(prefix="comuls-native-e2e-") as folder:
            base = Path(folder)
            seed_profiles(base, profiles)
            driver = base / "addons21" / "comuls_e2e_driver"
            driver.mkdir(parents=True)
            shutil.copyfile(ROOT / "tests" / "e2e" / "driver.py", driver / "driver.py")
            (driver / "__init__.py").write_text("from .driver import install\ninstall()\n", encoding="utf-8")
            common = {"package": manifest["package"], "addon_path": str(addon), "suggested_cohort": profile.get("cohort")}
            summary["runs"].append(invoke(base, profiles[0], dict(common, run_id="install", phase="install"), output, args.timeout))
            for i, (stage, kinds) in enumerate(plans):
                profile = profiles[i+1]
                run_id = f"{stage.lower()}-{i+1}"
                run = invoke(base, profile, dict(common, run_id=run_id, phase="student", stage=stage,
                             types=kinds, verify_caps=len(kinds) == 6, extra_controls=i == 0), output, args.timeout)
                summary["runs"].append(run)
                summary["runs"].append(invoke(base, profile, dict(common, run_id=run_id+"-reopen", phase="reopen",
                                            previous_report=str(output / (run_id+".json"))), output, args.timeout))
            for stage in ([] if args.smoke else args.stages):
                observed = {r["type"] for run in summary["runs"] if run.get("stage") == stage for r in run.get("reviews", [])}
                expected = {e["type"] for e in exercises}
                if observed != expected:
                    raise AssertionError(f"{stage} missing review formats: {sorted(expected-observed)}")
            if not args.smoke and not any(r.get("six_unit_cap_verified") for r in summary["runs"]):
                raise AssertionError("No actual six-unit admission cap was exercised")
            if not args.smoke:
                ratings = {r["ease"] for run in summary["runs"] for r in run.get("reviews", [])}
                assert ratings == {1, 2, 3, 4}, "All four native rating buttons must be exercised"
            summary["passed"] = True
    except Exception as error:
        summary["error"] = str(error)
        raise
    finally:
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
