"""Recoverable local catalog activation, independent of native Anki undo."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from .core import validate_pack

ACTIVE = "course-pack.json"
PENDING = "pending-pack.json"
RECEIPT = "pack-install-receipt.json"


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _atomic(path, data):
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def pending_pack(root):
    path = Path(root) / PENDING
    receipt_path = Path(root) / RECEIPT
    if not path.is_file() or not receipt_path.is_file():
        return None
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != receipt.get("pending_sha256"):
        raise ValueError("The staged pack checksum does not match. Keep the active course and reselect the original update.")
    pack = json.loads(data)
    errors = validate_pack(pack)
    if errors:
        raise ValueError("The staged pack is invalid: " + "; ".join(errors[:5]))
    return pack


def stage_install(root, pack, report):
    root = Path(root)
    errors = validate_pack(pack)
    if errors:
        raise ValueError("; ".join(errors[:5]))
    data = _bytes(pack)
    if len(data) > 8_000_000:
        raise ValueError("The combined demo catalog exceeds its 8 MB limit.")
    active = root / ACTIVE
    receipt = {"schema_version": 1, "phase": "staged",
        "previous_sha256": hashlib.sha256(active.read_bytes()).hexdigest() if active.is_file() else None,
        "pending_sha256": hashlib.sha256(data).hexdigest(),
        "pack_id": pack["pack_id"], "version": pack["version"], "preflight": report}
    _atomic(root / PENDING, data)
    _atomic(root / RECEIPT, _bytes(receipt))
    return root / PENDING


def activate_install(root):
    root = Path(root)
    pack = pending_pack(root)
    if pack is None:
        raise ValueError("No verified staged course pack is available.")
    active = root / ACTIVE
    if active.is_file():
        _atomic(root / "course-pack.previous.json", active.read_bytes())
    _atomic(active, (root / PENDING).read_bytes())
    receipt = json.loads((root / RECEIPT).read_text(encoding="utf-8"))
    receipt["phase"] = "active"
    _atomic(root / RECEIPT, _bytes(receipt))
    (root / PENDING).unlink()
    return pack
