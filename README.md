# COMULS — Imperial French prototype

COMULS is an Anki Desktop add-on for separate Imperial French B1 and B2 pilot groups. Version 0.2.0 contains 130 original exercises: 65 per route, with five examples of each of thirteen formats. It prepares new material before practice, offers easier repair and supported listening previews, and leaves scheduling and review ratings to Anki.

[Download version 0.2.0](https://github.com/alverstris/COMULS/releases/tag/imperial-demo-0.2.0) · [Student guide](docs/STUDENT_GUIDE.md) · [Organiser guide](docs/IMPERIAL_STUDY_GUIDE.md)

<!-- RELEASE_VERIFICATION_STATUS -->
Published installers are gated on exact-package tests in Linux Anki 26.09.3. The release includes native verification reports tied to its source commit and file hashes. Windows and macOS installation remain unverified.

## Install and start

1. Install [Anki Desktop](https://apps.ankiweb.net/). This prototype targets version 26.09.3; see the verification status above.
2. Download one installer from the release:

| Course | File |
| --- | --- |
| B1 | `comuls-imperial-b1.ankiaddon` |
| B2 | `comuls-imperial-b2.ankiaddon` |
| Choose during setup | `comuls-imperial-demo.ankiaddon` |

3. In Anki, choose Tools → Add-ons → Install from file…, select the file, and restart.
4. Open Tools → COMULS. On Levels, choose your course and select Use this level. On Home, run Check French audio and Try the card controls.
5. Select Prepare one new exercise, complete its preparation, then Study due / new cards in Anki → Study Now.

All installers contain both routes and use the same add-on identity. The B1/B2 filenames set only the initial suggestion for a new profile. Installing a different variant does not overwrite your selected course or progress. Install one variant; choose the route inside COMULS.

## What the pilot provides

The thirteen formats cover meaning recall, French-form recall, vocabulary cloze, grammar cloze, grammar interpretation, sentence transformation, sound discrimination, connected-word recognition, sentence reconstruction, partial dictation, full transcription, transcript choices and meaning choices.

Preparation shows the exact use and its support before testing. When asked about surrounding language, distinguish a use you already understand from one you have just learned. New supporting uses count toward the daily target limit. You can choose Not yet instead of admitting an unclear exercise.

The defaults are 15 active minutes, six new targets, eight new cards and at most one new above-stage target per day. Due reviews reserve time first. Level changes govern new admissions and preserve introduced cards and their native history. Lower-level repair is available without changing the main route.

French synthetic recordings are bundled for offline playback; no French system voice, speech-service account or study-time API is needed. Whole sentences stay intact. Sound contrasts include separate comparison recordings. [Audio provenance and verification](docs/AUDIO_PROVENANCE.md) records the voice and licensing details.

Library references, progress by sampled skill, managed pauses, optional local reports and study export are included. COMULS does not upload study data automatically; ordinary Anki sync is a separate service you control. Manage new admissions from one desktop.

## Scope and evidence

This is a bounded operational prototype. Its original items have undergone authoring review and [independent agent content review](docs/INDEPENDENT_CONTENT_REVIEW.md), not French-teacher validation. Task levels are provisional routing estimates; plus stages are COMULS subdivisions. Progress labels do not certify CEFR attainment or improved learning effectiveness.

The full vocabulary CSV is source material for later expansion. Its existing expression placements are unchanged, and the pilot does not turn that inventory into a complete course. See the [source audit](docs/source_audit.json) and [implementation specification](docs/IMPLEMENTATION_SPEC.md).

Release assets include installer checksums and build provenance. Use the verification evidence attached to the release for the tested source and package; older `tester-0.1.7` results cover a different 90-item prototype.

## Working on the add-on

`addon/` contains the add-on, native card integration, course packs and bundled audio. `tests/` covers policy, collection behavior, cards, content and media. `tools/build_addon.py` builds the three installer variants; release builds require committed source and matching native-application evidence.

```sh
python -m pytest tests -q
node tests/test_frontend.cjs
python tools/build_audio.py --verify-only
python tools/build_addon.py --require-clean
```

See [native application testing](tests/e2e/README.md) before publishing. Keep exercise identities stable for compatible updates; changed retrieval contracts need deliberate migration. Student updates use the same `.ankiaddon` installation menu and preserve compatible cards and personal notes. Study and preparation upgrade recognised old COMULS templates automatically. Custom templates are retained until you explicitly choose Settings → Content manager… → Restore current course controls; confirmation first saves the customised note type as a separate backup, then restores the current controls without replacing the cards.
