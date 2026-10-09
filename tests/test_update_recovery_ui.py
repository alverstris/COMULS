"""The real controller must resume the exact staged catalog after interruption."""
import copy
import importlib
import json

from test_ui import app, course, first_text_exercise, show_window, ui


def test_recover_button_preserves_receipt_and_previous_catalog(course, tmp_path, monkeypatch):
    show_window(course)
    install = importlib.import_module(ui.__package__ + ".pack_install")
    original = install._bytes(course.pack)
    course.catalog_path.write_bytes(original)
    exercise = copy.deepcopy(first_text_exercise(course))
    exercise["id"] = "recovery-ui-new-exercise"
    update = {"schema_version": 1, "pack_id": "separate-update-pack", "version": "2",
              "exercises": [exercise]}
    source = tmp_path / "update.json"
    source.write_text(json.dumps(update))
    monkeypatch.setattr(ui.QMessageBox, "question",
                        lambda *_args, **_kwargs: ui.QMessageBox.StandardButton.Yes)
    atomic = install._atomic

    def interrupt_after_activation(path, data):
        atomic(path, data)
        if path.name == install.ACTIVE:
            raise OSError("simulated failure after catalog activation")

    monkeypatch.setattr(install, "_atomic", interrupt_after_activation)
    course.install_pack(source)
    pending_bytes = (course.local.root / install.PENDING).read_bytes()
    assert exercise["id"] not in course.by_id
    monkeypatch.setattr(install, "_atomic", atomic)
    course.recover_pending_pack()
    assert course.catalog_path.read_bytes() == pending_bytes
    assert exercise["id"] in course.by_id
    assert course.pack["last_update"]["pack_id"] == "separate-update-pack"
    assert (course.local.root / "course-pack.previous.json").read_bytes() == original
    assert not (course.local.root / install.PENDING).exists()
