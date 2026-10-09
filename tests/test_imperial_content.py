"""Semantic fixtures and coverage gates for the bounded Imperial launch packs.

These tests check authored contracts. They do not establish natural pronunciation,
CEFR validity, teacher approval, or educational effectiveness.
"""
import collections
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('imperial_content_core', ROOT / 'addon/core.py')
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def read_pack(stage):
    return core.load_pack(ROOT / 'addon/data' / ('imperial_' + stage.lower() + '.json'))


def words(text):
    return collections.Counter(re.sub(r'[.,;:!?]', '', core.normalize_answer(text)).split())


class ImperialContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs = {stage: read_pack(stage) for stage in ('B1', 'B2')}
        cls.items = [e for p in cls.packs.values() for e in p['exercises']]
        cls.byid = {e['id']: e for e in cls.items}

    def test_bounded_separate_cohorts_cover_every_format(self):
        self.assertEqual(len(self.items), 130)
        self.assertEqual(len(self.byid), 130)
        for stage, pack in self.packs.items():
            self.assertEqual(len(pack['exercises']), 65)
            self.assertEqual(collections.Counter(e['type'] for e in pack['exercises']),
                             collections.Counter({kind: 5 for kind in core.EXERCISE_TYPES}))
            self.assertTrue(all(e['cohort'] == e['origin_entry_level'] == stage for e in pack['exercises']))
            self.assertTrue(all(core.level_eligible(e, stage) for e in pack['exercises']))
            self.assertTrue(pack['coverage_limitations'])

    def test_repair_remains_available_without_global_demotion(self):
        for exercise in self.packs['B1']['exercises']:
            self.assertTrue(core.level_eligible(exercise, 'B2'))
        b2_repair = [e for e in self.packs['B2']['exercises'] if e['level'] == 'A2+']
        self.assertGreaterEqual(len(b2_repair), 2)
        for exercise in b2_repair:
            self.assertTrue(core.level_eligible(exercise, 'B2'))

    def test_synthesis_assesses_only_below_selected_stage(self):
        for e in self.items:
            if e['type'] not in core.SYNTHESIS_TYPES:
                continue
            for field in ('level', 'target_level', 'carrier_level', 'construction_level'):
                self.assertLess(core.LEVELS.index(e[field]), core.LEVELS.index(e['cohort']), (e['id'], field))

    def test_first_item_of_every_format_can_start_without_above_stage_preview(self):
        for stage, pack in self.packs.items():
            for kind in core.EXERCISE_TYPES:
                e = next(e for e in pack['exercises'] if e['type'] == kind)
                self.assertLessEqual(core.LEVELS.index(e['level']), core.LEVELS.index(stage), e['id'])
                self.assertLessEqual(len(e['support_units']), 2)

    def test_source_identity_is_specific_and_legacy_contracts_are_untouched(self):
        legacy = {e['id'] for e in core.load_pack(ROOT / 'addon/data/tester.json')['exercises']}
        for e in self.items:
            self.assertNotIn(e['id'], legacy)
            for key in ('parent_id', 'sense_id', 'form_id', 'construction_id', 'context_id',
                        'required_construction', 'target_form', 'target_meaning', 'evidence_facets'):
                self.assertTrue(e[key], (e['id'], key))
            self.assertFalse(e['local_task_assignment']['source_lexical_cefr_claim'])
            self.assertFalse(e['qa']['human_reviewed'])
            self.assertEqual(e['qa']['level_status'], 'provisional')

    def test_definition_languages_are_frozen_per_parent_and_meet_pilot_quotas(self):
        for stage, pack in self.packs.items():
            assignments = pack['definition_policy']['assignments']
            self.assertEqual(len(assignments), 6)
            self.assertEqual(sum(v == 'fr' for v in assignments.values()), 0 if stage == 'B1' else 3)
            for e in pack['exercises']:
                if e['type'] in ('meaning_recall', 'french_form_recall'):
                    self.assertEqual(e['definition_language'], assignments[e['parent_id']])
                    if e['definition_language'] == 'fr':
                        supports = [s for s in e['support_units'] if s['scope'] == 'definition_support']
                        self.assertTrue(supports)
                        self.assertTrue(all(s['level'] == 'B1' and s['english'] for s in supports))

        policy = self.packs['B2']['definition_policy']
        ranked = sorted(policy['assignments'], key=lambda parent: hashlib.sha256(
            (policy['policy_seed'] + parent).encode()).hexdigest())
        self.assertEqual(policy['assignment_order'], ranked)
        self.assertEqual({p for p, lang in policy['assignments'].items() if lang == 'fr'}, set(ranked[:3]))

    def test_unknown_support_blocks_admission_and_explicit_support_opens_it(self):
        for e in self.items:
            supports = {s['id']: s for s in e['support_units']}
            self.assertEqual(set(e['prerequisites']), set(supports))
            self.assertNotIn(e['unit_id'], supports)
            self.assertTrue(all(s['requires'] == [] and s['english'] for s in supports.values()))
            blocked = core.admission_decision(e, e['cohort'], True, set(), set(core.EXERCISE_TYPES), {})
            if supports:
                self.assertFalse(blocked['allowed'], e['id'])
                self.assertIn('prerequisites_missing', blocked['reasons'])
            else:
                self.assertIn(e['type'], {'sentence_reconstruction', 'sentence_transcription',
                                         'audio_transcript_choice', 'audio_meaning_choice'})
                self.assertTrue(blocked['allowed'])
            ready = core.admission_decision(e, e['cohort'], True, set(supports), set(core.EXERCISE_TYPES), {})
            self.assertTrue(ready['allowed'], (e['id'], ready))

    def test_reference_answers_and_explicit_alternatives(self):
        for e in self.items:
            if e['type'] in core.CHOICE_TYPES:
                for option in e['choices']:
                    status = core.evaluate_answer(e, option['id'])['status']
                    self.assertEqual(status, 'correct' if option['correct'] else 'incorrect', e['id'])
            elif e['type'] == 'meaning_recall':
                self.assertEqual(core.evaluate_answer(e, e['answer'])['status'], 'self_compare')
            else:
                for answer in [e['answer'], *e['accepted']]:
                    self.assertEqual(core.evaluate_answer(e, answer)['status'], 'correct', (e['id'], answer))

    def test_known_variant_and_accents_are_handled_intentionally(self):
        key = self.byid['imperial_b1_vocabulary_cloze_01']
        self.assertEqual(core.evaluate_answer(key, 'clef')['status'], 'correct')
        self.assertEqual(core.evaluate_answer(key, 'cle')['status'], 'incorrect')
        implement = self.byid['imperial_b2_partial_dictation_05']
        self.assertEqual(core.evaluate_answer(implement, 'mettre en œuvre')['status'], 'correct')
        self.assertEqual(core.evaluate_answer(implement, 'mettre en oeuvre')['status'], 'correct')
        refund = self.byid['imperial_b1_french_form_recall_03']
        self.assertEqual(core.evaluate_answer(refund, 'payer')['status'], 'incorrect')
        opening = self.byid['imperial_b1_sentence_transcription_04']
        self.assertEqual(core.evaluate_answer(opening, 'Je voudrais connaitre les horaires d’ouverture.')['status'], 'correct')

    def test_first_letter_assistance_is_optional_and_options_have_meaning_support(self):
        for e in self.items:
            if e['type'] in {'french_form_recall', 'vocabulary_cloze'}:
                self.assertNotRegex(e['prompt'], r'\bbegins?\b|\bbeginning\b')
                self.assertTrue(e['target_hint'])
            if e['type'] in core.CHOICE_TYPES:
                self.assertEqual({g['choice_id'] for g in e['option_glosses']},
                                 {c['id'] for c in e['choices']})
                self.assertTrue(all(g['text'] and g['english'] for g in e['option_glosses']))

    def test_reconstruction_has_real_alternative_order_and_interchangeable_duplicates(self):
        for e in self.items:
            if e['type'] != 'sentence_reconstruction':
                continue
            alternative = e['qa']['no_audio_check']['alternative_grammatical_order']
            self.assertEqual(words(e['answer']), words(alternative), e['id'])
            self.assertNotEqual(core.normalize_answer(e['answer']), core.normalize_answer(alternative))
            self.assertEqual(core.evaluate_answer(e, alternative)['status'], 'incorrect')
            tokens = e['tokens']
            self.assertTrue(all(t['text'] == t['text'].lower() and not re.search(r'[.,;:!?]', t['text']) for t in tokens))
            response = [t['id'] for t in tokens]
            self.assertEqual(core.evaluate_answer(e, response)['status'], 'correct')
            for i, token in enumerate(tokens):
                for j in range(i+1, len(tokens)):
                    if token['text'] == tokens[j]['text']:
                        swapped = response[:]
                        swapped[i], swapped[j] = swapped[j], swapped[i]
                        self.assertEqual(core.evaluate_answer(e, swapped)['status'], 'correct')

    def test_audio_contract_text_matches_what_is_assessed(self):
        for e in self.items:
            if e['type'] not in core.AUDIO_TYPES:
                continue
            self.assertTrue(e['audio_text'])
            if e['type'] in ('sound_discrimination', 'sentence_reconstruction', 'sentence_transcription', 'audio_transcript_choice'):
                self.assertEqual(core.normalize_answer(e['audio_text']), core.normalize_answer(e['answer']))
            elif e['type'] in ('connected_word_recognition', 'partial_dictation'):
                self.assertIn(core.normalize_answer(e['answer']), core.normalize_answer(e['audio_text']))
            if e['type'] == 'sound_discrimination':
                self.assertEqual(len(e['choices']), 2)
                self.assertTrue(all(c['audio_text'] == c['text'] for c in e['choices']))
                contrast = e['qa']['phonetic_contrast']
                self.assertNotEqual(contrast['correct_ipa'], contrast['distractor_ipa'])
                self.assertTrue(contrast['recording_must_preserve_contrast'])

    def test_answer_revealing_help_and_cross_card_exposure_are_marked(self):
        revealing = {'sentence_transformation', 'sentence_reconstruction',
                     'partial_dictation', 'sentence_transcription',
                     'audio_transcript_choice', 'audio_meaning_choice'}
        self.assertTrue(all(e['carrier_help_reveals_target'] for e in self.items if e['type'] in revealing))
        g = self.byid['imperial_b1_grammar_cloze_01']['exposure_groups']
        t = self.byid['imperial_b1_sentence_transformation_01']['exposure_groups']
        self.assertIn('imperial_form_aller_present_nous', set(g) & set(t))
        for pack in self.packs.values():
            grouped = collections.defaultdict(list)
            for e in pack['exercises']:
                if e['type'] in ('meaning_recall', 'french_form_recall'):
                    grouped[e['sense_id']].append(e)
            for exercises in grouped.values():
                if len(exercises) > 1:
                    self.assertTrue(set(exercises[0]['exposure_groups']) & set(exercises[1]['exposure_groups']))


if __name__ == '__main__':
    unittest.main()
