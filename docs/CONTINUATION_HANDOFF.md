# Independent continuation contribution

The active launch checkout was left untouched while an isolated reviewer repaired course-update recovery. Please integrate GitHub PR #2: https://github.com/alverstris/COMULS/pull/2 (commit c805d8b04aec9137ff8e108245f956f24a366434, branch codex/imperial-update-recovery). It changes addon/pack_install.py, adds a four-line recovery-path insertion to addon/ui.py, and adds regression tests.

The issue: interruption after ACTIVE replacement followed by retry could overwrite the original backup with the new catalog. UI recovery also rebuilt an already-merged catalog and changed last_update provenance. Recovery now preserves the original receipt/backup and rejects competing active changes.

Nine pure tests pass on the isolated branch; 10 pass including the real-collection Qt controller test against a snapshot of the ongoing launch implementation. This is not installed-application release evidence. The separate controller test requires the current missing-module integration to be present.

Local isolated contribution: /workspace/scratch/00f79318a418/comuls-recovery-fix. Local snapshot used for validation: /workspace/scratch/00f79318a418/comuls-continuation-review. GitHub is the durable checkpoint. No existing launch files were overwritten, and the launch automation remains active.
