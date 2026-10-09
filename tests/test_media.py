"""Offline media integrity, installation crash boundaries and actual Anki files."""
import array
import copy
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import types
import wave

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "_comuls_media_test"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(ROOT / "addon")]
sys.modules[PACKAGE] = package
media = importlib.import_module(PACKAGE + ".media")


def fixture(root, words=("bonjour", "merci")):
    directory = root / "data" / "media"
    directory.mkdir(parents=True)
    assets = []
    for index, text in enumerate(words):
        stream = io.BytesIO()
        with wave.open(stream, "wb") as wav:
            wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
            wav.writeframes(array.array("h", [1000 + index, -1000 - index] * 11025).tobytes())
        data = stream.getvalue()
        digest = hashlib.sha256(data).hexdigest()
        asset = {"filename": "comuls_" + digest + ".wav", "sha256": digest,
                 "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                 "channels": 1, "sample_width": 2, "sample_rate": 22050,
                 "duration_seconds": 1, "bytes": len(data)}
        (directory / asset["filename"]).write_bytes(data)
        assets.append(asset)
    manifest = {"schema_version": 1, "audio_check_file": assets[0]["filename"], "assets": assets}
    (root / "data" / "media_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack = {"exercises": [{"id": "one", "audio_text": "merci", "audio_file": assets[1]["filename"], "audio_sha256": assets[1]["sha256"]}]}
    return pack, manifest


class FakeMedia:
    def __init__(self, directory):
        self.directory = directory
        self.directory.mkdir()
        self.writes = []
        self.fail_at = None
        self.rename = False

    def dir(self):
        return str(self.directory)

    def add_file(self, path):
        if self.fail_at == len(self.writes):
            raise OSError("Simulated interrupted installation")
        source = Path(path)
        self.writes.append(source.name)
        name = "renamed.wav" if self.rename else source.name
        (self.directory / name).write_bytes(source.read_bytes())
        return name


def collection(tmp_path):
    return types.SimpleNamespace(media=FakeMedia(tmp_path / "collection.media"))


def test_install_reuses_verified_files_and_preserves_unrelated_media(tmp_path):
    root = tmp_path / "addon"
    pack, manifest = fixture(root)
    col = collection(tmp_path)
    unrelated = col.media.directory / "my-recording.wav"
    unrelated.write_bytes(b"user audio")
    report = media.ensure_pack_media(col, pack, root)
    assert report["verified"] == report["installed"] == 2
    assert set(report["filenames"]) == {asset["filename"] for asset in manifest["assets"]}
    assert media.ensure_pack_media(col, pack, root)["installed"] == 0
    assert len(col.media.writes) == 2
    assert unrelated.read_bytes() == b"user audio"


def test_all_source_hashes_are_checked_before_collection_writes(tmp_path):
    root = tmp_path / "addon"
    pack, manifest = fixture(root)
    col = collection(tmp_path)
    (root / "data/media" / manifest["assets"][1]["filename"]).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        media.ensure_pack_media(col, pack, root)
    assert col.media.writes == []


def test_interrupted_install_recovers_without_duplicate_files(tmp_path):
    root = tmp_path / "addon"
    pack, _ = fixture(root)
    col = collection(tmp_path)
    col.media.fail_at = 1
    with pytest.raises(OSError, match="interrupted"):
        media.ensure_pack_media(col, pack, root)
    col.media.fail_at = None
    assert media.ensure_pack_media(col, pack, root)["installed"] == 1
    assert len(col.media.writes) == 2


def test_existing_conflict_is_preserved_and_cannot_look_successful(tmp_path):
    root = tmp_path / "addon"
    pack, manifest = fixture(root)
    col = collection(tmp_path)
    conflict = col.media.directory / manifest["assets"][1]["filename"]
    conflict.write_bytes(b"a different user file")
    with pytest.raises(ValueError, match="conflict"):
        media.ensure_pack_media(col, pack, root)
    assert conflict.read_bytes() == b"a different user file"
    assert col.media.writes == []


def test_native_renaming_is_not_mistaken_for_correct_installation(tmp_path):
    root = tmp_path / "addon"
    pack, _ = fixture(root)
    col = collection(tmp_path)
    col.media.rename = True
    with pytest.raises(ValueError, match="renamed"):
        media.ensure_pack_media(col, pack, root)


def test_unsafe_names_and_stale_transcripts_are_rejected(tmp_path):
    root = tmp_path / "addon"
    pack, _ = fixture(root)
    invalid = copy.deepcopy(pack)
    invalid["exercises"][0]["audio_file"] = "../outside.wav"
    with pytest.raises(ValueError, match="filename"):
        media.validate_pack_media(invalid, root)
    pack["exercises"][0]["audio_text"] = "different speech"
    with pytest.raises(ValueError, match="transcript"):
        media.validate_pack_media(pack, root)


def test_choice_media_and_audio_check_are_required_even_without_primary(tmp_path):
    root = tmp_path / "addon"
    pack, manifest = fixture(root)
    ref = pack["exercises"].pop()
    pack["exercises"] = [{"choices": [ref]}]
    assert len(media.validate_pack_media(pack, root)) == 2
    assert media.audio_check_filename(root) == manifest["audio_check_file"]


def test_real_anki_installs_frozen_french_audio_and_restores_a_missing_file(tmp_path):
    from anki.collection import Collection
    course = importlib.import_module(PACKAGE + ".course")
    root = ROOT / "addon"
    pack = course.load_course(root)
    col = Collection(str(tmp_path / "collection.anki2"))
    try:
        report = media.ensure_pack_media(col, pack, root)
        assert report["verified"] >= 50
        assert report["installed"] == report["verified"]
        assert media.ensure_pack_media(col, pack, root)["installed"] == 0
        path = Path(col.media.dir()) / report["filenames"][0]
        original = path.read_bytes()
        path.unlink()
        assert media.ensure_pack_media(col, pack, root)["installed"] == 1
        assert path.read_bytes() == original
        with wave.open(str(path), "rb") as wav:
            assert wav.getnframes() > 3000
    finally:
        col.close()
