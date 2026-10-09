"""Interrupted catalog activation must retain the actual previous course."""
import importlib
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAME = "_comuls_recovery_test"
package = types.ModuleType(NAME)
package.__path__ = [str(ROOT / "addon")]
sys.modules[NAME] = package
install = importlib.import_module(NAME + ".pack_install")


def staged(root):
    original = b'{"previous":"keep this original catalog"}'
    (root / install.ACTIVE).write_bytes(original)
    pack = json.loads((ROOT / "addon/data/tester.json").read_text())
    install.stage_install(root, pack, {})
    return original, pack


@pytest.mark.parametrize("boundary", ["backup", "active", "receipt"])
def test_retry_after_each_atomic_write_preserves_original(tmp_path, monkeypatch, boundary):
    original, pack = staged(tmp_path)
    real_atomic = install._atomic
    filename = {"backup": "course-pack.previous.json", "active": install.ACTIVE,
                "receipt": install.RECEIPT}[boundary]

    def interrupted(path, data):
        real_atomic(path, data)
        if path.name == filename:
            raise OSError("simulated interruption after atomic replacement")

    monkeypatch.setattr(install, "_atomic", interrupted)
    with pytest.raises(OSError, match="simulated interruption"):
        install.activate_install(tmp_path)
    monkeypatch.setattr(install, "_atomic", real_atomic)
    receipt_before = (tmp_path / install.RECEIPT).read_bytes()
    # The UI asks for preflight again; restaging the same catalog must not
    # silently reset previous_sha256 to the just-activated catalog's hash.
    install.stage_install(tmp_path, pack, {"repeat_preflight": True})
    assert (tmp_path / install.RECEIPT).read_bytes() == receipt_before
    assert install.activate_install(tmp_path) == pack
    assert (tmp_path / "course-pack.previous.json").read_bytes() == original
    assert json.loads((tmp_path / install.ACTIVE).read_text()) == pack
    assert install.pending_pack(tmp_path) is None


def test_changed_active_catalog_is_not_overwritten(tmp_path):
    _, _ = staged(tmp_path)
    changed = b'{"outside_update":"must survive"}'
    (tmp_path / install.ACTIVE).write_bytes(changed)
    with pytest.raises(ValueError, match="active course changed"):
        install.activate_install(tmp_path)
    assert (tmp_path / install.ACTIVE).read_bytes() == changed
    assert (tmp_path / install.PENDING).is_file()


def test_second_update_cannot_replace_pending_recovery(tmp_path):
    _, pack = staged(tmp_path)
    before = (tmp_path / install.PENDING).read_bytes()
    pack["version"] = "different-update"
    with pytest.raises(ValueError, match="existing pending"):
        install.stage_install(tmp_path, pack, {})
    assert (tmp_path / install.PENDING).read_bytes() == before


def test_first_install_retry_needs_no_previous_catalog(tmp_path, monkeypatch):
    pack = json.loads((ROOT / "addon/data/tester.json").read_text())
    install.stage_install(tmp_path, pack, {})
    real_atomic = install._atomic

    def interrupted(path, data):
        real_atomic(path, data)
        if path.name == install.ACTIVE:
            raise OSError("interrupted")

    monkeypatch.setattr(install, "_atomic", interrupted)
    with pytest.raises(OSError):
        install.activate_install(tmp_path)
    monkeypatch.setattr(install, "_atomic", real_atomic)
    assert install.activate_install(tmp_path) == pack
    assert not (tmp_path / "course-pack.previous.json").exists()


def test_corrupt_backup_after_interruption_is_not_silently_accepted(tmp_path, monkeypatch):
    _, _ = staged(tmp_path)
    real_atomic = install._atomic

    def interrupted(path, data):
        real_atomic(path, data)
        if path.name == install.ACTIVE:
            raise OSError("interrupted")

    monkeypatch.setattr(install, "_atomic", interrupted)
    with pytest.raises(OSError):
        install.activate_install(tmp_path)
    monkeypatch.setattr(install, "_atomic", real_atomic)
    (tmp_path / "course-pack.previous.json").write_bytes(b"unrelated backup")
    with pytest.raises(ValueError, match="backup is missing or changed"):
        install.activate_install(tmp_path)
    assert (tmp_path / install.PENDING).exists()
