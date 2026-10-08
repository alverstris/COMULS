"""Native collection adapter. Call mutating helpers inside an Anki CollectionOp.

COMULS owns admission, never due dates, intervals, ratings or FSRS settings.
Payload identity lives in note fields so pack reimports preserve native IDs.
"""
from __future__ import annotations

import copy
import hashlib
import html
import json
import time
from typing import Any

from . import core, templates

CONFIG_KEY = "comuls_v1"
MODEL_NAME = "COMULS v1"
DEFAULT_DECK_NAME = "COMULS::Practice"
FIELDS = ("COMULS_ID", "Payload", "Prompt", "Answer", "AudioText",
          "AudioFile", "PersonalNotes", "State")
DAY_RETENTION = 14


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _write_json(note: Any, field: str, value: Any) -> None:
    note[field] = html.escape(_json(value), quote=True)


def _read_json(note: Any, field: str) -> dict[str, Any]:
    try:
        result = json.loads(html.unescape(note[field]))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid COMULS {field} on native note {note.id}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"COMULS {field} must be an object on native note {note.id}")
    return result


def note_payload(note: Any) -> dict[str, Any]:
    return _read_json(note, "Payload")


def note_state(note: Any) -> dict[str, Any]:
    return _read_json(note, "State")


def get_state(col: Any) -> dict[str, Any]:
    result = {
        "schema_version": 1, "stage": "B1", "budget_minutes": 15,
        "enabled": list(core.EXERCISE_TYPES), "audio_confirmed": False,
        "days": {}, "manager_id": None, "deck_id": None,
    }
    saved = col.get_config(CONFIG_KEY, default=None)
    if saved is not None:
        if not isinstance(saved, dict):
            raise ValueError("COMULS control state is invalid; restore a backup.")
        result.update(copy.deepcopy(saved))
    if result["stage"] not in core.ENTRY_LEVELS:
        raise ValueError("COMULS entry stage must be B1, B2 or C1.")
    return result


def save_state(col: Any, state: dict[str, Any]) -> Any:
    """Save small synced controls without creating or clearing native undo."""
    saved = copy.deepcopy(state)
    if saved.get("stage") not in core.ENTRY_LEVELS:
        raise ValueError("COMULS entry stage must be B1, B2 or C1.")
    days = saved.get("days", {})
    if not isinstance(days, dict):
        raise ValueError("COMULS day records must be an object.")
    # Day keys are native scheduler day numbers or ISO dates. Handle both.
    def day_key(value: str) -> tuple[int, Any]:
        try:
            return (1, int(value))
        except (ValueError, TypeError):
            return (0, str(value))
    saved["days"] = {
        str(day): days[day]
        for day in sorted(days, key=day_key)[-DAY_RETENTION:]
    }
    if len(_json(saved).encode("utf-8")) > 8192:
        raise ValueError("COMULS control state exceeds its 8 KiB limit; keep telemetry local.")
    return col.set_config(CONFIG_KEY, saved, undoable=False)


def ensure_model(col: Any) -> dict[str, Any]:
    model = col.models.by_name(MODEL_NAME)
    if model is not None:
        actual = tuple(field["name"] for field in model["flds"])
        if actual != FIELDS or len(model["tmpls"]) != 1:
            raise ValueError("COMULS note type was structurally edited; migrate explicitly.")
        # Do not silently overwrite a user's templates or styling.
        return model
    model = col.models.new(MODEL_NAME)
    for name in FIELDS:
        col.models.add_field(model, col.models.new_field(name))
    template = col.models.new_template("Practice")
    template["qfmt"] = templates.front_template()
    template["afmt"] = templates.back_template()
    col.models.add_template(model, template)
    model["css"] = templates.css()
    result = col.models.add_dict(model)
    return col.models.get(result.id)


def ensure_deck(col: Any, state: dict[str, Any]) -> int:
    """Reuse a stored ID, including renamed decks; never relocate existing notes."""
    existing = state.get("deck_id")
    if existing is not None:
        if type(existing) is not int or col.decks.get_legacy(existing) is None:
            raise ValueError("The COMULS practice deck was deleted. Restore it or migrate explicitly.")
        return existing
    # If managed notes already exist, recover their single current deck instead
    # of moving them to a newly created default deck.
    notes = exercise_notes(col)
    deck_ids = {int(card.odid or card.did)
                for note in notes.values() for card in note.cards()}
    if len(deck_ids) > 1:
        raise ValueError("Managed cards span multiple decks; choose a migration explicitly.")
    if deck_ids:
        deck_id = deck_ids.pop()
        if col.decks.get_legacy(deck_id) is None:
            raise ValueError("The existing COMULS deck is missing.")
    else:
        deck_id = int(col.decks.add_normal_deck_with_name(DEFAULT_DECK_NAME).id)
    state["deck_id"] = deck_id
    save_state(col, state)
    return deck_id


def exercise_notes(col: Any) -> dict[str, Any]:
    model = col.models.by_name(MODEL_NAME)
    if model is None:
        return {}
    result: dict[str, Any] = {}
    for nid in col.models.nids(model["id"]):
        note = col.get_note(nid)
        identity = note["COMULS_ID"]
        if not identity:
            raise ValueError(f"Managed note {nid} has no COMULS identity.")
        if identity in result:
            raise ValueError(f"Duplicate COMULS identity {identity}; resolve the duplicate before continuing.")
        result[identity] = note
    return result


def _authored_fields(exercise: dict[str, Any]) -> dict[str, str]:
    audio = exercise.get("type") in core.AUDIO_TYPES
    filename = exercise.get("audio_file", "") if audio else ""
    if filename:
        # Shared content may name collection media, not paths or commands.
        if not isinstance(filename, str) or any(c in filename for c in "/\\:\r\n[]"):
            raise ValueError("Audio filenames must be safe collection-media basenames.")
        filename = f"[sound:{filename}]"
    return {
        "Prompt": html.escape(exercise["prompt"], quote=True),
        "Answer": html.escape(exercise["answer"], quote=True),
        "AudioText": html.escape(exercise.get("audio_text", "") if audio else "", quote=True),
        "AudioFile": filename,
    }


def _check_existing(note: Any, exercise: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    previous = note_payload(note)
    state = note_state(note)
    if previous.get("id") != note["COMULS_ID"] or previous.get("id") != exercise.get("id"):
        raise ValueError("COMULS note identity does not match its payload.")
    if state.get("authored_hash") != _hash(previous):
        raise ValueError(f"Payload for {exercise['id']} was edited locally; preserve it and resolve the conflict.")
    if core.semantic_hash(previous) != core.semantic_hash(exercise):
        raise ValueError(f"Exercise {exercise['id']} changed its retrieval contract; use a new ID.")
    for field, expected in _authored_fields(previous).items():
        if note[field] != expected:
            raise ValueError(f"{field} for {exercise['id']} was edited locally; resolve the conflict before importing.")
    return previous, state


def prepare_exercise(col: Any, exercise: dict[str, Any], day: int | str) -> int:
    """Upsert content safely and create new cards paused for familiarisation.

    Preparation itself is not evidence that the learner has understood content.
    """
    if not isinstance(exercise.get("id"), str) or not exercise["id"]:
        raise ValueError("An exercise requires a stable nonempty ID.")
    fields = _authored_fields(exercise)
    model = ensure_model(col)
    notes = exercise_notes(col)
    note = notes.get(exercise["id"])
    if note is not None:
        previous, state = _check_existing(note, exercise)
        if previous != exercise:
            _write_json(note, "Payload", exercise)
            state["authored_hash"] = _hash(exercise)
            state["semantic_hash"] = core.semantic_hash(exercise)
            _write_json(note, "State", state)
            for name, value in fields.items():
                note[name] = value
            col.update_note(note)
        return int(note.id)

    state_controls = get_state(col)
    deck_id = ensure_deck(col, state_controls)
    note = col.new_note(model)
    note["COMULS_ID"] = exercise["id"]
    _write_json(note, "Payload", exercise)
    for name, value in fields.items():
        note[name] = value
    note["PersonalNotes"] = ""
    _write_json(note, "State", {
        "lifecycle": "prepared", "managed_pause": "preparation",
        "familiarised_day": None, "admitted_day": None,
        "prepared_day": str(day), "unit_id": exercise.get("unit_id", exercise["id"]),
        "authored_hash": _hash(exercise), "semantic_hash": core.semantic_hash(exercise),
    })
    note.add_tag("comuls::managed")
    col.add_note(note, deck_id)
    cards = note.cards()
    if len(cards) != 1:
        raise ValueError("A COMULS exercise must generate exactly one native card.")
    col.sched.suspend_cards([card.id for card in cards])
    return int(note.id)


def mark_familiarised(col: Any, exercise_id: str, day: int | str) -> int:
    """Record completed ungraded exposure, after UI confirms completion."""
    note = exercise_notes(col).get(exercise_id)
    if note is None:
        raise ValueError("Prepare the exercise before recording familiarisation.")
    payload = note_payload(note)
    _, state = _check_existing(note, payload)
    if state.get("familiarised_day") is None:
        state["familiarised_day"] = str(day)
        _write_json(note, "State", state)
        col.update_note(note)
    return int(note.id)


def activate_exercise(col: Any, exercise: dict[str, Any], day: int | str) -> int:
    """Admit an already familiarised exercise; caller applies full core budget gates."""
    note = exercise_notes(col).get(exercise["id"])
    if note is None:
        raise ValueError("Prepare and familiarise an exercise before admitting it.")
    _, state = _check_existing(note, exercise)
    cards = note.cards()
    if len(cards) != 1:
        raise ValueError("A COMULS exercise must have exactly one native card.")
    card = cards[0]
    # Established reviews remain entirely under native Anki scheduling.
    if card.reps > 0:
        return int(note.id)
    if not core.level_eligible(exercise, get_state(col)["stage"]):
        raise ValueError("This exercise is outside the current entry-stage gate.")
    if state.get("familiarised_day") is None:
        raise ValueError("Complete supported familiarisation before admission.")
    if state.get("lifecycle") == "admitted" and not state.get("managed_pause"):
        if card.queue < 0:
            raise ValueError("This card was manually paused; COMULS will not resume it.")
        return int(note.id)
    if state.get("managed_pause") not in ("preparation", "stage"):
        raise ValueError("This card is not paused by COMULS; preserve its native state.")
    # Only Anki's native new-card suspension can be released here.
    if card.type != 0 or card.queue not in (-1, 0):
        raise ValueError("The card has an unexpected native state; inspect it in Anki.")
    if card.queue == -1:
        col.sched.unsuspend_cards([card.id])
    state.update(lifecycle="admitted", managed_pause=None, admitted_day=str(day))
    _write_json(note, "State", state)
    col.update_note(note)
    return int(note.id)


def stage_change(col: Any, newstage: str, catalog: Any = None) -> dict[str, int]:
    """Withdraw only admitted, never-reviewed cards; retain all introduced reviews."""
    if newstage not in core.ENTRY_LEVELS:
        raise ValueError("Choose the B1, B2 or C1 entry route.")
    notes = exercise_notes(col)
    planned: list[tuple[Any, dict[str, Any], list[int]]] = []
    retained = 0
    for note in notes.values():
        payload = note_payload(note)
        _, state = _check_existing(note, payload)
        cards = note.cards()
        if any(card.reps > 0 for card in cards):
            retained += len(cards)
            continue
        if state.get("lifecycle") != "admitted" or core.level_eligible(payload, newstage):
            continue
        # A manually suspended/buried card remains the user's pause, not ours.
        active = [card.id for card in cards if card.queue == 0 and card.type == 0]
        if active and not state.get("managed_pause"):
            planned.append((note, state, active))
    for note, state, ids in planned:
        col.sched.suspend_cards(ids)
        state.update(lifecycle="prepared", managed_pause="stage")
        # Preserve historical admission day so a rollback cannot reset daily caps.
        _write_json(note, "State", state)
        col.update_note(note)
    controls = get_state(col)
    controls["stage"] = newstage
    save_state(col, controls)
    return {"withdrawn": sum(len(ids) for _, _, ids in planned),
            "retained_reviews": retained}


def stats(col: Any) -> dict[str, Any]:
    controls = get_state(col)
    deck_id = controls.get("deck_id")
    model = col.models.by_name(MODEL_NAME)
    rows = []
    if model is not None:
        # Read-only SQL is intentional. All native writes use supported APIs.
        rows = col.db.all(
            "select c.id, c.reps, c.queue, c.type, c.due from cards c "
            "join notes n on n.id=c.nid where n.mid=?", model["id"])
    today = int(col.sched.today)
    now = int(time.time())
    learning = sum(1 for _, _, queue, _, _ in rows if queue in (1, 3))
    due = sum(1 for _, _, queue, _, value in rows
              if (queue == 2 and value <= today)
              or (queue == 1 and value <= now)
              or (queue == 3 and value <= today))
    # Report the raw backlog separately from the scheduler-limited session.
    available_due = due
    if deck_id is not None and col.decks.get_legacy(deck_id) is not None:
        tree = col.sched.deck_due_tree(deck_id)
        if tree is not None:
            available_due = int(tree.review_count + tree.learn_count)
    return {
        "total": len(rows), "reviewed": sum(1 for _, reps, _, _, _ in rows if reps > 0),
        "new": sum(1 for _, _, queue, _, _ in rows if queue == 0),
        "due": due, "available_due": available_due,
        "learning": learning, "native_day": today, "deck_id": deck_id,
    }
