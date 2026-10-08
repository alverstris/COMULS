"""Small, pure validation boundary for COMULS review messages.

No Anki imports, scheduling, grade writes, or raw-answer persistence occur here.
The caller must check live Reviewer identity and its current card before parsing.
"""
from __future__ import annotations

import json
from typing import Any

PREFIX = "comuls:"
EVENTS = frozenset(("attempt", "hint", "replay", "report", "skip"))
_IDENTITY = frozenset(("event", "nonce", "card_id", "exercise_id"))
_FIELDS = {
    "attempt": _IDENTITY | frozenset((
        "response", "selected_ids", "submitted", "target_hint",
        "carrier_help", "replays", "presentation_seed",
    )),
    "hint": _IDENTITY | frozenset(("kind", "reveals_target")),
    "replay": _IDENTITY | frozenset(("side",)),
    "report": _IDENTITY | frozenset(("reason", "side")),
    "skip": _IDENTITY | frozenset(("reason", "side")),
}


def context_matches(
    context: Any, current_reviewer: Any, reviewer_type: type,
    expected_card_id: int,
) -> bool:
    """Reject preview/browser/stale contexts before their messages are parsed."""
    if not isinstance(context, reviewer_type) or context is not current_reviewer:
        return False
    card = getattr(context, "card", None)
    identity = getattr(card, "id", None)
    return (type(identity) is int and type(expected_card_id) is int
            and expected_card_id > 0 and identity == expected_card_id)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON field")
        value[key] = item
    return value


def _invalid_constant(value: str) -> Any:
    raise ValueError("Non-finite JSON number")


def _text(value: Any, maximum: int, nonempty: bool = False) -> bool:
    return (isinstance(value, str) and len(value) <= maximum
            and (not nonempty or bool(value.strip())))


def validate_message(
    message: str, expected: dict[str, Any], maxbytes: int = 8192,
) -> dict[str, Any] | None:
    """Return a bounded, identity-matched event or None.

    Only this namespace is accepted. Unknown fields, repeated JSON fields,
    non-finite values, boolean card IDs, and unbounded responses are rejected.
    Identity values are never coerced between strings and integers.
    """
    if (not isinstance(message, str) or not message.startswith(PREFIX)
            or type(maxbytes) is not int or maxbytes <= 0):
        return None
    try:
        if len(message.encode("utf-8")) > maxbytes:
            return None
        value = json.loads(
            message[len(PREFIX):], object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return None
    if not isinstance(value, dict) or not isinstance(expected, dict):
        return None
    event = value.get("event")
    if not isinstance(event, str) or event not in EVENTS:
        return None
    if not _IDENTITY <= value.keys() or value.keys() - _FIELDS[event]:
        return None
    if (not _text(value.get("nonce"), 128, True)
            or not _text(value.get("exercise_id"), 256, True)
            or type(value.get("card_id")) is not int or value["card_id"] <= 0):
        return None
    for key in ("nonce", "card_id", "exercise_id"):
        if type(value[key]) is not type(expected.get(key)) or value[key] != expected.get(key):
            return None
    if event == "attempt":
        if (not _text(value.get("response"), 4096)
                or value.get("submitted") is not True
                or type(value.get("target_hint")) is not bool
                or type(value.get("carrier_help")) is not bool
                or type(value.get("replays")) is not int
                or not 0 <= value["replays"] <= 1000):
            return None
        selected = value.get("selected_ids")
        if (not isinstance(selected, list) or len(selected) > 256
                or any(not _text(item, 128, True) for item in selected)
                or len(set(selected)) != len(selected)):
            return None
        if "presentation_seed" in value and not _text(value["presentation_seed"], 256, True):
            return None
    elif event == "hint":
        if (value.get("kind") not in ("target", "carrier")
                or type(value.get("reveals_target")) is not bool
                or value["reveals_target"] != (value["kind"] == "target")):
            return None
    elif event in ("report", "skip"):
        if "reason" in value and not _text(value["reason"], 200, True):
            return None
    if "side" in value and value["side"] not in ("front", "back"):
        return None
    return value


class SubmissionLatch:
    """One submitted response per review nonce; duplicated front/back is harmless."""

    def __init__(self) -> None:
        self.nonce: str | None = None
        self.submitted = False

    def reset(self, nonce: str | None = None) -> None:
        self.nonce = nonce
        self.submitted = False

    def accept(self, event: dict[str, Any]) -> bool:
        if (event.get("event") != "attempt" or event.get("submitted") is not True
                or event.get("nonce") != self.nonce or self.submitted):
            return False
        self.submitted = True
        return True
