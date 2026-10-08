# COMULS: Imperial French demo

COMULS runs inside Anki Desktop. Choose the B1 or B2 download for your French course. The packages share one add-on identity; install one package per Anki profile.

## Install

1. Install Anki Desktop from https://apps.ankiweb.net/. This release is tested against Anki 26.09.3.
2. Download `comuls-imperial-b1.ankiaddon` or `comuls-imperial-b2.ankiaddon` from the COMULS GitHub release.
3. In Anki, open **Tools → Add-ons → Install from file…**, select the downloaded file, and restart Anki.
4. Open **Tools → COMULS**, or the COMULS button on Anki's deck screen.
5. On **Levels**, confirm **B1** or **B2** with **Use this level**. The download suggests the course; it does not change a previously selected course.
6. On **Home**, select **Check French audio**, listen, and confirm only if playback works. Recordings are included in the package.
7. Select **Try the card controls** for ungraded examples of recall, typing, choices and sentence tiles.

Use a separate Anki profile for a study if your teacher asks you to. Do not import another student's collection or share an AnkiWeb account.

## A normal study session

Select **Study due / new cards in Anki** to open the managed deck. Use Anki's **Study Now** button. COMULS leaves due dates, review order and scheduling with Anki.

To learn something new, return to COMULS and select **Prepare one new exercise**. Read its meaning and explanation, play the recording when present, and confirm that you understand it before adding it to practice. Choose a particular exercise type from the list if needed.

On a card, attempt the task before revealing the answer. Compare the answer and choose Anki's rating yourself:

- **Again:** the target was not retrieved.
- **Hard:** correct retrieval was difficult.
- **Good:** successful retrieval with ordinary effort.
- **Easy:** successful retrieval was unusually easy.

COMULS gives feedback but never selects a rating for you. A missing typed attempt is not automatically marked incorrect. A different valid sentence transformation may require self-comparison.

Use **Report** for an ambiguous, defective or technically broken card. Skip a defective card without recording a false failure. Use **Pause** when interrupted. Resume explicitly; a pause does not restart audio automatically.

## Listening and sentence boundaries

Listening exercises include sound contrasts, connected-word recognition, transcript and meaning choices, partial dictation, sentence reconstruction and full sentence transcription. Listen to the complete utterance. After revealing, compare its words and use the available playback controls to connect what you heard with the written sentence.

Chunk captions are teaching support. Only chunks supported by the recording's alignment are played separately. A whole-utterance replay remains available. COMULS does not assess speech production.

## Levels and workload

B1 and B2 are separate course routes. A B1 learner may receive lower-level cloze or sentence transformation and supported B1+/B2 listening. The same principle applies at B2. Selecting B2 does not declare all B1 abilities mastered.

Use **Prepare lower-level repair** for easier practice. Changing level governs new admissions; it preserves existing review history.

Defaults are 15 active minutes, six new targets, eight new cards, and at most one new above-stage target per day. A related second representation can be a separate card without being a new target. Preparation uses study time. Due reviews reserve time before new admission, and Anki's own deck limits also apply.

Settings let you lower or adjust these limits, change text size, show accent keys, enable question audio autoplay, select exercise types and choose whether COMULS opens at profile startup. Audio autoplay starts off.

If a new exercise is unavailable, COMULS lists the reason: level, preparation, prerequisites, audio, same-day exposure, disabled exercise type, daily limit or remaining time. Existing reviews remain accessible.

## Library, progress and content

**Library** opens ungraded references. Seeing an answer there is recorded conservatively as exposure; it does not establish retrieval knowledge.

**Progress** distinguishes sampled exercise evidence from course coverage. “Stable” requires separated successful unaided reviews with sufficient exposure records. It is not a CEFR certificate. Immediate success after preparation is not evidence of durable independent recall.

**Settings → Content manager** shows installed content and managed cards. Pause and restore controls preserve card identities and history. Restoring a COMULS pause does not reverse a suspension you made yourself in Anki.

Use GitHub releases for add-on updates. Install the newer `.ankiaddon` through the same menu and restart Anki. Keep the same profile; do not delete the old cards. Personal notes and native history survive compatible updates.

## Privacy and study export

COMULS does not upload study data automatically. Optional detailed diagnostics are off by default. Card problem reports stay on this computer.

When your teacher requests it, choose **Progress → Export study data…** and save the JSON file. It contains course/version, exercise IDs, native review records, conservative evidence summaries, active study time, any effort ratings, and optional local events. It excludes your name, email, profile path, device identifier and raw typed answers. You decide whether and where to share it.

Use **Record today's effort / fatigue** if the study asks for it. Deleting local diagnostics does not delete Anki's review history.

Ordinary Anki sync is separate from COMULS export. Manage new admissions on one designated desktop. Synced mobile reviews have reduced add-on, assistance and timing coverage; the Imperial demo should be run on its tested desktop configuration.

## Troubleshooting

- **No audio:** check the computer's output device and volume; run the French audio check again. Content manager can verify and restore bundled media.
- **No new cards:** read the admission reasons and check Anki's new-card limits in native deck options. Preparation and the daily target limit are intentional.
- **A long pause:** select Resume. Unfocused time is not counted as study.
- **Content conflict:** keep your data and inspect the Content manager report. Do not delete a reviewed card to force an update.
- **Another desktop manages the course:** sync both desktops before explicitly transferring management in Settings.
- **Problem report to the organiser:** include the add-on version, Anki version, operating system, exercise ID and what happened. Do not send your whole Anki collection unless you intend to share everything in it.
