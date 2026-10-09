# Imperial prototype launch completed

The operational desktop prototype was published on 9 October 2026. No launch implementation work remains open in this checkpoint. The hourly continuation task was disabled after public download and verification checks succeeded.

## Release

- [Version 0.2.0 and all installers](https://github.com/alverstris/COMULS/releases/tag/imperial-demo-0.2.0)
- [Passing publication workflow](https://github.com/alverstris/COMULS/actions/runs/37925824515)
- Verified release source: `a341b94c116ab9e2af32eaec1fa467e97c8e6e6d`.
- PR #1 is merged into `main`. The interrupted-update contribution from PR #2 was integrated and its redundant draft closed.

## Delivered and verified

- 130 original exercises, 65 per B1/B2 route, with five examples of every one of thirteen formats.
- 81 attributed, frozen offline French recordings, with byte/transcript hashes and bounded independent automated audio QA.
- Exact supporting-use preparation, known/new declarations, conservative daily workload caps, manual course selection, safe native scheduling/history, and recoverable content/template updates.
- 227 Python tests and 3,655 DOM assertions across 220 cards pass.
- 22 actual installed-Anki application runs and 30 native reviews pass, covering all thirteen formats in both cohorts, native ratings and Undo/Redo, install/restart, course changes, updates, export and B1/B2 installer replacement.
- Four public installers and six accompanying checksum/provenance/verification assets were downloaded successfully. Installer hashes, archive integrity, embedded source provenance and attached native reports match the clean release source.
- Student instructions, content and audio review records, release notes and organiser guidance match the published pilot.

## Scope and remaining limits

The verified desktop environment is Linux Anki 26.09.3. Windows/macOS installation, physical student audio equipment, human pronunciation review and French-teacher validation remain outside this automated verification. They must not be represented as completed.

This is a bounded operational prototype, not a complete vocabulary course, a validated CEFR assessment or a learning-efficacy result. The original 10,407 source rows and 24,608 senses remain source material; existing expression placements were not changed. Full-corpus expansion and independent learning assessments are separate future work.

Resume development only for a new requested task or a concrete reported defect. Do not republish the existing version or restart the completed continuation task automatically.
