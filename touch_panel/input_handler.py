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
    """Atomic writer for the shared PLTN touch input JSON file."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path(tempfile.gettempdir()) / "pltn_input.json"
        self._lock = threading.Lock()

    def write_events(self, events: Sequence[TouchEvent]) -> Path:
        if not events:
            raise ValueError("events tidak boleh kosong")

        payload = {
            "timestamp": events[-1].timestamp,
            "events": [event.to_dict() for event in events],
        }

        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_path.replace(self.path)

        return self.path

    def append_events(self, events: Sequence[TouchEvent]) -> Path:
        if not events:
            raise ValueError("events tidak boleh kosong")

        with self._lock:
            current = {"timestamp": 0.0, "events": []}
            if self.path.exists():
                try:
                    current = json.loads(self.path.read_text(encoding="utf-8"))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"JSON input sentuh tidak valid di {self.path}: {exc}") from exc

            current_events = list(current.get("events", []))
            current_events.extend(event.to_dict() for event in events)
            current["timestamp"] = events[-1].timestamp
            current["events"] = current_events

            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
            tmp_path.replace(self.path)

        return self.path


class TouchGestureClassifier:
    """Classify gestures as tap or hold."""

    def __init__(self, hold_threshold: float = 0.35, repeat_interval: float = 0.05) -> None:
        self.hold_threshold = hold_threshold
        self.repeat_interval = repeat_interval

    def classify(self, duration: float) -> TouchKind:
        return TouchKind.HOLD if duration >= self.hold_threshold else TouchKind.TAP

    def repeat_count(self, duration: float) -> int:
        if duration < self.hold_threshold:
            return 1
        repeats = int(duration / self.repeat_interval)
        return max(1, repeats)


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
        classifier: Optional[TouchGestureClassifier] = None,
    ) -> None:
        self.writer = writer or TouchInputWriter()
        self.classifier = classifier or TouchGestureClassifier()
        self._active_presses: Dict[str, float] = {}

    def begin_touch(self, control: str, timestamp: Optional[float] = None) -> None:
        self._validate_control(control)
        self._active_presses[control] = timestamp or time.time()

    def end_touch(self, control: str, timestamp: Optional[float] = None) -> Tuple[TouchKind, List[TouchEvent]]:
        self._validate_control(control)
        if control not in self._active_presses:
            raise ValueError(f"Tidak ada sentuhan aktif untuk kontrol {control}")

        start_ts = self._active_presses.pop(control)
        end_ts = timestamp or time.time()
        duration = max(0.0, end_ts - start_ts)
        return self.emit(control, duration=duration, timestamp=start_ts)

    def emit(
        self,
        control: str,
        duration: float = 0.0,
        timestamp: Optional[float] = None,
    ) -> Tuple[TouchKind, List[TouchEvent]]:
        self._validate_control(control)
        kind = self.classifier.classify(duration)
        events = self._build_events(control, kind, duration, timestamp or time.time())
        self.writer.append_events(events)
        logger.info("Sentuh %s -> %s (%s event)", control, kind.value, len(events))
        return kind, events

    def _build_events(self, control: str, kind: TouchKind, duration: float, timestamp: float) -> List[TouchEvent]:
        if control in self.HOLDABLE_CONTROLS and kind is TouchKind.HOLD:
            repeat_count = self.classifier.repeat_count(duration)
            return [self._event_for_control(control, timestamp + (index * self.classifier.repeat_interval)) for index in range(repeat_count)]
        return [self._event_for_control(control, timestamp)]

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
    "REACTOR_RESET": ("RESET", {}),
    "EMERGENCY": ("EMERGENCY", {}),
    "LOFA_SIMULATE_PRIMARY": ("LOFA_SIMULATE", {"target": "PRIMARY"}),
    "LOFA_SIMULATE_SECONDARY": ("LOFA_SIMULATE", {"target": "SECONDARY"}),
    "LOFA_SIMULATE_TERTIARY": ("LOFA_SIMULATE", {"target": "TERTIARY"}),
    "LOFA_CANCEL": ("LOFA_CANCEL", {}),
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
        _, events = handler.emit(control, duration=duration)
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


class UsbTouchInputBridge:
    """Optional USB HID bridge for real touchscreen devices.

    The bridge is intentionally lightweight so the prototype can work on
    hardware without pulling the full UI stack into the controller process.
    """

    def __init__(
        self,
        resolver: Callable[[int, int], Optional[str]],
        handler: Optional[TouchInputHandler] = None,
        device_path: Optional[str] = None,
    ) -> None:
        self.resolver = resolver
        self.handler = handler or TouchInputHandler()
        self.device_path = device_path
        self._device = None
        self._evdev = None

    def open(self) -> None:
        try:
            from evdev import InputDevice, ecodes
        except Exception as exc:
            raise RuntimeError("evdev diperlukan untuk bridge USB HID tetapi tidak terinstal") from exc

        if not self.device_path:
            raise RuntimeError("device_path diperlukan untuk prototipe bridge USB HID")

        self._evdev = ecodes
        self._device = InputDevice(self.device_path)

    def run_forever(self) -> None:
        if self._device is None or self._evdev is None:
            self.open()

        active_control: Optional[str] = None
        last_x = 0
        last_y = 0
        start_ts = 0.0

        for event in self._device.read_loop():  # type: ignore[union-attr]
            if event.type == self._evdev.EV_ABS:
                if event.code == self._evdev.ABS_X:
                    last_x = int(event.value)
                elif event.code == self._evdev.ABS_Y:
                    last_y = int(event.value)
            elif event.type == self._evdev.EV_KEY and event.code == self._evdev.BTN_TOUCH:
                if event.value == 1:
                    active_control = self.resolver(last_x, last_y)
                    if active_control:
                        start_ts = float(event.timestamp())
                        self.handler.begin_touch(active_control, timestamp=start_ts)
                elif event.value == 0 and active_control:
                    self.handler.end_touch(active_control, timestamp=float(event.timestamp()))
                    active_control = None

