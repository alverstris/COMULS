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
from .evidence import timestamp

CONFIG_KEY = "comuls_v1"
STAGE_KEY = "comuls_stage_v1"
MODEL_NAME = "COMULS v1"
DEFAULT_DECK_NAME = "COMULS::Practice"
FIELDS = ("COMULS_ID", "Payload", "Prompt", "Answer", "AudioText",
          "AudioFile", "PersonalNotes", "State", "MediaRefs")
DAY_RETENTION = 14
EVIDENCE_RETENTION = 12
EVIDENCE_PREFIX = "comuls_evidence_v1_"
TEMPLATE_KEY = "comuls_template_hashes_v1"
# Exact qfmt/afmt/css SHA-256 values regenerated from the published
# tester-0.1.7 tag. Only the complete matching set permits automatic migration.
_LEGACY_TEMPLATE_HASHES = {
    ("f9d92e276317fb5b2345d149008a6c5947a648a4180fbea0825d73d5331b1a55",
     "7aa6b5bffbaca441c762a0d4ba36a2322aed7792ef3bf666f21c790b43093729",
     "0eef3d06363ee29acfa81e9ab4ee97ded77b4228aa33f217d4542c6a7aeeb290"),
}


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


def _evidence_key(exercise_id: str) -> str:
    return EVIDENCE_PREFIX + hashlib.sha256(exercise_id.encode("utf-8")).hexdigest()[:32]


def _evidence_record(col: Any, exercise_id: str) -> dict[str, Any]:
    value = col.get_config(_evidence_key(exercise_id), default={})
    if not isinstance(value, dict):
        raise ValueError("COMULS evidence metadata is invalid; native review history is intact.")
    return copy.deepcopy(value)


def _save_evidence(col: Any, exercise_id: str, value: dict[str, Any]) -> None:
    if len(_json(value).encode("utf-8")) > 8192:
        raise ValueError("COMULS evidence metadata exceeds its bounded record size.")
    # Facts about what was seen are not undone when a native grade is undone.
    # This also avoids inserting a second undo step after a native rating.
    col.set_config(_evidence_key(exercise_id), value, undoable=False)


def evidence_state(col: Any, note: Any) -> dict[str, Any]:
    """Overlay bounded durable exposure facts and revlog-linked assistance data."""
    result = note_state(note)
    extra = _evidence_record(col, note["COMULS_ID"])
    if (timestamp(extra.get("last_exposed_at")) or 0) >= (timestamp(result.get("last_exposed_at")) or 0):
        result.update({k: extra[k] for k in ("last_exposed_at", "last_exposed_day", "last_exposed_by") if k in extra})
    result["review_evidence"] = extra.get("review_evidence", {})
    result["native_reviews"] = [
        {"id": rid, "button_chosen": grade, "review_kind": kind}
        for card in note.cards()
        for rid, grade, kind in col.db.all("select id, ease, type from revlog where cid=? order by id", card.id)
    ]
    return result


def record_reference_exposure(col: Any, exercise_id: str, exposed_at: float,
                              *, exposure_groups: Any = None) -> list[str]:
    """Record factual reference/answer exposure without creating notes or grades.

    Linked existing notes receive the fact only for explicitly declared answer
    exposure groups. Burial remains a separate native operation owned by the
    caller; reference browsing does not admit or move any exercise.
    """
    when = timestamp(exposed_at)
    if not isinstance(exercise_id, str) or not exercise_id or when is None:
        raise ValueError("Reference exposure requires a stable identity and timestamp.")
    notes = exercise_notes(col)
    groups = set(exposure_groups or [])
    if exercise_id in notes:
        groups.update(note_payload(notes[exercise_id]).get("exposure_groups", []))
    identities = {exercise_id}
    if groups:
        identities.update(identity for identity, note in notes.items()
                          if groups.intersection(note_payload(note).get("exposure_groups", [])))
    for identity in sorted(identities):
        value = _evidence_record(col, identity)
        if when >= (timestamp(value.get("last_exposed_at")) or 0):
            value.update(last_exposed_at=when, last_exposed_day=str(col.sched.today),
                         last_exposed_by=exercise_id)
            _save_evidence(col, identity, value)
    return sorted(identities)


def record_review_evidence(col: Any, exercise_id: str, event: dict[str, Any]) -> str | None:
    """Attach optional assistance observations to an already committed native grade.

    The caller supplies the live card ID and question-time exposure snapshot.
    Only the exact latest native record, agreeing on card and grade, is accepted.
    Unknown or missing capture metadata never becomes verified independence.
    """
    note = exercise_notes(col).get(exercise_id)
    if note is None:
        return None
    cards = {int(card.id): card for card in note.cards()}
    cid = event.get("card_id")
    if type(cid) is not int or cid not in cards:
        return None
    rows = col.db.all("select id, ease, type from revlog where cid=? order by id desc limit 1", cid)
    if not rows:
        return None
    rid, grade, kind = rows[0]
    if (grade != event.get("ease") or grade not in (1, 2, 3, 4)
            or kind not in (0, 1, 2, 3) or abs(time.time() - int(rid) / 1000) > 60):
        return None
    value = _evidence_record(col, exercise_id)
    observations = value.setdefault("review_evidence", {})
    if not isinstance(observations, dict):
        observations = value["review_evidence"] = {}
    known = (type(event.get("target_hint")) is bool
             and type(event.get("carrier_help")) is bool
             and type(event.get("replays")) is int
             and event.get("replays", -1) >= 0
             and type(event.get("prior_exposure_today")) is bool
             and event.get("capture_phase") in ("question", "no_submission", "after_exposure"))
    record = {key: event[key] for key in (
        "outcome", "target_hint", "carrier_help", "replays", "capture_phase",
        "prior_exposure_today", "submitted",
    ) if key in event and (event[key] is None or isinstance(event[key], (str, int, bool)))}
    record.update(assistance_known=known, prior_exposed_at=timestamp(event.get("prior_exposed_at")),
                  study_day=str(col.sched.today))
    observations[str(rid)] = record
    # Missing native IDs are retained briefly for redo, but summary credit always
    # requires that ID to be present in current native review history.
    value["review_evidence"] = {key: observations[key] for key in sorted(observations, key=int)[-EVIDENCE_RETENTION:]}
    _save_evidence(col, exercise_id, value)
    return str(rid)


def declare_understood(col: Any, exercise_id: str, support_ids: list[str],
                       *, target: bool = False, declared_at: float | None = None,
                       newly_learned_ids: list[str] | None = None,
                       day: int | str | None = None) -> int:
    """Persist explicit exact-support declarations; never fabricate a native grade."""
    note = exercise_notes(col).get(exercise_id)
    if note is None:
        raise ValueError("Prepare the exercise before recording its comprehension declarations.")
    exercise = note_payload(note)
    _, state = _check_existing(note, exercise)
    allowed = {item["id"] for item in exercise.get("support_units", []) if isinstance(item, dict) and "id" in item}
    if (not isinstance(support_ids, list) or any(not isinstance(identity, str) for identity in support_ids)
            or not set(support_ids).issubset(allowed)):
        raise ValueError("Declarations must identify exact support units shown for this exercise.")
    newly_learned_ids = [] if newly_learned_ids is None else newly_learned_ids
    if (not isinstance(newly_learned_ids, list)
            or any(not isinstance(identity, str) for identity in newly_learned_ids)
            or not set(newly_learned_ids).issubset(set(support_ids))):
        raise ValueError("Newly learned support must be among the exact understood declarations.")
    try:
        learned_day = int(col.sched.today if day is None else day)
    except (ValueError, TypeError):
        raise ValueError("Support learning requires the native scheduler day.")
    when = timestamp(time.time() if declared_at is None else declared_at)
    if when is None:
        raise ValueError("A comprehension declaration requires a valid timestamp.")
    state["understood_support"] = sorted(set(state.get("understood_support", [])) | set(support_ids))
    state["declared_understood_at"] = when
    learned_days = state.setdefault("support_learned_days", {})
    for identity in newly_learned_ids:
        learned_days[identity] = str(min(learned_day, int(learned_days.get(identity, learned_day))))
    if target:
        state["declared_understood"] = True
    _write_json(note, "State", state)
    col.update_note(note)
    return int(note.id)


def get_state(col: Any) -> dict[str, Any]:
    result = {
        "schema_version": 1, "stage": "B1", "stage_confirmed": False, "budget_minutes": 15,
        "enabled": list(core.EXERCISE_TYPES), "audio_confirmed": False,
        "days": {}, "manager_id": None, "deck_id": None,
    }
    saved = col.get_config(CONFIG_KEY, default=None)
    if saved is not None:
        if not isinstance(saved, dict):
            raise ValueError("COMULS control state is invalid; restore a backup.")
        result.update(copy.deepcopy(saved))
    separate_stage = col.get_config(STAGE_KEY, default=None)
    if separate_stage is not None:
        result["stage"] = separate_stage
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
    # Seed a separate stage key once; settings/time writes never replace it.
    # This lets native undo restore a stage action without rolling back clocks.
    if col.get_config(STAGE_KEY, default=None) is None:
        col.set_config(STAGE_KEY, saved["stage"], undoable=False)
    saved.pop("stage", None)
    return col.set_config(CONFIG_KEY, saved, undoable=False)


def ensure_model(col: Any) -> dict[str, Any]:
    model = col.models.by_name(MODEL_NAME)
    if model is not None:
        actual = tuple(field["name"] for field in model["flds"])
        if actual == FIELDS[:-1] and len(model["tmpls"]) == 1:
            # Append only: existing note/card IDs, template ordinals and field
            # positions remain stable across the tester-to-Imperial migration.
            col.models.add_field(model, col.models.new_field("MediaRefs"))
            col.models.update_dict(model)
            model = col.models.get(model["id"])
            actual = tuple(field["name"] for field in model["flds"])
        if actual != FIELDS or len(model["tmpls"]) != 1:
            raise ValueError("COMULS note type was structurally edited; migrate explicitly.")
        status = template_status(col)
        if status["status"] == "upgradable":
            _install_templates(col, model)
            return col.models.get(model["id"])
        # Unknown/local template edits are preserved. The UI offers explicit
        # restoration with a native backup; nothing silently overwrites them.
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
    col.set_config(TEMPLATE_KEY, {"model_id": int(result.id), "hashes": list(_template_hashes(model))}, undoable=False)
    return col.models.get(result.id)


def _template_hashes(model: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in (
        model["tmpls"][0]["qfmt"], model["tmpls"][0]["afmt"], model["css"],
    ))


def template_status(col: Any) -> dict[str, Any]:
    """Read-only template compatibility check for upgrade/onboarding messages."""
    model = col.models.by_name(MODEL_NAME)
    if model is None:
        return {"status": "missing", "model_name": MODEL_NAME}
    if len(model["tmpls"]) != 1:
        return {"status": "structural_conflict", "model_name": model["name"]}
    current = _template_hashes(model)
    expected = tuple(hashlib.sha256(value.encode("utf-8")).hexdigest() for value in (
        templates.front_template(), templates.back_template(), templates.css(),
    ))
    saved = col.get_config(TEMPLATE_KEY, default={})
    previously_authored = isinstance(saved, dict) and saved.get("model_id") == model["id"] and tuple(saved.get("hashes", [])) == current
    status = ("current" if current == expected else
              "upgradable" if current in _LEGACY_TEMPLATE_HASHES or previously_authored else "customized")
    return {"status": status, "model_name": model["name"]}


def _install_templates(col: Any, model: dict[str, Any]) -> None:
    model["tmpls"][0]["qfmt"] = templates.front_template()
    model["tmpls"][0]["afmt"] = templates.back_template()
    model["css"] = templates.css()
    col.models.update_dict(model)
    col.set_config(TEMPLATE_KEY, {"model_id": int(model["id"]), "hashes": list(_template_hashes(model))}, undoable=False)


def restore_course_templates(col: Any) -> dict[str, Any]:
    """Explicit user action: save customized note type, then install current assets.

    Existing notes remain on their original model, with native IDs and history.
    The copied note type keeps the prior fields/templates/style for recovery.
    The caller groups this command in a native collection undo operation.
    """
    model = ensure_model(col)
    status = template_status(col)["status"]
    backup_name = None
    if status == "customized":
        backup = col.models.copy(model)
        backup_name = backup["name"]
    if status != "current":
        _install_templates(col, model)
    return {"status": "current", "backup_note_type": backup_name}


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
    references = []
    for choice in exercise.get("choices", []):
        media = choice.get("audio_file", "")
        if media:
            if not isinstance(media, str) or any(c in media for c in "/\\:\r\n[]"):
                raise ValueError("Audio filenames must be safe collection-media basenames.")
            references.append('<audio preload="none" src="' + html.escape(media, quote=True) + '"></audio>')
    return {
        "Prompt": html.escape(exercise["prompt"], quote=True),
        "Answer": html.escape(exercise["answer"], quote=True),
        "AudioText": html.escape(exercise.get("audio_text", "") if audio else "", quote=True),
        "AudioFile": filename,
        "MediaRefs": "".join(dict.fromkeys(references)),
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
        # The exact legacy model is migrated only in a mutation, never in a
        # read-only update preview. Its absent appended field is safely empty.
        if field == "MediaRefs" and field not in note.keys() and not expected:
            continue
        if note[field] != expected:
            raise ValueError(f"{field} for {exercise['id']} was edited locally; resolve the conflict before importing.")
    return previous, state


def _pause_snapshot(cards: list[Any]) -> dict[str, str]:
    """Native-state fingerprints detect outside changes to a managed suspension."""
    return {str(card.id): _hash({name: getattr(card, name, None) for name in (
        "nid", "did", "odid", "type", "queue", "due", "odue", "ivl", "reps", "lapses", "mod", "usn",
    )}) for card in cards}


def _owns_pause(state: dict[str, Any], cards: list[Any]) -> bool:
    expected = state.get("managed_pause_snapshot")
    return bool(expected and all(card.queue == -1 for card in cards)
                and expected == _pause_snapshot(cards))


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
            old_support = {item["id"]: item for item in previous.get("support_units", [])}
            new_support = {item["id"]: item for item in exercise.get("support_units", [])}
            unchanged_support = {identity for identity in new_support if new_support[identity] == old_support.get(identity)}
            if old_support != new_support:
                # A prior comprehension declaration cannot silently transfer to
                # a changed sense/construction even when its supplied ID repeats.
                state["understood_support"] = [identity for identity in state.get("understood_support", []) if identity in unchanged_support]
            gating_fields = ("prerequisites", "support_units", "level", "entry_levels",
                             "target_level", "carrier_level", "construction_level", "cohort", "origin_entry_level")
            if any(previous.get(field) != exercise.get(field) for field in gating_fields):
                cards = note.cards()
                if (state.get("lifecycle") == "admitted" and not state.get("managed_pause")
                        and len(cards) == 1 and cards[0].reps == 0 and cards[0].type == 0 and cards[0].queue == 0):
                    col.sched.suspend_cards([cards[0].id])
                    state.update(lifecycle="prepared", managed_pause="update",
                                 managed_pause_snapshot=_pause_snapshot(note.cards()))
            _write_json(note, "Payload", exercise)
            state["authored_hash"] = _hash(exercise)
            state["semantic_hash"] = core.semantic_hash(exercise)
            _write_json(note, "State", state)
            for name, value in fields.items():
                note[name] = value
            col.update_note(note)
        if exercise.get("retired") is True or exercise.get("content_status") in ("retired", "content_blocked"):
            retire_exercises(col, [exercise["id"]], replacement_id=exercise.get("replacement_id"))
        return int(note.id)

    if exercise.get("retired") is True or exercise.get("content_status") in ("retired", "content_blocked"):
        raise ValueError("Retired content cannot be prepared as a new exercise.")

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
    state = note_state(note)
    state["managed_pause_snapshot"] = _pause_snapshot(note.cards())
    _write_json(note, "State", state)
    col.update_note(note)
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
        record_reference_exposure(col, exercise_id, time.time())
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
    if state.get("lifecycle") in ("retired", "content_blocked"):
        raise ValueError("This exercise is retired; restore it explicitly before admission.")
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
    if state.get("managed_pause") not in ("preparation", "stage", "update"):
        raise ValueError("This card is not paused by COMULS; preserve its native state.")
    # Only Anki's native new-card suspension can be released here.
    if card.type != 0 or card.queue not in (-1, 0):
        raise ValueError("The card has an unexpected native state; inspect it in Anki.")
    if card.queue == -1:
        if not _owns_pause(state, cards):
            raise ValueError("Pause ownership is uncertain; inspect the card in Anki before resuming it.")
        col.sched.unsuspend_cards([card.id])
    state.update(lifecycle="admitted", managed_pause=None, admitted_day=str(day),
                 admission_stage=get_state(col)["stage"])
    state.pop("managed_pause_snapshot", None)
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
        origin = payload.get("cohort", payload.get("origin_entry_level"))
        on_route = not origin or origin == newstage
        # Broad entry_levels allow a B2 learner to explicitly request B1 repair.
        # They must not silently retain another cohort's unreviewed normal queue
        # after a course switch. Reviewed cards are retained above in all cases.
        if state.get("lifecycle") != "admitted" or (on_route and core.level_eligible(payload, newstage)):
            continue
        # A manually suspended/buried card remains the user's pause, not ours.
        active = [card.id for card in cards if card.queue == 0 and card.type == 0]
        if active and not state.get("managed_pause"):
            planned.append((note, state, active))
    for note, state, ids in planned:
        col.sched.suspend_cards(ids)
        state.update(lifecycle="prepared", managed_pause="stage")
        state["managed_pause_snapshot"] = _pause_snapshot(note.cards())
        # Preserve historical admission day so a rollback cannot reset daily caps.
        _write_json(note, "State", state)
        col.update_note(note)
    controls = get_state(col)
    col.set_config(STAGE_KEY, newstage, undoable=True)
    controls["stage"] = newstage
    save_state(col, controls)
    return {"withdrawn": sum(len(ids) for _, _, ids in planned),
            "retained_reviews": retained}


def set_managed_pause(col: Any, exercise_ids: list[str], paused: bool,
                      reason: str = "user") -> dict[str, Any]:
    """Pause/resume only positively attributable native suspensions.

    A manually suspended/buried card is never taken over. An existing pause for
    another reason is never cleared, and uncertain ownership requires the
    student's explicit reconciliation using Anki's own card controls.
    """
    if not isinstance(reason, str) or not reason or len(reason) > 80:
        raise ValueError("A managed pause requires a short explicit reason.")
    notes = exercise_notes(col)
    if any(identity not in notes for identity in exercise_ids):
        raise ValueError("A selected exercise no longer exists; refresh the content manager.")
    plans = []
    for identity in dict.fromkeys(exercise_ids):
        note = notes[identity]
        _, state = _check_existing(note, note_payload(note))
        cards = note.cards()
        if len(cards) != 1:
            raise ValueError("A COMULS exercise must have exactly one native card.")
        plans.append((identity, note, state, cards))
    changed, preserved = [], []
    for identity, note, state, cards in plans:
        if paused:
            if state.get("managed_pause") or any(card.queue < 0 for card in cards):
                preserved.append({"exercise_id": identity, "reason": "existing_pause"})
                continue
            col.sched.suspend_cards([card.id for card in cards])
            state.update(managed_pause=reason, managed_pause_snapshot=_pause_snapshot(note.cards()))
        else:
            if state.get("managed_pause") != reason or not _owns_pause(state, cards):
                preserved.append({"exercise_id": identity, "reason": "ownership_uncertain_or_other_reason"})
                continue
            if state.get("lifecycle") in ("retired", "content_blocked", "prepared"):
                preserved.append({"exercise_id": identity, "reason": "requires_explicit_restore_or_admission"})
                continue
            col.sched.unsuspend_cards([card.id for card in cards])
            state["managed_pause"] = None
            state.pop("managed_pause_snapshot", None)
        _write_json(note, "State", state)
        col.update_note(note)
        changed.append(identity)
    return {"changed": changed, "preserved": preserved}


def retire_exercises(col: Any, exercise_ids: list[str], *, replacement_id: str | None = None) -> dict[str, Any]:
    """Retire without deletion, moving decks, resetting dates or rewriting history."""
    notes = exercise_notes(col)
    if any(identity not in notes for identity in exercise_ids):
        raise ValueError("Only existing exercises can be retired.")
    if replacement_id is not None and (not isinstance(replacement_id, str) or not replacement_id or replacement_id in exercise_ids):
        raise ValueError("A replacement must be a different stable exercise identity.")
    result = set_managed_pause(col, exercise_ids, True, "retired")
    for identity in dict.fromkeys(exercise_ids):
        note = col.get_note(notes[identity].id)
        state = note_state(note)
        if state.get("lifecycle") not in ("retired", "content_blocked"):
            state["lifecycle_before_retirement"] = state.get("lifecycle", "prepared")
        state["lifecycle"] = "retired"
        if replacement_id is not None:
            state["replacement_id"] = replacement_id
        _write_json(note, "State", state)
        col.update_note(note)
    return result


def restore_retired(col: Any, exercise_id: str) -> dict[str, Any]:
    """Restore a retired exercise while retaining any independent user suspension."""
    note = exercise_notes(col).get(exercise_id)
    if note is None:
        raise ValueError("The retired exercise no longer exists.")
    state = note_state(note)
    if state.get("lifecycle") != "retired":
        return {"changed": [], "preserved": []}
    exercise = note_payload(note)
    if exercise.get("content_status") == "content_blocked":
        raise ValueError("Content blocked by its publisher requires a corrected compatible update or replacement.")
    state["lifecycle"] = state.pop("lifecycle_before_retirement", "prepared")
    _write_json(note, "State", state)
    col.update_note(note)
    if state.get("lifecycle") == "admitted":
        return set_managed_pause(col, [exercise_id], False, "retired")
    # An unintroduced exercise must still pass preparation/admission gates.
    if state.get("managed_pause") == "retired":
        state["managed_pause"] = "preparation"
        _write_json(note, "State", state)
        col.update_note(note)
    return {"changed": [exercise_id], "preserved": []}


def preflight_update(col: Any, exercises: list[dict[str, Any]], *, retire_missing: bool = False) -> dict[str, Any]:
    """Read-only diff for a declarative update; absent delta IDs are not removals."""
    if not isinstance(exercises, list) or any(not isinstance(item, dict) for item in exercises):
        raise ValueError("The content update must be a list of exercise objects.")
    incoming: dict[str, dict[str, Any]] = {}
    for exercise in exercises:
        identity = exercise.get("id")
        if not isinstance(identity, str) or not identity or identity in incoming:
            raise ValueError("Every update requires a unique nonempty exercise identity.")
        incoming[identity] = exercise
        _authored_fields(exercise)
    report: dict[str, Any] = {"added": [], "compatible_revisions": [], "unchanged": [],
                            "material_changes": [], "conflicts": [], "retired": [],
                            "changed_prerequisites": [], "changed_support_units": [], "changed_stage_assignments": []}
    try:
        notes = exercise_notes(col)
    except ValueError as error:
        report["conflicts"].append({"exercise_id": None, "reason": str(error)})
        return report
    for identity, exercise in incoming.items():
        if exercise.get("retired") is True or exercise.get("content_status") in ("retired", "content_blocked"):
            report["retired"].append(identity)
        note = notes.get(identity)
        if note is None:
            report["added"].append(identity)
            continue
        try:
            previous = note_payload(note)
            _check_existing(note, previous)
        except (ValueError, KeyError) as error:
            report["conflicts"].append({"exercise_id": identity, "reason": str(error)})
            continue
        if core.semantic_hash(previous) != core.semantic_hash(exercise):
            report["material_changes"].append(identity)
            continue
        report["unchanged" if previous == exercise else "compatible_revisions"].append(identity)
        if previous.get("prerequisites", []) != exercise.get("prerequisites", []):
            report["changed_prerequisites"].append(identity)
        if previous.get("support_units", []) != exercise.get("support_units", []):
            report["changed_support_units"].append(identity)
        if any(previous.get(field) != exercise.get(field) for field in ("level", "entry_levels", "target_level", "carrier_level", "construction_level", "cohort", "origin_entry_level")):
            report["changed_stage_assignments"].append(identity)
    if retire_missing:
        report["retired"].extend(identity for identity in notes if identity not in incoming)
    return report


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
