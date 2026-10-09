# Tester verification

Automated checks cover the pure admission/answer rules, source parsing, pack coverage, real Anki collection imports and review-history preservation, reviewer bridge validation, Qt management controls, and browser card interactions. The workflow builds an .ankiaddon only after required checks pass.

Before a supervised student session, check the actual student platform:

- Install the package into a fresh disposable Anki profile, restart, open COMULS and choose each entry band.
- Confirm French audio is intelligible and each phonetic contrast is distinguishable with the installed voice.
- Prepare one card of each type over the permitted days; use native Show Answer, keyboard input, replay and grading.
- Review, undo, close/reopen, sync and install the same package again. Confirm note identities and schedules persist.
- Use a smaller daily budget to exercise the stopping point; change levels and check that reviewed cards remain due normally.
- Export with diagnostics off and on, and inspect that no names, profile paths or raw answers appear.
- Confirm your platform's accessibility/zoom/keyboard needs in the actual reviewer.

These manual checks are not asserted as complete by CI. A first tester release is suitable for supervised usability evaluation after these checks; it does not validate learning efficacy or the full source vocabulary.
