import json
import os
import tempfile
from pathlib import Path
import unittest
from gazebloom.eventlog import LocalEventLog

class EventLogTests(unittest.TestCase):
    def test_explicit_opt_in_only(self):
        with tempfile.TemporaryDirectory() as p:
            path = Path(p)/"private"/"events.jsonl"
            log = LocalEventLog(path, interval_seconds=1200, break_seconds=20)
            self.assertFalse(path.exists())
            log.record([]); self.assertFalse(path.exists())
            log.record([{"event_type":"break_completed","state":"working","source":"user_confirmed"}])
            log.record([{"event_type":"session_ended","state":"stopped","source":"user"}])
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["session_id"], rows[1]["session_id"])
            self.assertEqual(rows[0]["source"], "user_confirmed")
            self.assertEqual(rows[0]["break_target_seconds"], 20)
            self.assertEqual(rows[0]["schema_version"], "0.1")
            self.assertIn("+00:00", rows[0]["timestamp_utc"])
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
if __name__ == "__main__":
    unittest.main()
