"""Publication must reject stale, dirty, altered or incompletely tested installers."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("comuls_build_test", ROOT / "tools/build_addon.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def release_fixture(tmp_path):
    commit = "a" * 40
    tree = "b" * 64
    types = list(build.addon_module(ROOT, "core").EXERCISE_TYPES)
    manifest = {"source_commit": commit, "source_dirty": False, "source_tree_sha256": tree, "installers": []}
    reports = tmp_path / "native-verification"
    reports.mkdir()
    for name, filename, mode in (("general", "comuls-imperial-demo.ankiaddon", "full"),
                                  ("b1-installer", "comuls-imperial-b1.ankiaddon", "smoke"),
                                  ("b2-installer", "comuls-imperial-b2.ankiaddon", "smoke")):
        content = (filename + " verified installer bytes").encode()
        (tmp_path / filename).write_bytes(content)
        digest = build.sha256(content)
        manifest["installers"].append({"file": filename, "sha256": digest})
        report = {"source_commit": commit, "source_dirty": False, "source_tree_sha256": tree,
                  "package_sha256": digest, "passed": True, "verification_mode": mode,
                  "runs": [{"passed": True, "stage": stage, "reviews": [{"type": kind} for kind in types]}
                           for stage in ("B1", "B2")]}
        (reports / (name + ".json")).write_text(json.dumps(report))
    (tmp_path / "build_manifest.json").write_text(json.dumps(manifest))
    return commit


def mutate(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def test_gate_accepts_matching_complete_evidence(tmp_path):
    commit = release_fixture(tmp_path)
    assert build.verify_release(tmp_path, commit)["source_commit"] == commit


@pytest.mark.parametrize("field,value", [("source_commit", "c" * 40), ("source_dirty", True)])
def test_gate_rejects_dirty_or_stale_source(tmp_path, field, value):
    commit = release_fixture(tmp_path)
    mutate(tmp_path / "build_manifest.json", lambda m: m.update({field: value}))
    with pytest.raises(ValueError, match="clean requested source"):
        build.verify_release(tmp_path, commit)


def test_gate_rejects_changed_installer_bytes(tmp_path):
    commit = release_fixture(tmp_path)
    (tmp_path / "comuls-imperial-b1.ankiaddon").write_bytes(b"changed after native verification")
    with pytest.raises(ValueError, match="changed after verification"):
        build.verify_release(tmp_path, commit)


def test_gate_rejects_smoke_as_full_verification(tmp_path):
    commit = release_fixture(tmp_path)
    mutate(tmp_path / "native-verification/general.json", lambda r: r.update(verification_mode="smoke"))
    with pytest.raises(ValueError, match="did not pass"):
        build.verify_release(tmp_path, commit)


def test_gate_rejects_missing_format_despite_passed_flag(tmp_path):
    commit = release_fixture(tmp_path)
    mutate(tmp_path / "native-verification/general.json", lambda r: r["runs"][0]["reviews"].pop())
    with pytest.raises(ValueError, match="all thirteen formats"):
        build.verify_release(tmp_path, commit)


def test_gate_rejects_native_results_from_another_package(tmp_path):
    commit = release_fixture(tmp_path)
    mutate(tmp_path / "native-verification/b2-installer.json", lambda r: r.update(package_sha256="0" * 64))
    with pytest.raises(ValueError, match="another installer"):
        build.verify_release(tmp_path, commit)
