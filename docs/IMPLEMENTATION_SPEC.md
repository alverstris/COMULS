COMULS implementation specification

Implementation baseline v1.0 • 7 October 2026

A consolidated product, curriculum, content and Anki engineering specification. Research-backed principles are distinguished from initial product defaults. Current source inspection limits and release gates are stated explicitly.

Document map

| Sections | Coverage |
|---|---|
| 01–03 | Product decisions, inspected vocabulary and research findings |
| 04–06 | Source schemas, import validation and definition prerequisites |
| 07–09 | CEFR windows, learner progression and sustainable workload |
| 10–13 | Screens, grading, thirteen exercises and connected-speech practice |
| 14–18 | Data contracts, Anki lifecycle, sync, packs and admission algorithms |
| 19–20 | Build sequence, deliverables and acceptance tests |
| 21 | Research and implementation sources |

01 — Purpose and implementation decisions

COMULS means Concurrent Multi Level System. It is a French curriculum implemented through short Anki flashcards. Earlier material remains in spaced review, current material is acquired, and selected future material is prepared through supported listening. The product aims to improve sustainable learning per minute. It does not certify CEFR attainment or claim that flashcards alone establish complete fluency.

This specification fixes the product behaviour, architecture, content contracts and release tests. “Required” denotes an implementation invariant. Numerical defaults are initial product settings to calibrate through use, rather than experimentally established optima. The research supports the learning principles; the implementation choices below apply those principles to COMULS.

The implementation consists of an offline content compiler, a versioned course pack, an Anki Desktop add-on, and portable templates for reviewing admitted cards on supported mobile clients. Sentence generation, dictionary lookup and speech synthesis happen during content production. A study session requires no model call or paid API.

The first compatibility target is Anki Desktop 26.09. Native Anki owns cards, ratings, review history and scheduling. COMULS owns content selection, prerequisite checks, the learning interface and admission of new exercises. COMULS must never implement a competing spaced-repetition scheduler by rewriting due dates.

The scope is thirteen short exercise types. Speech production, pronunciation recording, conversation simulation, long reading, long listening and open-ended essays are excluded. Full-sentence transcription and controlled sentence transformation form the upper end of the intended task complexity.

A single ordinary note type, COMULS Exercise v1, generates one card per exercise instance. Thirteen pedagogical types share four interaction shells. Stable exercise identities preserve histories. A new context that materially changes the retrieval problem receives a new identity; it is not randomly substituted on an existing scheduled card.

Course advancement is manual. The selected level controls admission, while introduced cards continue in review. Uneven skills are handled through prerequisites and targeted repair. The system never silently demotes the learner’s whole course because one skill is weak.

The first release supports one designated desktop for course management. Other clients can review synced cards. This avoids pretending that Python-only admission, detailed telemetry and time-budget enforcement are available on stock mobile Anki.

02 — Source inspection and corpus status

The source inventory consists of six uploaded files. Their matching Google Drive counterparts were located in the same vocabulary export folder. The guide and the two smaller CSVs were read completely; the smaller CSVs were parsed as quoted CSV, including embedded newlines and JSON. The three large CSV responses exceeded the connector’s 8 MiB response limit. Their complete contents were not independently audited in this session.

Matching filenames and byte sizes do not prove byte equality between the uploads and the Drive copies. The compiler must hash and audit the actual chosen input bundle before a release. The findings below distinguish parsed records from guide-reported counts.

| File | Observed bytes | Role and inspection |
|---|---:|---|
| french_vocabulary_b1_c1.csv | 44,886,462 | Final parent learning-list view; metadata and guide available; full parsing still required |
| french_vocabulary_verified.csv | 44,886,462 | Verified parent view; equality with the learning list must be checked |
| french_vocabulary_senses.csv | 32,023,973 | Flattened retained senses; joins and complete contents still require parsing |
| french_baseline_family_meanings.csv | 1,348,222 | Fully parsed Drive copy: 259 senses, 107 distinct parents |
| french_definition_support.csv | 379,501 | Fully parsed Drive copy: 169 senses, 96 distinct parents |
| french_vocabulary_guide.txt | 12,954 | Readable Drive guide inspected completely |

The baseline file contains 189 records under A1-labelled parent families and 70 under A2-labelled families. All 259 definitions are English. The support file contains 169 English definitions with local introduction stage B1. Both files have unique sense IDs internally, no shared sense IDs with each other, no populated context_sentence values, and no card_ready=true rows. Every populated JSON field parsed successfully. These are structural findings, not a linguistic certification.

The guide reports 10,037 advanced word families, 370 expressions and 24,608 advanced sense/usage records. Baseline extensions and definition support are separate scopes and must not inflate that advanced-family count. The full advanced-file audit must reproduce or explicitly explain any difference from those reported totals.

| Source band | COMULS stage | New word families | New expressions | English parents | French parents |
|---|---|---:|---:|---:|---:|
| B1 | B1 | 916 | 141 | 1,057 | 0 |
| B1/B2 | B1+ | 810 | 0 | 607 | 203 |
| B2 | B2 | 2,616 | 177 | 1,396 | 1,397 |
| B2/C1 | B2+ | 2,446 | 13 | 615 | 1,844 |
| C1 | C1 | 3,249 | 39 | 0 | 3,288 |

These are guide-reported introduction counts, not cumulative totals. B1 introduces 141 expressions; B1+ currently introduces zero additional expressions and retains those 141 for continued study. The substantive uncertainty is the accuracy of individual expression placements throughout all bands. None of the 370 expression placements has been independently validated by this specification's source inspection. The zero B1+ count neither proves nor disproves a classification error, and equalizing counts would not validate difficulty. Preserve the source allocation as provenance and treat it as provisional until the exact expression meanings and task demands have been audited. These are personal curriculum selections, not official vocabulary quotas for CEFR qualifications.

The current GitHub tree has README.md, COMULS_workflow_preferences.json and one older 42,149,306-byte parent CSV. The guide names definition_policy.json, inventory.json, reference validators, prerequisite scripts and repair receipts, but those files are absent from that repository tree. Their contents must not be represented as inspected or implemented. Recover them into the source bundle when available; otherwise implement the explicit contracts in this specification and record the replacement policy version.

Current content is a lexical foundation. It still needs sense-specific curriculum assignments, reviewed contexts, exact accepted answers, construction records, media and complete dependency validation. No C2 dataset is present. The 259 baseline-family extensions are not a complete A1–A2 curriculum.

Source links: [vocabulary guide](https://drive.google.com/file/d/1VVs8E6Vkp-DfRyU2Hl74Dq1FtmVZ4E9a/view?usp=drivesdk), [baseline meanings](https://drive.google.com/file/d/1_2-HVOq4T_PniK9ceMdr7y-PCIR-Z18e/view?usp=drivesdk), [definition support](https://drive.google.com/file/d/1r1gDxbx8aJnoJwClidk_jmiGs6kLqp8k/view?usp=drivesdk), [repository](https://github.com/alverstris/COMULS).

03 — Learning evidence and its implementation consequences

The relevant outcome is retained, usable knowledge per total study minute, together with continued participation. Immediate accuracy, cards per minute, perceived effort and fatigue are separate measurements.

| Finding | Evidence and limit | COMULS decision |
|---|---|---|
| Familiar components reduce demands from processing many interacting unfamiliar elements | Cognitive-load research; effectiveness depends on prior knowledge [R01] | One principal unfamiliar demand per card; understandable carrier language and instructions |
| Recall can be more effortful while improving delayed retention | Coppens et al. compared free recall, cued recall and recognition; recall benefited one-week retention [R02] | Preserve short cued recall; use recognition for the distinctions it actually tests |
| Longer unsuccessful searching is not automatically more valuable | Vaughn et al. found similar final learning after 5, 10 or 30 seconds of attempted retrieval; different materials from COMULS [R03] | Permit answer reveal after a sincere attempt; no compulsory countdown |
| Elaborate after-error hints can consume time without improving later unaided recall | Three classroom vocabulary experiments by van den Broek et al. [R04] | Optional concise support; avoid mandatory hint ladders |
| Spacing benefits language learning | Kim and Webb analysed 48 experiments with 3,411 participants [R05] | Preserve native spaced returns across days; avoid excessive immediate repetition |
| More within-session repetition can reduce efficiency per minute | Nakata: 98 learners; more repetitions improved raw retention, one retrieval had the largest time-adjusted gain [R06] | Evaluate the opportunity cost of extra repetitions; do not turn one success into permanent retirement |
| Silent retrieval can work, with important compliance and task limits | Smith et al. found similar benefits; Jönsson et al. found a small overt advantage [R07, R08] | Silent recall for meaning; typing for French form, morphology and transcription |
| Interleaving effects depend on what is mixed and when | Grammar study favoured delayed interleaved practice; vocabulary study favoured initial focused practice followed by mixing [R09, R10] | Focused acquisition, then mix learned targets; keep interfaces consistent |
| Listening accuracy can conceal effort | Borghini and Hazan measured greater pupil responses in non-native listeners; this measured effort, not fatigue [R11] | Use support/replay and occasional self-report alongside accuracy |
| Support should depend on knowledge | Jiang et al. found reading-plus-listening benefits for novice language learners [R12] | Familiarise difficult audio with meaning/transcript; later assess unsupported recognition |
| Listening-related fatigue is associated with proficiency | McGarrigle et al., 2026, observational study; no card-duration prescription [R13] | Keep lower-proficiency listening demands bounded and inspect cumulative fatigue |
| Breaks can improve comfort without a proven general performance gain | Micro-break meta-analysis: 22 samples, 2,335 people, small fatigue/energy benefits [R14] | Offer stopping points and optional breaks |
| No universal break cadence is established | Scheduled and self-regulated break studies have differing subjective results [R15, R16] | Adjustable budget, dismissible break suggestions, no forced Pomodoro schedule |
| Multiple choice still requires reading and comparison | Listening eye-tracking research shows interactions between format and timing [R17] | Short familiar options; separate exact-wording recognition from meaning comprehension |

Exact CEFR offsets, demanding-card run lengths, readiness thresholds and daily time limits are product policies. The cited experiments do not validate those precise settings or this combined system. COMULS can be released as a functional curriculum before claiming an experimentally demonstrated improvement in learning speed.

04 — The canonical vocabulary model

The importer preserves the original files byte-for-byte in a source snapshot and builds a normalized catalog. Source records, compiled teaching material and learner evidence are separate layers.

| Entity | Identity and required information |
|---|---|
| SourceSnapshot | Bundle ID, file name, SHA-256, bytes, parsed rows, source location, schema fingerprint, import time |
| LexicalParent | Source entry_id, displayed headword, scope, word/expression kind, original band, assigned definition language, provenance |
| Sense | Source sense_id, parent ID, selected meaning, POS, gender, usage, required construction, source claims, aliases, original level status |
| Form | New persistent form_id, surface form, exact sense compatibility, morphology, construction constraints, pronunciation variants |
| Construction | Persistent construction_id, form and meaning, permitted frames, prerequisite graph, positive and negative fixtures |
| CurriculumAssignment | Entity ID, internal COMULS stage, rationale, assessor/method version, confidence and approval disposition |
| SupportText | Persistent support_id, text, language, exact lexical/form/grammar dependencies, translation provenance |
| Utterance | Persistent context_id, fixed text, semantic frame, token spans, target spans, carrier requirements, register and locale |
| AudioArtifact | Audio ID and hash, utterance hash, generation settings, rights, duration, alignment and validation |
| ExerciseSpec | Persistent exercise_id; runtime-only native note binding; recipe, target, fixed context, answer contract, prerequisites, media and QA |
| LearnerEvidence | Entity and facet, event source, assistance class, native review reference or explicit declaration, validity/version |

Form is the conceptual entity called realization in the normalized SQL schema; form_id/realization_id must be mapped consistently by the schema adapter, not treated as two unrelated objects.

A parent count is a family count. A sense count is not a family count. Ordinary inflections are not additional families. The add-on reports families, senses, exercises and review attempts separately.

Use entry_id and sense_id exactly as supplied. Sense display order is never an identity. A renamed headword, reordered definition or changed dictionary URL does not create a new sense. Retired aliases point to the surviving identity; conflicting or cyclic aliases fail validation. IDs must not be regenerated from current text.

Preserve all source fields even if the first application version does not display them. In particular preserve source_claims_json, sense_aliases_json, grammatical_realizations_json, property_action_relation_json, original_advanced_parent_json, family_relation_review_json and the baseline parent-preservation fields.

The importer normalizes empty sense_cefr_level to null and retains sense_level_status. It does not fill that blank from lemma_cefr_level. An internal curriculum assignment is a distinct, auditable decision. The application displays “COMULS introduction stage” where that is the actual claim.

Expression-level placement audit

Audit the exact expression sense and construction, retaining source_band separately from the reviewed COMULS assignment. A multiword unit must not inherit a level from its hardest component, a related single-word parent, a dictionary verification flag or a target count for a band. Familiar everyday formulas, discourse markers, collocations and opaque idioms require different evidence; the label “expression” alone supplies none.

For every expression, record: stable parent/sense IDs; exact form/meaning/construction; original band and assignment method; any matching French reference-level or graded teaching evidence; whole-expression frequency and dispersion with corpus/register identified; grammatical and semantic prerequisites; distinct recognition and controlled-production task demands; proposed introduction stage or unresolved range; rationale, sources and confidence basis; and disposition keep, raise, lower or unresolved. An AI-generated confidence percentage is not calibrated evidence. Half-stage choices require explicit local sequencing reasons and must not imply an official B1+ lexical classification.

FLELex reports receptive frequencies from textbook reading and simplified readers. Those distributions are evidence about observed exposure, not direct measurements of an individual learner's ability to retrieve a particular meaning or use it correctly. [FLELex project description](https://cental.uclouvain.be/cefrlex/flelex/).

The 2020 FLELex/Beacco modelling study used the TreeTagger version, which excluded multiword expressions, and collapsed fine-grained sense distinctions during resource matching. Its reported validation therefore cannot by itself validate COMULS's expression placements or sense-specific production tasks. This identifies a limitation of that evidence; it does not establish which COMULS records actually used that model. [Pintard and François (2020), sections 3.1.1–3.1.3](https://aclanthology.org/2020.readi-1.13.pdf).

Review all 370 expression parents and their retained meanings before claiming that their allocation is validated. Cross-check available French Reference Level Descriptions and genuinely graded materials for the same meaning, rather than assigning a level from intuition alone. Conflicting or absent evidence remains visible; unresolved task assignments cannot activate cards. Do not redistribute expressions simply to fill B1+ or make the table look balanced. Preserve definition-language assignments during any reclassification, and rerun prerequisite, task-ceiling and introduction-count checks. The current document does not assert that any specific expression has already been proved misclassified.

POS labels are heterogeneous, including English and French labels. Normalize them through an explicit mapping table while retaining the original value. Unknown labels block affected recipes; they are not guessed from the headword ending.

A grammatical realization is evidence to inspect, not automatically a permitted answer. The parsed surprendre record for “cause surprise” retains surpris/surprise and a historical adjective construction. A verb-recall card must not accept an adjective merely because that form exists inside the record. Likewise, the guide’s humilié/humilier and bétail/bestiaux examples require distinct accepted forms and meanings.

Expression relationships remain links until a recipe explicitly uses them. Do not generate duplicate cards by independently importing the parent summary, every flattened sense, each alias and each expression-overlap candidate.

05 — Import contracts and validation

Choose one source bundle explicitly. Compute SHA-256 over raw bytes before decoding. Decode UTF-8 with optional BOM and use a standards-compliant quoted CSV parser. Embedded newlines and JSON are expected. Parse false/true case-insensitively into booleans; the nonempty string “false” must never become truthy readiness.

The two parent views must be compared, not concatenated. If they are identical, retain one canonical parent dataset and two source-view records. If they differ, produce an ID-and-field difference report and refuse an implicit winner. Compare flattened advanced senses against the nested senses_json representation by sense_id. Any missing, duplicated or materially conflicting record blocks the affected release.

The source schema adapter must have explicit mappings. Known parent fields from the repository documentation are entry_id, definition and senses_json; the actual uploaded parent headers still need the complete import audit. Do not hard-code invented source column names as if they were inspected.

The fully parsed baseline and support files share this verified field set:
sense_id, entry_id, vocabulary, sense_order, semantic_label, definition, definition_language, part_of_speech, gender, usage, required_construction, sense_cefr_level, sense_level_status, lemma_cefr_level, tags, context_sentence, context_provenance, definition_source, definition_source_url, dictionary_sense, definition_wording, definition_accessed_on, source_claims_json, verification_status, card_ready, card_preparation_status, expression_meaning_relation_ids_json, sense_aliases_json, grammatical_realizations_json, property_action_relation_json, property_category_repair, original_advanced_parent_json, family_relation_review_json.

Baseline additionally contains parent_inflection_aliases_json and parent_sense_preservation_requirements_json. Support additionally contains definition_scope, local_intro_stage, level_basis, published_band, french_prerequisites_json and field_languages_json.

JSON-valued cells can contain arrays, objects or null. Validate the expected type per field. Preserve nested originals and receipts. Do not flatten their historical contents into the learner’s current definition or accepted answer set.

Required import audit outputs:

1. File hashes, schema fingerprints and row counts.

2. Counts by scope, band, definition language, verification state and readiness.

3. Duplicate parent IDs, duplicate sense IDs, alias collisions and orphaned links.

4. Parent/nested/flattened-view reconciliation.

5. JSON syntax and type failures; boolean and null normalization.

6. Counts and examples of conflicting forms, POS, required constructions and inherited level claims.

7. Definition dependency coverage, unresolved references and strongly connected components.

8. A separate coverage map for A2 recovery, A2–C1 and absent C1+/C2 additions.

9. A machine-readable pass/fail report with record IDs and reason codes.

No release uses a “best effort” partially parsed row. Valid unrelated records may be released only through an explicitly scoped manifest that lists excluded IDs and reasons. A malformed row is quarantined, not silently dropped from claimed totals.

The input CSV card_ready flags remain unchanged during planning. The compiler creates a separate compiled_card_ready result after all exercise gates pass. Later publishing repairs to vocabulary CSVs must regenerate all affected views consistently and follow the repository’s standing rule to save completed CSVs to both Google Drive and GitHub.

06 — Definition language and prerequisite closure

Definition language is assigned to a vocabulary parent and preserved across its selected meanings. Existing assignments are authoritative. The advanced-parent denominator includes word parents and expression parents, producing the guide’s counts. Baseline extensions and definition-support records are outside these quotas.

For newly authored parents, calculate desired French parents = round_half_up(total parents in the band's new version × French share). Subtract the number of already assigned French parents, clamp the result between zero and the number of unassigned parents, then assign that many new parents after sorting their IDs by a stable course-policy hash. Persist the assignment. If frozen old assignments make the exact new overall quota impossible, report the deviation rather than changing existing cards. Never make an independent random language choice for each meaning or review. An update must not rebalance already assigned parents by flipping their language.

The established shares are B1 0% French, B1+ 25%, B2 50%, B2+ 75%, C1 100%. There is no verified C1+/C2 export quota to apply to absent records; new advanced packs use an explicit authoring policy when they exist. Earlier English cards remain English after course advancement.

All learner-visible French needs exact dependencies: definition, semantic label, usage note, instruction, example, distractor, feedback and audio transcript. A common headword or lower parent band does not establish knowledge of the particular sense or form. Source-receipt metadata is not automatically shown as teaching text.

The compiler annotates each required unit as sense, form, construction, phonetic feature or instruction, with its required modality and minimum knowledge state. Inflected function words and multiword constructions are included. Proper names are either explicitly introduced labels or supplied as support; they are not silently classified as known.

The default support ceiling is an earlier full CEFR band: B1/B1+ definitions use A2 support; B2/B2+ use B1; C1/C1+ use B2; C2 uses C1. This is the conservative v1 replacement policy until the guide’s precise definition_policy.json is recovered and reconciled. An active runtime exception may use an exact prerequisite introduced at or below the target’s stage when the learner has explicitly confirmed understanding or demonstrated the required facet. It may never admit an unresolved or higher-stage dependency.

Model knowledge states separately:

- unknown: no usable evidence;

- familiarised: its exact form and meaning have been presented;

- understood: an explicit declaration for a permitted supporting use, or a genuine successful native review of the required facet;

- stable: the configured separated-review criterion is met;

- repair_needed: a separate weakness overlay, not erasure of earlier evidence.

Persist the evidence kind separately: learner_declaration, observed_native_retrieval or familiarisation. The aliases stable_retrieval and stable refer to the same derived criterion. Introduced describes native exercise lifecycle, not mere exposure.

A confirmation is a declaration, not measured mastery. It can make supporting language usable while a clear “Explain this word” control remains available. It never grants productive ability or advances a level. The target facet being taught must not be required to be mastered before its own exercise can appear.

New French-definition exercises require complete authoring dependency closure and learner-level support availability. Unknown prerequisites are taught through English or offered for an exact-use confirmation. English support words familiar to the English-speaking learner do not need their own cards. The 169 support senses and 259 baseline extensions provide specific acquisition material, not universal proof of the entire baseline.

Build a directed prerequisite graph and reject unresolved cycles. Break a cycle by rewriting a definition with earlier language or supplying a legitimate English acquisition route. Do not resolve a cycle by marking both meanings known.

An introduced review must remain usable if a supporting word is forgotten. Supply an optional gloss for that prerequisite without disclosing the primary target. If the available repair reveals the target answer, mark target assistance and recommend Again; exclude the attempt from unaided readiness evidence regardless of the chosen native rating. If the prompt itself is defective or the answer cannot be evaluated, skip without grading and send it to content repair.

Canonical French wording remains intact when an English support gloss is shown. This is support for comprehension, not a silent replacement of the card’s definition language. The card’s answer screen identifies the primary objective so support for unrelated carrier language is not confused with failure of the target.

An optional French replacement for an older English acquisition exercise receives a distinct exercise identity linked to the same sense. Retire the English acquisition card only after the French representation reaches the configured separated-review criterion, with its history preserved. Keep English/French contrast exercises where contrast is the objective. Retirement is reversible and must not suspend a user’s unrelated cards.

07 — Curriculum stages and eligibility

Use these ordered curriculum indices: A2=0, A2+=1, B1=2, B1+=3, B2=4, B2+=5, C1=6, C1+=7, C2=8. A2-R is a separate recovery mode. Plus stages are local subdivisions, not official CEFR qualifications. A half-level is one index; a full-level offset is two indices. Clamp upper preview ceilings at C2.

Store selected_stage, recovery_mode, source introduction band, target assignment, carrier assignment and construction assignments separately. A stage is a ceiling for new activities, not a statement that all lower-stage language is known. Parent introduction bands never substitute for assessed task assignments.

The ranges below are the complete v1 admission policy. Below-X requirements apply to the target, carrier and required construction, not only the missing word. Supported previews above X require prior familiarisation with the relevant meaning and written/audio form. Empty or unavailable bands contribute no fabricated exercises.

| Exercise ID | New-task ceiling | Additional release condition |
|---|---|---|
| meaning_recall | X | Target meaning familiarised; cue and definition comprehensible |
| french_form_recall | X | Exact intended meaning/form made clear; target form previously presented |
| vocabulary_cloze | Strictly below X | One gap; known carrier; disambiguated target and accepted alternatives |
| grammar_cloze | Strictly below X | Target feature familiarised and components understood; known carrier; one grammatical operation |
| grammar_meaning_choice | X | Relevant constructions familiarised; comprehensible contrasting meanings |
| sentence_transformation | Strictly below X | Source understood; one explicit operation; input/output forms familiarised and understood |
| sound_discrimination | X+½ for lexical previews | Contrast and response labels familiarised; phonetic complexity recorded separately |
| connected_word_recognition | X for new foundation training | Known target meaning/form and accessible carrier; repair may be far below X |
| sentence_reconstruction | Strictly below X | All tiles and constructions understood; recording determines sequence |
| partial_dictation | X+½ | Target chunk familiarised; written carrier understood; above-X task supported first |
| sentence_transcription | X+½ | Short utterance; all indispensable meaning/form support supplied before preview review |
| audio_transcript_choice | X+1 | Audio familiarised; readable options; audible distinction |
| audio_meaning_choice | X+1 | Meanings familiarised; answer options understandable at X or through English |

The cloze and transformation ceilings preserve the agreed requirement that contextual synthesis sits below X. X−½ is the maximum, not a compulsory minimum: a B1 learner may receive A2 work. More demanding contextual variants use at least a full level below X. Because there is no established numerical equivalence between CEFR distance and mental load, the compiler also enforces independent load controls.

A2 learners can receive below-X cards only from independently authored and assessed baseline content. A1/A2 parent labels on the 259 extensions do not automatically qualify their particular senses. If no suitable lower content exists, show another eligible activity and describe the content gap.

At C1/C2, exhaustion of the current word list does not establish course completion or CEFR attainment. The interface reports available content coverage. Unsupported C1+/C2 acquisition shows “Content not yet available”; earlier reviews remain usable.

Activation into the native new queue is evaluated in this order: valid pack and exercise → authoring readiness → selected-stage ceiling → exact prerequisite closure → target familiarisation → user-enabled capability → admission budget → exposure-group spacing. Eligible content may be materialized in a COMULS-paused preparation state to record ungraded familiarisation before activation; preparation cannot bypass authoring or stage gates. Return a reason code for every refusal. Do not let a low-priority constraint obscure a defective source or missing answer key.

08 — Progression, placement and learner state

The Levels screen displays all stages, current selection, available validated material and skill-specific readiness. Selecting “Use this stage” is the only ordinary way to change the course stage. A higher selection expands eligibility; it does not introduce a whole band at once. A lower selection narrows future admission while retaining genuine earlier learning.

Distinguish the following lifecycle states:
catalog_candidate → validated_catalog → prepared_paused → familiarised → admitted_new → introduced → maintained.
Separate overlays record user_paused, content_blocked, admission_withdrawn and retired. Suspended is an Anki scheduling state, not a sufficient explanation of why a card is paused.

Materialisation means creating a native note/card. Preparation creates it suspended with a COMULS preparation reason for ungraded familiarisation and durable evidence. Admission means activating that prepared card in the native new queue after all gates pass. Introduction means the first genuine native answer event. An admitted-but-unreviewed card can be withdrawn from the active new queue after a stage change or prerequisite correction, using a recorded COMULS-owned suspension reason. A card with genuine review history remains reviewable irrespective of the new window. Preserve records in both cases.

The optional placement check suggests a stage and identifies weak facets. It is not a validated CEFR examination. Use short tasks drawn from the actual recipes and report evidence separately for meaning, written form, grammar interpretation, grammar production, sound contrast, segmentation and sentence comprehension. Placement does not mark an entire band or word family known.

The default diagnostic samples four items at a stage for a selected domain; 3–4 correct suggests testing one stage higher, 0–1 one lower, and 2 adds four items at the same stage. Stop after twelve items per chosen domain and report uncertainty. This is a configurable starting procedure. Ungraded diagnostic results inform suggestions only; scheduled native exercise reviews provide durable prerequisite evidence.

An experienced learner can inspect a required baseline use and choose “I understand this use.” Persist that declaration against the exact sense/form on its acquisition note, with evidence_kind=learner_declaration. The note can remain COMULS-paused as assumed known. It carries no fabricated native grade. Requesting help on that use offers to activate its normal acquisition card. The declaration never certifies unrelated forms or senses.

For readiness and optional representation retirement, default stable_retrieval means two unaided successful native review episodes on different dates, each at least 24 hours after any known answer-revealing exposure. Apply this only where exposure evidence is sufficiently complete. A mobile review can contribute ordinary recall evidence, but unknown assistance or exposure history cannot be treated as verified independent evidence. The threshold is a policy to calibrate.

The home screen shows readiness as evidence with coverage: “12 of 20 sampled grammar targets stable” is acceptable. A percentage must disclose its denominator. It must not imply mastery of all vocabulary or an official language qualification.

Essential state is synced in native note fields and small collection configuration. Store selected stage, policy version and designated manager identifier in a namespaced collection setting. Store admitted/familiarised state, explicit declarations, managed suspension reason and retirement links on their exercise notes. Derive graded skill evidence from native review history plus declared card objectives. High-volume click/replay telemetry is local and dispensable.

If local telemetry is lost, preserve all native learning and rebuild conservative derived evidence. Unknown assistance history reduces the strength of readiness claims; it does not erase the learner’s cards or change due dates.

09 — Time budgets, review load and concurrent practice

Set an adjustable default daily desktop budget of 15 active minutes and a default cap of six new knowledge units per day. A knowledge unit is a new selected sense, construction or phonetic target, not every generated card. Actual admission is further limited by remaining time and required prerequisite work. Sessions consume the same daily remainder; restarting a session does not replenish it. Explicit continuation records a budget override. These defaults are configurable product choices.

Count playback, replay, response and feedback processing as active study time. Pause playback and the timer together when the learner explicitly pauses or the application loses focus. On return, show Resume without automatically restarting playback. Long idle intervals trigger a pause prompt; do not use that prompt as a retrieval deadline. Wall-clock session time and active time are reported separately.

Estimate work using observed median active duration per exercise type, falling back to initial estimates: 8 seconds for meaning recall, 12 for short selection, 18 for a short typed form/cloze, 25 for partial dictation/reconstruction, and 40 for full transcription/transformation. These are forecasting values, never answer timers. Replace them with robust observations after at least twenty completed attempts of the relevant type.

The offered COMULS preset uses native reviews-before-new ordering; necessary repair and eligible acquisition are offered after due review if time remains. Respect an existing user preset and display its actual ordering. The add-on does not promise reviews-first ordering when the learner has chosen native mixed ordering. If estimated due work exceeds the daily budget, stop default new admissions. Expose the outstanding workload and allow the learner to change the budget or explicitly continue. Never conceal a growing backlog by resetting due dates or pretending skipped cards were completed.

New learning resumes automatically after estimated due work stays below 70% of the budget on two completed study dates. An explicit learner override can resume sooner. Every admission decision records the budget estimate and reason. This hysteresis is a tunable policy to avoid rapid pause/resume oscillation.

Use Anki’s ordinary queue and due ordering in v1. COMULS does not pull an independently ranked due card and then write its own scheduling result. Activity filters apply to eligible new acquisition and repair selection; ordinary due study uses the complete COMULS native queue. V1 does not create activity subdecks or custom filtered review queues. Existing native review scheduling remains authoritative.

After three consecutive full-sentence transcription or transformation cards, offer a stopping point when the next card is also demanding. The suggestion is dismissible. Do not silently bury due cards merely to enforce an aesthetic sequence.

Do not generate thirteen representations per sense. Start with the representation needed for acquisition and at most one complementary representation when it serves a distinct objective. Add other representations when a curriculum requirement or diagnosed weakness justifies them. Existing useful representations retain their schedules; optional retirement follows evidence, not a global card-count quota.

Exposure groups are separate from native Anki siblings. The one-card-per-note model means two notes sharing a sense are not automatically buried together. The compiler declares exact_answer_exposure_groups, shared_utterance_groups and looser related_target_groups. Only groups that reveal the answer require strict separation; sharing a family alone is not enough.

On desktop, an answer reveal may temporarily bury other unintroduced or review cards whose exact target was disclosed, using native bury operations and preserving history. The default separation is until the next Anki day. Undo grade-derived achievement evidence when the grade is undone, while retaining the factual answer exposure and conservative exposure protection. An intentional immediate follow-up is labelled primed practice and excluded from independent readiness evidence.

Stock mobile cannot run this cross-note exposure policy. Reduce exposure leakage through selective materialization, and label mobile readiness evidence conservatively. Native scheduling still operates. Desktop-only detailed budgets are not presented as a fully synchronized hard limit across devices.

Repeated difficulty triggers diagnosis. Default alert: three failures among the last five genuine reviews across at least three dates. Check ambiguity, unknown prerequisites, meaning confusion, spelling and auditory segmentation separately. After three failed presentations in one session, suggest repair or ending that session. Do not overwrite FSRS learning steps or apply an automatic “successful” grade to escape the loop.

10 — Screen layout and navigation

The add-on adds a COMULS button to the desktop deck-browser toolbar and a Tools → COMULS menu entry. The Home view opens inside a dedicated Qt window or stacked panel and returns cleanly to ordinary Anki. “Open COMULS on profile startup” is an explicit onboarding preference, initially off for shared Anki profiles. It must not block startup, sync or access to other decks.

| Screen | Visible information | Primary actions and states |
|---|---|---|
| Onboarding | Course scope, available content stages, current Anki compatibility, existing scheduling mode | Choose manual stage and time budget; test audio; try one example of each interaction shell; choose startup preference |
| Home | Selected stage, due reviews, estimated time, pending new material, content/repair notices | Study due cards; learn eligible new material; resume; open Levels or Library |
| Study | Small objective label, prompt, response, stable help/playback controls | Submit/reveal; inspect feedback; choose native rating; pause; report problem |
| Levels | Stage sequence, current selection, actual pack coverage, facet readiness with sample counts | Use this stage; inspect prerequisites; enter/leave A2-R manually |
| Library | Search by French form, meaning, parent, sense, construction, stage and exercise | Browse definitions and examples; inspect relationships; manage target-specific practice |
| Progress | Review time, recall by objective, coverage and support use | Select date range; inspect weak targets; export local report |
| Settings | Audio, accessibility, active exercise families, time budget, startup and managed decks | Change preferences; open native Anki deck options; repair/reconcile pack |
| Content manager | Installed pack/version, source audit status, update preview and quarantine | Validate pack; apply non-destructive update; inspect conflicts; restore retired exercise |

Home keeps “Study due cards” visually primary whenever due work exists. The user may choose a specific activity for eligible acquisition or repair; ordinary due study uses the complete native queue. The interface explains remaining due work rather than hiding it. New material is visibly unavailable when source readiness, missing prerequisites or budget blocks it, with the specific reason and a useful next action.

Levels change admission only. The confirmation screen states the new stage, number of currently eligible candidates and how existing reviews are preserved. It does not promise a bulk unlock of thousands of cards. A downward change lists admitted-but-unreviewed cards being paused. Ordinary stage changes do not require a technical warning dialog.

The Library groups senses under entry_id and shows the exact required form/construction for each selected sense. Historical provenance is collapsed under Sources. It must not display raw JSON, unrelated dictionary subdivisions or all meanings on an ordinary study back.

Browse mode is ungraded. Viewing an answer is still an exposure for desktop independence tracking, but does not create a native review or a successful recall. Previewing a future item cannot bypass its curriculum gate.

Study uses a centred reading area, adjustable text size, consistent spacing and one main response region. The objective, playback, help and submit controls remain in fixed locations across types. Choice and tile controls reserve their space before being populated. Use adequate contrast, visible focus and text labels; correctness must not rely on red/green alone. No compulsory animations, dragging or countdowns.

Keyboard policy: Tab/Shift+Tab move focus; Enter submits an active text field; Space activates a focused control or native reveal in the correct state. Native 1–4 ratings work only on the answer side. Choice shortcuts cannot also grade the revealed card. Letter shortcuts are inactive while typing. Escape pauses/closes the relevant overlay while preserving the current desktop attempt in memory. A crash or fresh card render may restart the attempt and creates no completion credit. IME composition must finish before Enter can submit.

A screen reader can identify the task, input, choices, playback controls, feedback and rating actions. Diacritics can be entered through the operating system keyboard or an optional on-screen accent row. An auditory task disabled for accessibility is recorded as not assessed; a text replacement does not certify listening ability.

Disabling an exercise family stops new admission by default. For an accessibility need or deliberate practice pause, offer a separate action to pause its existing cards with an explicit COMULS-owned reason. Re-enabling reverses only a pause still attributable to COMULS; it must not undo an unrelated user suspension.

11 — Shared card state machine and grading

The state sequence is loading → ready → responding → submitted → feedback → graded. Pause, abort and unavailable are separate exits. Each render has a nonce and expected native card ID. The primary response and reference answer are fixed for that exercise version.

During loading, verify required fields and local media. In ready, show the prompt and enable its response action. Begin audio once if autoplay is enabled and the platform permits it. Listening cards may allow typing while audio plays; do not add an artificial memory delay.

Submission saves the attempt in temporary state and reveals the native answer side. Submission never commits a grade. The back renders correctly even when no front-side state exists, as in preview or after a restart.

Feedback begins with the correct target and a compact comparison. Then show at most one explanation of the tested distinction. Further usage notes, annotated transcript and sources are expandable. The learner controls the time spent correcting an error.

| Native rating | Required meaning |
|---|---|
| Again | Primary target was not retrieved correctly, or target-revealing assistance was needed |
| Hard | Primary target was retrieved correctly with substantial difficulty |
| Good | Correct target retrieval with ordinary effort |
| Easy | Correct, confident target retrieval with very little effort |

COMULS can recommend a grade but the native reviewer commits the learner’s final choice exactly once. Hard must never be presented as the ordinary wrong-answer button. An uncertain evaluator allows self-comparison and correction of its diagnosis; it cannot confidently reject every unlisted valid paraphrase.

Classify support separately:

- ordinary replay, accessibility settings and instructions: permitted task controls;

- carrier explanation that does not disclose the answer: log carrier support;

- first-letter or partial target hint: log target assistance and exclude independent mastery evidence;

- full transcript/answer reveal before a response: answer-revealing assistance;

- correction after the response: feedback, not a second independent attempt.

Replay alone never recommends a failure grade. A target hint recommends Again and marks the attempt assisted regardless of the learner's chosen rating. Carrier help can coexist with a correct primary retrieval, but cannot prove that the carrier prerequisite was already secure.

For French form, cloze and full transcription, the answer contract names whether exact orthography is part of the primary objective. Full-sentence transcription requires the specified word sequence and meaningful spelling/morphology; separate diagnostics can still acknowledge correct hearing. Partial dictation can target spelling or segmentation, but that choice is fixed in the exercise identity and displayed before answering.

Normalize Unicode to NFC, typographic apostrophes, permitted equivalent spacing and sentence-initial case when case is incidental. Do not globally strip accents, negation, inflections or apostrophes. Punctuation tolerance is declared per exercise. The checker uses explicitly accepted variants and grammar constraints; fuzzy similarity is diagnostic only.

Return evaluation dimensions independently: lexical identity, sequence, orthography, target morphology, grammatical meaning and semantic meaning. Dimensions not assessed are null, not silently passed. If the answer is ambiguous or the recording cannot distinguish alternatives, use content_problem and skip without a learning grade.

Stop audio on reveal when required for focus, on grade, navigation, pause, focus loss and profile close. Repeated keydown, double-click, delayed callbacks and stale messages cannot produce a second submission or rating.

“I don’t know” reveals the answer and recommends Again. “Report a problem” records a local issue and allows an ungraded skip. A missing asset, invalid payload or playback-device failure never produces Again. Leaving before grading creates no completed review. After a crash, restart the card without claiming that the abandoned attempt succeeded.

An ungraded skip uses native bury-for-today to advance without a rating or review-log event, recording the reason separately. A confirmed defective item can instead receive a managed content_blocked suspension. Both paths must preserve the existing schedule and avoid repeatedly presenting the unavailable card during that session.

Native automatic question/answer advancement must be off during COMULS study so no timer reveals or grades on the learner's behalf. The desktop version adapter suspends auto-advance for the COMULS session and restores the previous session setting on exit, without changing unrelated deck presets. Guard re-enabling through shortcuts while a COMULS card is active. Supported mobile installation guidance and client tests must also establish manual reveal/rating; if the client cannot enforce it, state the required native setting explicitly.

Custom submission captures the attempt before requesting native reveal. Native Show Answer, keyboard or platform reveal without a captured response remains a valid self-grading route: show the reference answer and mark comparison coverage unknown. Do not invent a blank-response failure. Every reveal path invalidates the front interaction once; delayed callbacks cannot create a second submission.

The desktop skip action uses the supported native scheduling bury operation and lets Anki refresh its queue. Calling nextCard repeatedly is not a skip implementation. On mobile/web, offer instructions for the client's native bury or exit action; a portable template cannot promise unsupported programmatic scheduling.

12 — Exact contracts for the thirteen exercises

All recipes inherit the shared state machine, prerequisite checks and grading contract. Familiarisation, hints, transcript repair and replay are stages within these recipes, not additional exercise categories.

| Type | Front and response | Back and assessment |
|---|---|---|
| meaning_recall | Written French word/chunk with a concise sense cue; retrieve one specific meaning mentally, then reveal | Definition in the parent’s assigned language, meaning units and one usage cue; self-grade intended meaning |
| french_form_recall | Precise meaning/situation and necessary register/form constraint; type a word or short phrase | Canonical form and accepted alternatives; assess lexical choice and specified orthography |
| vocabulary_cloze | One blank in a short understood sentence; add a meaning cue if several natural completions fit | Completed sentence, intended sense and permitted alternatives; assess the missing target only |
| grammar_cloze | One gap testing a named or contextually clear grammatical distinction | Completed sentence and short explanation of the target form/function; retain exact agreement requirements |
| grammar_meaning_choice | A short written sentence with concise interpretations or situations | Correct interpretation and the grammatical reason the nearest distractor differs |
| sentence_transformation | One short understood source sentence and one explicit transformation | Accepted transformed sentences, changes highlighted in text, meaning-preservation check; uncertain alternatives allow self-comparison |
| sound_discrimination | One audio stimulus with two familiar phonetic/word labels | Correct label, contrasting audio and concise phonetic cue; assess the audible contrast |
| connected_word_recognition | Natural connected utterance; select the heard familiar word/chunk from a small set | Locate the target in the utterance, replay its surrounding chunk and explain the relevant liaison/elision/reduction |
| sentence_reconstruction | Hear a short sentence; arrange word/chunk tiles using click, tap or keyboard | Correct and attempted sequences, mismatch locations, transcript and replay |
| partial_dictation | Audio with one word/chunk removed from the visible transcript; type the missing span | Restored span and separate decoding/spelling diagnostics |
| sentence_transcription | Short audio with transcript hidden; type the entire sentence | Full reference transcript, sequence and spelling comparison, targeted replay |
| audio_transcript_choice | Audio and concise alternative written transcriptions | Exact matching wording and the audible difference from the nearest distractor |
| audio_meaning_choice | Audio and short meanings, pictures or actions | Correct meaning, the supporting part of the audio, optional transcript after responding |

Choice cards use two alternatives for a sound contrast and normally three for other selection tasks. Four is permitted only when all distractors are useful and familiar. These are authoring defaults, not scientific optima. Distractor length and complexity should be comparable to the answer. Each option has a stable ID independent of display position.

Option shuffling is enabled by default on each presentation using a stored render seed. Correctness follows option ID, not position. The seed is logged for reproducibility. Option shuffling does not change the exercise identity because the target and distractor set remain fixed.

Reconstruction tokens have stable token IDs and surface forms; repeated words are separate occurrences. Evaluate the resulting surface sequence and accepted token equivalences so swapping indistinguishable repeated tokens does not create a false failure. Provide undo and reset. The correct result must depend on the recording rather than grammatical plausibility alone.

Desktop reconstruction reveals tiles after the first playback, with an explicit “Show support” alternative. Both are supported practice. A later transcription card assesses independent recovery. Do not count tile-assisted reconstruction as independent spelling.

Meaning recall does not demand every dictionary sense. French-form recall must narrow a cue enough to distinguish synonyms or accept legitimate alternatives. A bare “bank” cue, for example, is insufficient to identify a particular French sense and construction.

A cloze such as “Je prends le ___ demain” is ambiguous without a cue or accepted set: train, bus and other options may fit. Narrow it to the intended vehicle or change the context. A controlled transformation specifies tense, person/number, register and intended meaning where those affect the answer.

Acoustic distractors must remain distinguishable under the accepted pronunciation set. “Il mange” and “ils mangent” cannot be used as a hearing distinction when the utterance offers no audible disambiguation. Written grammar-meaning cards may legitimately test that written distinction.

Compiler length defaults: one sentence; 3–10 written words for early carriers, at most 14 for ordinary sentence tasks; primary audio at most 8 seconds. Exceptions require an explicit recipe waiver with a reason and load check. These limits are starting engineering settings. Syntactic density, unknown dependencies and memory demand can disqualify a shorter item.

An exercise receives no implicit claim of transfer to every other recipe. Audio-meaning choice establishes meaning recognition in that task, not exact word segmentation. A sound contrast establishes perception of that contrast, not vocabulary meaning or speech production.

Auditory choice defaults: familiar short response labels appear before playback; the user can read them, then start audio. Autoplay is initially off for sound, connected-word, transcript and meaning choice. Transcription and partial dictation default to one autoplay when enabled in Settings, with unlimited manual ordinary replay. Reconstruction plays before revealing tiles; its no-autoplay mode has the same sequence behind a Play button. Optional audio on backs always requires an explicit play action. No answer is committed when playback ends.

Reconstruction authoring includes a no-audio check. If grammar and tiles alone make the target sequence uniquely obvious, redesign with another plausible sequence or a familiar, acoustically relevant alternative. This check reduces an avoidable shortcut; it cannot prove that listening is the only possible way to guess the answer. Keep the activity labelled supported sequence recovery.

13 — Listening preparation and media production

Connected-speech teaching follows a bounded sequence: attempt → identify the difficult stretch → hear it with an aligned transcript and meaning → hide the text → replay the natural whole utterance. A later new utterance or speaker checks transfer. The system teaches lexical segmentation without implying that words are separated by acoustic silence or requiring literal visual imagery of text.

Preteach unknown meanings and written forms before above-level listening retrieval. Full transcription remains a short independent task. Partial dictation and connected-word recognition isolate difficulty when full transcription combines too many demands.

Generate a whole utterance in natural connected speech. Derive replay chunks from that same recording with enough surrounding sound to preserve onsets and coarticulation. Do not concatenate isolated word recordings to simulate a natural sentence. If alignment cannot yield a safe boundary, replay a larger chunk.

Each audio record includes audio_id, source utterance ID/hash, exact generated-byte hash, provider/model/voice settings, locale, pronunciation overrides, normalized spoken text, duration, sample format, rights and alignment diagnostics. Store the exact bytes. A provider seed alone does not guarantee reproducibility [R18].

Use provider adapters behind a fixed render(request) contract. Local or cloud synthesis is a build-time choice with explicit credentials and cost limits. The runtime uses bundled media only. Select a broadly intelligible French variety for core material, and label alternative varieties instead of treating a valid regional realization as an error.

Alignment can use provider timestamps or a forced aligner. Convert normalized/provider character offsets to the canonical text explicitly. Forced alignment supplies timing; it does not certify pronunciation quality. The French MFA model documentation explicitly excludes using it as a pronunciation-quality assessor [R19].

Automated media checks verify decoding, truncation, clipping, silence proportion, duration, text/audio agreement and monotonic alignment. Sound-discrimination and liaison targets need independent phonetic checks of the actual signal; ASR returning the expected text alone is insufficient. Uncertain audio remains quarantined.

The default normal-speed file is always available. An optional slower support file uses pitch-preserving processing and separate validation. Normal speech remains the later assessment condition. Chunk and slow support are labelled; they never silently replace the reference utterance.

Portable audio uses Anki collection media and native sound references. Keep primary playback, alternative clips and bundled assets explicitly referenced so media checks can find them. The primary front may autoplay once; alternative clips must not all autoplay on reveal. The desktop playback adapter and every supported mobile template must pass this test before release.

If media sync has not completed, show “Audio is still unavailable” with retry and skip. Collection-sync completion does not guarantee media-sync completion. Do not reveal a transcript and mark the listening task completed merely to work around a missing file.

Primary autoplay has one owner, native Anki playback or the validated client template runtime, never both. MediaRefs supports discovery but is not rendered as a hidden sound-tag list. CSS hiding does not prevent native sound tags from being parsed or played. Only the intended primary recording is eligible for front autoplay; chunk/support clips require explicit playback.

14 — Implementation architecture and contracts

Use Python for the offline compiler and desktop add-on, with a small TypeScript codebase compiled to self-contained template JavaScript. Keep the language-data model independent of Anki. A course pack is a declarative archive with a manifest, normalized catalog, compiled exercise records and local media. It contains no executable Python, arbitrary template code or credentials.

The compiler produces an immutable catalog.sqlite for indexed content lookup. This file contains course data only, not authoritative learner progress. It is safe to replace after an update. Use explicit schema_version and compiler_version, foreign keys, migration scripts and reproducible validation reports.

| Catalog entity | Primary key and required relationships | Purpose |
|---|---|---|
| source_file | source_file_id; name, byte count, SHA-256, source location, retrieved time | Establish which actual input bytes were processed |
| parent | entry_id; vocabulary, source introduction band, assigned definition language | Preserve lexical-family identity and source quotas |
| sense | sense_id → parent; definition, languages, POS, gender, usage, source assessment status | Preserve the exact selected meaning |
| realization | realization_id → sense; written form, morphology, construction constraints, status | Distinguish a taught form from a historical alias |
| construction | construction_id; pattern, meaning, assessed stage | Identify grammatical requirements independently of words |
| relation | relation_id; typed endpoints and original source payload | Preserve expression and property/action relationships |
| context | context_id; immutable text, target span, sense/form/construction references | Define an unambiguous short retrieval setting |
| dependency | owner identity → required identity; modality and evidence requirement | Build explicit prerequisite closure |
| exercise | exercise_id; type, objective, context, answers, prerequisites, load and stage | One scheduled retrieval task |
| media | media_id; content hash, local filename, transcript, alignment, rights and QA | Reproduce approved listening material |
| provenance | evidence_id; source fields, URL/date, claim and qualification | Retain traceability without cluttering study cards |
| validation_issue | issue_id; severity, code, entity, field and resolution | Make quarantine actionable |

Preserve source JSON as structured data alongside normalized claims. Distinguish absent, unknown, explicitly false and not applicable. SQL NULL is not permission to invent a value. Every normalized claim points to source evidence or a separately attributed editorial decision.

Identifiers use namespaced stable hashes of canonical UTF-8 input, with SHA-256 collision checks. Preserve source entry_id and sense_id exactly. A realization identity derives from the sense, normalized form and construction, not a row number. An exercise identity derives from its semantic retrieval contract: target identities, exercise type, fixed context, objective, response constraints and material answer requirements. Formatting-only content revisions increment content_revision without changing exercise_id.

Illustrative contract, showing relationships rather than pretending this example is an approved card:

```json
{
  "schema_version": 1,
  "exercise_id": "ex_<semantic-contract-sha256>",
  "content_revision": 1,
  "exercise_type": "meaning_recall",
  "target": {
    "entry_id": "definition_support_4834632f8ef36765",
    "sense_id": "sense_e0ec26a0-5b18-5457-b526-4f6bd5c18dc2",
    "realization_id": null,
    "construction_id": null,
    "primary_objective": "written_form_to_meaning"
  },
  "prompt": {"text": "un récipient", "language": "fr"},
  "answer": {
    "mode": "self_compare",
    "reference": "a container used to hold something",
    "language": "en",
    "accepted_variants": [],
    "normalization_policy": "meaning_self_compare_v1"
  },
  "assignment": {
    "source_local_intro_stage": "B1",
    "assessed_task_stage": null,
    "assessment_status": "pending"
  },
  "prerequisites": [],
  "exposure_group_ids": ["meaning:<sense_id>:fr-en"],
  "media_ids": [],
  "qa": {"compiled_card_ready": false}
}
```

The abbreviated example omits provenance, complete QA and load fields; it is not importable production output. The schema requires these fields in production. Null task assessment blocks admission. English output in the example is an illustrative editorial rendering, not a claim that this wording appears verbatim in the CSV.

ExerciseSchema also requires: instruction_key; input language; carrier identities; context_id where contextual; assessed target/carrier/construction stage ceilings; visible-language dependency closure; response constraints; evaluation dimensions; explanation; target-revealing support policy; input-character limit; media requirements; load class; estimated time prior; source attribution; creation/review dates; reviewer decisions; and supersession links. A context-free vocabulary card may legitimately have context_id=null.

Use a registry rather than thirteen separate note types. Each registry entry supplies its schema validator, eligibility rule, renderer, evaluator, audio policy, load prior and prerequisite modalities. The shared renderer dispatches only on the thirteen allowlisted IDs. Unknown types fail closed with a recoverable content notice.

Module boundaries:

- ingest: CSV parsing, byte receipts, schema adapters, provenance preservation;

- lexicon: normalized parents, senses, forms, constructions and relations;

- dependencies: exact prerequisite graph and cycle detection;

- authoring: context, question, answer and audio candidate production;

- compile: validated ExerciseSchema records, catalog and pack;

- addon/content: pack installation, catalog queries and update previews;

- addon/admission: eligibility, budget estimates and candidate selection;

- addon/anki_adapter: all native collection and scheduler operations;

- addon/progress: evidence derivation and conservative cache rebuilding;

- addon/ui: Home, Levels, Library, Settings and content management;

- templates: four response shells, thirteen renderers and evaluators;

- qa: deterministic fixtures, client integration checks and source reports.

Keep curriculum policy in versioned data, not scattered conditionals. Changing a ceiling, definition prerequisite band or default timing estimate should generate a policy diff and admission forecast before applying.

15 — Native Anki storage and card lifecycle

The add-on manages one ordinary note type named COMULS Exercise v1 and one template named Exercise. This creates exactly one native card per exercise note. Vocabulary and grammar cloze use this ordinary template and explicit answer spans; do not use Anki's built-in Cloze note type or its c1/c2 card-generation rules.

| Note field | Ownership and function |
|---|---|
| COMULS_ID | First field; immutable exercise_id; used for deduplication and reconciliation |
| ExerciseType | Compiler-owned allowlisted exercise type |
| ContentRevision | Compiler-owned version of this same retrieval contract |
| PackID | Compiler-owned course pack identity |
| ParentIDs | Compiler-owned JSON array of source parent identities |
| SenseIDs | Compiler-owned JSON array of source sense identities |
| Payload | Compiler-owned escaped, versioned JSON with the complete portable exercise |
| QuestionHTML | Compiler-owned safe static front fallback |
| AnswerHTML | Compiler-owned safe static back fallback |
| MediaRefs | Compiler-owned native sound/image references so media checking can discover assets |
| LearnerState | Add-on-owned small versioned JSON for durable exercise-level state |
| PersonalNotes | User-owned text; never replaced by a course update |

Use native note GUIDs as Anki's persistent note identity and COMULS_ID as the course identity. Preserve both on updates. Numeric note/card IDs identify local native records; never encode them into a distributable course pack or use them as cross-profile course keys. Maintain an indexed lookup from COMULS_ID to the actual note ID after reconciliation.

Content fields are managed by COMULS. If a user edits them through Anki, the next update shows a conflict with keep-local, restore-course or duplicate-for-personal-use actions. PersonalNotes and unrelated user tags always survive. Internal tags use a comuls:: namespace and are diagnostic; do not make a tag the only copy of essential state.

LearnerState contains only necessary state: schema version, familiarisation evidence, learner declarations, managed pause reason, retirement/supersession links and conservative answer-exposure markers where available. It must not contain an ever-growing event log. Detailed events belong in a local disposable cache. Include a bounded summary sufficient to avoid incorrectly claiming independence after a known answer exposure.

Create a top-level COMULS deck and one managed child deck, COMULS::Practice. Use the parent as the ordinary study entry. Do not create a deck for every CEFR stage, sense or exercise type. Those are searchable properties and eligibility constraints. Store the created deck identity; respect later user renames and moves. If the user deletes the managed deck, offer reconciliation and show where existing cards actually reside before creating a replacement.

Use ordinary native new/review limits, learning steps and review order. The add-on may recommend settings after inspecting the user's existing configuration, but never silently enable FSRS collection-wide or change another deck's preset. A dedicated COMULS preset can isolate supported deck options; FSRS enablement itself is collection-wide. If FSRS is disabled, core admission and cards still work with the current native scheduler.

Native operations for the pinned desktop target:

- col.new_note(note_type) and col.add_note(note, deck_id), or supported add_notes requests, create notes and native cards.

- col.get_note and col.update_note/update_notes change fields while preserving note identity and native review history.

- col.card_ids_of_note resolves the generated card; col.set_deck moves cards only for an explicit course-management action.

- col.sched.suspend_cards and unsuspend_cards implement managed pauses; native bury operations provide short-lived review exclusion.

- col.media.add_file/write_data installs media and returns the actual stored filename. Use that returned filename in fields.

- col.set_config with undoable=True stores small namespaced course settings.

- col.add_custom_undo_entry and merge_undo_entries group related native mutations where supported.

Use the supported CollectionOp/QueryOp model. Database work runs through Anki's collection operation machinery; Qt rendering stays on the main thread. Never write directly to collection tables, call deprecated note/card flush methods, fabricate revlog rows or edit due/interval/stability values to express a curriculum decision.

Suspension ownership requires care. COMULS records why it paused a card and only automatically reverses a pause it can attribute to itself. If native state changes outside COMULS or ownership is uncertain, preserve the pause and show a reconciliation choice. Native suspension does not preserve a stack of separate user and add-on reasons; do not pretend it does.

Cross-note exposure protection is distinct from Anki's sibling burying. One note per exercise means native sibling burying alone cannot hide a reverse-direction or near-identical exercise on another note. On desktop, known answer-revealing exposure can temporarily bury explicitly linked exposure-group cards for the remainder of the current Anki study day. Mere shared parent identity is insufficient: different senses need not leak each other's answers. Respect user/native burial and do not automatically unbury unrelated cards.

Before every managed operation, resolve filtered-deck status using the original deck where applicable. Do not strand cards in a filtered deck or change their original home as a side effect. If the safe operation is not supported in that state, defer the managed change with a clear reason while ordinary review remains available.

Deleting an exercise is not an update strategy. Removed or defective content is marked retired/content_blocked, and suspended with an explicit managed reason when necessary. Keep the note, review history and replacement link. Permanent deletion requires an explicit user action through normal Anki controls.

An undoable command must restore the associated note/config changes and invalidate derived caches. Media-file creation and external catalog replacement are not made atomic merely by grouping Anki undo entries. Installation therefore stages content, records a recoverable operation manifest, commits native changes and only then marks the pack active. Recovery reconciles by immutable exercise identity rather than creating duplicate notes.

Native add_note is not the COMULS uniqueness constraint. Reconcile COMULS_ID across managed notes before creation and quarantine duplicate identities. Native sync does not merge separately created notes just because first fields match. A user-created personal duplicate receives a new native GUID and leaves the managed COMULS identity namespace; never silently merge histories.

For a standalone management command, create a custom undo entry, perform supported note/config/card mutations inside one serialized collection operation, and merge into that entry. Prevent unrelated mutations from interleaving. When extending a native operation, preserve its undo identity and label. Optional post-grade telemetry creates no extra native undo step. Keep immutable pack versions while active or referenced by recoverable operations so undo cannot point to a deleted catalog.

16 — Reviewer integration, mobile and synchronization

Portable card fields contain everything required to render the prompt, correct answer, explanation and media references. The front/back template never needs the desktop Python catalog to reveal an answer. Use namespaced CSS, no remote fonts or scripts, and a static semantic fallback. Both front and back initialize independently.

JSON embedded in HTML must be escaped for its exact context, including less-than characters that could terminate a script element. Prefer a non-executable payload element read by a bundled parser. Render source strings as text, not trusted HTML. Compile any permitted rich text through a strict sanitizer. Do not place source text into JavaScript code.

The desktop webview bridge accepts only allowlisted event types with a render nonce, native card ID, exercise ID and bounded payload. Validate profile, reviewer context and current card before acting. A stale, duplicated, preview-originated or malformed message has no scheduling effect. The bridge does not accept arbitrary commands, Python expressions, filesystem paths or SQL.

Connect the pinned Anki hooks through one adapter:

- card_will_show and webview_will_set_content add or prepare safe presentation assets;

- webview_did_receive_js_message handles only the COMULS message namespace, preserving the incoming handler result for unrelated messages;

- reviewer_did_show_question and reviewer_did_show_answer establish render state and feedback;

- reviewer_will_answer_card can guard a known invalid state, but cannot silently substitute a different rating;

- reviewer_did_answer_card observes the committed native event;

- collection-operation and undo notifications invalidate affected caches;

- sync completion triggers reconciliation, with collection and media completion treated separately.

The exact event signatures belong in the version adapter and compatibility tests. Do not assume a hook name alone guarantees identical signatures across versions. Preview and browser renders may display and evaluate a card locally, but they cannot create a native successful review.

The learner's native rating remains authoritative for scheduling. A correctness recommendation and a native grade are separate events. Immediately after a native answer, update conservative derived evidence. A failure to record optional telemetry must never roll back or duplicate a successful native scheduling operation.

| Capability | Desktop with add-on | Synced mobile / web client |
|---|---|---|
| Native spaced review and ratings | Supported | Native client function |
| Portable prompt/back and local audio | Supported | Required for clients advertised as supported; test each |
| Choice/typing/tile enhancement | Supported | Capability-tested; static response/self-comparison fallback |
| Select stage, compile prerequisites, admit new notes | Supported on designated manager | Requires designated desktop in v1 |
| Detailed replay/help timing | Available locally | Not assumed available or synced |
| Cross-note answer-exposure burying | Add-on-managed | Not guaranteed |
| Adaptive daily time admission | Available at desktop admission | No promise of live budget enforcement |
| Update packs and diagnose source conflicts | Supported | Synced results only |
| Independently verified assistance-free mastery | Where evidence is complete | Self-reported/native recall evidence only |

AnkiDroid and AnkiMobile support is a release gate, not an assertion that untested templates already work. Record the exact tested app versions in each pack/add-on release. AnkiWeb receives a static readable fallback; advanced interaction is optional until verified. If a mobile interaction is unavailable, show an instruction to answer mentally or externally and compare on the back, with the same primary objective. Never show a dead input or misleading automatic score.

Before mobile study, use native sync and confirm required media is present. After study, sync before making course changes on the manager. Collection sync completion does not prove every audio file has arrived. A missing audio file offers retry/device setup and an ungraded skip. It does not count as failed listening.

One designated desktop writes course-level admission policy in v1. A second desktop opens management read-only until the learner explicitly transfers the manager role after synchronization. This is a product safeguard, not a guarantee against all offline native conflicts. Review on multiple clients remains subject to Anki's normal sync behaviour. If simultaneous edits conflict, preserve native state and ask the user to choose between concrete versions; never overwrite an entire collection automatically.

No canonical learner state lives in browser localStorage or an unsynced SQLite sidecar. LocalStorage may carry a transient front-to-back response when the client permits it, with card/render keys and expiry, but the back must work without it. Losing it removes the automatic comparison for that attempt, not the correct answer or review history.

At startup, verify supported Anki version, note schema, template asset version and active pack manifest. If incompatible, disable management operations and show the reason; ordinary portable reviews remain available wherever the template is compatible. Add-on removal leaves notes, media and native schedules intact. A clean reinstall rebuilds indexes from note fields and the installed pack.

Exposure handling has a serialized reviewer barrier. Collect exposure facts immediately. Complete any required cross-note burial before enabling the rating action, using a CollectionOp with initiator=reviewer and excluding the active card. Validate the render nonce before re-enabling controls. Note-state persistence and burial must not redraw, replace or advance the current question/feedback. Do not launch required burial asynchronously from reviewer_did_answer_card: native next-card advancement follows that hook synchronously. A burial failure offers Stop or explicit continuation labelled as unprotected exposure; such responses cannot establish verified independence. The reviewer still performs the eventual native rating.

The small synced course snapshot includes schema_version, manager_id, revision, previous_revision, selected_stage, recovery_mode, policy_version and updated_at. Native configuration sync supplies neither a COMULS compare-and-swap primitive nor a conflict-free replicated data structure. A bounded last-observed local snapshot can detect some conflicts; offline conflicts may be overwritten before detection. Manager transfer requires sync and explicit adoption of the resulting snapshot. Unknown/conflicting state disables management until reconciliation while native review remains available.

Daily time limits are advisory when native reviews lack matching desktop measurements. Native review-log timing is capped/coarse and is not a complete active-study-time measurement. Display measurement coverage and unknown work; never describe desktop-only minutes as the learner's entire daily workload.

17 — Pack production, updates and operational safeguards

Run content production outside the learner's review session. The pipeline is:

1. Receive source bytes, hash them and preserve immutable originals.

2. Parse every CSV and nested JSON field; normalize into catalog entities without dropping provenance.

3. Reconcile parent and sense exports; validate identities, declared counts, language quotas and cross-file references.

4. Resolve exact prerequisites and detect missing nodes or cycles.

5. Generate or author short candidate contexts and answer contracts.

6. Assess task, carrier and construction levels separately.

7. Review semantic accuracy, answer uniqueness and load limits.

8. Produce and review audio; validate alignment and required media.

9. Compile portable exercises, safe render fields and catalog indexes.

10. Emit an immutable pack, validation report, checksums, provenance/license ledger and release manifest.

A model may draft sentences, cloze distractors, explanations and provisional level labels. Its output is a candidate. Structural validation cannot establish linguistic correctness. Release must pass a documented autonomous QA process: compare exact sense/construction claims with attributed dictionary and grammar evidence; check natural usage against an authorized corpus or independently sourced examples; generate plausible alternative answers and adversarial counterexamples; evaluate them independently of the generator; and run deterministic grammar, normalization and acoustic fixtures. Independent model agreement alone is insufficient evidence. Unresolved sense, idiomaticity, level, answer-ambiguity or audio issues remain quarantined. Human French/phonetic review is an optional additional check, not a production dependency. Record every automated or human assessor, source, method/version, decision and content hash. These checks control release uncertainty; they do not certify infallible linguistic judgment.

The pack manifest records pack_id, semantic version, schema/compiler/policy versions, source hashes, supported renderer versions, catalog and media hashes, exercise counts by readiness/stage/type, rights status, QA report hash, supersessions and minimum compatible desktop version. A checksum detects corruption; it does not authenticate the publisher. Public distribution requires signed manifests with a pinned publisher key or an equally explicit trusted distribution channel. A private local development pack can be marked unverified and must never execute code.

Use content-addressed audio filenames with a COMULS prefix. Updating a recording writes a new asset and updates only approved compatible content references. Never overwrite a shared media file with different bytes. Keep old referenced files available for history and rollback; let native media checking identify genuinely unused files. Do not delete unrelated user media.

A pack update first runs a dry comparison: added exercises, compatible revisions, materially changed contracts, retired content, conflicts, new prerequisites, changed stage assignments and required media size. Apply compatible revisions to the same native notes. Material changes create replacement exercises with new identities. The old exercise retains its history and can be retired after replacement introduction according to explicit policy.

Idempotence is mandatory. Installing the same pack twice creates zero additional notes, preserves user fields and does not reschedule cards. Interrupted installations resume by manifest and COMULS_ID. A partially copied media directory never produces an “installed successfully” status. Mark the new pack active only after checksum and native reconciliation complete.

Input safeguards include bounded field/JSON size, normalized relative archive paths, rejection of traversal and absolute paths, archive expansion limits, no executable archive payloads, strict JSON schemas and HTML sanitization. Use source URLs as attribution, never as code or an instruction channel.

Keep API keys outside packs, notes and logs. Runtime study is offline. Content production can use external providers only with deliberate configuration and a visible cost estimate. Store provider/model/voice/version parameters and the actual approved output; a seed alone is not proof that speech synthesis is reproducible.

Dictionary attribution does not by itself establish redistribution permission. Track terms for definitions, examples, recordings and voices in the rights ledger. Prefer reviewed paraphrases and original examples where permitted; retain evidence without assuming that all copied dictionary material is publishable. Distribute only content whose rights status has been resolved for the intended audience.

The repository's standing CSV publication workflow calls for completed vocabulary outputs to be stored in both Google Drive and GitHub. This document does not edit those CSVs. Future vocabulary changes should publish the validated complete outputs and their hash/validation manifest to both destinations, preserving the source receipt and reviewable diff.

Local reports contain exercise IDs, error category and optional user text. Do not send study answers or issue reports to a server by default. Provide an explicit export/share action with a readable preview. Crash logs exclude private notes, full answer text and credentials unless deliberately included by the user.

Track operational metrics without turning fast responding into the learning goal: native completed reviews, active study time with measurement coverage, delayed unaided recall where observable, repair frequency, answer ambiguity reports, missing-media incidents, and new-card admission accuracy. Report review latency separately by type; a forty-second transformation is not a failed eight-second vocabulary card.

Package executable runtime code separately as an .ankiaddon, with __init__.py at the archive root and the distribution manifest identifying package and name. Course packs remain declarative. Keep installed course data in Anki's designated persistent add-on user-data area or another documented profile-specific location preserved by updates, with recovery receipts. Compatibility tests include payload versions already present in notes, not only newly compiled cards.

18 — Deterministic admission and evidence rules

Implement eligibility and selection as pure functions over a versioned catalog, learner snapshot and policy. They return a decision and reason codes, not direct database mutations. The Anki adapter applies an approved admission batch.

Use these evidence levels for each exact sense, realization or construction and required modality:

- unknown: no relevant exposure or evidence;

- familiarised: the learner has completed a clear explanation/example of this exact use;

- understood: one successful genuine retrieval for the required objective, or an explicit declaration for a permitted comprehension prerequisite;

- stable: the spaced, unaided criterion in section 8 is met;

- repair_needed: recent evidence or learner help request identifies a weakness.

These are evidence summaries, not independent scheduling queues. A successful reading meaning card cannot supply listening segmentation evidence. A learner declaration is distinguishable from observed retrieval. There is no universal forgetting time inferred from CEFR level. Native scheduling history remains intact even when a readiness summary becomes uncertain.

First acquisition is exempt from requiring prior retrieval of its own target. It requires comprehensible instructions and support. Materialize a small COMULS-paused preparation note before its familiarisation panel is shown; persist the completed exposure there, then activate it only after all remaining gates pass. A short familiarisation panel presents the target's exact form, meaning and necessary construction before the first retrieval. Mark it familiarised, not understood or stable. Never require a learner to pass a scheduled card that cannot yet be admitted in order to admit that same card.

For admission, require understood evidence for every indispensable carrier dependency. Require familiarised evidence for the new primary target. Demanding contextual synthesis additionally requires understood evidence for the target components it combines. Answer-revealing familiarisation in the same episode makes the following response primed practice; it can be a genuine native first review, but it cannot satisfy the independent stable criterion.

The dependency graph can use alternative prerequisite paths. A comprehensible English acquisition representation is the terminal fallback for an unknown French defining word. French A requires B and B requires A must resolve to an approved English support path or remain blocked. Never break a cycle by asserting that one unknown node is known.

Default candidate ordering is deterministic:

1. Explicitly requested repair for a known weak prerequisite.

2. Prerequisites that unlock the learner's next current-stage target.

3. Eligible current-stage acquisition ordered by source introduction order where present, then reviewed pedagogical priority.

4. Supported above-stage listening previews within their exercise ceilings.
Within equal priorities, prefer the least represented required objective in the last completed admission batches, then lower predicted incremental workload, then stable exercise_id. This balances admission; it does not reorder native due reviews.

Above-stage previews are capped at one new knowledge unit within the default six-unit daily cap until pilot evidence justifies another default. Any support needed for that preview consumes the same knowledge-unit and time budgets; never hide six prerequisite acquisitions under one nominal preview. A unit is counted once when first familiarised, including a prerequisite. Activating a new representation of an already introduced unit consumes card/time allowance but does not count as a new semantic unit.

Compute remaining_time = chosen_daily_budget − measured_active_time − estimated_remaining_due_time. If it is nonpositive, admit no default new work. A candidate batch must fit its initial familiarisation/review estimates plus an explicit relearning allowance. Start with one extra predicted attempt for each new card; this is a conservative forecast assumption to calibrate. Stop before exceeding the smaller of remaining time, unit cap and the hard new-card cap.

Set the initial hard cap to eight newly activated cards per Anki day, including complementary representations of old units, in addition to the six new-knowledge-unit cap. Without a card cap, “only six units” could still introduce dozens of cards. Both settings are visible and adjustable. Cards materialized only as paused declarations do not enter this active-card cap until activated.

Do not pre-create the whole catalog as tens of thousands of suspended notes. Keep unadmitted content in the pack catalog. Materialize only the small eligible batch needed for the next session, plus durable paused declaration records where necessary. A future-stage Library preview reads the catalog and leaves native learning state untouched.

Use the collection's native study-day rollover for counters and burial. Do not use local midnight or UTC midnight independently. Stage changes do not reset the daily cap. Track the admission batch and date in durable exercise fields so the designated desktop can rebuild counts. Time telemetry lost or unavailable from another client produces an incomplete estimate, disclosed in Home; it is not zero study time.

Minimum refusal codes: invalid_schema, unassessed_task, content_not_ready, unsupported_exercise, unavailable_band, ceiling_exceeded, missing_dependency, dependency_cycle, familiarisation_needed, disabled_capability, media_missing, budget_exhausted, unit_cap_reached, card_cap_reached, revealing_exposure, user_paused and incompatible_client. A candidate can report multiple reasons in authoring tools; learner UI shows the most actionable valid reason.

Native undo removes the undone review's achievement credit and invalidates derived progress. It cannot make the learner unsee an answer: preserve the factual answer-exposure marker. A reattempt following undo remains potentially primed. Group reversible native bookkeeping carefully, but never equate database rollback with a reversal of human exposure.

The repeated-failure detector excludes previews, ungraded diagnostics, content-problem skips and immediate correction attempts. Native Again events remain real reviews for scheduling. Distinguish “target not retrieved,” “carrier unknown,” “heard correctly but misspelled” and “ambiguous item” in repair suggestions; do not claim that native Again alone tells which problem occurred.

Dependency edges carry a role: trained_target, carrier, instruction or explanatory_support. The trained facet is not a prerequisite for itself. Carrier/instruction edges may require understanding; answer-side explanatory language may have an approved English support path. Merely appearing in the completed answer does not create a self-dependency.

Preparation is also bounded: prepare only the current admission batch, never the whole catalog. A prepared card remains suspended if the learner leaves familiarisation unfinished. Resume that same identity next time; do not create another note. Re-evaluate stage and prerequisite gates before activation. First familiarisation counts toward the daily knowledge-unit cap even if its scheduled card is activated later.

19 — Build sequence and concrete deliverables

Implement in vertical slices with explicit exit criteria. Complete the data audit and the native scheduling adapter before scaling authoring. The thirteen-type specification remains the product scope; sequencing development does not silently remove the harder exercises.

| Work package | Concrete deliverables | Exit criterion / dependency |
|---|---|---|
| P0 Source reconciliation | raw source receipt; schema adapters; inventory.json; import_audit.json; cross-view diff | Every current input parsed; counts/IDs reconciled or explicitly quarantined; no invented source mappings |
| P1 Domain and policy | typed schemas; catalog migrations; stage/definition policy; dependency graph; validation command | Deterministic import; exact-sense closure; cycle and quota tests pass |
| P2 Native Anki spine | note type; one-card template; Anki adapter; manifest installer; idempotent update/undo | Real sandbox profile demonstrates create, rate, sync, update, undo and reinstall without losing history |
| P3 First usable course slice | meaning recall, French-form recall, compact feedback; Home/Levels/Library; selective admission | Beginner recovery and experienced-learner declaration paths both function with approved content |
| P4 Listening foundation | sound discrimination, connected-word recognition, transcript/meaning choice; reviewed local audio | Connected-speech targets audible; missing-media paths harmless; native ratings remain authoritative |
| P5 Contextual tasks | vocabulary/grammar cloze, grammar-meaning choice, reconstruction, partial/full dictation, transformation | All thirteen registry contracts implemented; ambiguous answers and input edge cases covered |
| P6 Load and maintenance | time forecasts; repair suggestions; exposure groups; representation retirement; update/conflict manager | Stage changes and backlog handling preserve introduced reviews; no unbounded card multiplication |
| P7 Portable release | AnkiDroid/AnkiMobile test matrix; static web fallback; packaging and installation guide | Every advertised client passes offline review, sync, media and answer-side tests |
| P8 Evidence calibration | pilot protocol; delayed tests; fatigue/time dashboard; default-policy revision report | Defaults evaluated against learning and burden; claims remain within observed evidence |

Proposed repository additions, to be created during implementation:

- schemas/: source adapters, ExerciseSchema, CoursePackManifest and LearnerState schemas.

- comuls_core/: lexicon, dependencies, validation, eligibility and workload functions.

- compiler/: ingest, authoring adapters, media adapters and pack build commands.

- addon/: metadata, native adapter, profile lifecycle, management screens and reviewer bridge.

- templates/: source styles and four interaction shells, compiled into bundled media.

- data/policies/: stage ceilings, definition-language rules, grading/normalization policies.

- tests/fixtures/: minimal real-schema records and deliberately invalid/ambiguous cases.

- docs/: authoring, installation, migration, mobile support and troubleshooting.

- reports/: source audit summaries and reproducible release validation manifests.

Recommended command contracts are proposed implementation interfaces, not claims that these commands already exist:

```text
comuls ingest --manifest sources.json --out build/catalog.sqlite
comuls validate --catalog build/catalog.sqlite --require-gap-free
comuls compile --catalog build/catalog.sqlite --policy data/policies/v1.json
comuls pack --compiled build/compiled --out dist/<pack-id>.comuls
comuls inspect-pack dist/<pack-id>.comuls
```

The ingest and validate commands are read-only with respect to source CSVs. Explicit export commands are responsible for new source versions. Production compiles fail on blocking errors; an authoring preview command can display quarantined candidates without making a releasable pack.

Start with a complete pilot bundle of 130 approved exercise instances: ten per type, distributed across distinct targets and the available assessed stages. This is a coverage fixture and usability pilot, not enough to claim a finished course. Include at least two approved baseline/recovery paths, a French-definition prerequisite path, a multiple-sense family and a property/adjective realization case. Avoid assigning every type to the same ten words.

Each pilot exercise must have a primary objective, exact target identities, reviewed answer contract, carrier dependencies, stage assignment, exposure links and content provenance. Listening exercises additionally require approved audio/alignment and rights status. The autonomous linguistic/audio QA gates and a tested native review path are required even if a template renders beautifully. Optional human review can strengthen them.

Deliver the add-on as a versioned installable package and the course as a separate versioned pack. Include an offline installation guide, sample course, tested-client matrix, release notes, recovery procedure and validation report. A portable .apkg export may be offered for already admitted exercises; it cannot replace the desktop course manager or promise dynamic prerequisite gates.

Performance budgets are engineering targets to verify on a declared reference machine: no network operation in study; cached local card rendering under 150 ms at the 95th percentile excluding media-device startup; Home indexed queries under one second; no collection-blocking full-corpus scan during review. Large import/build work runs outside the reviewer with progress and cancellation checkpoints. Publish measured results, not assumed compliance.

No precise delivery date is claimed without implementing and timing the data/content work. The work packages identify the critical path: source reconciliation → safe native spine → approved exercise bundle → complete interaction set → client/recovery verification. Engineering can start immediately from P0–P2 while linguistic authoring proceeds against frozen schemas.

20 — Acceptance tests and release gates

Use unit/property tests for parsers, identity, eligibility and normalization; integration tests against a disposable real Anki profile for scheduling and updates; manual client checks for audio, keyboard, accessibility and sync. Mocking Anki's scheduler is insufficient evidence that review history survives an update.

| ID | Scenario | Required result |
|---|---|---|
| D01 | CSV contains quoted newlines, commas, BOM and JSON | Correct row/field boundaries; stable raw-byte hash |
| D02 | card_ready contains false as a string | Boolean false; no accidental admission |
| D03 | Duplicate sense ID has conflicting meaning | Quarantined conflict with both receipts |
| D04 | Parent and flattened sense views disagree | Release report identifies exact IDs/fields; no silent winner |
| D05 | Historical alias has different POS/construction | Preserved as evidence; not automatically accepted as the target form |
| D06 | Local support B1 band appears | Preserved as local introduction policy, not published CEFR proof |
| D07 | Missing or cyclic French definition dependency | Approved English bridge or blocked item; no fabricated knowledge |
| D08 | Existing parent definition assignment plus new release | Old assignment unchanged; new-parent quota deterministic |
| C01 | B1 learner has A2 grammar weakness | Appropriate A2 repair remains available; whole course not silently demoted |
| C02 | Cloze target/carrier equals selected X | New admission refused under strict-below-X rule |
| C03 | Transcription exceeds X+½ or choice exceeds X+1 | New admission refused even if source family band is lower |
| C04 | First acquisition has unknown target | Comprehensible familiarisation works without a self-prerequisite cycle |
| C05 | Same parent, unfamiliar second sense | First-sense success does not mark second sense known |
| C06 | Stage raised/lowered | Eligibility changes; reviewed cards preserve history; only eligible unreviewed admission states change |
| C07 | C2 selected but pack has no C2 content | Honest coverage notice; existing reviews remain available |
| C08 | Six units would create too many representations | Eight-active-new-card cap and time estimate both apply |
| C09 | Native day rolls over or timezone changes | Counts use native study day; stage changes cannot reset cap |
| E01 | Correct accented and typographic variants | Declared normalization passes; meaningful accents/morphology retained |
| E02 | Valid but unlisted transformation | Uncertainty/self-comparison route; reportable content issue |
| E03 | Acoustically identical distractors | Content rejected before release |
| E04 | Repeated identical reconstruction tokens | Surface-equivalent sequence accepted |
| E05 | Replay without answer help | No automatic Again; support history recorded where available |
| E06 | Target hint before response | Grade recommendation Again; independent mastery excluded |
| E07 | Carrier gloss without target leakage | Primary retrieval can be correct; carrier weakness remains visible |
| E08 | Double Enter, stale callback, repeated click | At most one native grade for the current card |
| E09 | Back opened without front-side state | Correct answer and rating interface still usable |
| E10 | Leaving before grade | No fabricated successful review |
| A01 | Install identical pack twice | No duplicate notes/cards or scheduling changes |
| A02 | Compatible content update after several reviews | Same note/card identity, due state and review history preserved |
| A03 | Materially changed retrieval contract | New exercise identity; old record preserved with replacement link |
| A04 | Update collides with user content edit | Visible conflict; PersonalNotes and unrelated tags survive |
| A05 | Grade then native undo | Native schedule restored; achievement credit recomputed; factual exposure retained |
| A06 | Add-on operation interrupted during media install | Recoverable manifest; no false success or duplicate creation |
| A07 | User suspension overlaps managed pause | User intent preserved; ambiguous ownership not auto-unsuspended |
| A08 | Managed deck renamed, moved or filtered | Stable identity resolved; no accidental move or original-deck corruption |
| A09 | Add-on removed and reinstalled | Portable cards still review; indexes rebuild without losing progress |
| A10 | FSRS disabled or shared preset used | No silent collection-wide scheduler change |
| A11 | Exposure note write/bury while feedback open | Active card/attempt preserved; required burial finishes before rating and next-card fetch |
| A12 | Native auto-advance enabled or shortcut pressed | No timer-driven reveal or grade during COMULS study |
| A13 | Native reveal bypasses custom submit | Back works; unknown comparison coverage; no fabricated failure |
| A14 | Ungraded native skip | Reviewer advances through supported bury/exit; no rating/revlog event |
| A15 | Duplicate managed COMULS_ID exists | Visible quarantine; no automatic history merge |
| M01 | Offline supported mobile review | Prompt, media, back and native rating work |
| M02 | Media sync incomplete or device playback fails | Retry/skip without Again |
| M03 | All optional audio references exist | Only intended primary clip autoplays; alternatives stay manual |
| M04 | Review on mobile then sync to manager | Native history retained; uncertain assistance evidence marked accordingly |
| M05 | Two desktops attempt course management | Designated-manager rule enforced; concrete conflict handling |
| M06 | Focus lost while audio plays | Audio and active timer pause together; Resume is explicit |
| M07 | Hidden media-reference field exists | Media discoverable without unintended multi-clip autoplay |
| U01 | Keyboard-only, IME and accent entry | No accidental submission/grading; visible focus; complete task possible |
| U02 | Dark theme, large text and narrow screen | No clipped answer/control; semantic correctness indicators |
| U03 | Screen-reader navigation | Task/input/playback/feedback/ratings meaningfully labelled |
| U04 | Demanding-card sequence and exhausted budget | Dismissible stopping point; new admission pauses; due dates unchanged |
| S01 | Malicious HTML/script in a source field | Displayed as safe content; no executable injection |
| S02 | Archive traversal or expanded-size attack | Rejected before extraction/installation |
| S03 | Stale or forged bridge message | No collection mutation |
| S04 | Private report export | User can inspect contents; no automatic external transmission |

Source release gate: raw-byte identity established; all released rows parsed; parent/sense reconciliation complete; required identities and dependencies resolved; source language quotas checked; unresolved data excluded visibly rather than counted as ready.

Content release gate: all released exercises have reviewed semantic targets, assessed task levels, valid answers and prerequisites; no ambiguous cloze/transformation/audio distinctions; audio and rights approved; source card_ready and compiled readiness remain distinct.

Engineering release gate: native lifecycle, undo, interruption recovery and idempotence tests pass on the pinned desktop version. Every advertised mobile client passes its portable review matrix. Every gating failure has a clear learner-facing state and no false learning grade.

Learning-quality release gate: initial pilot users can understand instructions, correct errors and complete short sessions without repetitive UI friction. Measure delayed retention and transfer to new utterances separately from same-card recognition. Pre-register the comparison and decision rules before using a pilot to claim an educational advantage.

The initial pilot should compare a simpler acquisition-plus-listening mix against the full eligible mix at matched active study time, counterbalancing targets and learner order where feasible. Evaluate delayed target recall, segmentation on new short recordings, grammar transfer on new sentences, error-correction time and brief self-reported effort/fatigue. A fast completion rate alone does not establish better learning. Do not set an arbitrary small pilot sample as sufficient for statistical efficacy claims.

Tune numerical defaults only after observing the trade-off among delayed learning, completion burden and return rate. Preserve policy versions so a change in exercise mixture, time estimates or ceilings can be distinguished from a change in the content itself.

21 — Research and implementation sources

References R01–R17 support the learning discussion in section 3; they do not validate the complete COMULS system or exact stage offsets. Entries described as “research on…” are descriptive labels, not purported verbatim article titles. R18–R19 support the media pipeline.

R01 — [Sweller, van Merriënboer & Paas (2019). Cognitive Architecture and Instructional Design: 20 Years Later.](https://link.springer.com/article/10.1007/s10648-019-09465-5) Review of cognitive-load theory; supports managing interacting unfamiliar elements and adapting to expertise.

R02 — [Coppens et al. (2020). The effect of practice test modality on perceived mental effort and delayed retention.](https://research-portal.uu.nl/en/publications/the-effect-of-practice-test-modality-on-perceived-mental-effort-a/) Original experiment; effort and delayed retention are distinct outcomes. DOI: 10.1080/20445911.2020.1822366.

R03 — [Vaughn, Hausman & Kornell (2017). Retrieval attempts enhance learning regardless of time spent trying to retrieve.](https://sites.williams.edu/nk2/files/2011/08/Retrieval-attempts-enhance-learning-regardless-of-time-spent-trying-to-retrieve.pdf) Original experiments comparing retrieval-attempt duration; does not prescribe a universal reveal deadline.

R04 — [van den Broek et al. (2019). Effects of elaborate feedback during practice tests: Costs and benefits.](https://research.rug.nl/en/publications/effects-of-elaborate-feedback-during-practice-tests-costs-and-ben/) Original vocabulary experiments; time cost and later unaided retrieval matter. DOI: 10.1037/xap0000212.

R05 — [Kim & Webb (2022). The effects of spaced practice on second language learning: A meta-analysis.](https://onlinelibrary.wiley.com/doi/10.1111/lang.12479) 48 experiments; supports spacing in L2 learning without determining COMULS's precise schedule.

R06 — [Nakata (2017). Does repeated practice make perfect? The effects of within-session repeated retrieval on second language vocabulary learning.](https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/abs/does-repeated-practice-make-perfect-the-effects-of-withinsession-repeated-retrieval-on-second-language-vocabulary-learning/F14BA8A576CD2563D14CEA46E35D842E) Original study of 98 learners; time-adjusted efficiency differs from raw retention.

R07 — [Smith, Roediger & Karpicke (2013). Covert retrieval practice benefits retention as much as overt retrieval practice.](https://learninglab.psych.purdue.edu/downloads/2013/2013_Smith_Roediger_Karpicke_JEPLMC.pdf) Original experiments; interpretation depends on actual retrieval compliance and task.

R08 — [Jönsson et al. (2014). Learning and retention of foreign vocabulary: Effects of response format and feedback.](https://link.springer.com/article/10.1007/s00426-013-0522-8) Original foreign-vocabulary study; overt/covert equivalence is not universal.

R09 — [Nakata & Suzuki (2019). Mixing grammar exercises facilitates long-term retention: Effects of blocking, interleaving, and increasing practice.](https://onlinelibrary.wiley.com/doi/10.1111/modl.12581) Original grammar-practice study; relevant to delayed discrimination between learned patterns.

R10 — [Hwang (2025). Research on when interleaving becomes an undesirable difficulty in L2 vocabulary practice.](https://onlinelibrary.wiley.com/doi/full/10.1111/lang.12659) Primary study; supports distinguishing initial acquisition from later mixed practice.

R11 — [Borghini & Hazan (2018). Listening effort during sentence processing is increased for non-native listeners: A pupillometry study.](https://www.frontiersin.org/journals/neuroscience/articles/10.3389/fnins.2018.00152/full) Original listening-effort study; pupil response is not a direct measure of cumulative fatigue.

R12 — [Jiang, Kalyuga & Sweller (2018). Research on reading support for novice foreign-language listening.](https://link.springer.com/article/10.1007/s10648-017-9427-1) Primary instructional research; transcript support can be useful, particularly with limited prior knowledge.

R13 — [McGarrigle, Havelka & de Bruin (2026). Research on listening-related fatigue and language proficiency.](https://link.springer.com/article/10.3758/s13423-026-03005-3) Observational evidence published September 2026; association does not establish an optimal flashcard length.

R14 — [Albulescu et al. (2022). Give me a break! A systematic review and meta-analysis on the efficacy of micro-breaks for increasing well-being and performance.](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0272460) 22 samples and 2,335 participants; small fatigue/vigour benefits, heterogeneous performance results.

R15 — [Biwer et al. (2023). Research comparing systematic and self-regulated breaks during study.](https://bpspsychub.onlinelibrary.wiley.com/doi/10.1111/bjep.12593) Primary study; relevant to effort regulation, without establishing one universal cadence.

R16 — [Göksu, Wiradhany & de Bruin (2026). When to take a break: Comparing effects of systematic short and self-regulated breaks.](https://cris.maastrichtuniversity.nl/en/publications/when-to-take-a-break-comparing-effects-of-systematic-short-pomodo/) Primary study. DOI: 10.3390/bs16071158. Interpret in its own population/task.

R17 — [Liu & Aryadoust (2026). An eye-tracking study of the impact of item presentation and item format on cognitive processing in L2 listening assessment.](https://www.cambridge.org/core/journals/studies-in-second-language-acquisition/article/an-eyetracking-study-of-the-impact-of-item-presentation-and-item-format-on-cognitive-processing-in-l2-listening-assessment/EC9FBD4200BF03F0D8D87CF758CF244B) Original assessment study; recognition options create their own reading and comparison demands.

R18 — [ElevenLabs. Text to speech with timestamps: official API documentation.](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps) Technical source for timestamp output and limits of seed-based determinism.

R19 — [Montreal Forced Aligner. French MFA acoustic-model card.](https://huggingface.co/MontrealCorpusTools/french_mfa) Technical source; timing alignment must not be treated as pronunciation assessment.

Anki implementation baseline: release 26.09, commit [e62e773905ed4f7c1439106247f5885ac79d598c](https://github.com/ankitects/anki/commit/e62e773905ed4f7c1439106247f5885ac79d598c). Pin integration tests to the release and record upgrades explicitly.

| Source | Implementation question |
|---|---|
| [Collection API](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/pylib/anki/collection.py) | Native note updates, configuration, undo and identity |
| [Scheduler API](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/pylib/anki/scheduler/base.py) | Native suspension, burial and scheduling interface |
| [Deck API](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/pylib/anki/decks.py) | Managed deck creation and identity |
| [Media API](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/pylib/anki/media.py) | Actual returned filenames and media installation |
| [GUI hook definitions](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/qt/tools/genhooks_gui.py) | Reviewer and webview lifecycle hooks |
| [Reviewer implementation](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/qt/aqt/reviewer.py) | Grade/advance ordering and active-card refresh |
| [Collection operations](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/qt/aqt/operations/__init__.py) | Background mutations, initiators and UI notification |
| [Background-operations guidance](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/docs-site/addons/background-ops.mdx) | Main-thread UI and collection operation separation |
| [Reviewer JavaScript guidance](https://github.com/ankitects/anki/blob/e62e773905ed4f7c1439106247f5885ac79d598c/docs-site/addons/reviewer-javascript.mdx) | Webview integration and reviewer messages |
| [Anki deck options manual](https://docs.ankiweb.net/deck-options.html) | Native queue options, FSRS and preset behaviour |

The COMULS repository was inspected at tree commit d12a6a968cd01ccede3988156e275214db822e02. The source guide and complete baseline/support Drive copies informed the schema contracts. The large current parent/sense files require the byte-level audit specified in P0; the older repository export must not silently replace them.

Complete current source locations:

- [Export folder](https://drive.google.com/drive/folders/1cUNhWb4stty_dW034wf6-mz-h05tNQNU)

- [Guide](https://drive.google.com/file/d/1VVs8E6Vkp-DfRyU2Hl74Dq1FtmVZ4E9a/view)

- [Verified parent view](https://drive.google.com/file/d/1zZuAE7NiQJai234vXo9VEklOmCb2wmts/view)

- [B1–C1 parent view](https://drive.google.com/file/d/10P7ALyU6y-e0LUTrFq5qjKI9Mz-jl8YC/view)

- [Flattened senses](https://drive.google.com/file/d/1rrHPKqZ97TN9RNLUBvzB2y_-cszgWHr2/view)

- [Baseline meanings](https://drive.google.com/file/d/1_2-HVOq4T_PniK9ceMdr7y-PCIR-Z18e/view)

- [Definition support](https://drive.google.com/file/d/1r1gDxbx8aJnoJwClidk_jmiGs6kLqp8k/view)

This is an implementation specification, not a claim that the add-on, complete exercise corpus or automated test suite has already been built. Architecture, user flows, policies, exercise contracts and release tests are fixed sufficiently to begin implementation. Remaining source reconciliation, linguistic/audio validation and client verification are concrete work packages with acceptance criteria, rather than unanswered product decisions.
