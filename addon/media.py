"""Verify and install bundled, content-addressed audio through Anki's media API.

No network access or speech engine is used by this module. Validation finishes
before the first collection write. An interrupted copy can safely be retried;
already verified files are reused and unrelated collection media is untouched.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import re
import wave
from typing import Any

_NAME = re.compile(r"comuls_[0-9a-f]{64}\.wav\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _name(value: Any) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise ValueError("Invalid bundled audio filename: use a COMULS content-addressed WAV.")
    return value


def load_manifest(root: Path) -> dict[str, Any]:
    """Read strict metadata; audio-byte verification belongs to validate_pack_media."""
    path = Path(root) / "data" / "media_manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("The bundled audio manifest is missing or unreadable. Reinstall COMULS.") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported COMULS audio manifest.")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("The bundled audio manifest has no assets.")
    seen = set()
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("Invalid bundled audio record.")
        filename = _name(asset.get("filename"))
        digest = asset.get("sha256")
        if not isinstance(digest, str) or not _SHA.fullmatch(digest):
            raise ValueError("Invalid bundled audio checksum.")
        if filename != f"comuls_{digest}.wav":
            raise ValueError("Bundled audio filename does not match its checksum.")
        if filename in seen:
            raise ValueError("Duplicate bundled audio filename.")
        seen.add(filename)
        text = asset.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Bundled audio must identify its spoken text.")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != asset.get("text_sha256"):
            raise ValueError("Bundled audio transcript checksum mismatch.")
        duration = asset.get("duration_seconds")
        if type(duration) not in (int, float) or not math.isfinite(duration) or not 0.15 <= duration <= 12:
            raise ValueError("Invalid bundled audio duration.")
        if any(type(asset.get(key)) is not int for key in ("bytes", "channels", "sample_width", "sample_rate")):
            raise ValueError("Invalid bundled audio sample-format metadata.")
    if _name(manifest.get("audio_check_file")) not in seen:
        raise ValueError("The French audio check is missing from the manifest.")
    return manifest


def audio_check_filename(root: Path) -> str:
    return load_manifest(root)["audio_check_file"]


def _references(value: Any):
    """All declarative media references, including contrast choices/replay chunks."""
    if isinstance(value, dict):
        if value.get("audio_file"):
            yield value
        for key, child in value.items():
            if key != "audio_file":
                yield from _references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _references(child)


def _verify_bytes(path: Path, asset: dict[str, Any]) -> bytes:
    if path.is_symlink():
        raise ValueError("Bundled audio cannot be a symbolic link.")
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"Missing bundled audio: {path.name}. Reinstall COMULS.") from exc
    if hashlib.sha256(data).hexdigest() != asset["sha256"]:
        raise ValueError(f"Bundled audio checksum mismatch: {path.name}.")
    if len(data) != asset.get("bytes"):
        raise ValueError(f"Bundled audio length mismatch: {path.name}.")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            actual = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
            expected = (asset.get("channels"), asset.get("sample_width"), asset.get("sample_rate"))
            if actual != expected or actual != (1, 2, 22050):
                raise ValueError("Bundled audio must be mono 16-bit PCM at 22050 Hz.")
            frames = wav.getnframes()
            if wav.getcomptype() != "NONE" or len(wav.readframes(frames)) != frames * 2:
                raise ValueError("Bundled audio is truncated or compressed.")
            duration = frames / wav.getframerate()
            if not 0.15 <= duration <= 12 or abs(duration - asset.get("duration_seconds", 0)) > 0.001:
                raise ValueError("Bundled audio duration mismatch.")
    except (wave.Error, EOFError) as exc:
        raise ValueError(f"Invalid WAV audio: {path.name}.") from exc
    return data


def validate_pack_media(pack: dict[str, Any], root: Path) -> dict[str, dict[str, Any]]:
    """Validate metadata, referenced transcripts and exact packaged WAV bytes.

    Returns filename -> asset metadata for every clip required by this pack and
    its onboarding audio check. Does not alter the supplied pack.
    """
    manifest = load_manifest(root)
    indexed = {asset["filename"]: asset for asset in manifest["assets"]}
    required = {manifest["audio_check_file"]}
    for reference in _references(pack.get("exercises", [])):
        filename = _name(reference["audio_file"])
        if filename not in indexed:
            raise ValueError(f"Audio is not in the bundled manifest: {filename}.")
        asset = indexed[filename]
        if reference.get("audio_sha256") not in (None, asset["sha256"]):
            raise ValueError("Exercise audio checksum does not match the manifest.")
        if reference.get("audio_text") and reference["audio_text"] != asset["text"]:
            raise ValueError("Exercise audio transcript does not match the manifest.")
        required.add(filename)
    result = {filename: indexed[filename] for filename in sorted(required)}
    for filename, asset in result.items():
        _verify_bytes(Path(root) / "data" / "media" / filename, asset)
    return result


def ensure_pack_media(col: Any, pack: dict[str, Any], root: Path) -> dict[str, Any]:
    """Idempotently install verified media; call within an Anki CollectionOp.

    A different existing file with a content-addressed name is a conflict. It is
    never overwritten, because another note could refer to it. Native returned
    filenames are checked: a silently renamed file must not produce a false
    successful installation with broken note references.
    """
    assets = validate_pack_media(pack, root)
    destination = Path(col.media.dir())
    pending = []
    for filename, asset in assets.items():
        target = destination / filename
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != asset["sha256"]:
                raise ValueError(f"Collection media conflict: {filename}. Preserve the existing file and resolve this conflict before retrying.")
        else:
            pending.append(filename)
    installed = []
    for filename in pending:
        returned = col.media.add_file(str(Path(root) / "data" / "media" / filename))
        if returned != filename:
            raise ValueError("Anki renamed bundled audio during installation. Resolve the collection media conflict and retry.")
        target = destination / returned
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != assets[filename]["sha256"]:
            raise ValueError("Anki media installation did not preserve the verified audio bytes. Retry installation.")
        installed.append(returned)
    return {"verified": len(assets), "installed": len(installed), "filenames": list(assets)}
