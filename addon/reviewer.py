"""COMULS controls on Anki's native Reviewer.

Anki owns card selection, undo, scheduling, rating buttons and review history.
This module records observational metadata only. It never submits a grade.
"""
from __future__ import annotations

import html
import hashlib
import json
import secrets
import time
import wave
from pathlib import Path
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
        self.capture_after_exposure = False
        self.prior_exposure_today: bool | None = None
        self.prior_exposed_at: str | float | None = None
        self.pending_skip = False
        self.busy = False
        self._saved_auto_advance: bool | None = None
        self._auto_reviewer: Reviewer | None = None
        self._closed = False
        self._audio_playback: dict[str, Any] | None = None
        self._autoplay_pending_card: int | None = None
        self.blocked_reason: str | None = None
        self._read_error: str | None = None

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
            ("reviewer_will_show_context_menu", self._context_menu),
            ("audio_will_replay", self._audio_will_replay),
            ("reviewer_will_play_question_sounds", self._question_sounds),
            ("reviewer_will_play_answer_sounds", self._answer_sounds),
            ("av_player_will_play", self._playback_will_play),
            ("av_player_did_begin_playing", self._playback_began),
            ("av_player_did_end_playing", self._playback_ended),
            ("reviewer_did_show_question", self._playback_question_shown),
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
        self._read_error = None
        note = card.note()
        try:
            identity = note["COMULS_ID"]
        except (KeyError, IndexError):
            return None
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 256:
            self._read_error = "This managed card has no valid exercise identity."
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
            self._read_error = "This card has invalid exercise data. Repair or re-import " + identity + "."
            return None

    def _media_problem(self, exercise: dict[str, Any]) -> str | None:
        """Check local required bytes before a question or a native rating.

        Reading media is observational. Repair/copying stays in the content
        manager; unavailable media never becomes a failed learning attempt.
        """
        references = [exercise] + [item for item in exercise.get("choices", []) if isinstance(item, dict)]
        for reference in references:
            filename = reference.get("audio_file")
            if not filename:
                continue  # Legacy TTS-only cards remain a manual client feature.
            if (not isinstance(filename, str) or filename in (".", "..")
                    or any(char in filename for char in "/\\:\r\n[]")):
                return "This card has an invalid recording reference. Repair the course content."
            try:
                path = Path(aqt.mw.col.media.dir()) / filename
                if not path.is_file() or path.stat().st_size == 0:
                    return "A required recording is unavailable. Finish media sync or restore bundled audio in COMULS Settings."
                if path.stat().st_size > 16_000_000:
                    return "A required recording exceeds the supported file limit. Repair the course content."
                expected = reference.get("audio_sha256")
                if expected and (not isinstance(expected, str) or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                    return "A required recording is damaged. Restore bundled audio in COMULS Settings."
            except (OSError, AttributeError, TypeError, ValueError):
                return "The required recordings could not be checked. Restore audio before reviewing this card."
        return None

    def _unavailable_html(self) -> str:
        context = json.dumps(self.expected, ensure_ascii=True).replace("<", "\\u003c")
        return ('<script>window.comulsContext=' + context + ';</script>'
            '<main class="comuls-card" role="alert"><h2>COMULS card unavailable</h2><p>'
            + html.escape(self.blocked_reason or "This card needs repair.")
            + '</p><p>This is a content or audio issue. It will not receive a learning grade. '
            'Use the ungraded skip, or return to COMULS Settings → Content manager.</p>'
            '<button type="button" onclick="pycmd(\'comuls:\'+JSON.stringify(Object.assign({},'
            'window.comulsContext,{event:\'skip\',reason:\'content_unavailable\'})))">'
            'Skip without grading</button></main>')

    def _snapshot_prior_exposure(self, card: Any) -> None:
        """Read exposure before this question's own answer updates synced State."""
        try:
            from .collection import evidence_state
            state = evidence_state(aqt.mw.col, card.note())
            day = str(aqt.mw.col.sched.today)
            if isinstance(state, dict):
                self.prior_exposed_at = state.get("last_exposed_at") or state.get("familiarised_at")
                self.prior_exposure_today = (
                    str(state.get("last_exposed_day")) == day
                    or str(state.get("familiarised_day")) == day
                )
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            # Unknown is different from proof that the target was unprimed.
            self.prior_exposure_today = None

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
        self.capture_after_exposure = False
        self.prior_exposure_today = None
        self.prior_exposed_at = None
        self.pending_skip = False
        self.busy = False
        self.blocked_reason = None

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
            read_error = self._read_error
            note = card.note()
            try:
                identity = note["COMULS_ID"]
                managed = True
            except (KeyError, IndexError):
                identity, managed = None, False
            if exercise is None:
                if managed:
                    self._clear()
                    self.expected = {"nonce": secrets.token_urlsafe(18), "card_id": int(card.id),
                        "exercise_id": identity if isinstance(identity, str) and identity.strip() and len(identity) <= 256
                        else "invalid-managed-" + str(card.id)}
                    self.latch.reset(self.expected["nonce"])
                    self.blocked_reason = read_error or "This managed card has invalid data. Repair the course content."
                    self._disable_auto(mw.reviewer)
                    av_player.stop_and_clear_queue()
                    return self._unavailable_html()
                if self.expected is not None:
                    self._event("foreign_card")
                self._clear()
                self._restore_auto()
                return "<script>window.comulsContext=null;</script>" + text
            self._clear()
            self.exercise = exercise
            self._snapshot_prior_exposure(card)
            self.expected = {
                "nonce": secrets.token_urlsafe(18), "card_id": int(card.id),
                "exercise_id": exercise["id"],
            }
            self.latch.reset(self.expected["nonce"])
            self._disable_auto(mw.reviewer)
            self.blocked_reason = self._media_problem(exercise)
            if self.blocked_reason:
                av_player.stop_and_clear_queue()
                return self._unavailable_html()
        elif self._live() and self.blocked_reason:
            return self._unavailable_html()
        elif not self._live() or self.exercise is None:
            return "<script>window.comulsContext=null;</script>" + text
        # This must precede the template's card.js on BOTH sides.
        serialized = json.dumps(self.expected, ensure_ascii=True, separators=(",", ":"))
        serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        state_reader = getattr(self.controller, "state", None)
        state = state_reader() if callable(state_reader) else {}
        preferences = {"font_percent": min(160, max(85, int(state.get("font_percent", 100)))),
                       "accent_row": state.get("accent_row", True) is True}
        return ("<script>window.comulsContext=" + serialized
                + ";window.comulsPreferences=" + json.dumps(preferences) + ";</script>" + text)

    def _question_sounds(self, card: Any, sounds: list[Any]) -> None:
        """Control only managed-card autoplay; do not change deck preferences."""
        exercise = self._read_exercise(card)
        if exercise is None:
            try:
                managed = bool(str(card.note()["COMULS_ID"]).strip())
            except (KeyError, IndexError):
                managed = False
            if not managed:
                return
        # Native Anki passes the cached tag list itself. Detach that cache
        # before changing this invocation's autoplay queue; replay indices
        # must still address the original primary recording afterwards.
        output = card.render_output()
        if sounds is output.question_av_tags:
            output.question_av_tags = list(sounds)
        self._autoplay_pending_card = int(card.id)
        sounds.clear()
        if exercise is None:
            return
        state_reader = getattr(self.controller, "state", None)
        state = state_reader() if callable(state_reader) else {}
        if state.get("audio_autoplay", False) and not getattr(self.controller, "paused", False):
            # Only the primary recording belongs in question autoplay.
            from anki.sound import SoundOrVideoTag
            if exercise.get("audio_file"):
                sounds.append(SoundOrVideoTag(filename=exercise["audio_file"]))
            elif exercise.get("audio_text"):
                sounds.extend(card.question_av_tags()[:1])

    def _answer_sounds(self, card: Any, sounds: list[Any]) -> None:
        try:
            managed = bool(str(card.note()["COMULS_ID"]).strip())
        except (KeyError, IndexError):
            managed = False
        if managed:
            output = card.render_output()
            if sounds is output.answer_av_tags:
                output.answer_av_tags = list(sounds)
            sounds.clear()

    def _playback_will_play(self, tag: Any) -> None:
        """Observe native playback; a click alone never reveals listening tiles."""
        self._audio_playback = None
        mw = aqt.mw
        if self._closed or mw is None or mw.state != "review" or mw.reviewer.state != "question":
            return
        card = mw.reviewer.card
        if card is None:
            return
        exercise = self._read_exercise(card)
        filename = getattr(tag, "filename", None)
        if not exercise or not filename or filename != exercise.get("audio_file"):
            return
        try:
            with wave.open(str(Path(mw.col.media.dir()) / filename), "rb") as wav:
                duration = wav.getnframes() / wav.getframerate()
        except (OSError, ValueError, wave.Error, EOFError):
            return
        if duration <= 0:
            return
        # Autoplay is requested before Anki renders a new question/context.
        # Bind that playback to its nonce once the real question is shown.
        nonce = None
        if self._autoplay_pending_card != int(card.id) and self._live():
            nonce = self.expected["nonce"]
        self._audio_playback = {"card_id": int(card.id), "filename": filename,
                                "duration": duration, "nonce": nonce,
                                "started": None, "player_id": None}

    def _playback_question_shown(self, card: Any) -> None:
        playback = self._audio_playback
        self._autoplay_pending_card = None
        if (playback is not None and playback["nonce"] is None
                and playback["card_id"] == int(card.id) and self._live()):
            playback["nonce"] = self.expected["nonce"]

    def _playback_began(self, player: Any, tag: Any) -> None:
        playback = self._audio_playback
        if playback is None or getattr(tag, "filename", None) != playback["filename"]:
            return
        playback["started"] = time.monotonic()
        playback["player_id"] = id(player)
        if playback["nonce"] is None and self._live() and self.expected["card_id"] == playback["card_id"]:
            playback["nonce"] = self.expected["nonce"]

    def _playback_ended(self, player: Any) -> None:
        playback = self._audio_playback
        self._audio_playback = None
        if (playback is None or playback["started"] is None or playback["player_id"] != id(player)
                or not self._live() or aqt.mw.reviewer.state != "question"
                or getattr(self.controller, "paused", False)
                or self.expected["card_id"] != playback["card_id"]
                or self.expected["nonce"] != playback["nonce"]
                or time.monotonic() - playback["started"] < playback["duration"] * .85):
            return
        nonce = json.dumps(self.expected["nonce"])
        aqt.mw.reviewer.web.eval("if(window.COMULSPlaybackEnded){window.COMULSPlaybackEnded(" + nonce + ");}")

    def _did_show_question(self, card: Any) -> None:
        if self.blocked_reason:
            return
        if self._live() and card.id == self.expected["card_id"]:
            self._disable_auto(aqt.mw.reviewer)
            self._event("question", type=self.exercise["type"],
                        prior_exposure_today=self.prior_exposure_today)

    def _did_show_answer(self, card: Any) -> None:
        if self.blocked_reason:
            return
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
        from .collection import (_write_json, exercise_notes, note_payload, note_state,
                                 record_reference_exposure)

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
            # Factual exposure survives native undo. It is not achievement credit.
            record_reference_exposure(col, expected["exercise_id"],
                                      datetime.fromisoformat(now).timestamp())
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
                if self.pending_skip:
                    self.pending_skip = False
                    self._skip_current()

        def failure(exception: Exception) -> None:
            if self.expected == expected:
                # Preserve the grading block: otherwise a failed save would let
                # linked retrievals appear unprimed. Leaving review is safe.
                self.busy = True
                self._event("exposure_save_failed")
            self._error("COMULS could not save answer exposure. Return to the deck and repair the card data before continuing.")

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
        if not isinstance(context, Reviewer) or not self._live(context):
            return (True, None)
        event = validate_message(message, self.expected)
        if event is None:
            return (True, None)
        kind = event["event"]
        if self.blocked_reason and kind not in ("skip", "report", "pause", "activity"):
            return (True, None)
        if kind == "attempt":
            if self.latch.accept(event):
                self.capture_after_exposure = self.exposed
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
            self.carrier_help = self.carrier_help or event.get("carrier_help", False)
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
        elif kind == "activity":
            self._event("activity")
        elif kind == "pause":
            self.controller.pause("manual")
        elif kind == "play_comparison":
            # Resolve the ID in trusted current content; never accept a path
            # supplied by the webview and never reveal alternatives on fronts.
            if aqt.mw.reviewer.state != "answer":
                return (True, None)
            for choice in self.exercise.get("choices", []):
                if choice.get("id") == event["choice_id"] and choice.get("audio_file"):
                    from anki.sound import SoundOrVideoTag
                    av_player.play_tags([SoundOrVideoTag(filename=choice["audio_file"])])
                    self._event("replay", side="back", source="comparison")
                    break
        return (True, None)

    def _attempt_metadata(self) -> dict[str, Any]:
        return {
            "submitted": self.latch.submitted, "outcome": self.outcome,
            "target_hint": self.target_hint, "carrier_help": self.carrier_help,
            "replays": self.replays,
            "capture_phase": ("after_exposure" if self.capture_after_exposure
                              else "question" if self.latch.submitted else "no_submission"),
            "prior_exposure_today": self.prior_exposure_today,
            "prior_exposed_at": self.prior_exposed_at,
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
        if self.blocked_reason or self.busy:
            return (False, ease_tuple[1])
        media_problem = self._media_problem(self.exercise) if self.exercise else None
        if media_problem:
            self.blocked_reason = media_problem
            av_player.stop_and_clear_queue()
            self._error(media_problem + " Use Anki's Bury Card action or leave review; no grade was recorded.")
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
        if not self._live():
            return
        if self.busy:
            self.pending_skip = True
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

    def _context_menu(self, reviewer: Reviewer, menu: Any) -> None:
        if not self._live(reviewer):
            return
        from aqt.qt import QKeySequence
        self._disable_auto(reviewer)

        def disable_auto_action(current: Any) -> None:
            for action in current.actions():
                if action.shortcut() == QKeySequence("Shift+A"):
                    action.setEnabled(False)
                    if action.isCheckable():
                        action.setChecked(False)
                submenu = action.menu()
                if submenu is not None:
                    disable_auto_action(submenu)

        disable_auto_action(menu)

    def _audio_will_replay(self, webview: Any, card: Any, question_side: bool) -> None:
        if (not self._live() or card.id != self.expected["card_id"]
                or webview is not aqt.mw.reviewer.web):
            return
        if question_side:
            self.replays += 1
        self._event("replay", side="front" if question_side else "back",
                    source="native_shortcut")

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
