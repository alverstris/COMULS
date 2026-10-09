# COMULS Imperial French prototype 0.2.0

A downloadable Anki Desktop prototype for separate B1 and B2 French groups: 130 original exercises, 65 per route, with five of each of thirteen formats. The add-on includes preparation, lower-level repair, supported listening previews, native Anki scheduling and manual ratings, daily workload limits, references, progress, card reports and optional study-data export.

## Download and install

| Starting course | Installer |
| --- | --- |
| B1 | [comuls-imperial-b1.ankiaddon](https://github.com/alverstris/COMULS/releases/download/imperial-demo-0.2.0/comuls-imperial-b1.ankiaddon) |
| B2 | [comuls-imperial-b2.ankiaddon](https://github.com/alverstris/COMULS/releases/download/imperial-demo-0.2.0/comuls-imperial-b2.ankiaddon) |
| Choose during setup | [comuls-imperial-demo.ankiaddon](https://github.com/alverstris/COMULS/releases/download/imperial-demo-0.2.0/comuls-imperial-demo.ankiaddon) |

Install [Anki Desktop 26.09.3](https://apps.ankiweb.net/), then choose Tools → Add-ons → Install from file…, select one installer and restart. Open Tools → COMULS, confirm your route on Levels, run Check French audio, and try the controls before preparing your first exercise.

All installers contain both routes and share one add-on identity. The course-specific files set only the starting suggestion for a new profile; replacing an installer preserves an existing route and progress. `comuls-tester.ankiaddon` is a compatibility alias of the general installer.

See the [student guide](https://github.com/alverstris/COMULS/blob/imperial-demo-0.2.0/docs/STUDENT_GUIDE.md) for daily use, updates, pauses and export, and the [organiser guide](https://github.com/alverstris/COMULS/blob/imperial-demo-0.2.0/docs/IMPERIAL_STUDY_GUIDE.md) for running a pilot.

## Offline audio and content scope

The package includes 81 synthetic French recordings, including the audio check and separate sound-contrast examples. No installed French voice, speech-service account or study-time network connection is required. Sentence replay uses whole utterances; no word-level alignment or pronunciation assessment is claimed.

The original content received authoring and independent agent review. Recordings underwent integrity checks and separate ASR screening. There was no human-listener pronunciation review or French-teacher validation; ASR agreement alone does not establish naturalness or phonetic quality. [Audio provenance](https://github.com/alverstris/COMULS/blob/imperial-demo-0.2.0/docs/AUDIO_PROVENANCE.md) documents the voice, attribution and verification limits.

Task levels are provisional routing estimates. This bounded pilot does not constitute a complete course, a CEFR assessment or evidence of improved learning effectiveness. The full source vocabulary inventory has not been expanded into teaching cards, and existing source expression placements remain unchanged.

## Verification and updates

These installers passed automated checks and actual installed Anki 26.09.3 Linux scenarios before publication. Checks cover course contracts, card interfaces, native collection operations and review-history preservation, packaged installation, both routes and all thirteen formats. Windows and macOS installation, physical student audio devices and mobile operation have not been verified by these Linux runs.

The [release workflow](https://github.com/alverstris/COMULS/actions/workflows/anki-tester.yml) binds the native results to the same clean source commit and installer hashes used for this release. Attached assets provide:

- `SHA256SUMS`: installer checksums.
- `build_manifest.json`: exact source commit, source fingerprint and installer hashes.
- `general.json`, `b1-installer.json`, `b2-installer.json`: native application verification reports for those package bytes.
- `source_audit.json`: the inspected source inventory, separate from the 130 pilot exercises.

Install updates through the same Anki menu without deleting your cards. Compatible updates preserve identities, native history and personal notes. Recognised old COMULS templates upgrade on Study or preparation. Custom controls require Settings → Content manager… → Restore current course controls; confirmation saves the customised note type as a separate backup before restoration.

COMULS does not upload study data automatically. Reports and optional diagnostics remain local unless you export and share them. Ordinary Anki sync is separate; use one desktop to manage new admissions.
