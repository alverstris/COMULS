"""Pure COMULS admission and answer rules, independent of Anki and Qt.

Anki remains the sole scheduler.  These functions govern admission of NEW
exercises; callers must never apply them to hide already introduced reviews.
CEFR sublevels are local curriculum bands, not certified test scores.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

LEVELS = ("A2", "A2+", "B1", "B1+", "B2", "B2+", "C1", "C1+", "C2")
STAGES = LEVELS  # Compatibility alias for curriculum integration.
ENTRY_LEVELS = ("B1", "B2", "C1")
EXERCISE_TYPES = (
    "meaning_recall", "french_form_recall", "vocabulary_cloze",
    "grammar_cloze", "grammar_meaning_choice", "sentence_transformation",
    "sound_discrimination", "connected_word_recognition",
    "sentence_reconstruction", "partial_dictation",
    "sentence_transcription", "audio_transcript_choice", "audio_meaning_choice",
)
SYNTHESIS_TYPES = frozenset((
    "vocabulary_cloze", "grammar_cloze", "sentence_transformation",
    "sentence_reconstruction",
))
CHOICE_TYPES = frozenset((
    "grammar_meaning_choice", "sound_discrimination",
    "audio_transcript_choice", "audio_meaning_choice",
))
AUDIO_TYPES = frozenset((
    "sound_discrimination", "connected_word_recognition",
    "sentence_reconstruction", "partial_dictation",
    "sentence_transcription", "audio_transcript_choice", "audio_meaning_choice",
))
CEILING_OFFSETS = {
    "meaning_recall": 0, "french_form_recall": 0,
    "vocabulary_cloze": -1, "grammar_cloze": -1,
    "grammar_meaning_choice": 0, "sentence_transformation": -1,
    "sound_discrimination": 1, "connected_word_recognition": 0,
    "sentence_reconstruction": -1, "partial_dictation": 1,
    "sentence_transcription": 1, "audio_transcript_choice": 2,
    "audio_meaning_choice": 2,
}
DEFAULT_SESSION_SECONDS = 15 * 60
MAX_NEW_UNITS = 6
MAX_NEW_CARDS = 8
POLICIES = frozenset(("strict", "punctuation"))

_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u02bc": "'",
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u00a0": " ", "\u202f": " ",
})


def normalize_answer(text: str, policy: str = "strict") -> str:
    """Normalize typography, case and spacing, while retaining French accents.

    'strict' assesses lexical spelling but ignores final sentence punctuation.
    'punctuation' additionally assesses that punctuation. Neither policy strips
    accents, permits fuzzy spelling, or drops words/internal punctuation.
    """
    if policy not in POLICIES:
        raise ValueError("Unknown answer policy: " + str(policy))
    if not isinstance(text, str):
        raise TypeError("An answer must be text")
    value = unicodedata.normalize("NFC", text).translate(_TRANSLATION).casefold()
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s*'\s*", "'", value)
    value = re.sub(r"\s*-\s*", "-", value)
    if policy == "strict":
        value = re.sub(r"[.!?…]+\s*$", "", value).rstrip()
    return value


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_pack(pack: Any) -> list[str]:
    """Return actionable validation errors; never execute content from a pack."""
    errors: list[str] = []
    if not isinstance(pack, dict):
        return ["pack must be an object"]
    if type(pack.get("schema_version")) is not int or pack["schema_version"] != 1:
        errors.append("schema_version must be 1")
    for field in ("pack_id", "version"):
        if not _nonempty(pack.get(field)):
            errors.append(field + " must be nonempty text")
    exercises = pack.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        return errors + ["exercises must be a nonempty list"]
    seen: set[str] = set()
    for index, exercise in enumerate(exercises):
        prefix = "exercises[" + str(index) + "]"
        if not isinstance(exercise, dict):
            errors.append(prefix + " must be an object")
            continue
        identity = exercise.get("id")
        if not _nonempty(identity):
            errors.append(prefix + ".id must be nonempty text")
        elif identity in seen:
            errors.append(prefix + ".id duplicates " + identity)
        else:
            seen.add(identity)
        kind = exercise.get("type")
        if kind not in EXERCISE_TYPES:
            errors.append(prefix + ".type is unsupported")
            kind = ""
        for field in ("level", "target_level", "carrier_level", "construction_level"):
            if field == "level" or field in exercise:
                if exercise.get(field) not in LEVELS:
                    errors.append(prefix + "." + field + " is not a supported level")
        entry_levels = exercise.get("entry_levels")
        if (not isinstance(entry_levels, list) or not entry_levels
                or any(level not in ENTRY_LEVELS for level in entry_levels)):
            errors.append(prefix + ".entry_levels must name B1, B2 and/or C1")
        elif len(entry_levels) != len(set(entry_levels)):
            errors.append(prefix + ".entry_levels must be unique")
        for field in ("prompt", "answer", "unit_id"):
            if not _nonempty(exercise.get(field)):
                errors.append(prefix + "." + field + " must be nonempty text")
        for field in ("prerequisites", "exposure_groups", "accepted"):
            items = exercise.get(field, [])
            if not isinstance(items, list) or any(not _nonempty(v) for v in items):
                errors.append(prefix + "." + field + " must be a list of nonempty strings")
        if exercise.get("answer_policy", "strict") not in POLICIES:
            errors.append(prefix + ".answer_policy is unsupported")
        qa = exercise.get("qa")
        if not isinstance(qa, dict) or qa.get("ready") is not True:
            errors.append(prefix + ".qa.ready must be true; quarantine unfinished exercises")
        if not isinstance(exercise.get("provenance"), dict):
            errors.append(prefix + ".provenance must be an object")
        if kind in AUDIO_TYPES and not (
            _nonempty(exercise.get("audio_text"))
            or _nonempty(exercise.get("audio_file"))
        ):
            errors.append(prefix + " requires audio_text or audio_file")
        if "estimated_seconds" in exercise:
            value = exercise["estimated_seconds"]
            if not _finite_number(value) or value <= 0:
                errors.append(prefix + ".estimated_seconds must be a positive finite number")
        if kind in CHOICE_TYPES:
            choices = exercise.get("choices")
            if not isinstance(choices, list) or not 2 <= len(choices) <= 3:
                errors.append(prefix + ".choices must contain two or three options")
                continue
            option_ids: set[str] = set()
            correct = 0
            for option in choices:
                if not isinstance(option, dict):
                    errors.append(prefix + ".choices contains a non-object option")
                    continue
                option_id = option.get("id")
                if not _nonempty(option_id):
                    errors.append(prefix + ".choices requires nonempty stable IDs")
                elif option_id in option_ids:
                    errors.append(prefix + ".choices has duplicate ID " + option_id)
                else:
                    option_ids.add(option_id)
                if not _nonempty(option.get("text")):
                    errors.append(prefix + ".choices requires nonempty option text")
                if type(option.get("correct")) is not bool:
                    errors.append(prefix + ".choices.correct must be boolean")
                elif option["correct"]:
                    correct += 1
            if correct != 1:
                errors.append(prefix + ".choices requires exactly one correct option")
        if "tokens" in exercise:
            tokens = exercise["tokens"]
            if not isinstance(tokens, list) or not tokens:
                errors.append(prefix + ".tokens must be a nonempty list")
            else:
                token_ids: set[str] = set()
                for token in tokens:
                    if not isinstance(token, dict) or not _nonempty(token.get("id")) or not _nonempty(token.get("text")):
                        errors.append(prefix + ".tokens requires stable IDs and text")
                        continue
                    if token["id"] in token_ids:
                        errors.append(prefix + ".tokens has duplicate ID " + token["id"])
                    token_ids.add(token["id"])
        # Every advertised entry point must respect the actual task complexity,
        # including familiar carrier language and the grammar construction.
        if isinstance(entry_levels, list) and kind in CEILING_OFFSETS:
            levels = [exercise.get(field, exercise.get("level"))
                      for field in ("level", "target_level", "carrier_level", "construction_level")]
            if all(level in LEVELS for level in levels):
                maximum = max(LEVELS.index(level) for level in levels)
                for stage in entry_levels:
                    if stage in ENTRY_LEVELS and maximum > LEVELS.index(stage) + CEILING_OFFSETS[kind]:
                        errors.append(prefix + " exceeds " + stage + " ceiling for " + kind)
    return errors


def load_pack(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        pack = json.load(handle)
    errors = validate_pack(pack)
    if errors:
        raise ValueError("Invalid COMULS pack:\n" + "\n".join(errors))
    return pack


def level_eligible(exercise: dict[str, Any], stage: str) -> bool:
    """Pure admission-level gate; no budgets, familiarity, QA or scheduling.

    This can withdraw an admitted but never-reviewed card on a stage change.
    It must never be used to hide already reviewed cards from Anki's due queue.
    """
    kind = exercise.get("type")
    if stage not in ENTRY_LEVELS or kind not in EXERCISE_TYPES:
        return False
    if stage not in exercise.get("entry_levels", []):
        return False
    ceiling = LEVELS.index(stage) + CEILING_OFFSETS[kind]
    levels = [exercise.get(field, exercise.get("level"))
              for field in ("level", "target_level", "carrier_level", "construction_level")]
    return all(level in LEVELS and LEVELS.index(level) <= ceiling for level in levels)


def admission_decision(
    exercise: dict[str, Any], stage: str, familiarised: bool,
    understood: set[str], enabled: set[str], budget: dict[str, Any],
) -> dict[str, Any]:
    """Decide NEW-card admission, with machine-readable reason codes.

    Budget new_units/admitted_cards are used counts, not remaining allowances.
    remaining_seconds counts active study time. due_seconds reserves time for
    Anki reviews. override bypasses backlog/pause pressure only; it cannot waive
    content readiness, prerequisites, level ceilings or daily caps.
    """
    reasons: list[str] = []
    kind = exercise.get("type")
    if stage not in ENTRY_LEVELS:
        reasons.append("unsupported_stage")
    if kind not in EXERCISE_TYPES:
        reasons.append("unsupported_type")
    if kind not in enabled:
        reasons.append("exercise_disabled")
    if stage not in exercise.get("entry_levels", []):
        reasons.append("entry_level_unavailable")
    if exercise.get("qa", {}).get("ready") is not True:
        reasons.append("content_not_ready")
    if stage in ENTRY_LEVELS and kind in CEILING_OFFSETS:
        ceiling = LEVELS.index(stage) + CEILING_OFFSETS[kind]
        for field in ("level", "target_level", "carrier_level", "construction_level"):
            level = exercise.get(field, exercise.get("level"))
            if level not in LEVELS:
                reasons.append("invalid_" + field)
            elif LEVELS.index(level) > ceiling:
                reasons.append(field + "_above_ceiling")
    if not familiarised:
        reasons.append("familiarisation_required")
    prerequisites = exercise.get("prerequisites", [])
    if not isinstance(prerequisites, list):
        reasons.append("invalid_prerequisites")
        missing = []
    else:
        missing = sorted({value for value in prerequisites
                          if isinstance(value, str) and value not in understood})
        if any(not isinstance(value, str) for value in prerequisites):
            reasons.append("invalid_prerequisites")
        if missing:
            reasons.append("prerequisites_missing")
    remaining = budget.get("remaining_seconds", DEFAULT_SESSION_SECONDS)
    due = budget.get("due_seconds", 0)
    used_units = budget.get("new_units", 0)
    used_cards = budget.get("admitted_cards", 0)
    estimate = exercise.get("estimated_seconds", 25)
    if any(not _finite_number(value) or value < 0
           for value in (remaining, due, used_units, used_cards, estimate)):
        reasons.append("invalid_budget")
    else:
        if remaining <= 0 or estimate > remaining:
            reasons.append("session_budget_exhausted")
        if used_cards >= MAX_NEW_CARDS:
            reasons.append("daily_card_limit")
        if not exercise.get("unit_already_introduced", False) and used_units >= MAX_NEW_UNITS:
            reasons.append("daily_unit_limit")
        if not budget.get("override", False):
            if budget.get("pause_new", False):
                reasons.append("new_admission_paused")
            if due > 0 and due + estimate > remaining:
                reasons.append("review_backlog")
    return {"allowed": not reasons, "reasons": reasons, "missing_prerequisites": missing}


def _response_text(exercise: dict[str, Any], response: Any) -> str | None:
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        value = response.get("text", response.get("choice_id"))
        return value if isinstance(value, str) else None
    if isinstance(response, list) and exercise.get("type") == "sentence_reconstruction":
        tokens = exercise.get("tokens", [])
        lookup = {token["id"]: token["text"] for token in tokens}
        # IDs, not a tile's current position, identify a response. Repeated
        # equivalent words can exchange IDs without becoming spelling errors.
        if any(not isinstance(item, str) or item not in lookup for item in response):
            return None
        if len(response) != len(tokens) or len(set(response)) != len(response):
            return None
        return " ".join(lookup[item] for item in response)
    return None


def evaluate_answer(exercise: dict[str, Any], response: Any) -> dict[str, Any]:
    """Offer objective feedback where safe; Anki's final rating remains the user’s.

    None/empty means no captured attempt and never implies failure. Semantic
    recall and unenumerated transformations require honest self-comparison.
    """
    reference = exercise.get("answer", "")
    result: dict[str, Any] = {"status": "self_compare", "reference": reference}
    text = _response_text(exercise, response)
    if text is None or not text.strip():
        return result
    kind = exercise.get("type")
    if kind == "meaning_recall":
        return result
    if kind in CHOICE_TYPES:
        option = next((item for item in exercise.get("choices", []) if item.get("id") == text), None)
        result["status"] = "correct" if option and option.get("correct") is True else "incorrect"
        return result
    if kind not in EXERCISE_TYPES:
        return result
    policy = exercise.get("answer_policy", "strict")
    alternatives = [reference] + exercise.get("accepted", [])
    normalized = normalize_answer(text, policy)
    matched = any(normalize_answer(value, policy) == normalized for value in alternatives)
    if matched:
        result["status"] = "correct"
    elif kind != "sentence_transformation":
        result["status"] = "incorrect"
    return result


def semantic_hash(exercise: dict[str, Any]) -> str:
    """Hash the immutable retrieval contract, not editable feedback/QA labels.

    Harmless option/tile display reordering does not reset a card. Changes to
    tested prompts, alternatives, targets or audio require a new exercise ID.
    """
    fields = (
        "type", "prompt", "answer", "audio_text", "audio_file", "audio_sha256",
        "unit_id", "target_meaning", "carrier_meaning", "required_construction",
        "answer_policy", "context_id", "sense_id",
    )
    contract = {field: exercise.get(field) for field in fields}
    contract["answer_policy"] = exercise.get("answer_policy", "strict")
    contract["accepted"] = sorted(exercise.get("accepted", []))
    contract["choices"] = sorted(
        ({"id": option.get("id"), "text": option.get("text"), "correct": option.get("correct")}
         for option in exercise.get("choices", [])), key=lambda option: str(option["id"]),
    )
    contract["tokens"] = sorted(
        ({"id": token.get("id"), "text": token.get("text")}
         for token in exercise.get("tokens", [])), key=lambda token: str(token["id"]),
    )
    payload = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
