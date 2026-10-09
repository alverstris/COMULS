"""Build and verify the frozen offline French recordings.

Normal CI uses --verify-only and requires no speech/model dependencies. See
docs/AUDIO_PROVENANCE.md for the explicitly invoked regeneration procedure.
Voice weights and speech engines are build inputs, never add-on dependencies.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import importlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import sys
import types
import unicodedata
import urllib.request
import wave

ROOT = Path(__file__).resolve().parents[1]
MODEL_REVISION = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
MODEL_NAME = "fr_FR-siwis-medium.onnx"
MODEL_SHA = "641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99"
CONFIG_SHA = "39479916c2db192b5ac9764daddd0c744d83e023ad890c6976c0633ae4df8959"
CHECK_TEXT = "Bonjour. Écoutez cette phrase en français."
SYNTHESIS = {"length_scale": 1.0, "noise_scale": 0.0, "noise_w_scale": 0.0,
             "volume": 0.85, "normalize_audio": True}
REQUIRED_VERSIONS = {"piper-tts": "1.4.2", "onnxruntime": "1.31.0", "numpy": "2.5.3"}
RIGHTS = {
    "source_dataset": "SIWIS French Speech Synthesis Database (2017)",
    "authors": ["Junichi Yamagishi", "Pierre-Edouard Honnet", "Philip Garner", "Alexandros Lazaridis"],
    "source_dataset_license": "CC-BY-4.0",
    "source_dataset_url": "https://doi.org/10.7488/ds/1705",
    "voice_model_card": f"https://huggingface.co/rhasspy/piper-voices/blob/{MODEL_REVISION}/fr/fr_FR/siwis/medium/MODEL_CARD",
    "voice_repository_license": "MIT; voice-specific dataset attribution retained",
    "engine_license": "GPL-3.0-or-later (build tool only; not distributed)",
    "recording_notice": "Synthetic speech generated for COMULS from original teaching text; attribution retained. No endorsement by the dataset contributors is implied.",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def media_module():
    name = "_comuls_audio_build"
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(ROOT / "addon")]
        sys.modules[name] = package
    return importlib.import_module(name + ".media")


def references(value):
    if isinstance(value, dict):
        if value.get("audio_text"):
            yield value
        for key, child in value.items():
            if key not in ("audio_text", "provenance", "qa"):
                yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def signal_metrics(data):
    """Actual PCM checks; these are not pronunciation or forced-alignment tests."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 22050, "NONE"):
            raise ValueError("Unexpected audio sample format")
        pcm = array.array("h", wav.readframes(wav.getnframes()))
        if sys.byteorder == "big":
            pcm.byteswap()
        rate = wav.getframerate()
        if len(pcm) != wav.getnframes():
            raise ValueError("Truncated WAV")
    if not pcm:
        raise ValueError("Empty audio")
    peak = max(abs(x) for x in pcm) / 32768
    rms = math.sqrt(sum(x * x for x in pcm) / len(pcm)) / 32768
    clipped = sum(abs(x) >= 32760 for x in pcm) / len(pcm)
    frame_length = round(rate * 0.02)
    windows = [math.sqrt(sum(x * x for x in pcm[i:i + frame_length]) / len(pcm[i:i + frame_length])) / 32768
               for i in range(0, len(pcm), frame_length)]
    quiet = sum(value < 0.003 for value in windows) / len(windows)
    active = [i for i, value in enumerate(windows) if value >= 0.003]
    if not active or rms < 0.005 or peak < 0.03 or clipped > 0.001 or quiet > 0.8:
        raise ValueError("Audio failed signal-energy/clipping/silence checks")
    duration = len(pcm) / rate
    if not 0.15 <= duration <= 8:
        raise ValueError(f"Audio duration {duration:.3f}s is outside the prototype limit")
    return {"duration_seconds": round(duration, 6), "sample_rate": rate,
            "sample_width": 2, "channels": 1, "bytes": len(data),
            "quality": {"decoded_pcm": True, "complete_wav_frames": True,
                "peak_fraction": round(peak, 6), "rms_fraction": round(rms, 6),
                "clipped_sample_fraction": round(clipped, 6),
                "quiet_20ms_window_fraction": round(quiet, 6),
                "leading_quiet_seconds": round(active[0] * 0.02, 3),
                "trailing_quiet_seconds": round((len(windows) - active[-1] - 1) * 0.02, 3),
                "human_listening_review": False,
                "independent_text_audio_agreement": "not_evaluated"}}


def fetch_model(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name, expected in ((MODEL_NAME, MODEL_SHA), (MODEL_NAME + ".json", CONFIG_SHA)):
        path = directory / name
        if not path.is_file():
            # Explicit build-time request only; not called during verification/study.
            mode = "raw" if name.endswith(".json") else "resolve"
            base = f"https://huggingface.co/rhasspy/piper-voices/{mode}/{MODEL_REVISION}/fr/fr_FR/siwis/medium/"
            with urllib.request.urlopen(base + name + "?download=true", timeout=60) as stream:
                data = stream.read()
            if sha(data) != expected:
                raise ValueError("Downloaded voice model/config checksum mismatch")
            path.write_bytes(data)
        if sha(path.read_bytes()) != expected:
            raise ValueError("Voice model/config checksum mismatch")
    return directory / MODEL_NAME


def load_voice(path):
    for distribution, expected in REQUIRED_VERSIONS.items():
        if importlib.metadata.version(distribution) != expected:
            raise ValueError(f"Build requires {distribution}=={expected}")
    if sha(path.read_bytes()) != MODEL_SHA or sha(Path(str(path) + ".json").read_bytes()) != CONFIG_SHA:
        raise ValueError("Voice model/config checksum mismatch")
    from piper import PiperVoice, SynthesisConfig
    return PiperVoice.load(path), SynthesisConfig(**SYNTHESIS)


def render(voice, configuration, text):
    if text != unicodedata.normalize("NFC", text) or text != text.strip():
        raise ValueError("Audio text must be trimmed canonical Unicode NFC")
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        voice.synthesize_wav(text, wav, syn_config=configuration)
    data = stream.getvalue()
    digest = sha(data)
    return data, {"audio_id": "sha256:" + digest, "filename": f"comuls_{digest}.wav",
        "sha256": digest, "text": text, "text_sha256": sha(text.encode("utf-8")),
        "source_utterance_id": "text-sha256:" + sha(text.encode("utf-8")),
        "normalized_spoken_text": text, "locale": "fr-FR", "pronunciation_overrides": {},
        "planned_phonemes": voice.phonemize(text), **signal_metrics(data),
        "alignment": {"status": "whole_utterance_only", "word_timestamps": None,
                      "note": "Replay always uses the original complete utterance. No inferred word boundaries or isolated-word sentence reconstruction."},
        "rights": RIGHTS}


def verify(packs, root):
    media = media_module()
    assets = {}
    for pack in packs:
        assets.update(media.validate_pack_media(pack, root))
        for exercise in pack["exercises"]:
            for ref in references(exercise):
                if not ref.get("audio_file") or not ref.get("audio_sha256"):
                    raise ValueError(f"Unbundled audio text in {exercise['id']}")
    manifest = media.load_manifest(root)
    voice = manifest.get("voice", {})
    if (voice.get("model_sha256"), voice.get("config_sha256"), voice.get("model_revision")) != (MODEL_SHA, CONFIG_SHA, MODEL_REVISION):
        raise ValueError("The frozen manifest does not identify the pinned French voice/config")
    if voice.get("dependencies") != REQUIRED_VERSIONS or voice.get("settings") != SYNTHESIS:
        raise ValueError("The frozen manifest does not identify the pinned synthesis settings")
    declared = {asset["filename"] for asset in manifest["assets"]}
    disk = {path.name for path in (root / "data" / "media").glob("*.wav")}
    if set(assets) != declared or disk != declared:
        raise ValueError("Bundled manifest, course references, and WAV files must match exactly")
    for filename in assets:
        signal_metrics((root / "data" / "media" / filename).read_bytes())
    print(f"Verified {len(assets)} frozen WAVs; {sum(a['bytes'] for a in assets.values())} bytes; no speech engine/network required.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--download-model", type=Path, metavar="CACHE_DIRECTORY")
    parser.add_argument("--write-pack-references", action="store_true")
    parser.add_argument("--prune-unreferenced", action="store_true",
                        help="Remove only verified prior build WAVs no longer used by these packs; never collection media")
    parser.add_argument("--packs", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.packs or [ROOT / "addon/data/imperial_b1.json", ROOT / "addon/data/imperial_b2.json"]
    packs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    root = ROOT / "addon"
    if args.verify_only:
        verify(packs, root)
        return
    model = fetch_model(args.download_model) if args.download_model else args.model
    if model is None:
        parser.error("Specify --verify-only, --model PATH or --download-model CACHE_DIRECTORY")
    voice, configuration = load_voice(model)
    text_refs = {}
    for pack in packs:
        for ref in references(pack["exercises"]):
            text_refs.setdefault(ref["audio_text"], []).append(ref)
    text_refs.setdefault(CHECK_TEXT, [])
    output = root / "data" / "media"
    output.mkdir(exist_ok=True)
    manifest_path = root / "data" / "media_manifest.json"
    frozen = {}
    if manifest_path.is_file():
        frozen = {a["text"]: a for a in media_module().load_manifest(root)["assets"]}
    assets = []
    for index, text in enumerate(sorted(text_refs), 1):
        asset = frozen.get(text)
        if asset and (output / asset["filename"]).is_file():
            media_module()._verify_bytes(output / asset["filename"], asset)
        else:
            data, generated = render(voice, configuration, text)
            if asset and asset["sha256"] != generated["sha256"]:
                raise ValueError("Regeneration differs from frozen audio bytes; do not silently replace the approved manifest")
            asset = asset or generated
            (output / asset["filename"]).write_bytes(data)
        assets.append(asset)
        for ref in text_refs[text]:
            ref["audio_file"] = asset["filename"]
            ref["audio_sha256"] = asset["sha256"]
        print(f"{index}/{len(text_refs)}: {text} ({asset['duration_seconds']:.2f}s)", flush=True)
    manifest = {"schema_version": 1, "created": "2026-10-09", "voice": {
        "provider": "Piper (local build-time synthesis)", "model": "fr_FR-siwis-medium",
        "model_revision": MODEL_REVISION, "model_sha256": MODEL_SHA, "config_sha256": CONFIG_SHA,
        "dependencies": REQUIRED_VERSIONS, "settings": SYNTHESIS, "locale": "fr-FR"},
        "audio_check_file": next(a["filename"] for a in assets if a["text"] == CHECK_TEXT),
        "assets": sorted(assets, key=lambda a: a["filename"])}
    if args.prune_unreferenced:
        retained = {asset["filename"] for asset in assets}
        for asset in frozen.values():
            path = output / asset["filename"]
            if asset["filename"] not in retained and path.is_file():
                media_module()._verify_bytes(path, asset)
                path.unlink()
                print("Removed superseded build recording:", asset["text"], flush=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.write_pack_references:
        # The curriculum reviewer may have amended non-audio metadata during
        # synthesis. Reload and merge these two fields only; never replace that
        # work with the initial source snapshot.
        by_text = {asset["text"]: asset for asset in assets}
        current_packs = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
        for pack in current_packs:
            for ref in references(pack["exercises"]):
                if ref["audio_text"] not in by_text:
                    raise ValueError("Course audio text changed during synthesis. Regenerate before saving references.")
                asset = by_text[ref["audio_text"]]
                ref["audio_file"] = asset["filename"]
                ref["audio_sha256"] = asset["sha256"]
        for path, pack in zip(paths, current_packs):
            path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        packs = current_packs
    verify(packs, root)


if __name__ == "__main__":
    main()
