"""Crash boundaries preserve a complete previous or staged catalog."""
import importlib
import json
import sys
import types
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
NAME = "_comuls_install_test"
package = types.ModuleType(NAME)
package.__path__ = [str(ROOT / "addon")]
sys.modules[NAME] = package
install = importlib.import_module(NAME + ".pack_install")


def pack():
    return json.loads((ROOT / "addon/data/tester.json").read_text(encoding="utf-8"))


def test_staging_does_not_replace_active_catalog_and_recovery_is_verified(tmp_path):
    original = b'{"previous":"untouched"}'
    (tmp_path / install.ACTIVE).write_bytes(original)
    update = pack()
    install.stage_install(tmp_path, update, {"compatible": [], "conflicts": []})
    assert (tmp_path / install.ACTIVE).read_bytes() == original
    assert install.pending_pack(tmp_path) == update
    assert install.activate_install(tmp_path) == update
    assert json.loads((tmp_path / install.ACTIVE).read_text()) == update
    assert (tmp_path / "course-pack.previous.json").read_bytes() == original
    assert install.pending_pack(tmp_path) is None
    assert json.loads((tmp_path / install.RECEIPT).read_text())["phase"] == "active"


def test_corrupt_staged_update_cannot_replace_active_catalog(tmp_path):
    original = b'{"previous":"untouched"}'
    (tmp_path / install.ACTIVE).write_bytes(original)
    install.stage_install(tmp_path, pack(), {})
    (tmp_path / install.PENDING).write_text('{"bad":"content"}')
    with pytest.raises(ValueError, match="checksum"):
        install.activate_install(tmp_path)
    assert (tmp_path / install.ACTIVE).read_bytes() == original
