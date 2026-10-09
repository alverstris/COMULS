# COMULS Imperial French: student guide

Version 0.2.0 is a desktop Anki prototype with separate B1 and B2 routes. Each route has 65 original exercises: five of each of thirteen formats. It is a short pilot, not a complete French course. The task levels are provisional estimates and the content has been reviewed by agents, not validated by a French teacher.

<!-- RELEASE_VERIFICATION_STATUS -->
Published installers are gated on exact-package tests in Linux Anki 26.09.3. The release includes native verification reports tied to its source commit and file hashes. Windows and macOS installation remain unverified.

## Install

1. Install [Anki Desktop](https://apps.ankiweb.net/). Use Anki 26.09.3, the compatibility target for this prototype.
2. Open the [COMULS 0.2.0 release](https://github.com/alverstris/COMULS/releases/tag/imperial-demo-0.2.0). Download `comuls-imperial-b1.ankiaddon` for B1 or `comuls-imperial-b2.ankiaddon` for B2. `comuls-imperial-demo.ankiaddon` lets you choose during setup.
3. In Anki, choose Tools → Add-ons → Install from file…, select the downloaded file, and restart Anki.
4. Open Tools → COMULS, or the COMULS button on the deck screen.
5. On Levels, choose B1 or B2 and click Use this level.
6. On Home, select Check French audio. Confirm only after hearing the recording clearly. Then select Try the card controls for ungraded examples.

Install one variant. All three contain both routes and replace the same add-on; B1/B2 installers only suggest a starting course in a new profile. Existing course selections and progress are retained. No separate COMULS login is needed.

Recordings are bundled synthetic French speech and work offline after installation. You do not need to install a French voice. Use the audio check to confirm your headphones or speakers work.

## Prepare something new

On Home, choose an exercise type or leave All exercise types selected, then click Prepare one new exercise.

Read the explanation, meaning and example. For listening, play the whole recording; for sound discrimination, play both comparison words as well. Response choices are explained before practice.

If supporting words or constructions appear, select one of these for each exact use:

- I already understand this use: it was understood before this preparation.
- I have just learned this use: the explanation taught you something new. It counts toward today's new-target limit.

Confirm that the target and surrounding language make sense, then click Add to Anki practice. Choose Not yet if they do not. Understanding this example is not a declaration that you have mastered the whole word or grammatical topic.

Immediate practice after preparation is expected to feel easier. COMULS records the exposure and does not treat that first success as independent mastery.

## Review in Anki

Select Study due / new cards in Anki, then Anki's Study Now button. Attempt each task before revealing its answer. You may type, select a choice, arrange sentence tiles or recall a meaning mentally, depending on the card.

After revealing, compare your response and choose Anki's rating:

| Rating | Use when |
| --- | --- |
| Again | You could not retrieve the target. |
| Hard | You retrieved it correctly with difficulty. |
| Good | You retrieved it correctly with ordinary effort. |
| Easy | Correct retrieval was unusually easy. |

COMULS offers feedback and recommendations; you choose the rating. A blank typed response is not automatically a failure. Meaning recall allows your own wording. A sentence transformation that differs from the reference may need your judgment. Replaying audio alone does not require Again.

Meaning and target hints are available when needed. Answer-revealing help is recorded as assistance. Listening replays whole utterances; the prototype does not provide word-level audio cuts or assess your pronunciation. After a sound-choice answer, compare both word recordings.

Use Skip without grading to bury the card through Anki without assigning a rating. Report this card records a problem locally. To hold a defective card out of future sessions, use Settings → Content manager… → Pause selected; Restore selected reverses COMULS-owned pauses, preserving your personal Anki suspensions.

Use Pause when interrupted, then Resume when ready. Audio stops during the pause and does not restart automatically. Paused or unfocused time does not consume the active-study budget.

## Daily pacing and course changes

The defaults are 15 active minutes, six new targets, eight new cards and one new above-stage target per day. Preparation counts as study. Newly learned supporting uses count as new targets, so one exercise can consume more than one target allowance. Due reviews reserve time before new admissions, and Anki's own deck limits also apply.

You are not expected to unlock all thirteen formats on the first day. Related representations may wait until the next Anki study day. If no new card is available, read the displayed reasons and return to existing reviews. Settings lets you adjust the limits; raising them does not establish readiness for harder material. A backlog can pause new learning; the Home override Resume new learning today despite backlog is an explicit choice to resume it.

B1 and B2 are separate new-learning routes. Easier cloze and transformation tasks, and supported listening above the selected level, are intentional. Prepare lower-level repair offers easier practice without changing your main route.

Change the route through Levels → Use this level. Introduced cards retain their review history and remain reviewable. New cards that no longer fit may be paused. Selecting B2 does not mark earlier knowledge as mastered or erase B1 reviews.

## References, progress and updates

Library provides searchable, ungraded references. Looking at an answer records exposure, not retrieval knowledge. Progress describes the exercises sampled so far; its stability indicators require separated successful reviews with adequate assistance records. They are not a CEFR qualification.

For an update, download the newer `.ankiaddon`, install it through the same menu and restart Anki. Keep the same profile and cards. Compatible updates preserve card identities, scheduling history and personal notes. Study and preparation automatically upgrade recognised old COMULS templates. If your templates were customised, use Settings → Content manager… → Restore current course controls. After confirmation, COMULS saves the customised note type as a separate backup and restores its current controls; your cards and history remain. Do not delete reviewed cards to force an update.

Settings → Content manager… also provides Verify / restore bundled audio. If an update reports a content or template conflict, retain your existing data and send the message to the organiser.

## Privacy and sharing

COMULS does not upload study data automatically. Optional local diagnostics start off, and card reports stay on this computer. If the organiser requests a study export, choose Progress → Export study data…, inspect the saved JSON if desired, and share it yourself. It contains exercise/review records, progress evidence, active time and optional diagnostics; it excludes your name, email, profile path, device identifier and raw typed answers.

Ordinary Anki sync is separate. Manage COMULS admissions on one desktop. Before moving management to another desktop, sync both and use Settings → Transfer course management here. Mobile and web reviews have reduced management, assistance and timing coverage; they are not the verified launch environment.

## If something does not work

- No audio: check your output device and volume, then rerun Check French audio. Use Content manager to verify or restore bundled media.
- No new cards: read the admission reasons, complete due reviews, and check Native Anki deck options for Anki's new-card limits.
- Old or customised controls after updating: use Content manager → Restore current course controls and read its confirmation. If a structural conflict is reported, retain your data and contact the organiser.
- A broken exercise: report and skip it, then pause it if necessary. Include the add-on version, Anki version, operating system, exercise ID and what happened when contacting the organiser.
