# Integrated continuation contribution

The interrupted-update recovery fix from [PR #2](https://github.com/alverstris/COMULS/pull/2) has been integrated into the Imperial launch implementation. `addon/pack_install.py` preserves the original receipt and backup if activation was interrupted after replacing the active catalog, and rejects competing active changes. `addon/ui.py` resumes the already-merged pending catalog without changing its provenance.

Nine focused installation regressions and a real Anki collection/Qt controller recovery test pass. These checks are separate from the exact-package native release gate. Follow `docs/LAUNCH_STATUS.md` for the remaining launch work; do not reapply this contribution.
