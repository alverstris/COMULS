# Imperial prototype content review

Review date: 9 October 2026. Content version: 0.2.0.

## Released scope

The two new course packs contain 130 original exercises: 65 for B1 and 65 for B2, with five examples of every one of the thirteen implemented exercise formats. This is a bounded launch prototype for checking the learning workflow. It is not a complete B1/B2 syllabus, a CEFR qualification, or evidence that COMULS improves learning compared with another course. No teacher approval or student pilot result is claimed.

Each cohort contains six lexical acquisition parents and ten acquisition cards, four parent senses represented in both meaning and French-form recall. The other exercises teach separate grammatical, phonetic, segmentation or comprehension objectives; thirteen representations are not generated for every vocabulary item. Each primary target, fixed context, form, construction and exercise has an explicit identity. All exercises have new IDs, so the released tester contracts are not rewritten.

B1 has four explicitly A2 grammar/transformation repair exercises. Other B1 synthesis uses A2+ local routing. B2 has two A2+ repair exercises and B1+ synthesis. The B1 pack remains eligible when a learner selects B2. Every format has a first example at or below its cohort level, making a start possible without immediately requiring an above-stage preview.

All source vocabulary CSVs and their expression placements remain unchanged. These packs use independently authored language. Their task-stage assignments are conservative local sequencing estimates, separately recorded from any source lexical CEFR claim. The source-corpus reconciliation and the 370-expression allocation audit are not completed by this prototype.

## Definition languages and comprehension

Both cohorts have six acquisition parents. B1 freezes all six in English. B2 freezes three in French and three in English: échéance, compromis and démarche use French. B2 uses a stored SHA256 policy seed and ascending parent-ID hash order to choose exactly half of the six parents. The assignment is stored by parent identity and shared across that parent’s exercises; later stage changes must not change it. The regression suite reproduces this initial allocation.

French definitions have an English bridge and a B1-level exact-definition support record. Carrier support names the precise fixed use, provides an English explanation and is explicitly confirmed by the learner. Confirmation is a declaration of understanding, not mastery, a successful review or evidence of CEFR attainment. Unknown support can be taught during preparation; it must never become implicitly known merely because the student chose B1 or B2.

Whole-utterance reconstruction, transcription and listening-choice exercises have no artificial lower-stage prerequisite asserting that their own complete target is already known. Their whole meaning and form are directly familiarised. Every choice has a stable-ID option glossary; French transcript and connected-word alternatives receive English bridges during preparation. Carrier prerequisites on other formats are masked where needed so they do not silently require the target facet itself. Sound response labels are familiarised in both written and audio form.

## Answer and help contracts

- Meaning recall uses honest semantic self-comparison; a single stored wording is not treated as the only correct definition.
- French-form recall requests the specific form introduced in the lesson. Vocabulary cloze supplies a precise meaning cue and enumerated alternatives where another ordinary form fits.
- Initial-letter clues were removed from compulsory prompts and stored as optional target hints. Using one is target assistance, so it cannot create independent written-form evidence.
- Answer normalisation preserves accents and grammatical endings. Explicit accepted variants include clé/clef, réveil/réveil-matin, objectif/but, avantage/atout, conséquence/répercussion, œuvre/oeuvre and connaître/connaitre in the stated contexts.
- Transformations request one explicit operation. Valid unlisted wording remains self-comparison rather than an invented automatic failure.
- Every reconstruction task has a different grammatical ordering with exactly the same tile multiset. All tiles are lower-case without punctuation boundary clues. The actual recording determines which order to reproduce; identical duplicate tiles are interchangeable.
- Audio transcript alternatives differ in audible wording. The original Ces/Ses homophone trap in one transcription was removed by changing the first word to Les.
- Full translations and other help that reveal the primary answer are marked as target help. Masked carrier glosses are marked separately. Cross-card exposure groups link paired lexical representations and the shared nous allons target.

## Review and evidence

The authoring review examined all 130 complete items: prompt, target sense/form/construction, intended stage, carrier meaning, prerequisite scope, answer alternatives, choice contrasts, exact audio script, explanation, exposure group and help disclosure. The independent French reviewer separately read all 130 items, including every reconstruction alternative and all ten intended sound contrasts. See [INDEPENDENT_CONTENT_REVIEW.md](INDEPENDENT_CONTENT_REVIEW.md) for findings and correction verification.

The thirteen tests in tests/test_imperial_content.py cover both full packs. They check exact cohort coverage, stage ceilings, real lower-stage repair, all-format starting candidates, stable identities, frozen definition quotas, declared-prerequisite admission, accepted answers, optional hint separation, glossary coverage, nontrivial reconstruction alternatives, repeated-tile interchangeability, audio-to-answer contracts and answer-exposure grouping. These are contract checks; they do not certify naturalness, pronunciation or teaching efficacy.

The packaged waveforms have a separate production and verification path described in [AUDIO_PROVENANCE.md](AUDIO_PROVENANCE.md). An independent recogniser failed to distinguish two initial synthetic contrast pairs reliably. The final text therefore uses fin/vin and belle/bulle, which passed the candidate discrimination checks. Textual IPA review and speech-recognition checks complement each other; neither is a human classroom listening trial. Runtime media integrity and installed-Anki checks remain separate launch gates.

## Item-by-item audit coverage

The inventory below is exhaustive for the 130-item text review. “Stage” is the local exercise-routing assignment, not a validated CEFR lexical rating. “Target/reference” identifies exactly what was reviewed; the JSON remains authoritative for accepted variants, all choices and help fields.

### B1 cohort

| Exercise ID | Format | Stage | Target/reference |
|---|---|---|---|
| imperial_b1_meaning_recall_01 | meaning_recall | B1 | to borrow an item with the intention of returning it |
| imperial_b1_meaning_recall_02 | meaning_recall | B1 | to save money by spending less |
| imperial_b1_meaning_recall_03 | meaning_recall | B1 | to repay money that was lent or paid |
| imperial_b1_meaning_recall_04 | meaning_recall | B1 | an appointment arranged for a particular time |
| imperial_b1_meaning_recall_05 | meaning_recall | B1 | a journey between two places, considered as a route or stretch of travel |
| imperial_b1_french_form_recall_01 | french_form_recall | B1 | emprunter |
| imperial_b1_french_form_recall_02 | french_form_recall | B1 | économiser |
| imperial_b1_french_form_recall_03 | french_form_recall | B1 | rembourser |
| imperial_b1_french_form_recall_04 | french_form_recall | B1 | rendez-vous |
| imperial_b1_french_form_recall_05 | french_form_recall | B1 | billet |
| imperial_b1_vocabulary_cloze_01 | vocabulary_cloze | A2+ | clé |
| imperial_b1_vocabulary_cloze_02 | vocabulary_cloze | A2+ | arrêt |
| imperial_b1_vocabulary_cloze_03 | vocabulary_cloze | A2+ | étage |
| imperial_b1_vocabulary_cloze_04 | vocabulary_cloze | A2+ | réveil |
| imperial_b1_vocabulary_cloze_05 | vocabulary_cloze | A2+ | addition |
| imperial_b1_grammar_cloze_01 | grammar_cloze | A2 | allons |
| imperial_b1_grammar_cloze_02 | grammar_cloze | A2+ | grandes |
| imperial_b1_grammar_cloze_03 | grammar_cloze | A2+ | a pris |
| imperial_b1_grammar_cloze_04 | grammar_cloze | A2 | avez |
| imperial_b1_grammar_cloze_05 | grammar_cloze | A2+ | finissent |
| imperial_b1_grammar_meaning_choice_01 | grammar_meaning_choice | B1 | I no longer drink coffee. |
| imperial_b1_grammar_meaning_choice_02 | grammar_meaning_choice | B1 | He has just closed the door. |
| imperial_b1_grammar_meaning_choice_03 | grammar_meaning_choice | B1 | She has lived here for two years and still lives here. |
| imperial_b1_grammar_meaning_choice_04 | grammar_meaning_choice | B1 | You have to return the book tomorrow. |
| imperial_b1_grammar_meaning_choice_05 | grammar_meaning_choice | B1 | I will come if I have time. |
| imperial_b1_sentence_transformation_01 | sentence_transformation | A2 | Nous allons à la bibliothèque. |
| imperial_b1_sentence_transformation_02 | sentence_transformation | A2+ | Paul n’aime pas le café. |
| imperial_b1_sentence_transformation_03 | sentence_transformation | A2 | Est-ce que tu travailles demain ? |
| imperial_b1_sentence_transformation_04 | sentence_transformation | A2+ | Elles travaillent ici. |
| imperial_b1_sentence_transformation_05 | sentence_transformation | A2+ | Je vais manger à midi. |
| imperial_b1_sound_discrimination_01 | sound_discrimination | B1 | rue |
| imperial_b1_sound_discrimination_02 | sound_discrimination | B1 | dessus |
| imperial_b1_sound_discrimination_03 | sound_discrimination | B1 | poisson |
| imperial_b1_sound_discrimination_04 | sound_discrimination | B1 | pain |
| imperial_b1_sound_discrimination_05 | sound_discrimination | B1 | fin |
| imperial_b1_connected_word_recognition_01 | connected_word_recognition | B1 | vous avez |
| imperial_b1_connected_word_recognition_02 | connected_word_recognition | B1 | les enfants |
| imperial_b1_connected_word_recognition_03 | connected_word_recognition | B1 | j’ai |
| imperial_b1_connected_word_recognition_04 | connected_word_recognition | B1 | on arrive |
| imperial_b1_connected_word_recognition_05 | connected_word_recognition | B1 | nous allons |
| imperial_b1_sentence_reconstruction_01 | sentence_reconstruction | A2+ | Nous prenons le bus demain. |
| imperial_b1_sentence_reconstruction_02 | sentence_reconstruction | A2+ | Elle lit le livre dans le train. |
| imperial_b1_sentence_reconstruction_03 | sentence_reconstruction | A2+ | Ce matin nous avons acheté du pain. |
| imperial_b1_sentence_reconstruction_04 | sentence_reconstruction | A2+ | Après le cours tu peux venir. |
| imperial_b1_sentence_reconstruction_05 | sentence_reconstruction | A2+ | Je prépare le repas avec Paul. |
| imperial_b1_partial_dictation_01 | partial_dictation | B1 | dans dix minutes |
| imperial_b1_partial_dictation_02 | partial_dictation | B1+ | à partir de lundi |
| imperial_b1_partial_dictation_03 | partial_dictation | B1+ | une pièce d’identité |
| imperial_b1_partial_dictation_04 | partial_dictation | B1+ | en espèces |
| imperial_b1_partial_dictation_05 | partial_dictation | B1+ | jusqu’à nouvel ordre |
| imperial_b1_sentence_transcription_01 | sentence_transcription | B1 | Le magasin ferme à midi. |
| imperial_b1_sentence_transcription_02 | sentence_transcription | B1+ | Cette offre est valable pendant une semaine. |
| imperial_b1_sentence_transcription_03 | sentence_transcription | B1+ | La réservation est obligatoire pour ce spectacle. |
| imperial_b1_sentence_transcription_04 | sentence_transcription | B1+ | Je voudrais connaître les horaires d’ouverture. |
| imperial_b1_sentence_transcription_05 | sentence_transcription | B1+ | Nous vous remercions de votre patience. |
| imperial_b1_audio_transcript_choice_01 | audio_transcript_choice | B1 | Le cours commence à neuf heures. |
| imperial_b1_audio_transcript_choice_02 | audio_transcript_choice | B2 | Le départ a été reporté à demain. |
| imperial_b1_audio_transcript_choice_03 | audio_transcript_choice | B2 | Les frais de livraison sont inclus. |
| imperial_b1_audio_transcript_choice_04 | audio_transcript_choice | B2 | Cette démarche nécessite une autorisation. |
| imperial_b1_audio_transcript_choice_05 | audio_transcript_choice | B2 | Les travaux seront achevés avant vendredi. |
| imperial_b1_audio_meaning_choice_01 | audio_meaning_choice | B1 | The next bus arrives in five minutes. |
| imperial_b1_audio_meaning_choice_02 | audio_meaning_choice | B2 | They will handle your request as soon as possible. |
| imperial_b1_audio_meaning_choice_03 | audio_meaning_choice | B2 | The refund depends on meeting certain conditions. |
| imperial_b1_audio_meaning_choice_04 | audio_meaning_choice | B2 | We recommend booking ahead. |
| imperial_b1_audio_meaning_choice_05 | audio_meaning_choice | B2 | Only people who have a ticket may enter. |

### B2 cohort

| Exercise ID | Format | Stage | Target/reference |
|---|---|---|---|
| imperial_b2_meaning_recall_01 | meaning_recall | B2 | date à laquelle il faut payer ou terminer quelque chose |
| imperial_b2_meaning_recall_02 | meaning_recall | B2 | accord dans lequel chaque personne accepte de ne pas obtenir tout ce qu’elle veut |
| imperial_b2_meaning_recall_03 | meaning_recall | B2 | to cause a feeling, reaction or interest to arise |
| imperial_b2_meaning_recall_04 | meaning_recall | B2 | reliable; can be trusted to work or give accurate information |
| imperial_b2_meaning_recall_05 | meaning_recall | B2 | an important issue or interest at stake in a situation |
| imperial_b2_french_form_recall_01 | french_form_recall | B2 | échéance |
| imperial_b2_french_form_recall_02 | french_form_recall | B2 | compromis |
| imperial_b2_french_form_recall_03 | french_form_recall | B2 | susciter |
| imperial_b2_french_form_recall_04 | french_form_recall | B2 | fiable |
| imperial_b2_french_form_recall_05 | french_form_recall | B2 | démarche |
| imperial_b2_vocabulary_cloze_01 | vocabulary_cloze | B1+ | budget |
| imperial_b2_vocabulary_cloze_02 | vocabulary_cloze | B1+ | délai |
| imperial_b2_vocabulary_cloze_03 | vocabulary_cloze | B1+ | objectif |
| imperial_b2_vocabulary_cloze_04 | vocabulary_cloze | B1+ | avantage |
| imperial_b2_vocabulary_cloze_05 | vocabulary_cloze | B1+ | conséquence |
| imperial_b2_grammar_cloze_01 | grammar_cloze | B1+ | travaillerais |
| imperial_b2_grammar_cloze_02 | grammar_cloze | B1+ | que |
| imperial_b2_grammar_cloze_03 | grammar_cloze | B1+ | pourrons |
| imperial_b2_grammar_cloze_04 | grammar_cloze | B1+ | terminé |
| imperial_b2_grammar_cloze_05 | grammar_cloze | A2+ | de |
| imperial_b2_grammar_meaning_choice_01 | grammar_meaning_choice | B2 | We will go out despite the rain. |
| imperial_b2_grammar_meaning_choice_02 | grammar_meaning_choice | B2 | Take a coat in case it is cold. |
| imperial_b2_grammar_meaning_choice_03 | grammar_meaning_choice | B2 | The resignation is reported without being presented as confirmed. |
| imperial_b2_grammar_meaning_choice_04 | grammar_meaning_choice | B2 | Although he keeps insisting, I refuse. |
| imperial_b2_grammar_meaning_choice_05 | grammar_meaning_choice | B2 | We will leave unless it rains. |
| imperial_b2_sentence_transformation_01 | sentence_transformation | B1+ | J’ai un voisin qui joue du piano. |
| imperial_b2_sentence_transformation_02 | sentence_transformation | A2+ | Je le lis. |
| imperial_b2_sentence_transformation_03 | sentence_transformation | B1+ | Nous prendrons le train demain. |
| imperial_b2_sentence_transformation_04 | sentence_transformation | B1+ | Voici la ville où je suis né. |
| imperial_b2_sentence_transformation_05 | sentence_transformation | B1+ | Je ne mange jamais de viande. |
| imperial_b2_sound_discrimination_01 | sound_discrimination | B2 | coussin |
| imperial_b2_sound_discrimination_02 | sound_discrimination | B2 | désert |
| imperial_b2_sound_discrimination_03 | sound_discrimination | B2 | égout |
| imperial_b2_sound_discrimination_04 | sound_discrimination | B2 | peur |
| imperial_b2_sound_discrimination_05 | sound_discrimination | B2 | belle |
| imperial_b2_connected_word_recognition_01 | connected_word_recognition | B2 | ils en ont |
| imperial_b2_connected_word_recognition_02 | connected_word_recognition | B2 | s’en est |
| imperial_b2_connected_word_recognition_03 | connected_word_recognition | B2 | n’y a plus |
| imperial_b2_connected_word_recognition_04 | connected_word_recognition | B2 | leur avez |
| imperial_b2_connected_word_recognition_05 | connected_word_recognition | B2 | nous en |
| imperial_b2_sentence_reconstruction_01 | sentence_reconstruction | B1+ | Je lui parlerai après le cours. |
| imperial_b2_sentence_reconstruction_02 | sentence_reconstruction | B1+ | Hier nous avons envoyé le dossier. |
| imperial_b2_sentence_reconstruction_03 | sentence_reconstruction | B1+ | Si tu veux, nous pouvons attendre. |
| imperial_b2_sentence_reconstruction_04 | sentence_reconstruction | B1+ | Pendant le voyage elle nous a raconté son histoire. |
| imperial_b2_sentence_reconstruction_05 | sentence_reconstruction | B1+ | Nous devrions vérifier les résultats avant de partir. |
| imperial_b2_partial_dictation_01 | partial_dictation | B2 | à la majorité |
| imperial_b2_partial_dictation_02 | partial_dictation | B2+ | dans la mesure où |
| imperial_b2_partial_dictation_03 | partial_dictation | B2+ | faute de temps |
| imperial_b2_partial_dictation_04 | partial_dictation | B2+ | à l’issue de |
| imperial_b2_partial_dictation_05 | partial_dictation | B2+ | mettre en œuvre |
| imperial_b2_sentence_transcription_01 | sentence_transcription | B2 | Cette mesure vise à réduire les dépenses. |
| imperial_b2_sentence_transcription_02 | sentence_transcription | B2+ | Le financement dépend de plusieurs conditions. |
| imperial_b2_sentence_transcription_03 | sentence_transcription | B2+ | Les résultats doivent être interprétés avec prudence. |
| imperial_b2_sentence_transcription_04 | sentence_transcription | B2+ | Nous souhaitons privilégier une solution durable. |
| imperial_b2_sentence_transcription_05 | sentence_transcription | B2+ | Cette proposition mérite un examen approfondi. |
| imperial_b2_audio_transcript_choice_01 | audio_transcript_choice | B2 | La décision sera annoncée demain. |
| imperial_b2_audio_transcript_choice_02 | audio_transcript_choice | C1 | Cette hypothèse demeure difficile à vérifier. |
| imperial_b2_audio_transcript_choice_03 | audio_transcript_choice | C1 | Les retombées de cette réforme restent incertaines. |
| imperial_b2_audio_transcript_choice_04 | audio_transcript_choice | C1 | Il convient de nuancer cette interprétation. |
| imperial_b2_audio_transcript_choice_05 | audio_transcript_choice | C1 | La portée de cet accord est limitée. |
| imperial_b2_audio_meaning_choice_01 | audio_meaning_choice | B2 | The total cost must be taken into account. |
| imperial_b2_audio_meaning_choice_02 | audio_meaning_choice | C1 | This conclusion needs some qualifications or caution. |
| imperial_b2_audio_meaning_choice_03 | audio_meaning_choice | C1 | We cannot guarantee an immediate result. |
| imperial_b2_audio_meaning_choice_04 | audio_meaning_choice | C1 | The decision may jeopardise the rest of the project. |
| imperial_b2_audio_meaning_choice_05 | audio_meaning_choice | C1 | It is important to distinguish correlation from causation. |

## Remaining evaluation boundary

This review supports a limited functional pilot using this fixed content. It does not validate the complete lexical corpus, all expression stages, spontaneous speech production, mobile platforms not actually tested, long-term learning gain or transfer to new recordings. Students should be able to report ambiguous or defective content and skip it without receiving a fabricated failure grade. Any material change to a published retrieval contract requires a new exercise identity.
