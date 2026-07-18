"""Touch input prototype for the PLTN touchscreen panel.

This module provides a small, testable prototype for TS-003:
- classify tap vs hold gestures
- emit PLTN input events into /tmp/pltn_input.json
- optionally bridge raw USB HID touch events into the prototype
"""

from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


class TouchKind(str, Enum):
    TAP = "tap"
    HOLD = "hold"


@dataclass(frozen=True)
class TouchEvent:
    """Normalized PLTN touch event payload."""

    type: str
    target: Optional[str] = None
    rod: Optional[str] = None
    direction: Optional[str] = None
    timestamp: float = field(default_factory=lambda: time.time())

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {"type": self.type, "timestamp": self.timestamp}
        if self.target is not None:
            payload["target"] = self.target
        if self.rod is not None:
            payload["rod"] = self.rod
        if self.direction is not None:
            payload["direction"] = self.direction
        return payload


class TouchInputWriter:
    """UDP writer for the shared PLTN touch input IPC."""

    def __init__(self, port: int = 9999) -> None:
        import socket
        self.address = ("127.0.0.1", port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def write_events(self, events: Sequence[TouchEvent]) -> str:
        if not events:
            raise ValueError("events tidak boleh kosong")

        payload = {
            "timestamp": events[-1].timestamp,
            "events": [event.to_dict() for event in events],
        }

        self.sock.sendto(json.dumps(payload).encode("utf-8"), self.address)
        return f"udp://{self.address[0]}:{self.address[1]}"

    def append_events(self, events: Sequence[TouchEvent]) -> str:
        # In UDP stream mode, append is just sending another datagram
        return self.write_events(events)


class TouchInputHandler:
    """Prototype touch handler that converts gestures into PLTN events."""

    HOLDABLE_CONTROLS = {
        "SAFETY_ROD_UP",
        "SAFETY_ROD_DOWN",
        "SHIM_ROD_UP",
        "SHIM_ROD_DOWN",
        "REGULATING_ROD_UP",
        "REGULATING_ROD_DOWN",
        "PRESSURE_UP",
        "PRESSURE_DOWN",
    }

    def __init__(
        self,
        writer: Optional[TouchInputWriter] = None,
    ) -> None:
        self.writer = writer or TouchInputWriter()

    def emit(
        self,
        control: str,
        timestamp: Optional[float] = None,
    ) -> Tuple[TouchKind, List[TouchEvent]]:
        self._validate_control(control)
        event = self._event_for_control(control, timestamp or time.time())
        events = [event]
        self.writer.append_events(events)
        logger.info("Sentuh %s (%s event)", control, len(events))
        return TouchKind.TAP, events


    def _validate_control(self, control: str) -> None:
        if control not in CONTROL_EVENT_MAP:
            raise ValueError(f"Kontrol tidak dikenal: {control}")

    def _event_for_control(self, control: str, timestamp: float) -> TouchEvent:
        event_type, kwargs = CONTROL_EVENT_MAP[control]
        return TouchEvent(type=event_type, timestamp=timestamp, **kwargs)


CONTROL_EVENT_MAP: Dict[str, Tuple[str, Dict[str, Optional[str]]]] = {
    "PUMP_PRIMARY_ON": ("PUMP_ON", {"target": "PRIMARY"}),
    "PUMP_PRIMARY_OFF": ("PUMP_OFF", {"target": "PRIMARY"}),
    "PUMP_SECONDARY_ON": ("PUMP_ON", {"target": "SECONDARY"}),
    "PUMP_SECONDARY_OFF": ("PUMP_OFF", {"target": "SECONDARY"}),
    "PUMP_TERTIARY_ON": ("PUMP_ON", {"target": "TERTIARY"}),
    "PUMP_TERTIARY_OFF": ("PUMP_OFF", {"target": "TERTIARY"}),
    "SAFETY_ROD_UP": ("ROD_MOVE", {"rod": "SAFETY", "direction": "UP"}),
    "SAFETY_ROD_DOWN": ("ROD_MOVE", {"rod": "SAFETY", "direction": "DOWN"}),
    "SHIM_ROD_UP": ("ROD_MOVE", {"rod": "SHIM", "direction": "UP"}),
    "SHIM_ROD_DOWN": ("ROD_MOVE", {"rod": "SHIM", "direction": "DOWN"}),
    "REGULATING_ROD_UP": ("ROD_MOVE", {"rod": "REGULATING", "direction": "UP"}),
    "REGULATING_ROD_DOWN": ("ROD_MOVE", {"rod": "REGULATING", "direction": "DOWN"}),
    "PRESSURE_UP": ("PRESSURE", {"direction": "UP"}),
    "PRESSURE_DOWN": ("PRESSURE", {"direction": "DOWN"}),
    "START_AUTO_SIMULATION": ("START_AUTO", {}),
    "START_CINEMATIC_LOFA": ("START_CINEMATIC_LOFA", {}),
    "REACTOR_RESET": ("RESET", {}),
    "EMERGENCY": ("EMERGENCY", {}),
    "LOFA_SIMULATE_PRIMARY": ("LOFA_SIMULATE", {"target": "PRIMARY"}),
    "LOFA_SIMULATE_SECONDARY": ("LOFA_SIMULATE", {"target": "SECONDARY"}),
    "LOFA_SIMULATE_TERTIARY": ("LOFA_SIMULATE", {"target": "TERTIARY"}),
    "LOFA_CANCEL": ("LOFA_CANCEL", {}),
    "SHOW_CREDITS": ("SHOW_CREDITS", {}),
    "HIDE_CREDITS": ("HIDE_CREDITS", {}),
}


def demo_sequence() -> List[TouchEvent]:
    """Generate a small demo sequence for manual verification."""
    handler = TouchInputHandler()
    demo_actions = [
        ("SAFETY_ROD_UP", 0.75),
        ("PRESSURE_UP", 0.55),
        ("PUMP_PRIMARY_ON", 0.0),
        ("START_AUTO_SIMULATION", 0.0),
        ("EMERGENCY", 0.0),
    ]

    written: List[TouchEvent] = []
    for control, duration in demo_actions:
        _, events = handler.emit(control)
        written.extend(events)
    return written


def run_demo() -> int:
    """Run the TS-003 input prototype demo."""
    events = demo_sequence()
    print("Demo Input Handler TS-003")
    for event in events:
        print(json.dumps(event.to_dict(), ensure_ascii=False))
    print(f"Menulis {len(events)} event ke /tmp/pltn_input.json")
    return 0


