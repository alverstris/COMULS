"""Local, optional study diagnostics. Native Anki remains authoritative."""
from __future__ import annotations
import json
import time
import uuid
from pathlib import Path

class LocalData:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        device = root / "manager-id.txt"
        if not device.exists():
            device.write_text(str(uuid.uuid4()), encoding="utf-8")
        self.manager_id = device.read_text(encoding="utf-8").strip()
        self.events_path = root / "study-events.jsonl"

    def record(self, event: dict, enabled: bool):
        if not enabled:
            return
        # Never retain typed answers, name, email, collection path or note prose.
        allowed = {"event", "exercise_id", "type", "ease", "outcome", "target_hint",
                   "carrier_help", "replays", "submitted", "reason", "rating",
                   "seconds", "stage", "presentation_seed", "capture_phase", "prior_exposure_today", "active_seconds", "cohort"}
        safe = {k: v for k, v in event.items() if k in allowed and
                (v is None or isinstance(v, (bool, int, float, str)))}
        safe["recorded_at"] = round(time.time(), 3)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe, ensure_ascii=False) + "\n")

    def events(self):
        if not self.events_path.exists():
            return []
        result = []
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            try:
                result.append(json.loads(line))
            except ValueError:
                continue
        return result

    def clear(self):
        if self.events_path.exists():
            self.events_path.unlink()
