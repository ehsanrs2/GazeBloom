"""Explicitly opt-in local JSONL event logging, no screens or eye measurements."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid


class LocalEventLog:
    def __init__(self, path: str | Path, *, interval_seconds: float, break_seconds: float):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.session_id = uuid.uuid4().hex
        self.interval_seconds = interval_seconds
        self.break_seconds = break_seconds

    def record(self, events: list[dict]) -> None:
        if not events:
            return
        # Exclusive append, restrictive permissions for new files. No overwrite.
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                for event in events:
                    payload = {
                        "schema_version": "0.1",
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "session_id": self.session_id,
                        "scheduled_interval_seconds": self.interval_seconds,
                        "break_target_seconds": self.break_seconds,
                        **event,
                    }
                    stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        except BaseException:
            # fdopen owns the descriptor after it successfully wraps it.
            raise
