# Imperial prototype launch checkpoint

Status: implementation complete; final native release verification in progress. Do not report launch complete until the release is published and checked.

The user authorized completing and publishing the separate B1/B2 Imperial French Anki prototype on 9 October 2026. An hourly continuation task is active. Resume real implementation and testing, not reminders. Disable the task only after the launch checklist below is satisfied and the released assets are verified.

Authoritative development branch: `codex/anki-tester`. The current session is integrating parallel curriculum, audio, evidence/lifecycle, policy and native application work. Before another scheduled worker changes the same files, inspect current activity and recent commits; coordinate with the active session. Never overwrite another worker's uncommitted changes.

## Launch scope

- Desktop Anki 26.09.3, separate B1 and B2 course installers with one stable add-on identity.
- At least 130 original bounded exercises across the two routes; every route covers all thirteen formats.
- Bundled offline French recordings with pinned voice provenance, file integrity checks and no live study API.
- Exact prerequisite preparation, manual stage selection, conservative evidence, native scheduling/history and recoverable content updates.
- Operational onboarding, daily study, repair, accessibility settings, content management and optional local export.
- Versioned GitHub release built from the same source commit that passed the native installed-application gates.

This is a bounded prototype, not the completed vocabulary corpus or a validated CEFR/learning-efficacy product. Existing source expression placements remain provisional and unchanged. Full source reconciliation remains separately tracked; the prototype uses explicitly authored original content and must not claim all source records are course-ready.

## Current work

1. Complete missing evidence/media and collection APIs, and wire exact support declarations.
2. Build and review the B1/B2 course packs and offline recordings.
3. Fix admission caps, card settings, reporting and ungraded skip controls.
4. Integrate the real installed-Anki harness from `codex/imperial-e2e`.
5. Run Python, card-interface, content/media and actual native application checks; repair failures.
6. Update all student/release documentation to match the actual package.
7. Publish installers, checksums, content/audio manifests and verification report; merge the completed implementation; verify links.

## Launch checklist

- [x] Every B1/B2 exercise passes content/answer/prerequisite checks.
- [ ] Bundled media are present, attributable, intact and played by the actual Anki player.
- [x] Missing APIs and imports resolved; 227 Python tests and 3,655 DOM assertions pass. Native release gates remain separate.
- [ ] Install/restart, all formats, native rating, undo/redo, level changes, update/import, history preservation and export verified in actual Anki.
- [x] UI screenshots inspected; accessibility, keyboard and settings regressions pass. Final native sweep in progress.
- [ ] Student instructions, limitations and release notes match the tested package.
- [ ] Passing source commit and downloadable release assets published and checked.
- [ ] Continuation automation disabled after completion.

## Previous verified baseline

`tester-0.1.7` at `a132bc74a9225d4365e6b32e864ce02c6d08fead` passed 117 Python tests and 1,460 DOM assertions; it is the older 90-exercise TTS tester. The later `3bbddfb` run failed 5 UI tests; `bbe8c1a` skipped CI and still lacked evidence/media/lifecycle APIs. Do not reuse the older passing results as proof of the Imperial iteration.

## Latest verification checkpoint

The real installed-Anki B1 smoke journey passed installation/restart, preparation, recording playback, native grading/undo/redo, route changes, managed pause/restore, compatible content update, export and add-on replacement. The full 13-format B1/B2 sweep is in progress; CI must rerun all gates against the clean release commit. Frozen audio contains 81 WAVs (6,212,588 bytes) with no unresolved automated audio QA flags. There is no human pronunciation or teacher review claim.

The isolated continuation recovery fix from PR #2 has been integrated and regression-tested. It preserves the original backup and catalog provenance when resuming interrupted updates.
