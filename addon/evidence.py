"""Conservative, rebuildable evidence from native reviews and bounded metadata.

The native review history is the authority: a metadata entry without its native
review never earns credit (including after Undo). Missing assistance information
is unknown, not evidence of an unaided attempt. These are exercise/objective
summaries, not CEFR certification and not a second scheduler.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

DAY_SECONDS = 86400


def timestamp(value: Any) -> float | None:
    """Accept persisted ISO UTC timestamps and numeric Unix seconds/milliseconds."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    return None
                return parsed.timestamp()
            except (ValueError, OverflowError):
                return None
    if not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
        return None
    return float(value) / 1000 if value > 100_000_000_000 else float(value)


def _field(value: Any, name: str, default: Any = None) -> Any:
    return value.get(name, default) if isinstance(value, dict) else getattr(value, name, default)


def review_identity(review: Any) -> str | None:
    """Prefer exact native IDs; API-only second timestamps cannot match metadata."""
    raw = _field(review, "id", _field(review, "time"))
    if isinstance(raw, bool):
        return None
    try:
        number = int(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    return str(number) if number > 0 else None


def summarize_exercise(exercise: dict[str, Any], state: dict[str, Any],
                       logs: list[Any], now: float) -> dict[str, Any]:
    """Summarize one exact objective without transferring evidence to other facets."""
    metadata = state.get("review_evidence", {})
    if not isinstance(metadata, dict):
        metadata = {}
    # Anki's display-oriented get_review_logs truncates IDs to seconds. The
    # collection adapter supplies exact read-only revlog rows to avoid matching
    # assistance to an undone/repeated review in the same second.
    source = state.get("native_reviews")
    if not isinstance(source, list):
        source = logs
    native: dict[str, tuple[float, int, Any]] = {}
    for log in source:
        identity = review_identity(log)
        when = timestamp(_field(log, "id", _field(log, "time")))
        grade = _field(log, "button_chosen", _field(log, "ease"))
        kind = _field(log, "review_kind", _field(log, "type", 0))
        # Administrative/rescheduling records do not constitute retrievals.
        if (identity is None or when is None or when > now + 1
                or type(grade) is not int or grade not in (1, 2, 3, 4)
                or kind not in (0, 1, 2, 3)):
            continue
        native[identity] = (when, grade, log)
    ordered = sorted(native.items(), key=lambda item: (item[1][0], int(item[0])))
    independent, assisted, unknown = [], 0, 0
    ordinary_success = 0
    repair_needed = bool(state.get("repair_requested", False))
    last_failure = None
    for identity, (when, grade, _log) in ordered:
        info = metadata.get(identity)
        if not isinstance(info, dict) or info.get("exercise_id", exercise["id"]) != exercise["id"]:
            info = None
        outcome = info.get("outcome") if info else None
        success = grade >= 3 and outcome not in ("incorrect", "invalid")
        if info and (info.get("target_hint") is True or info.get("capture_phase") == "after_exposure"):
            success = False
        if success:
            ordinary_success += 1
        failure = grade == 1 or outcome == "incorrect"
        if failure:
            last_failure = when
            repair_needed = True
        elif success:
            repair_needed = bool(state.get("repair_requested", False))
        complete = bool(info and info.get("assistance_known") is True
                        and info.get("capture_phase") in ("question", "no_submission")
                        and type(info.get("target_hint")) is bool
                        and type(info.get("carrier_help")) is bool
                        and type(info.get("replays")) is int
                        and info.get("prior_exposure_today") is False)
        if not complete:
            unknown += 1
            continue
        # Ordinary playback/replay is a permitted listening control. A count of
        # one can be the learner's first manual play, so it is not target help.
        # Explicitly non-revealing carrier help also preserves primary-objective
        # evidence; unknown carrier disclosure stays conservative.
        revealing_carrier_help = info["carrier_help"] and exercise.get("carrier_help_reveals_target", True)
        if info["target_hint"] or revealing_carrier_help:
            assisted += 1
            continue
        prior = timestamp(info.get("prior_exposed_at"))
        if prior is None or when - prior < DAY_SECONDS:
            # Unknown exposure coverage cannot prove a delayed independent test.
            unknown += 1
            continue
        if success and outcome in ("correct", "self_compare"):
            date = str(info.get("study_day") or datetime.fromtimestamp(when, timezone.utc).date())
            independent.append((when, date, identity))
    # An observed later failure invalidates the current stable claim until two
    # subsequent independent successes have been observed again.
    recent = [item for item in independent if last_failure is None or item[0] > last_failure]
    dates = {date for _, date, _ in recent}
    stable = len(dates) >= 2 and not repair_needed
    declared = state.get("declared_understood") is True or state.get("understood") is True
    familiarised = state.get("familiarised_day") is not None
    understood = declared or ordinary_success > 0
    level = ("repair_needed" if repair_needed else "stable" if stable else
             "understood" if understood else "familiarised" if familiarised else "unknown")
    return {
        "exercise_id": exercise["id"], "target_id": exercise.get("unit_id", exercise["id"]),
        "sense_id": exercise.get("sense_id"), "form_id": exercise.get("form_id"),
        "construction_id": exercise.get("construction_id"), "objective": exercise.get("type"),
        "facets": list(exercise.get("evidence_facets", [exercise.get("type", "unknown")])),
        "evidence_level": level, "familiarised": familiarised, "declared_understood": declared,
        "understood": understood, "stable": stable, "repair_needed": repair_needed,
        "total_reviews": len(ordered), "successful_native_reviews": ordinary_success,
        "independent_successes": len(recent), "independent_dates": len(dates),
        "assisted_reviews": assisted, "unknown_assistance_reviews": unknown,
        "last_review_at": ordered[-1][1][0] if ordered else None,
        "coverage_note": "Native ratings are learner reports; missing assistance or exposure metadata cannot establish stable retrieval.",
    }
