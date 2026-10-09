# Verification record — 8 October 2026

Anki Desktop compatibility target: 26.09.3. Validation used the official anki and aqt Python packages on a GitHub-hosted Ubuntu runner, Python 3.13 and Qt in offscreen mode.

The validated implementation passed:

- 117 Python tests, including native Anki collection operations and real Qt widgets.
- 1,460 DOM assertions across all 90 original tester cards and all thirteen exercise types.
- Full source-CSV audit: 10,407 unique parents, 24,608 unique senses, no duplicate/conflicting IDs, all existing card-readiness flags false.
- Installable .ankiaddon packaging and SHA-256 output.

Collection tests exercise actual native grading, import/update identity preservation, review-log retention, undo/redo, stage rollback, manual pauses and deck identity. Qt tests use real widgets and native collections with a controlled host window, user-dialog responses and operation dispatch. They do not constitute a hands-on end-to-end run in the distributed Windows or macOS Anki application. Reviewer bridge tests cover nonce/context validation, submission handling, exposure protection and manual grading boundaries.

The source CSV remains unchanged: SHA-256 094216cdd2269e8398734360799aa39aab33174bd90594d88c79f74d4ee9bb44. This audit covers the repository CSV, not reconciliation against every separately uploaded source view.

The release workflow reruns all required checks before publishing its exact commit. See GitHub Actions for the authoritative release-run result.

Remaining platform checks are listed in TESTER_CHECKLIST.md: actual installation/restart, intelligibility of installed French voices, live reviewer keyboard/audio behaviour and sync. Mobile behaviour is not certified. No learning-effectiveness result is claimed.
