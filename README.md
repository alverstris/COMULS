# COMULS — Concurrent Multi Level System

COMULS is a proposed curriculum and progression system for Anki. It combines retention of earlier language, mastery of the current level, and controlled preparation for upcoming material. The aim is smoother language learning with fewer abrupt jumps between CEFR levels.

Current stage: a desktop Anki tester is implemented on this branch, with B1/B2/C1 entry levels, all thirteen exercise formats and a bounded 90-exercise pack. See [student installation instructions](docs/STUDENT_GUIDE.md) and [verification checklist](docs/TESTER_CHECKLIST.md). Download the installable package from a passing tester release. Improved learning speed remains a design goal, not an established result. The full vocabulary inventory is not yet a ready-made course.

## How the system is meant to work

The learner has one explicit current curriculum level, while several levels serve different purposes concurrently. At **B1**, the intended window is:

| Material | Role |
| --- | --- |
| Earlier levels | Retain introduced material through due reviews |
| B1 | Learn and practise vocabulary, grammar, listening and production |
| B1+ | Selected spelling-from-audio and phonetic preparation |
| B2 | Controlled aural exposure, followed by recognition after familiarisation |
| B2+ and above | Normally locked; occasional ungraded exposure may be appropriate |

The planned progression is `A2-R → A2 → A2+ → B1 → B1+ → B2 → B2+ → C1 → C1+ → C2`. A2-R is an initial recovery stage. Plus stages are project curriculum subdivisions, not separate official CEFR qualifications. In the vocabulary files, **B1/B2 corresponds to B1+**, and **B2/C1 corresponds to B2+**, as a COMULS convention.

Progression is **manual**. Readiness indicators may inform the learner's decision, but do not force promotion. Advancing shifts the acquisition and preview window; it does not erase earlier learning or reset review history. Planned rollback pauses additional advanced acquisition while retaining already introduced material for review.

### Eligibility, prerequisites and reviews

A new task normally needs two independent gates: an appropriate curriculum level and adequately learned prerequisites. Reaching B2 alone would not release a compound-subjunctive card if its required construction and verb knowledge were missing.

A word's introduction level also does not determine every card's difficulty. A familiar word can appear in increasingly demanding grammar and contexts. Future cards therefore need separate assessments of the selected meaning, construction, surrounding language and complete task.

COMULS determines **which new material is eligible**. Anki's FSRS determines **when an introduced card is due for review**. Earlier cards remain reviewable after advancement. Targeted remediation can run alongside the main curriculum: a B2 learner may need A2+ listening-segmentation practice without being demoted across every skill.

### Preview and English scaffolding

Future vocabulary should initially receive exposure rather than a scored test requiring guesses. The intended sequence moves from hearing an explicitly labelled preview, through transcript-and-meaning support and repeated exposure, to recognition, spelling preparation and formal acquisition. Spelling previews should distinguish a largely correct sound pattern with incorrect orthography from hearing the wrong word.

English can support early acquisition. Later, French definitions, contextual retrieval, listening and production can provide stronger French-only representations. When these are stable, the original English acquisition card should be suspended with its history preserved. English/French contrast cards remain where contrast is itself the learning objective. This retirement logic is planned; the current dataset does not perform it.

## French vocabulary dataset

The final selection contains **10,037 distinct word families and 370 expressions**:

| Introduction band | Word families | Expressions | French-definition share |
| --- | ---: | ---: | ---: |
| B1 | 916 | 141 | 0% |
| B1/B2 | 810 | 0 | 25% |
| B2 | 2,616 | 177 | 50% |
| B2/C1 | 2,446 | 13 | 75% |
| C1 | 3,249 | 39 | 100% |

Definition shares apply to vocabulary parents, rounded to whole entries. Each parent has **one current definition language** across its selected meanings; English and French copies do not inflate the count. Previously introduced English definitions do not automatically change when the learner advances.

There are **24,153 word sense/usage records and 455 expression records**, totalling **24,608**, grouped within the CSV's parent rows. Multiple meanings, ordinary conjugations, agreement forms and verified spelling variants do not add word families. Distinct grammatical uses can remain separate records within a family; these records are not automatically separate cards. Coverage comprises selected verified senses, not every dictionary subdivision.

CEFR placements are tentative curriculum estimates informed by source/model labels and frequency evidence. They are not official word assignments or verified levels for every sense. The [CEFR vocabulary-range descriptors](https://rm.coe.int/common-european-framework-of-reference-for-languages-learning-teaching/16809ea0d4) describe communicative abilities rather than numerical word quotas; 10,000 advanced families is this project's selection target. B1/B2 qualifications are DELF and C1/C2 qualifications are DALF. The CSV retains source references and the basis for its level assignments.

## Getting started

Download the approximately **42 MB** [vocabulary CSV](outputs/french_vocabulary_b1_c1.csv). Each row groups one verified vocabulary parent. Its `definition` field provides a numbered readable summary; `senses_json` retains the individually identified meanings, grammatical constraints and source evidence. Display numbers are not permanent meaning identities.

The file uses UTF-8 with BOM, comma separators, quoted cells and embedded JSON. Embedded newlines are intentional. Use a CSV parser rather than splitting on commas or lines:

```python
import csv
import json

with open("outputs/french_vocabulary_b1_c1.csv", encoding="utf-8-sig", newline="") as file:
    rows = list(csv.DictReader(file))
print(len(rows))  # 10,407 vocabulary parents
first_parent_meanings = json.loads(rows[0]["senses_json"])
```

The published CSV passed structural checks for identities, counts, language shares, retained source evidence and the verified-word target. These checks do not certify teaching efficacy or official CEFR placement.

## Preparing Anki notes

`entry_id` groups a family; persistent `sense_id` values identify meanings. A future **separate `note_id`** must identify each note, with precise grammatical form/construction and reviewed context identities. Wording edits should preserve those identities and scheduling history.

A bare ambiguous word must not require recall of every meaning. Contextual prompts need one selected sense, an exact answer form and reviewed alternatives. A required adjective form is not interchangeable with its related infinitive. Review the aliases, grammatical realizations, construction restrictions and potential expression overlaps retained in the CSV before generating notes. Current contexts are empty and `card_ready` is false.

## Sources and reuse

Definitions are original paraphrases or translated paraphrases of consulted entries from **Académie française, WordReference and Reverso**, with source URLs, locators and wording provenance retained in the CSV. An English rendering of a French entry remains attributed to its actual dictionary source; it is not presented as a verbatim English dictionary definition.

Underlying lexical sources retain their licences: FLELex **CC BY-NC-SA 4.0**, PolyLexFLE **LGPL-2.1**, Lexique **CC BY-SA 4.0**, and FranceTerme **Licence Ouverte**. No blanket open licence is asserted for dictionary material or this combined dataset. Consult the source terms and retained provenance when reusing or redistributing it.
