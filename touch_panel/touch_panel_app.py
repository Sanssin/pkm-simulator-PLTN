"""Touch panel setup checker and future entrypoint.

This module provides a lightweight evaluation mode for TS-001 so the
touchscreen setup can be validated without requiring the full UI stack yet.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

try:
    from .input_handler import run_demo as run_input_demo
except ImportError:  # pragma: no cover - fallback for direct script execution
    from input_handler import run_demo as run_input_demo

try:
    from .base_app import launch_touch_panel, get_layout_spec
except ImportError:  # pragma: no cover - fallback for direct script execution
    from base_app import launch_touch_panel, get_layout_spec


@dataclass
class CheckResult:
    name: str
    status: str
    message: str

    @property
    def is_ok(self) -> bool:
        return self.status in {"PASS", "WARN"}


class TouchPanelSetupChecker:
    """Run basic environment checks for the touchscreen setup."""

    def __init__(self, expected_resolution: Tuple[int, int] = (1280, 800)) -> None:
        self.expected_resolution = expected_resolution
        self.ipc_dir = Path(tempfile.gettempdir())
        self.input_path = self.ipc_dir / "pltn_input.json"
        self.state_path = self.ipc_dir / "pltn_state.json"

    def run(self) -> List[CheckResult]:
        return [
            self._check_python_version(),
            self._check_temp_write_access(),
            self._check_display_environment(),
            self._check_screen_resolution(),
            self._check_optional_pyqt5(),
        ]

    def _check_python_version(self) -> CheckResult:
        current = sys.version_info
        if (current.major, current.minor) >= (3, 7):
            return CheckResult("python-version", "PASS", f"{current.major}.{current.minor}.{current.micro}")
        return CheckResult("python-version", "FAIL", "Python 3.7+ is required")

    def _check_temp_write_access(self) -> CheckResult:
        try:
            self.ipc_dir.mkdir(parents=True, exist_ok=True)
            probe = self.ipc_dir / "pltn_touch_panel_probe.tmp"
            probe.write_text("ok", encoding="utf-8")
            try:
                probe.unlink()
            except FileNotFoundError:
                pass
            return CheckResult(
                "ipc-write-access",
                "PASS",
                f"Writable IPC directory: {self.ipc_dir} ({self.input_path.name}, {self.state_path.name})",
            )
        except OSError as exc:
            return CheckResult("ipc-write-access", "FAIL", f"Cannot write IPC files in {self.ipc_dir}: {exc}")

    def _check_display_environment(self) -> CheckResult:
        system = platform.system().lower()
        if system != "linux":
            return CheckResult("display-env", "WARN", f"Running on {platform.system()}, display checks are informational only")

        display = os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
        if display:
            return CheckResult("display-env", "PASS", f"Display session detected: {display}")
        return CheckResult("display-env", "WARN", "No DISPLAY/WAYLAND_DISPLAY set; touchscreen GUI cannot be launched in this session")

    def _check_screen_resolution(self) -> CheckResult:
        system = platform.system().lower()
        if system != "linux":
            return CheckResult("screen-resolution", "WARN", "Screen resolution check skipped outside Linux")

        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return CheckResult("screen-resolution", "WARN", "Skipped because no display session is available")

        xrandr = subprocess.run(
            ["xrandr", "--current"],
            capture_output=True,
            text=True,
            check=False,
        )
        if xrandr.returncode != 0:
            return CheckResult("screen-resolution", "WARN", "xrandr not available; verify HDMI0 is set to 1280x800 manually")

        expected = f"{self.expected_resolution[0]}x{self.expected_resolution[1]}"
        if expected in xrandr.stdout:
            return CheckResult("screen-resolution", "PASS", f"Expected resolution detected: {expected}")
        return CheckResult("screen-resolution", "WARN", f"Expected {expected} not found in xrandr output")

    def _check_optional_pyqt5(self) -> CheckResult:
        try:
            __import__("PyQt5")
        except Exception:
            return CheckResult("pyqt5", "WARN", "PyQt5 is not installed yet; acceptable for TS-001 hardware setup")
        return CheckResult("pyqt5", "PASS", "PyQt5 is available")


def format_results(results: Sequence[CheckResult]) -> str:
    lines = []
    for result in results:
        lines.append(f"[{result.status}] {result.name}: {result.message}")
    return "\n".join(lines)


def main(argv: Sequence[str] = None) -> int:
    parser = argparse.ArgumentParser(description="PLTN touch panel setup checker")
    parser.add_argument("--test", action="store_true", help="Run setup evaluation checks")
    parser.add_argument("--check-hardware", action="store_true", help="Alias for --test")
    parser.add_argument("--screen", type=int, default=0, help="Screen index to display the app on (0, 1, etc.)")
    parser.add_argument("--windowed", action="store_true", help="Accepted for future GUI compatibility")
    parser.add_argument("--demo-input", action="store_true", help="Run the TS-003 touch input prototype demo")
    parser.add_argument("--launch", action="store_true", help="Launch the TS-010 touchscreen base app")
    parser.add_argument("--describe-layout", action="store_true", help="Print the TS-010 baseline layout summary")
    args = parser.parse_args(argv)
    _ = args.test, args.check_hardware

    if args.demo_input:
        return run_input_demo()

    if args.describe_layout:
        spec = get_layout_spec()
        print("Tata Letak Panel Sentuh PLTN")
        print(f"Judul: {spec.title}")
        print(f"Subjudul: {spec.subtitle}")
        print(f"Lencana Atas: {', '.join(spec.top_badges)}")
        print(f"Grup Kontrol: {len(spec.control_groups)}")
        print(f"Kartu Status: {len(spec.status_cards)}")
        return 0

    if args.launch:
        return launch_touch_panel(windowed=args.windowed, screen_idx=args.screen)

    checker = TouchPanelSetupChecker()
    results = checker.run()
    print("Pemeriksaan Persiapan Panel Sentuh PLTN")
    print(format_results(results))
    print("")
    all_ok = all(result.is_ok for result in results)
    if all_ok:
        print("Pemeriksaan persiapan panel sentuh selesai tanpa kesalahan.")
        return 0
    print("Pemeriksaan persiapan panel sentuh menemukan kesalahan kritis.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
