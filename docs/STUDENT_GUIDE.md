# COMULS tester: installation and first session

This version runs inside Anki Desktop. Choose B1, B2 or C1; the selected level controls a concurrent range of task difficulty, including supported listening above that level and contextual exercises below it.

## Install

1. Install Anki Desktop 26.09.3 or later from https://apps.ankiweb.net/ .
2. Download comuls-tester.ankiaddon from this repository's tester release.
3. In Anki, open Tools → Add-ons → Install from file, select the package, and restart Anki.
4. Open Tools → COMULS. In Levels, select B1, B2 or C1 and click Use this level.
5. Run Check French audio. Windows/macOS need an available French system voice. Linux needs a compatible Anki TTS add-on. Confirm only when the French sample is clear.
6. Choose Prepare one new exercise. Read the supported example, play any audio, and confirm that you understand the target and surrounding language.
7. Choose Study due / new cards in Anki, then Study Now. Enter or recall your answer, reveal the reference, and choose your own Anki rating.

The daily default is 15 active minutes, at most six new knowledge units and eight new cards. You can prepare a specific format or lower-level repair from Home. Stage changes do not reset these caps or remove introduced reviews. Related reverse-direction cards are separated across study days. Heavy due workloads pause new admission; it resumes after two study dates below the recovery threshold, or through the explicit Home override. Daily time and new-card caps still apply.

## While studying

- Again: recall failed or you needed the target answer as a hint.
- Hard: you recalled it, with substantial difficulty.
- Good: ordinary successful recall.
- Easy: effortless recall.

Automatic feedback is advisory. A valid transformation not in the answer list needs your comparison with the reference. French accents remain meaningful; typographic apostrophes and ordinary spacing are normalized. Replay itself does not imply failure.

Use native Show Answer at any time. A missing typed attempt never becomes an invented wrong answer. Listening feedback shows the transcript; hide the text and replay the whole phrase to practise hearing its word sequence. Full transcription and controlled transformation are the most demanding formats.

## Scope and data

The included pack has 90 original exercises: 30 starting examples per entry band, covering all thirteen formats. Earlier-band examples are also available for repair at higher entry levels. Task estimates are provisional. This is a bounded tester, not the entire vocabulary inventory and not a CEFR qualification.

The add-on uses your existing Anki scheduler; it does not enable FSRS globally or rewrite review dates. Reviews, notes and compact course settings sync with your normal collection. Keep one desktop responsible for new admission. Transfer that role explicitly in Settings after syncing both desktops.

Detailed diagnostic logging is optional and off by default. It stays on your computer. Progress → Export study data creates a file you may choose to share. No account, upload or email is required. The export excludes names, email, profile paths and raw typed answers. Native review history remains when the local diagnostic log is deleted.

## Compatibility limits

The target is desktop Anki. Cards include portable static answers and embedded interface assets, but mobile client behaviour and platform French voices require their own checks. Do not assume desktop course controls or timing operate on mobile.

This first tester uses native TTS. It does not include a human-reviewed recording corpus or aligned acoustic word-boundary clips. Student feedback can establish usability and uncover content issues; an effectiveness claim needs independent delayed testing.

## Report a problem

Use the card's Report control to record its identity locally, then export diagnostics if enabled. You can also copy its COMULS_ID from Anki's editor. Use Anki's native Bury action to skip for the day, or Suspend to pause a defective card. Neither should be replaced by an Again rating for a software or audio failure.
