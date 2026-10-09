# COMULS Anki tester

The tester is a desktop Anki add-on. Students install Anki first, then an .ankiaddon package. There is no separate website or browser scheduler.

## Scope

- Student entry stages: B1, B2 and C1. Plus stages remain internal curriculum bands.
- Thirteen short flashcard formats; no speech production or long-form reading/listening.
- Cloze, transformation and reconstruction stay below the selected stage.
- Supported listening previews extend to the next half/full band according to format.
- Native Anki owns scheduling, ratings, review history and sync. The add-on controls new admission.
- Existing expression placements remain unchanged.

## Implementation checkpoints

1. Domain policy and meaningful tests.
2. Portable note templates and guarded desktop reviewer integration.
3. Small original tester content pack, explicitly provisional task levels.
4. Level selection, familiarisation, admission, load management, diagnostics and export.
5. Real Anki collection integration tests, packaging and student installation instructions.

The full vocabulary CSV is source material, not a ready-made deck. Empty contexts and false readiness flags must never become publishable cards automatically. The first tester pack is a bounded original course slice, with its own identities and provenance; it does not represent completion of the entire inventory.

## Audio

The first package supports native Anki French text-to-speech and packaged recordings where available. A working French voice is checked during onboarding. TTS availability and naturalness must be verified on the intended student machines. Listening playback must never fabricate a successful answer or alter a rating. Segmentation feedback explains connected speech; text chunks must not be described as verified cuts from a continuous recording.

## Release evidence

Automated policy and real-collection tests are necessary. They do not replace hands-on checks of the Anki Qt reviewer, French audio, keyboard access, install/restart and sync. Published tester notes must distinguish checks actually run from remaining manual checks.
