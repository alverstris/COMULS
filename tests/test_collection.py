"""Integration checks against native Anki, without importing the Qt entry point."""
from __future__ import annotations

import copy
import importlib
import json
import sys
import time
import types
from pathlib import Path

import pytest
from anki.collection import Collection

PACKAGE = "_comuls_native_test"
if PACKAGE not in sys.modules:
    module = types.ModuleType(PACKAGE)
    module.__path__ = [str(Path(__file__).resolve().parents[1] / "addon")]
    sys.modules[PACKAGE] = module
adapter = importlib.import_module(PACKAGE + ".collection")
core = importlib.import_module(PACKAGE + ".core")


@pytest.fixture
def col(tmp_path):
    value = Collection(str(tmp_path / "collection.anki2"))
    yield value
    value.close()


@pytest.fixture
def exercise():
    return {
        "id": "test-word-one", "type": "meaning_recall", "level": "B1",
        "entry_levels": ["B1", "B2", "C1"], "prompt": "Que signifie « éviter » ?",
        "answer": "To avoid", "accepted": ["avoid"],
        "explanation": "One selected meaning.", "unit_id": "word-eviter",
        "target_meaning": "sense-eviter", "carrier_meaning": "",
        "prerequisites": [], "exposure_groups": [],
        "qa": {"ready": True, "level_status": "provisional"},
        "provenance": {"kind": "test_fixture"},
    }


def introduce(col, value, day=0):
    nid = adapter.prepare_exercise(col, value, day)
    adapter.mark_familiarised(col, value["id"], day)
    adapter.activate_exercise(col, value, day)
    return col.get_note(nid)


def snapshot(card):
    return (card.id, card.nid, card.did, card.type, card.queue, card.due,
            card.ivl, card.reps, card.lapses, card.factor)


def test_small_synced_controls_preserve_undo_and_cap_day_records(col):
    state = adapter.get_state(col)
    assert state["stage"] == "B1"
    assert state["budget_minutes"] == 15
    assert state["enabled"] == list(core.EXERCISE_TYPES)
    assert state["audio_confirmed"] is False
    model = adapter.ensure_model(col)
    previous = col.undo_status().undo
    state["days"] = {str(index): {"active_seconds": 5} for index in range(30)}
    adapter.save_state(col, state)
    assert col.undo_status().undo == previous
    assert list(adapter.get_state(col)["days"]) == [str(x) for x in range(16, 30)]
    assert model["name"] == adapter.MODEL_NAME
    col.undo()
    assert col.models.by_name(adapter.MODEL_NAME) is None
    assert list(adapter.get_state(col)["days"]) == [str(x) for x in range(16, 30)]


def test_prepare_is_idempotent_and_requires_completed_familiarisation(col, exercise):
    day = col.sched.today
    first = adapter.prepare_exercise(col, exercise, day)
    second = adapter.prepare_exercise(col, copy.deepcopy(exercise), day)
    assert first == second
    notes = adapter.exercise_notes(col)
    assert len(notes) == 1
    note = notes[exercise["id"]]
    assert note.cards()[0].queue == -1
    assert adapter.note_state(note)["familiarised_day"] is None
    with pytest.raises(ValueError, match="familiarisation"):
        adapter.activate_exercise(col, exercise, day)
    adapter.mark_familiarised(col, exercise["id"], day)
    adapter.activate_exercise(col, exercise, day)
    native = note.cards()[0]
    assert native.queue == 0
    assert native.reps == 0
    assert adapter.note_state(col.get_note(first))["admitted_day"] == str(day)
    assert adapter.activate_exercise(col, exercise, day) == first


def test_reimport_preserves_native_history_personal_notes_and_tags(col, exercise):
    note = introduce(col, exercise, col.sched.today)
    note["PersonalNotes"] = "My own notes <b>stay</b>."
    note.add_tag("my::tag")
    col.update_note(note)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    card = col.get_card(card.id)
    before = snapshot(card)
    logs_before = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    repaired = copy.deepcopy(exercise)
    repaired["explanation"] = "A repaired explanation with identical retrieval semantics."
    nid = adapter.prepare_exercise(col, repaired, col.sched.today)
    assert nid == note.id
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs_before
    updated = col.get_note(nid)
    assert updated["PersonalNotes"] == note["PersonalNotes"]
    assert "my::tag" in updated.tags
    assert adapter.note_payload(updated)["explanation"] == repaired["explanation"]


def test_same_id_changed_contract_and_local_edits_are_conflicts(col, exercise):
    nid = adapter.prepare_exercise(col, exercise, 0)
    changed = copy.deepcopy(exercise)
    changed["answer"] = "An unrelated answer"
    with pytest.raises(ValueError, match="retrieval contract"):
        adapter.prepare_exercise(col, changed, 0)
    note = col.get_note(nid)
    payload = adapter.note_payload(note)
    payload["explanation"] = "An intentional local edit."
    adapter._write_json(note, "Payload", payload)
    col.update_note(note)
    with pytest.raises(ValueError, match="edited locally"):
        adapter.prepare_exercise(col, exercise, 0)
    assert adapter.note_payload(col.get_note(nid))["explanation"] == "An intentional local edit."


def test_locally_edited_prompt_is_not_overwritten(col, exercise):
    nid = adapter.prepare_exercise(col, exercise, 0)
    note = col.get_note(nid)
    note["Prompt"] = "My own prompt"
    col.update_note(note)
    with pytest.raises(ValueError, match="Prompt"):
        adapter.prepare_exercise(col, exercise, 0)
    assert col.get_note(nid)["Prompt"] == "My own prompt"


def test_manually_paused_admitted_card_is_not_resumed(col, exercise):
    note = introduce(col, exercise)
    card = note.cards()[0]
    col.sched.suspend_cards([card.id])
    with pytest.raises(ValueError, match="manually paused"):
        adapter.activate_exercise(col, exercise, 1)
    assert col.get_card(card.id).queue == -1


def test_stage_change_keeps_review_history_and_withdraws_only_unreviewed(col, exercise):
    controls = adapter.get_state(col)
    controls["stage"] = "B2"
    adapter.save_state(col, controls)
    advanced = copy.deepcopy(exercise)
    advanced.update(id="advanced-reviewed", level="B2", entry_levels=["B2", "C1"])
    reviewed_note = introduce(col, advanced, col.sched.today)
    card = reviewed_note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    revlog = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    pending = copy.deepcopy(advanced)
    pending["id"] = "advanced-unreviewed"
    pending_note = introduce(col, pending, col.sched.today)
    report = adapter.stage_change(col, "B1", [advanced, pending])
    assert report == {"withdrawn": 1, "retained_reviews": 1}
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == revlog
    assert col.get_card(pending_note.cards()[0].id).queue == -1
    assert adapter.note_state(col.get_note(pending_note.id))["managed_pause"] == "stage"
    assert adapter.get_state(col)["stage"] == "B1"


def test_stored_deck_id_survives_rename_and_deleted_deck_is_reported(col, exercise):
    controls = adapter.get_state(col)
    controls["manager_id"] = "desktop-uuid"
    adapter.save_state(col, controls)
    adapter.prepare_exercise(col, exercise, 0)
    controls = adapter.get_state(col)
    assert controls["manager_id"] == "desktop-uuid"
    did = controls["deck_id"]
    assert isinstance(did, int)
    deck = col.decks.get_legacy(did)
    deck["name"] = "My renamed French practice"
    col.decks.save(deck)
    assert adapter.ensure_deck(col, controls) == did
    assert col.decks.id_for_name(adapter.DEFAULT_DECK_NAME) is None
    col.decks.remove([did])
    with pytest.raises(ValueError, match="deleted"):
        adapter.ensure_deck(col, controls)


def test_duplicate_identity_blocks_import_before_mutation(col, exercise):
    nid = adapter.prepare_exercise(col, exercise, 0)
    existing = col.get_note(nid)
    duplicate = col.new_note(adapter.ensure_model(col))
    for name in adapter.FIELDS:
        duplicate[name] = existing[name]
    col.add_note(duplicate, adapter.get_state(col)["deck_id"])
    with pytest.raises(ValueError, match="Duplicate"):
        adapter.prepare_exercise(col, exercise, 0)
    assert len(col.models.nids(existing.mid)) == 2


@pytest.mark.parametrize("kind", core.EXERCISE_TYPES)
def test_only_audio_tasks_receive_frontside_audio(col, exercise, kind):
    value = copy.deepcopy(exercise)
    value.update(id="audio-policy-" + kind, type=kind,
                 audio_text="Bonjour", audio_file="test-french.mp3")
    nid = adapter.prepare_exercise(col, value, 0)
    note = col.get_note(nid)
    if kind in core.AUDIO_TYPES:
        assert note["AudioText"] == "Bonjour"
        assert note["AudioFile"] == "[sound:test-french.mp3]"
    else:
        assert note["AudioText"] == note["AudioFile"] == ""


def test_payload_roundtrip_preserves_html_characters_and_unicode(col, exercise):
    exercise["explanation"] = "L'été <ici> & une chaîne littérale &amp;."
    nid = adapter.prepare_exercise(col, exercise, 0)
    assert adapter.note_payload(col.get_note(nid)) == exercise


def test_stats_read_native_collection_without_rescheduling(col, exercise):
    note = introduce(col, exercise)
    card = note.cards()[0]
    before = snapshot(card)
    values = adapter.stats(col)
    assert values["total"] == 1
    assert values["new"] == 1
    assert values["reviewed"] == 0
    assert values["native_day"] == col.sched.today
    assert values["deck_id"] == card.did
    assert snapshot(col.get_card(card.id)) == before


def test_raw_backlog_is_not_hidden_by_daily_review_limit(col, exercise):
    cards = []
    for index in range(3):
        value = copy.deepcopy(exercise)
        value["id"] = f"backlog-{index}"
        note = introduce(col, value)
        card = note.cards()[0]
        card.start_timer()
        col.sched.answerCard(card, 3)
        cards.append(card.id)
    # Configure a legitimate small native daily limit and make these reviews due.
    did = adapter.get_state(col)["deck_id"]
    config = col.decks.config_dict_for_deck_id(did)
    # Three grades have already consumed today's review counters; a limit of
    # four leaves capacity for one of these three due cards.
    config["rev"]["perDay"] = 4
    col.decks.update_config(config)
    col.sched.set_due_date(cards, "0")
    result = adapter.stats(col)
    assert result["due"] == 3
    assert result["available_due"] == 1


def test_stage_undo_is_atomic_without_resetting_later_active_time(col, exercise):
    controls = adapter.get_state(col)
    controls["stage"] = "B2"
    adapter.save_state(col, controls)
    advanced = copy.deepcopy(exercise)
    advanced.update(id="stage-undo-pending", level="B2", entry_levels=["B2", "C1"])
    note = introduce(col, advanced, col.sched.today)
    cid = note.cards()[0].id
    marker = col.add_custom_undo_entry("Change COMULS entry level")
    adapter.stage_change(col, "B1", [advanced])
    col.merge_undo_entries(marker)
    assert adapter.get_state(col)["stage"] == "B1"
    assert col.get_card(cid).queue == -1

    # A later non-undoable clock flush must survive undo of the stage change.
    current = adapter.get_state(col)
    day = str(col.sched.today)
    current["days"][day] = {"active_seconds": 123.0}
    adapter.save_state(col, current)
    col.undo()
    assert adapter.get_state(col)["stage"] == "B2"
    assert adapter.get_state(col)["days"][day]["active_seconds"] == 123.0
    assert col.get_card(cid).queue == 0
    assert adapter.note_state(col.get_note(note.id))["lifecycle"] == "admitted"
    col.redo()
    assert adapter.get_state(col)["stage"] == "B1"
    assert adapter.get_state(col)["days"][day]["active_seconds"] == 123.0
    assert col.get_card(cid).queue == -1


def test_review_metadata_matches_exact_native_id_and_does_not_add_undo_step(col, exercise):
    note = introduce(col, exercise, col.sched.today)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    native_undo = col.undo_status().undo
    event = {"card_id": int(card.id), "ease": 3, "outcome": "correct", "target_hint": False,
             "carrier_help": False, "replays": 0, "prior_exposure_today": False,
             "prior_exposed_at": time.time() - 3 * 86400, "capture_phase": "question"}
    identity = adapter.record_review_evidence(col, exercise["id"], event)
    assert identity == str(col.db.scalar("select id from revlog where cid=?", card.id))
    assert col.undo_status().undo == native_undo
    evidence = importlib.import_module(PACKAGE + ".evidence")
    def result():
        return evidence.summarize_exercise(exercise, adapter.evidence_state(col, col.get_note(note.id)),
                                           col.get_review_logs(card.id), time.time())
    assert result()["independent_successes"] == 1
    col.undo()
    assert result()["total_reviews"] == 0
    assert result()["independent_successes"] == 0
    col.redo()
    assert result()["independent_successes"] == 1


def test_reference_exposure_survives_native_undo_and_does_not_admit_future_card(col, exercise):
    note = introduce(col, exercise, col.sched.today)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = col.undo_status().undo
    exposed_at = time.time()
    adapter.record_reference_exposure(col, exercise["id"], exposed_at)
    adapter.record_reference_exposure(col, "future-not-materialised", exposed_at)
    assert len(adapter.exercise_notes(col)) == 1
    assert col.undo_status().undo == before
    col.undo()
    assert adapter.evidence_state(col, col.get_note(note.id))["last_exposed_at"] == pytest.approx(exposed_at, abs=1e-6, rel=0)
    assert not col.get_review_logs(card.id)


def test_reference_exposure_propagates_only_explicit_links(col, exercise):
    exercise["exposure_groups"] = ["exact-answer"]
    nid = adapter.prepare_exercise(col, exercise, 0)
    other = copy.deepcopy(exercise)
    other["id"] = "linked"
    linked = adapter.prepare_exercise(col, other, 0)
    other["id"] = "same-unit-unlinked"
    other["exposure_groups"] = []
    unrelated = adapter.prepare_exercise(col, other, 0)
    assert adapter.record_reference_exposure(col, exercise["id"], time.time()) == ["linked", exercise["id"]]
    assert adapter.evidence_state(col, col.get_note(linked))["last_exposed_by"] == exercise["id"]
    assert "last_exposed_by" not in adapter.evidence_state(col, col.get_note(unrelated))
    assert col.get_note(nid).cards()[0].queue == -1


def test_managed_pause_restores_only_owned_state_and_retains_native_schedule(col, exercise):
    note = introduce(col, exercise)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    logs = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    assert adapter.set_managed_pause(col, [exercise["id"]], True)["changed"] == [exercise["id"]]
    assert col.get_card(card.id).queue == -1
    assert adapter.set_managed_pause(col, [exercise["id"]], False)["changed"] == [exercise["id"]]
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs
    col.sched.suspend_cards([card.id])
    assert not adapter.set_managed_pause(col, [exercise["id"]], True)["changed"]
    assert not adapter.set_managed_pause(col, [exercise["id"]], False)["changed"]
    assert col.get_card(card.id).queue == -1


def test_changed_native_state_invalidates_managed_pause_ownership(col, exercise):
    note = introduce(col, exercise)
    card = note.cards()[0]
    adapter.set_managed_pause(col, [exercise["id"]], True)
    # A native browser operation changes the suspended card's schedule.
    col.sched.set_due_date([card.id], "7")
    col.sched.suspend_cards([card.id])
    assert not adapter.set_managed_pause(col, [exercise["id"]], False)["changed"]
    assert col.get_card(card.id).queue == -1


def test_retirement_and_restore_keep_history_and_preserve_user_pause(col, exercise):
    note = introduce(col, exercise)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    logs = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    adapter.retire_exercises(col, [exercise["id"]], replacement_id="replacement-v2")
    state = adapter.note_state(col.get_note(note.id))
    assert state["lifecycle"] == "retired" and state["replacement_id"] == "replacement-v2"
    assert adapter.restore_retired(col, exercise["id"])["changed"] == [exercise["id"]]
    assert snapshot(col.get_card(card.id)) == before
    col.sched.suspend_cards([card.id])
    adapter.retire_exercises(col, [exercise["id"]])
    adapter.restore_retired(col, exercise["id"])
    assert col.get_card(card.id).queue == -1
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs


def test_preflight_is_read_only_and_distinguishes_compatibility_conflicts_and_delta(col, exercise):
    note = introduce(col, exercise)
    before = snapshot(note.cards()[0])
    undo = col.undo_status().undo
    repaired = dict(exercise, explanation="Clearer explanation.", level="A2+")
    added = dict(exercise, id="new-identity")
    report = adapter.preflight_update(col, [repaired, added])
    assert report["compatible_revisions"] == [exercise["id"]]
    assert report["changed_stage_assignments"] == [exercise["id"]]
    assert report["added"] == ["new-identity"]
    assert not report["conflicts"] and not report["retired"]
    assert adapter.preflight_update(col, [dict(exercise, answer="changed")])["material_changes"] == [exercise["id"]]
    assert not adapter.preflight_update(col, [added])["retired"]
    assert adapter.preflight_update(col, [added], retire_missing=True)["retired"] == [exercise["id"]]
    assert snapshot(col.get_card(note.cards()[0].id)) == before
    assert col.undo_status().undo == undo
    note["Prompt"] = "A personal edit"
    col.update_note(note)
    assert adapter.preflight_update(col, [repaired])["conflicts"][0]["exercise_id"] == exercise["id"]


def test_pause_batch_prevalidates_all_notes_before_mutating(col, exercise):
    first = introduce(col, exercise)
    other = dict(exercise, id="second")
    second = introduce(col, other)
    second["Prompt"] = "Local edit"
    col.update_note(second)
    with pytest.raises(ValueError, match="edited locally"):
        adapter.set_managed_pause(col, [exercise["id"], "second"], True)
    assert first.cards()[0].queue == 0


def test_support_declarations_are_exact_and_do_not_create_review_evidence(col, exercise):
    exercise["support_units"] = [{"id": "support-specific-sense", "text": "un sens précis"}]
    nid = adapter.prepare_exercise(col, exercise, col.sched.today)
    with pytest.raises(ValueError, match="exact support"):
        adapter.declare_understood(col, exercise["id"], ["unshown-support"])
    adapter.declare_understood(col, exercise["id"], ["support-specific-sense"], target=True)
    state = adapter.note_state(col.get_note(nid))
    assert state["understood_support"] == ["support-specific-sense"]
    assert state["declared_understood"] is True
    assert state["familiarised_day"] is None
    assert col.get_note(nid).cards()[0].reps == 0
    assert not col.get_review_logs(col.get_note(nid).cards()[0].id)
    adapter.declare_understood(col, exercise["id"], ["support-specific-sense"],
                               newly_learned_ids=["support-specific-sense"], day=4)
    adapter.declare_understood(col, exercise["id"], ["support-specific-sense"],
                               newly_learned_ids=["support-specific-sense"], day=7)
    assert adapter.note_state(col.get_note(nid))["support_learned_days"] == {"support-specific-sense": "4"}


def test_alternative_media_refs_are_inert_and_protected(col, exercise):
    exercise["choices"] = [{"id": "one", "text": "son", "audio_file": "alternative.wav"}]
    nid = adapter.prepare_exercise(col, exercise, 0)
    note = col.get_note(nid)
    assert note["MediaRefs"] == '<audio preload="none" src="alternative.wav"></audio>'
    assert "[sound:" not in note["MediaRefs"]
    col.media.write_data("alternative.wav", b"RIFF-test-media")
    col.media.write_data("unreferenced.wav", b"RIFF-test-media")
    media_check = col.media.check()
    assert "alternative.wav" not in media_check.unused
    assert "unreferenced.wav" in media_check.unused
    assert not note.cards()[0].question_av_tags()
    note["MediaRefs"] = "My own change"
    col.update_note(note)
    with pytest.raises(ValueError, match="MediaRefs"):
        adapter.prepare_exercise(col, exercise, 0)


def test_legacy_model_appends_media_refs_preserving_card_and_field_identity(col, exercise):
    model = adapter.ensure_model(col)
    note = introduce(col, exercise)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    logs = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    col.models.remove_field(model, model["flds"][-1])
    col.models.update_dict(model)
    assert tuple(field["name"] for field in col.models.by_name(adapter.MODEL_NAME)["flds"]) == adapter.FIELDS[:-1]
    updated = adapter.ensure_model(col)
    assert tuple(field["name"] for field in updated["flds"]) == adapter.FIELDS
    assert updated["id"] == model["id"]
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs
    assert adapter.note_payload(col.get_note(note.id)) == exercise


def test_retirement_update_keeps_identity_and_cannot_admit_blocked_content(col, exercise):
    note = introduce(col, exercise)
    cid = note.cards()[0].id
    retired = dict(exercise, retired=True, replacement_id="replacement")
    assert adapter.prepare_exercise(col, retired, col.sched.today) == note.id
    assert col.get_note(note.id).cards()[0].id == cid
    assert adapter.note_state(col.get_note(note.id))["lifecycle"] == "retired"
    with pytest.raises(ValueError, match="retired"):
        adapter.activate_exercise(col, retired, col.sched.today)
    with pytest.raises(ValueError, match="Retired"):
        adapter.prepare_exercise(col, dict(retired, id="never-created"), col.sched.today)
    assert "never-created" not in adapter.exercise_notes(col)


def test_course_switch_withdraws_unreviewed_other_cohort_despite_repair_eligibility(col, exercise):
    exercise.update(cohort="B1", origin_entry_level="B1", entry_levels=["B1", "B2"])
    pending = introduce(col, exercise, col.sched.today)
    reviewed_exercise = dict(exercise, id="reviewed-b1")
    reviewed = introduce(col, reviewed_exercise, col.sched.today)
    card = reviewed.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    logs = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    assert core.level_eligible(exercise, "B2")
    result = adapter.stage_change(col, "B2")
    assert result == {"withdrawn": 1, "retained_reviews": 1}
    assert col.get_card(pending.cards()[0].id).queue == -1
    assert adapter.note_state(col.get_note(pending.id))["managed_pause"] == "stage"
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs


def test_compatible_dependency_update_reprepares_pending_but_retains_reviewed_cards(col, exercise):
    exercise["support_units"] = [{"id": "support-one", "text": "the old explanation"}]
    pending = introduce(col, exercise, col.sched.today)
    adapter.declare_understood(col, exercise["id"], ["support-one"])
    reviewed_value = dict(exercise, id="reviewed-compatible-update")
    reviewed = introduce(col, reviewed_value, col.sched.today)
    card = reviewed.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    logs = [row.SerializeToString() for row in col.get_review_logs(card.id)]
    updated = dict(exercise, prerequisites=["support-one"],
                   support_units=[{"id": "support-one", "text": "a revised exact use"}])
    preflight = adapter.preflight_update(col, [updated])
    assert preflight["changed_support_units"] == [exercise["id"]]
    adapter.prepare_exercise(col, updated, col.sched.today)
    state = adapter.note_state(col.get_note(pending.id))
    assert state["lifecycle"] == "prepared" and state["managed_pause"] == "update"
    assert state["understood_support"] == []
    assert state["admitted_day"] == str(col.sched.today)
    assert col.get_card(pending.cards()[0].id).queue == -1
    adapter.prepare_exercise(col, dict(updated, id=reviewed_value["id"]), col.sched.today)
    assert snapshot(col.get_card(card.id)) == before
    assert [row.SerializeToString() for row in col.get_review_logs(card.id)] == logs


def test_exact_known_legacy_templates_upgrade_without_resetting_review(col, exercise, monkeypatch):
    note = introduce(col, exercise)
    card = note.cards()[0]
    card.start_timer()
    col.sched.answerCard(card, 3)
    before = snapshot(col.get_card(card.id))
    model = col.models.by_name(adapter.MODEL_NAME)
    model["tmpls"][0]["qfmt"] = "{{Prompt}} legacy-front"
    model["tmpls"][0]["afmt"] = "{{Answer}} legacy-back"
    model["css"] = "/* legacy */"
    col.models.update_dict(model)
    monkeypatch.setattr(adapter, "_LEGACY_TEMPLATE_HASHES", {adapter._template_hashes(model)})
    assert adapter.template_status(col)["status"] == "upgradable"
    adapter.ensure_model(col)
    assert adapter.template_status(col)["status"] == "current"
    assert snapshot(col.get_card(card.id)) == before


def test_custom_templates_require_explicit_restore_and_have_native_backup(col, exercise):
    note = introduce(col, exercise)
    cid = note.cards()[0].id
    model = col.models.by_name(adapter.MODEL_NAME)
    custom = "{{Prompt}} My own front template"
    model["tmpls"][0]["qfmt"] = custom
    col.models.update_dict(model)
    assert adapter.template_status(col)["status"] == "customized"
    adapter.ensure_model(col)
    assert col.models.by_name(adapter.MODEL_NAME)["tmpls"][0]["qfmt"] == custom
    result = adapter.restore_course_templates(col)
    assert result["status"] == "current"
    backup = col.models.by_name(result["backup_note_type"])
    assert backup["tmpls"][0]["qfmt"] == custom
    assert adapter.template_status(col)["status"] == "current"
    assert col.get_note(note.id).cards()[0].id == cid
