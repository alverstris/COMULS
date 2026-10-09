# Concurrent launch review: course-update recovery

This branch is an isolated contribution based on `27ca99690d0e77aaac17c4a2ba0879e927624768`. The main launch checkout had active, uncommitted implementation work when inspected on 9 October 2026. Its source files were not overwritten. Integrate this commit into `codex/anki-tester` after checking concurrent edits, particularly `addon/ui.py`.

## Repaired defect

An interruption after replacing `course-pack.json`, but before finishing the receipt/cleanup, left a valid pending update. Retrying activation unconditionally backed up the already-updated catalog, overwriting the actual previous catalog. The UI recovery path also re-merged the pending catalog and rewrote its `last_update` provenance.

Activation now compares the active bytes to both the original and staged checksums. A retry finishes an already-activated update without replacing its original backup. Unexpected active changes and missing/corrupt backups retain the pending update and produce an error. Restaging the same pending update preserves its receipt; a different update cannot displace unresolved recovery. The controller preserves the already-merged pending catalog when recovery is selected.

The change does not alter Anki scheduling, note/card identities, review history or native undo. It concerns the local catalog activation boundary only.

## Verification performed

- Nine pure catalog tests passed on this branch: the two existing installation tests and seven added cases covering interruptions after backup, activation and receipt writes, first-install interruption, changed active content, a competing staged update and backup corruption.
- The same nine tests plus the actual Qt controller recovery test passed in an isolated copy of the active launch implementation: 10 passed in 0.45 seconds. The UI fixture uses a real Anki collection and real Qt controls with controlled dialog answers and synchronous operation dispatch. This is component integration evidence, not an installed-application release gate.
- `git diff --check` passed.

The active-work snapshot's broader test run was 158 passed / 10 failed, excluding the source-audit test because the temporary snapshot omitted its large CSV. All ten observed failures were in reviewer-hook test fixtures whose stub collection module lacked the newly imported `evidence_state`; those files remained owned by the active implementation session. This result is a snapshot finding, not a claim about subsequent changes.

## Launch state and next step

At inspection, PR #1 remained draft with head `27ca996`, and the sole published package remained `tester-0.1.7`. Latest observed Actions run `37839362136` failed on `3bbddfb`; no Imperial release gate had yet passed.

Integrate this recovery fix, rerun the controller regression with the final implementation, then continue the all-format packaged Anki validation, offline playback and release-byte verification described in `LAUNCH_STATUS.md`. The overall launch is not complete and the continuation task must remain active.
