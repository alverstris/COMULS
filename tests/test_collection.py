"""Integration checks against native Anki, without importing the Qt entry point."""
from __future__ import annotations

import copy
import importlib
import json
import sys
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
    previous = col.undo_status().last_step
    state["days"] = {str(index): {"active_seconds": 5} for index in range(30)}
    adapter.save_state(col, state)
    assert col.undo_status().last_step == previous
    assert list(adapter.get_state(col)["days"]) == [str(x) for x in range(16, 30)]
    assert model["name"] == adapter.MODEL_NAME


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
    config["rev"]["perDay"] = 1
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
