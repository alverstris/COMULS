"""COMULS controls on Anki's native Reviewer.

Anki owns card selection, undo, scheduling, rating buttons and review history.
This module records observational metadata only. It never submits a grade.
"""
from __future__ import annotations

import html
import json
import secrets
from datetime import datetime, timezone
from typing import Any, Callable

import aqt
from aqt import gui_hooks
from aqt.operations import CollectionOp
from aqt.reviewer import Reviewer
from aqt.sound import av_player

from .bridge import PREFIX, SubmissionLatch, context_matches, validate_message
from .core import EXERCISE_TYPES, evaluate_answer, validate_pack


class ReviewerIntegration:
    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.hooks: list[tuple[Any, Callable[..., Any]]] = []
        self.expected: dict[str, Any] | None = None
        self.exercise: dict[str, Any] | None = None
        self.latch = SubmissionLatch()
        self.outcome = "self_compare"
        self.target_hint = False
        self.carrier_help = False
        self.replays = 0
        self.exposed = False
        self.busy = False
        self._saved_auto_advance: bool | None = None
        self._auto_reviewer: Reviewer | None = None
        self._closed = False

    def install(self) -> "ReviewerIntegration":
        bindings = (
            ("card_will_show", self._card_will_show),
            ("webview_did_receive_js_message", self._web_message),
            ("reviewer_did_show_question", self._did_show_question),
            ("reviewer_did_show_answer", self._did_show_answer),
            ("reviewer_will_answer_card", self._will_answer_card),
            ("reviewer_did_answer_card", self._did_answer_card),
            ("reviewer_will_end", self._will_end),
            ("state_shortcuts_will_change", self._shortcuts_will_change),
        )
        for name, callback in bindings:
            hook = getattr(gui_hooks, name)
            hook.append(callback)
            self.hooks.append((hook, callback))
        return self

    def close(self) -> None:
        """Detach callbacks when reloading or disabling the add-on."""
        if self._closed:
            return
        self._will_end()
        for hook, callback in self.hooks:
            hook.remove(callback)
        self.hooks.clear()
        self._closed = True

    def _event(self, name: str, **details: Any) -> None:
        event = dict(self.expected or {})
        event.update(event=name, **details)
        callback = getattr(self.controller, "on_event", None)
        if callable(callback):
            callback(event)

    def _error(self, text: str) -> None:
        callback = getattr(self.controller, "content_error", None)
        if callable(callback):
            callback(text)

    def _live(self, context: Any = None) -> bool:
        mw = aqt.mw
        if mw is None or mw.state != "review" or self.expected is None:
            return False
        reviewer = mw.reviewer
        return context_matches(
            reviewer if context is None else context,
            reviewer, Reviewer, self.expected["card_id"],
        )

    def _read_exercise(self, card: Any) -> dict[str, Any] | None:
        note = card.note()
        try:
            identity = note["COMULS_ID"]
        except (KeyError, IndexError):
            return None
        if not isinstance(identity, str) or not identity.strip():
            return None
        try:
            raw = note["Payload"]
            if not isinstance(raw, str) or len(raw.encode("utf-8")) > 262144:
                raise ValueError("Payload is not bounded text")
            exercise = json.loads(html.unescape(raw))
            if not isinstance(exercise, dict) or exercise.get("id") != identity:
                raise ValueError("Payload identity does not match COMULS_ID")
            if exercise.get("type") not in EXERCISE_TYPES:
                raise ValueError("Unsupported exercise type")
            errors = validate_pack({
                "schema_version": 1, "pack_id": "review-card", "version": "1",
                "exercises": [exercise],
            })
            if errors:
                raise ValueError(errors[0])
            return exercise
        except (KeyError, IndexError, ValueError, TypeError, UnicodeError, RecursionError):
            self._error("This COMULS card has invalid exercise data. Check or re-import " + identity + ".")
            return None

    def _disable_auto(self, reviewer: Reviewer) -> None:
        if self._auto_reviewer is not reviewer:
            self._restore_auto()
            self._auto_reviewer = reviewer
            self._saved_auto_advance = bool(reviewer.auto_advance_enabled)
        reviewer.auto_advance_enabled = False
        reviewer.auto_advance_if_enabled()

    def _restore_auto(self) -> None:
        reviewer = self._auto_reviewer
        previous = self._saved_auto_advance
        self._auto_reviewer = None
        self._saved_auto_advance = None
        if reviewer is not None and previous is not None:
            reviewer.auto_advance_enabled = previous
            reviewer.auto_advance_if_enabled()

    def _clear(self) -> None:
        self.expected = None
        self.exercise = None
        self.latch.reset()
        self.outcome = "self_compare"
        self.target_hint = False
        self.carrier_help = False
        self.replays = 0
        self.exposed = False
        self.busy = False

    def _card_will_show(self, text: str, card: Any, kind: str) -> str:
        # Browser previews and template editors must be observationally inert.
        if kind not in ("reviewQuestion", "reviewAnswer"):
            return text
        mw = aqt.mw
        if (mw is None or mw.state != "review"
                or not isinstance(mw.reviewer, Reviewer)
                or getattr(getattr(mw.reviewer, "card", None), "id", None) != card.id):
            return text
        if kind == "reviewQuestion":
            exercise = self._read_exercise(card)
            if exercise is None:
                had_comuls = self.expected is not None
                self._clear()
                self._restore_auto()
                if had_comuls:
                    self._event("foreign_card")
                return "<script>window.comulsContext=null;</script>" + text
            self._clear()
            self.exercise = exercise
            self.expected = {
                "nonce": secrets.token_urlsafe(18), "card_id": int(card.id),
                "exercise_id": exercise["id"],
            }
            self.latch.reset(self.expected["nonce"])
            self._disable_auto(mw.reviewer)
        elif not self._live() or self.exercise is None:
            return "<script>window.comulsContext=null;</script>" + text
        # This must precede the template's card.js on BOTH sides.
        serialized = json.dumps(self.expected, ensure_ascii=True, separators=(",", ":"))
        serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        return "<script>window.comulsContext=" + serialized + ";</script>" + text

    def _did_show_question(self, card: Any) -> None:
        if self._live() and card.id == self.expected["card_id"]:
            self._disable_auto(aqt.mw.reviewer)
            self._event("question", type=self.exercise["type"])

    def _did_show_answer(self, card: Any) -> None:
        if not self._live() or card.id != self.expected["card_id"]:
            return
        self._disable_auto(aqt.mw.reviewer)
        if not self.exposed:
            self.exposed = True
            self._event("answer_exposure", type=self.exercise["type"])
            self._record_exposure(card)

    def _record_exposure(self, card: Any) -> None:
        """Sync factual answer exposure and bury explicitly linked siblings.

        This is a single native undoable operation. The current answer stays
        visible; no grade is possible until it finishes. Only declared exposure
        groups cause cross-note burial. A shared word alone creates no link.
        """
        from .collection import _write_json, exercise_notes, note_payload, note_state

        mw = aqt.mw
        reviewer = mw.reviewer
        expected = dict(self.expected)
        note_id = int(card.nid)
        groups = frozenset(self.exercise.get("exposure_groups", []))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.busy = True

        def operation(col: Any) -> Any:
            source_note = col.get_note(note_id)
            if source_note["COMULS_ID"] != expected["exercise_id"]:
                raise ValueError("COMULS exposure identity changed")
            notes = [source_note]
            if groups:
                for candidate in exercise_notes(col).values():
                    if int(candidate.id) == note_id:
                        continue
                    linked = set(note_payload(candidate).get("exposure_groups", []))
                    if groups.intersection(linked):
                        notes.append(candidate)
            day = str(col.sched.today)
            bury_ids: list[int] = []
            for note in notes:
                state = note_state(note)
                state["last_exposed_at"] = now
                state["last_exposed_day"] = day
                state["last_exposed_by"] = expected["exercise_id"]
                _write_json(note, "State", state)
                if int(note.id) != note_id:
                    bury_ids.extend(
                        int(sibling.id) for sibling in note.cards()
                        if sibling.id != expected["card_id"] and sibling.queue >= 0
                    )
            undo_entry = col.add_custom_undo_entry("COMULS answer exposure")
            col.update_notes(notes)
            if bury_ids:
                col.sched.bury_cards(sorted(set(bury_ids)), manual=True)
            return col.merge_undo_entries(undo_entry)

        def success(result: Any) -> None:
            if self.expected == expected:
                self.busy = False

        def failure(exception: Exception) -> None:
            if self.expected == expected:
                self.busy = False
            self._error("COMULS could not save answer exposure. Check the card data before continuing.")

        CollectionOp(parent=mw, op=operation).success(success).failure(failure).run_in_background(
            initiator=reviewer,
        )

    def _web_message(
        self, handled: tuple[bool, Any], message: str, context: Any,
    ) -> tuple[bool, Any]:
        if not isinstance(message, str) or not message.startswith(PREFIX):
            return handled
        # Own malformed/stale messages are consumed; they never fall through to
        # Anki's bridge. Verify Reviewer class, object and card before JSON parsing.
        if not self._live(context):
            return (True, None)
        event = validate_message(message, self.expected)
        if event is None:
            return (True, None)
        kind = event["event"]
        if kind == "attempt":
            if self.latch.accept(event):
                self.target_hint = self.target_hint or event["target_hint"]
                self.carrier_help = self.carrier_help or event["carrier_help"]
                self.replays = max(self.replays, event["replays"])
                response: Any = event["response"]
                if self.exercise["type"] == "sentence_reconstruction":
                    response = event["selected_ids"]
                self.outcome = evaluate_answer(self.exercise, response)["status"]
                metadata = self._attempt_metadata()
                if "presentation_seed" in event:
                    metadata["presentation_seed"] = event["presentation_seed"]
                self._event("attempt", **metadata)
        elif kind == "hint":
            if event["kind"] == "target":
                self.target_hint = True
            else:
                self.carrier_help = True
            self._event("hint", kind=event["kind"], reveals_target=event["reveals_target"])
        elif kind == "replay":
            if event.get("side", "front") == "front":
                self.replays += 1
            self._event("replay", side=event.get("side", "front"))
        elif kind == "report":
            self._event("report", reason=event.get("reason", "card_quality"),
                        side=event.get("side", "front"))
        elif kind == "skip":
            self._skip_current()
        return (True, None)

    def _attempt_metadata(self) -> dict[str, Any]:
        return {
            "submitted": self.latch.submitted, "outcome": self.outcome,
            "target_hint": self.target_hint, "carrier_help": self.carrier_help,
            "replays": self.replays,
        }

    def _will_answer_card(
        self, ease_tuple: tuple[bool, int], reviewer: Reviewer, card: Any,
    ) -> tuple[bool, int]:
        if not self._live(reviewer) or card.id != self.expected["card_id"]:
            return ease_tuple
        # Menus or other add-ons may re-enable auto advance. Cancel that rating,
        # clear its timers, and let the learner explicitly press a rating again.
        if reviewer.auto_advance_enabled:
            self._disable_auto(reviewer)
            return (False, ease_tuple[1])
        if self.busy:
            return (False, ease_tuple[1])
        # Manual self-comparison is valid even with no typed submission.
        return ease_tuple

    def _did_answer_card(self, reviewer: Reviewer, card: Any, ease: int) -> None:
        if not self._live(reviewer) or card.id != self.expected["card_id"]:
            return
        self._event("native_grade", ease=ease, **self._attempt_metadata())
        av_player.stop_and_clear_queue()
        # The native reviewer will select its next card after this hook.
        self._clear()

    def _skip_current(self) -> None:
        if not self._live() or self.busy:
            return
        mw = aqt.mw
        reviewer = mw.reviewer
        expected = dict(self.expected)
        self.busy = True
        av_player.stop_and_clear_queue()

        def success(result: Any) -> None:
            if self.expected != expected or not self._live(reviewer):
                return
            self.busy = False
            self._event("skip", reason="manual_bury")
            self._clear()
            # Advance only AFTER supported scheduler burial completed.
            reviewer.nextCard()

        def failure(exception: Exception) -> None:
            if self.expected == expected:
                self.busy = False
            self._error("The card could not be skipped. It is still available for review.")

        CollectionOp(
            parent=mw,
            op=lambda col: col.sched.bury_cards([expected["card_id"]], manual=True),
        ).success(success).failure(failure).run_in_background(initiator=reviewer)

    def _shortcuts_will_change(self, state: str, shortcuts: list[Any]) -> None:
        if state != "review":
            return
        for index, item in enumerate(shortcuts):
            if len(item) < 2 or getattr(item[1], "__name__", "") != "toggle_auto_advance":
                continue
            original = item[1]

            def guarded_toggle(*args: Any, _original: Callable[..., Any] = original, **kwargs: Any) -> Any:
                if self._live():
                    self._disable_auto(aqt.mw.reviewer)
                    return None
                return _original(*args, **kwargs)

            shortcuts[index] = (item[0], guarded_toggle, *item[2:])

    def _will_end(self) -> None:
        if self.expected is not None:
            self._event("reviewer_end")
        av_player.stop_and_clear_queue()
        self._clear()
        self._restore_auto()


def register(controller: Any) -> ReviewerIntegration:
    previous = getattr(controller, "_comuls_reviewer_integration", None)
    if isinstance(previous, ReviewerIntegration) and not previous._closed:
        return previous
    integration = ReviewerIntegration(controller).install()
    controller._comuls_reviewer_integration = integration
    return integration
