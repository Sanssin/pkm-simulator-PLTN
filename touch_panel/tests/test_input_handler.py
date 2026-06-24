from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from touch_panel.input_handler import (
    TouchInputHandler,
    TouchInputWriter,
    TouchKind,
)


class TouchInputHandlerTests(unittest.TestCase):
    def test_tap_writes_single_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pltn_input.json"
            handler = TouchInputHandler(writer=TouchInputWriter(path))

            kind, events = handler.emit("PUMP_PRIMARY_ON", timestamp=10.0)

            self.assertEqual(kind, TouchKind.TAP)
            self.assertEqual(len(events), 1)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["events"][0]["type"], "PUMP_ON")
            self.assertEqual(payload["events"][0]["target"], "PRIMARY")

    def test_hold_emits_repeated_rod_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "pltn_input.json"
            handler = TouchInputHandler(writer=TouchInputWriter(path))

            kind, events = handler.emit("SAFETY_ROD_UP", timestamp=20.0)

            self.assertEqual(kind, TouchKind.TAP)
            self.assertEqual(len(events), 1)

            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["events"][0]["type"], "ROD_MOVE")
            self.assertEqual(payload["events"][0]["rod"], "SAFETY")
            self.assertEqual(payload["events"][0]["direction"], "UP")

    def test_unknown_control_raises(self) -> None:
        handler = TouchInputHandler()
        with self.assertRaises(ValueError):
            handler.emit("NOT_A_CONTROL")


if __name__ == "__main__":
    unittest.main()
