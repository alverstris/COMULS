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
    # Recovery reuses the original receipt. Replacing it after activation has
    # started would forget which bytes belong in the previous-course backup.
    if (root / PENDING).exists():
        pending = pending_pack(root)
        if pending is None or _bytes(pending) != data:
            raise ValueError("Recover the existing pending course update before staging another update.")
        return root / PENDING
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
    receipt = json.loads((root / RECEIPT).read_text(encoding="utf-8"))
    current = active.read_bytes() if active.is_file() else None
    current_hash = hashlib.sha256(current).hexdigest() if current is not None else None
    previous_hash, pending_hash = receipt.get("previous_sha256"), receipt["pending_sha256"]
    backup = root / "course-pack.previous.json"
    if current_hash == pending_hash:
        # A previous attempt already replaced ACTIVE. Finish its receipt and
        # cleanup without saving the new course over the original backup.
        if previous_hash is not None and previous_hash != pending_hash:
            if not backup.is_file() or hashlib.sha256(backup.read_bytes()).hexdigest() != previous_hash:
                raise ValueError("The previous course backup is missing or changed. Preserve the pending update and resolve the backup before recovery.")
    elif current_hash == previous_hash:
        if current is not None:
            _atomic(backup, current)
        _atomic(active, (root / PENDING).read_bytes())
    else:
        raise ValueError("The active course changed after this update was staged. Keep both courses and resolve the conflict before recovery.")
    receipt["phase"] = "active"
    _atomic(root / RECEIPT, _bytes(receipt))
    (root / PENDING).unlink()
    return pack
