# Imperial B1/B2 Anki demo acceptance

This iteration turns the initial tester into a student-facing desktop Anki demo for two separate French course groups: B1 and B2. The versioned implementation specification in IMPLEMENTATION_SPEC.md is the baseline. Course selection does not certify the student's proficiency; it selects the appropriate curriculum window.

## Release requirements

| Area | Required behaviour | Evidence |
|---|---|---|
| Installation | Download one .ankiaddon, install through Anki, restart, open COMULS | Real packaged-addon application test |
| Cohorts | Separate B1 and B2 course routes; existing reviewed cards survive level changes | Native application and collection tests |
| Curriculum | All thirteen formats, lower contextual tasks, controlled higher listening, exact preparation | Course schema/content audit and admission tests |
| Audio | Bundled French recordings, offline playback, safe replay and segmentation feedback | Media manifest, signal checks and real native playback |
| Onboarding | Level, time budget, audio, controls, privacy and explicit startup setting | Real student journey |
| Daily use | Due review, bounded preparation, resume, repair, pause and help | Native application tests |
| Evidence | Readiness by exact target/facet with sample counts; conservative assistance/undo handling | Native history and evidence tests |
| Maintenance | Managed pauses, reversible retirement, preflight content updates, missing-media repair | Collection integration tests |
| Library/progress | Exact meanings/constructions, source details, weak-target view and export | UI and content checks |
| Distribution | Versioned GitHub source and downloadable .ankiaddon built from the same commit | Passing release workflow |

The desktop is the course-management client. The demo does not require a separate website, student cloud account or local French TTS installation. Study information is local unless the student explicitly exports it.

No release claim will substitute component tests for the real installed Anki application test. Content levels remain curriculum estimates; an operational demonstration does not establish learning effectiveness.
