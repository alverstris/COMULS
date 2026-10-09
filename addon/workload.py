"""COMULS new-admission backlog hysteresis; Anki remains the scheduler."""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any


def update_backlog(
    state: dict[str, Any],
    day: int,
    due_seconds: float,
    budget_seconds: float,
    completed: bool = False,
) -> dict[str, Any]:
    """Return a copy with the new-card pause state and recovery-date evidence.

    Any estimate strictly above the budget pauses new admission and clears
    previous recovery evidence. Resume after two distinct completed study dates
    below 70% of a positive budget, counted since the last overflow. Merely
    opening a screen or repeating a same-day callback cannot prove recovery.

    Temporary admission overrides belong to the caller, not to this state.
    No Anki card, due date or scheduling interval is changed here.
    """
    if type(day) is not int:
        raise ValueError("day must be an integer study-day identifier")
    for name, value in (("due_seconds", due_seconds), ("budget_seconds", budget_seconds)):
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value < 0):
            raise ValueError(name + " must be a finite nonnegative number")

    updated = deepcopy(state)
    paused = updated.get("pause_new", False) is True
    existing = updated.get("backlog_recovery_days", [])
    recovery: list[str] = []
    if isinstance(existing, list):
        for value in existing:
            if isinstance(value, str) and value and value not in recovery:
                recovery.append(value)
    recovery = recovery[-2:]

    if due_seconds > budget_seconds:
        paused = True
        recovery = []
    elif (paused and completed and budget_seconds > 0
          and due_seconds < 0.7 * budget_seconds):
        date = str(day)
        if date not in recovery:
            recovery.append(date)
        recovery = recovery[-2:]
        if len(recovery) >= 2:
            paused = False

    updated["pause_new"] = paused
    updated["backlog_recovery_days"] = recovery
    return updated
