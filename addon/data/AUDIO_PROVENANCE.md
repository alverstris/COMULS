# French recordings: provenance, reproduction and verification

The Imperial prototype uses bundled mono, 16-bit PCM WAV recordings at 22,050 Hz. Students do not need a French system voice, a speech service account, internet access during study, or any of the build dependencies below. Recordings are synthetic speech; they are not recordings of an Imperial teacher or an endorsement by Imperial College London.

## Voice and source attribution

The voice is Piper `fr_FR-siwis-medium`, contributed through Michael Hansen's `rhasspy/piper-voices` repository. The [voice-specific model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fr/fr_FR/siwis/medium/MODEL_CARD) identifies French (France), one speaker, 22,050 Hz audio, the SIWIS dataset under CC BY 4.0, and fine-tuning from the English Lessac medium voice. The repository's general MIT badge is not used as a substitute for that voice-specific attribution.

Dataset attribution: Junichi Yamagishi, Pierre-Edouard Honnet, Philip Garner and Alexandros Lazaridis (2017), The SIWIS French Speech Synthesis Database, 2016. University of Edinburgh, School of Informatics, Centre for Speech Technology Research. [Dataset and citation](https://doi.org/10.7488/ds/1705); [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). COMULS generates new speech from original teaching text rather than distributing the dataset recordings. No endorsement by the dataset authors, voice talent or model contributors is implied.

[Piper](https://github.com/OHF-Voice/piper1-gpl) is a GPL-3.0-or-later build tool. Neither the Piper engine nor its voice model is included in the Anki add-on. The [official Python interface](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md) documents `PiperVoice.synthesize_wav`. Synthesis runs locally when an author explicitly builds the recordings.

## Frozen inputs

| Input | Pinned value |
| --- | --- |
| Voice revision | `c10ece1aade47bb51c153c893d14e5bf8e5b7117` |
| ONNX SHA-256 | `641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99` |
| Configuration SHA-256 | `39479916c2db192b5ac9764daddd0c744d83e023ad890c6976c0633ae4df8959` |
| Piper | `1.4.2` |
| ONNX Runtime | `1.31.0` |
| NumPy | `2.5.3` |
| Inference | CPU; `length_scale=1.0`, `noise_scale=0`, `noise_w_scale=0` |
| Output | Peak normalization followed by `volume=0.85` |

Zero inference noise removes stochastic variation. It does not promise bit-identical regeneration on every CPU/runtime. The frozen bytes and their SHA-256 hashes remain authoritative: regeneration that differs must fail rather than silently replace a previously audited recording.

`addon/data/media_manifest.json` records the exact text and text hash, voice/config hashes, source utterance identity, exact recording-byte hash, byte count, duration, sample format, signal metrics, intended phoneme sequence and attribution. Each WAV's filename contains its full byte hash. Course records refer to those filenames and hashes.

## Build and verify

Normal verification requires Python's standard library only:

```sh
python tools/build_audio.py --verify-only
```

This checks every primary/contrast reference, exact text/hash agreement, all WAV byte hashes, complete PCM frames, sample format, duration, signal energy, clipping and quiet-window proportion. It rejects absent and unreferenced recordings. It does not access the network or install a voice model.

To generate audio for deliberately revised source packs, use an isolated build environment:

```sh
python -m venv .audio-venv
.audio-venv/bin/pip install piper-tts==1.4.2 onnxruntime==1.31.0 numpy==2.5.3
.audio-venv/bin/python tools/build_audio.py --download-model build/siwis --write-pack-references
```

The explicit download command fetches the pinned public model and rejects a checksum mismatch. Alternatively, supply `--model /absolute/path/fr_FR-siwis-medium.onnx` beside the corresponding `.onnx.json`. The model directory is a build input and must not be shipped. Existing verified assets are reused. Missing frozen assets may be regenerated only if their output matches the frozen hash. A changed teaching utterance creates a new content-addressed recording; do not replace old bytes under an existing filename.

The tool annotates the course JSON only with `--write-pack-references`. Run it after the text has been finalized and before packaging. Commit the manifest, course references and frozen audio together. Course changes can alter a retrieval contract; the curriculum author must decide whether a new exercise identity is required.

After a deliberately revised utterance, add `--prune-unreferenced` to remove verified, previously generated WAVs that the source packs no longer use. This option operates only on the build's `addon/data/media` directory. It never removes a student's collection media, and it refuses to delete a file whose bytes differ from the previous manifest.

## What the checks establish

The signal checks establish that each file decodes, contains nontrivial audio, stays below the clipping limit, has complete frames and meets the prototype's eight-second length limit. They do not establish that an utterance is natural, that a particular phoneme is correct, or that every liaison is present. The `planned_phonemes` field is the synthesis engine's input plan, not an independent transcription of the signal.

The media manifest marks independent text/audio agreement and human listening separately. Any independent acoustic/ASR audit is recorded with its own method and findings; a successful ASR transcript alone must not be described as a pronunciation-quality assessment. There is no human phonetic-review claim.

The released 81-clip bundle has a separate [audio QA report](audio_qa_report.json), also bundled as `data/audio_qa_report.json`. It identifies the exact final recording hashes, independent Vosk and Whisper methods, residual disagreements and their task-specific dispositions. Sixty-five recordings match unconstrained Vosk after case/punctuation normalization. All ten sound pairs identify both expected labels under paired-choice recognition; one `rue` result additionally contains an unknown trailing fragment, retained in the report. Nine pairs are exactly matched in both directions. The report records no unadjudicated flags; this does not mean every unconstrained ASR result matches or that pronunciation is certified.

Selected independent Praat measurements check the actual signal: `rue/roue` show the expected large second-formant contrast, `belle/bulle` show a first-formant difference, and `fin/vin` show strongly different initial low-frequency voicing energy. Their measurement intervals are diagnostic windows, not word/phoneme alignment for replay. Two original weak sound pairs and three problematic sentence/check recordings were replaced before launch. For the final partial-dictation sentence, Vosk identifies the assessed `faute de temps` span with confidence 1 on its three words; Whisper's remaining vowel disagreement is explicitly retained. The carrier's silent grammatical spelling is printed and is not part of the learner's answer.

`--verify-only` also rejects a missing or stale audit, a changed audit hash, an omitted recording or unresolved review flags. Generating changed speech is a build step: it requires a new independent review before release verification can succeed. The source manifest includes the audit's hash; the report separately identifies the pre-diagnostic media-build manifest to avoid a circular hash dependency.

This prototype does not expose word timestamps or pretend to have forced alignment. All sentence playback and replay use the complete original natural utterance. Sound-discrimination choices have separate isolated-word contrast recordings for comparison after answering. Those word recordings are never concatenated to simulate sentences. There are no synthesized phrase cuts, inferred silence boundaries, or unlabelled slower assessment recordings.

## Installing and recovering collection media

`addon/media.py` validates every required bundled file before writing any collection media, then calls Anki's native `col.media.add_file`. It checks the filename Anki actually returns and verifies the installed bytes. Repeating installation reuses unchanged files; restarting an interrupted installation copies only missing files. The French onboarding audio check is always installed with the pack.

A different collection file with the same content-addressed filename is reported as a conflict and preserved. It is not overwritten or silently renamed, because other notes may refer to it. Unrelated collection media is never removed. A missing managed file can be restored using Settings → Verify / restore bundled audio. A conflicting or corrupt existing file needs explicit conflict resolution before that retry succeeds.

The packaged clips are copied to Anki's collection media for native playback and later native media sync. A collection-sync result does not by itself establish that another device has received all recordings.
