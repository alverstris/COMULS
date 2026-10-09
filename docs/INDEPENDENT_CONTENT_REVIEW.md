# Independent Imperial content review

Reviewed on 9 October 2026 by an independent review agent, separate from the content-authoring agent. This is an agent review, not French-teacher approval, a student usability study, or CEFR validation.

## Scope

Read all 130 Imperial items: 65 in `addon/data/imperial_b1.json` and 65 in `addon/data/imperial_b2.json`, five of each of the thirteen formats in each course. Reviewed every prompt, answer, accepted alternative, choice set, target French audio text, meaning gloss, explanation, construction description and embedded prerequisite support. Compared contracts with sections 7 and 12 of `docs/IMPLEMENTATION_SPEC.md` and the implemented answer normalisation/self-comparison behavior.

The seven listening formats comprise 70 target recordings. This review checked their texts and intended phonetic distinctions. It did not certify the generated recordings' actual pronunciation or intelligibility; that requires the separate media review. No source vocabulary or expression level allocations were changed by this review.

## Findings raised before release

| Finding | Affected IDs | Required correction | Verification status |
|---|---|---|---|
| Unresolvable homophone in full dictation | `imperial_b2_sentence_transcription_03` | Replace initial `Ces` with `Les`: `Ces résultats` and `Ses résultats` are homophones without context. Update transcript, recording, answer and English support to `The results...`. | Corrected and reread in the JSON: `Les résultats...`; matching recording remains in media QA. |
| Person changed in meaning translation | `imperial_b2_audio_meaning_choice_03`, `imperial_b1_audio_meaning_choice_04` | Preserve `Nous` as `We`, or explicitly frame the answer as a report about the speakers. Keep answer, choices and support consistent. | Corrected and reread: both now use `We`; choices and glosses agree. |
| A correct standard spelling rejected | `imperial_b1_sentence_transcription_04` | Accept `Je voudrais connaitre les horaires d’ouverture.` as well as the version with `connaître`. | Corrected and reread; alternative is in `accepted`. |
| Meaning help presented as non-revealing | `imperial_b1_meaning_recall_05`, `imperial_b2_meaning_recall_01`, `imperial_b2_meaning_recall_03`, `imperial_b2_meaning_recall_05` | Target glosses such as `travel between two places`, `date`, `caused` and `important aspect` expose all or part of the requested meaning. Replace them with non-revealing gaps or mark the help as target-revealing. | Corrected and reread: the four carrier glosses use neutral gaps. |
| Placeholder carrier support | All ten `grammar_meaning_choice` items | Replace the generic instruction `Read the fixed situation...` with actual help for understanding the French. If a complete translation is supplied, mark it as target-revealing. | Corrected and reread: carrier help now gives lexical glosses without the tested grammar meaning; complete interpretations are confined to preparation support. |
| Distractor readability not explicitly supported | All ten `audio_transcript_choice` items; all ten `connected_word_recognition` items | Supply accessible glosses for the response labels and alternatives, including above-stage words; retain explicit exact-use understanding declarations. | Corrected and reread: every option has an English gloss and the French listening choices appear with translations in preparation. Whole-utterance targets use direct familiarisation instead of duplicating the target as its own prerequisite. |
| Sound contrast preparation promises more than the UI plays | All ten `sound_discrimination` items | Make both option recordings available during preparation and feedback; first preparation must cover both. The initial inspected preparation UI only played the correct target. | Source reread confirms preparation buttons and first-use checks for both word recordings, plus answer-side contrast buttons. Actual playback remains part of native release verification. |
| Small explanation defects | B1 meaning/form-recall items | Remove doubled full stops and lower-case English `i`. | Corrected and reread. |

The spelling decision was checked against the Académie française's ninth-edition entry for [connaître](https://www.dictionnaire-academie.fr/article/A9C3636), accessed 9 October 2026. It expressly permits both forms under the 1990 rectifications. This source supports the spelling decision only; no dictionary definition was copied into the pack.

## Format-by-format assessment

| Format | Items read | Contract assessment |
|---|---:|---|
| Meaning recall | 10 | Context fixes the intended sense. Free paraphrases must remain self-comparison; exact English/French wording is not a scoring requirement. The identified revealing carrier glosses were replaced with neutral gaps. |
| French-form recall | 10 | Part of speech, requested dictionary form and the explicitly introduced target define controlled recall. Initial letters are optional target help, not permanently visible prompts. This is recall of the taught form, not an unrestricted translation task. |
| Vocabulary cloze | 10 | Every gap has a semantic cue and form constraint. `clé`/`clef` is explicitly accepted. No additional valid synonym is wrongly excluded under the stated constraints. |
| Grammar cloze | 10 | The named tense, person, agreement or grammatical relation selects the expected form. Contextual tasks remain below the chosen course stage. |
| Grammar meaning choice | 10 | Interpretations and distractors accurately distinguish the written grammar, including recent past, continuing `depuis`, concessive `avoir beau`, reported conditional and expletive `ne`. Carrier help now supplies the underlying lexical meanings separately from the tested grammar. |
| Sentence transformation | 10 | Instructions specify a controlled operation. Unknown alternative formulations retain self-comparison rather than an automatic failure. B2 item 04 explicitly requires preserving the source spelling `né`, fixing the supplied speaker's agreement. |
| Sound discrimination | 10 | All final pairs differ audibly in the intended pronunciation set. Final B1 item 05 uses `fin`/`vin` (/f/ versus /v/); final B2 item 05 uses `belle`/`bulle` (/ɛ/ versus /y/). These replaced pairs that the media team found insufficiently distinct in the generated audio. `égout`/`écoute` differs in both medial consonant and final /t/; it is a word contrast, not a single-feature minimal pair. Actual recordings remain a media QA responsibility. |
| Connected-word recognition | 10 | The intended chunk occurs in the spoken sentence and differs audibly from alternatives. Explanations correctly identify relevant liaison, elision and nasal-vowel contrasts. Preparation includes English glosses for every response alternative. |
| Sentence reconstruction | 10 | Each item has a natural alternative grammatical arrangement using exactly the same tiles. The requested recorded order therefore cannot be established by grammar alone. Lowercase tiles and interchangeable duplicate words avoid visual clues and false duplicate-tile failures. |
| Partial dictation | 10 | Missing chunks fit their printed frames and their meanings. `mettre en œuvre`/`mettre en oeuvre` is explicitly accommodated. |
| Full sentence transcription | 10 | Sentences are natural and short. The Ces/Ses ambiguity was removed and the standard connaitre variant is accepted. Accents and endings remain meaningful, while case, typographic apostrophes and final punctuation are normalised. |
| Audio transcript choice | 10 | Alternatives change audible words, not silent inflections. Their French is natural. All response alternatives now have explicit English readability support before unfamiliar previews. |
| Audio meaning choice | 10 | Correct interpretations avoid strengthening possibility to certainty or treating a qualification as a rejection. The two first-person/reporting mismatches are corrected. |

## Level and prerequisite limits

The pilot spans everyday B1 situations and more formal B2 listening, with simpler contextual review and supported listening previews as specified. The task labels are usable as provisional routing choices. They do not establish that words such as `budget`, `coussin` or an individual expression belong to a certified CEFR level. Simple repair items may sit well below the selected course stage.

A support unit is an exact-use declaration, not evidence that every word family or construction within it is mastered. Full French sentences with English bridges can support the bounded pilot, provided the learner can decline admission when they do not understand them. Placeholder instructions are not sufficient support. The generated recordings, preparation controls, exposure tracking and native Anki behavior must be verified separately before a release can be called launch-ready.

## Release disposition

All identified semantic, spelling, answer-contract and textual-support findings have been corrected and independently reread. Final replacement sound pairs `fin`/`vin` and `belle`/`bulle`, their IPA, definitions and cues have been reread in the final JSON. The new French definition of `compromis` and English definition of `fiable` were also reread after the frozen definition-language assignment changed. The targeted content suite passed 13 tests after the corrections. This records coherence of the bounded pilot content, not teacher approval, actual-recording certification, or independent approval of the software release. Source reread confirms both contrast controls and preparation checks; actual playback remains part of native release verification.

## Final audio-driven sentence revisions

The media team identified two further generated-speech problems after the initial text review. Both replacement texts were approved, then reread in the saved course JSON with their answer/support contracts:

- `imperial_b1_sentence_reconstruction_02`: `Elle ouvre le livre dans le train.` Its alternative grammatical tile order is `Dans le train elle ouvre le livre.` Both are natural and have the same tiles, so the recording still determines the required order.
- `imperial_b2_partial_dictation_03`: `La réunion est reportée faute de temps.` The printed frame is `La réunion est reportée ___.`; the target remains `faute de temps`, with carrier support `The meeting is postponed [reason].` The agreement and meaning are correct.

The revised onboarding check, `Bonjour. Vous êtes prêt à écouter du français.`, is also natural French. It is an audio check, not an assessment of the written gender agreement.

## Final reviewed text snapshots

The following SHA-256 values identify the reviewed pedagogical fields, excluding generated-media paths, recording hashes and mutable QA metadata. For each pack, serialize a list in exercise order with the fields below (missing fields as null), plus choices reduced to `id`, `text`, `correct`, `audio_text`; use UTF-8 JSON with sorted keys, `ensure_ascii=False` and separators `,` and `:`.

Fields: `id`, `type`, `prompt`, `answer`, `accepted`, `answer_policy`, `audio_text`, `target_form`, `target_meaning`, `carrier_meaning`, `carrier_help_reveals_target`, `required_construction`, `prerequisites`, `support_units`, `option_glosses`, `target_hint`, `english_support`, `explanation`, `tokens`, `level`, `target_level`, `carrier_level`, `construction_level`, `definition_language`.

- `imperial_b1.json`: `f3b4f4e3105daa2f567dbceec373ace0f9910c41d76282672327c1316f6da374`
- `imperial_b2.json`: `4a810f289f1d88824ec0ef701fef4fd8cb3b44c69dcd05196b5c24212b0c329e`
