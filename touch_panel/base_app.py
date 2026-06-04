"""PyQt5 touchscreen base app for the PLTN simulator.

This module contains the TS-010 shell:
- Fullscreen 1280x800 window with premium modern layout
- Custom hold gestures for control rods and pressurizer pressure
- Real-time binding to telemetry state (/tmp/pltn_state.json)
- Standalone interactive simulation fallback mode for demonstrations
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Callable, Dict

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

try:  # pragma: no cover - optional dependency
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import (
        QApplication,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPushButton,
        QSizePolicy,
        QSpacerItem,
        QVBoxLayout,
        QWidget,
        QProgressBar,
        QGraphicsDropShadowEffect,
    )
    from PyQt5.QtGui import QColor
    _PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - import guard for environments without PyQt5
    QApplication = None  # type: ignore[assignment]
    QFrame = object  # type: ignore[assignment]
    QGridLayout = object  # type: ignore[assignment]
    QGroupBox = object  # type: ignore[assignment]
    QHBoxLayout = object  # type: ignore[assignment]
    QLabel = object  # type: ignore[assignment]
    QMainWindow = object  # type: ignore[assignment]
    QPushButton = object  # type: ignore[assignment]
    QSizePolicy = object  # type: ignore[assignment]
    QSpacerItem = object  # type: ignore[assignment]
    QVBoxLayout = object  # type: ignore[assignment]
    QWidget = object  # type: ignore[assignment]
    QProgressBar = object  # type: ignore[assignment]
    QGraphicsDropShadowEffect = object  # type: ignore[assignment]
    Qt = None  # type: ignore[assignment]
    QColor = None  # type: ignore[assignment]
    QTimer = None  # type: ignore[assignment]
    _PYQT_AVAILABLE = False

try:
    from .input_handler import TouchInputHandler, TouchInputWriter
except ImportError:  # pragma: no cover - fallback for direct execution
    try:
        from input_handler import TouchInputHandler, TouchInputWriter
    except ImportError:
        TouchInputHandler = None  # type: ignore[assignment]
        TouchInputWriter = None  # type: ignore[assignment]


WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 600


@dataclass(frozen=True)
class PanelButtonSpec:
    label: str
    action: str
    emphasis: str = "neutral"


@dataclass(frozen=True)
class StatusCardSpec:
    title: str
    value: str
    accent: str = "neutral"


@dataclass(frozen=True)
class TouchPanelLayoutSpec:
    title: str = "PLTN Touch Panel"
    subtitle: str = "Baseline touchscreen shell for TS-010"
    top_badges: List[str] = field(default_factory=lambda: ["Mode: Manual", "1280x800", "PyQt5"])
    control_groups: List[List[PanelButtonSpec]] = field(
        default_factory=lambda: [
            [
                PanelButtonSpec("PUMP PRIMARY ON", "PUMP_PRIMARY_ON"),
                PanelButtonSpec("PUMP PRIMARY OFF", "PUMP_PRIMARY_OFF"),
                PanelButtonSpec("PUMP SECONDARY ON", "PUMP_SECONDARY_ON"),
                PanelButtonSpec("PUMP SECONDARY OFF", "PUMP_SECONDARY_OFF"),
                PanelButtonSpec("PUMP TERTIARY ON", "PUMP_TERTIARY_ON"),
                PanelButtonSpec("PUMP TERTIARY OFF", "PUMP_TERTIARY_OFF"),
            ],
            [
                PanelButtonSpec("SAFETY ROD ▲", "SAFETY_ROD_UP"),
                PanelButtonSpec("SAFETY ROD ▼", "SAFETY_ROD_DOWN"),
                PanelButtonSpec("SHIM ROD ▲", "SHIM_ROD_UP"),
                PanelButtonSpec("SHIM ROD ▼", "SHIM_ROD_DOWN"),
                PanelButtonSpec("REG ROD ▲", "REGULATING_ROD_UP"),
                PanelButtonSpec("REG ROD ▼", "REGULATING_ROD_DOWN"),
                PanelButtonSpec("PRESSURE ▲", "PRESSURE_UP"),
                PanelButtonSpec("PRESSURE ▼", "PRESSURE_DOWN"),
            ],
            [
                PanelButtonSpec("START AUTO", "START_AUTO_SIMULATION", "primary"),
                PanelButtonSpec("RESET", "REACTOR_RESET", "secondary"),
                PanelButtonSpec("EMERGENCY", "EMERGENCY", "danger"),
                PanelButtonSpec("LOFA SIMULATE", "LOFA_SIMULATE_PRIMARY", "warning"),
                PanelButtonSpec("LOFA CANCEL", "LOFA_CANCEL", "warning"),
            ],
        ]
    )
    status_cards: List[StatusCardSpec] = field(
        default_factory=lambda: [
            StatusCardSpec("Pressurizer", "155.5 bar"),
            StatusCardSpec("Pump Status", "P1/P2/P3 ON"),
            StatusCardSpec("Rod Position", "100 / 75 / 60"),
            StatusCardSpec("Thermal Power", "450000 kW"),
            StatusCardSpec("System Status", "Ready"),
            StatusCardSpec("Alarm", "None"),
        ]
    )
    footer_text: str = "Tap controls on the left. Hold the rod/pressure controls for continuous adjustment."


def get_layout_spec() -> TouchPanelLayoutSpec:
    return TouchPanelLayoutSpec()


if _PYQT_AVAILABLE:
    class HoldButton(QPushButton):
        """Button that triggers touch press and release, supporting repeat triggers for rods/pressure."""

        def __init__(self, text: str, action: str, parent_window: TouchPanelBaseWindow) -> None:
            super().__init__(text)
            self.action = action
            self.window_ref = parent_window
            self.hold_timer = QTimer(self)
            self.hold_timer.setInterval(50)  # 50ms = 20 Hz
            self.hold_timer.timeout.connect(self._on_timeout)
            
            self.pressed.connect(self._on_pressed)
            self.released.connect(self._on_released)

        def _on_pressed(self) -> None:
            self.window_ref._on_button_press(self.action)
            self.hold_timer.start()

        def _on_timeout(self) -> None:
            self.window_ref._on_button_hold(self.action)

        def _on_released(self) -> None:
            self.hold_timer.stop()
            self.window_ref._on_button_release(self.action)
else:
    class HoldButton:  # type: ignore[no-redef]
        pass


class TouchPanelBaseWindow(QMainWindow):
    """Fullscreen base window for the touchscreen panel."""

    def __init__(self, layout_spec: Optional[TouchPanelLayoutSpec] = None, windowed: bool = False) -> None:
        super().__init__()
        self.layout_spec = layout_spec or get_layout_spec()
        self.windowed = windowed
        self._footer_label = None
        self._mode_label = None
        
        # Initialize IPC Handlers
        self._init_ipc()
        
        # Initialize Simulation States
        self._init_simulation_state()
        
        # Build UI layout
        self._build_window()
        
        # Setup polling timer
        if _PYQT_AVAILABLE:
            self.update_timer = QTimer(self)
            self.update_timer.setInterval(100)  # 100ms
            self.update_timer.timeout.connect(self._on_timer_tick)
            self.update_timer.start()

    def _init_ipc(self) -> None:
        if TouchInputHandler is None or TouchInputWriter is None:
            self.input_handler = None
            return

        # Setup platform paths
        if sys.platform == "win32":
            self.input_writer = TouchInputWriter(Path("C:/temp/pltn_input.json"))
        else:
            self.input_writer = TouchInputWriter(Path("/tmp/pltn_input.json"))
            
        self.input_handler = TouchInputHandler(writer=self.input_writer)

    def _init_simulation_state(self) -> None:
        # Default state
        self.sim_pressure = 155.5
        self.sim_safety_rod = 100
        self.sim_shim_rod = 75
        self.sim_regulating_rod = 60
        self.sim_pump_primary = 1
        self.sim_pump_secondary = 1
        self.sim_pump_tertiary = 1
        self.sim_thermal_kw = 450000.0
        self.sim_turbine_speed = 85.0
        self.sim_mode = "Manual"
        self.sim_auto_running = False
        self.sim_emergency = False
        self.sim_alarm = "None"
        
        # Extended coolant & temperatures
        self.sim_coolant_temp_primary = 295.5
        self.sim_coolant_temp_secondary = 252.0
        self.sim_fuel_cladding_temp = 420.0
        self.sim_condenser_pressure = 0.05
        
        # Active holds and timers
        self._active_holds: Dict[str, float] = {}
        self.tick_counter = 0
        self.flash_toggle = False
        self.local_mode = True

    def _build_window(self) -> None:
        self.setWindowTitle(self.layout_spec.title)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        root = QWidget()
        root.setObjectName("centralWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_header())
        root_layout.addLayout(self._build_body())
        root_layout.addWidget(self._build_footer())

        self.setCentralWidget(root)
        self.setStyleSheet(self._stylesheet())

        if self.windowed:
            self.show()
            self._center_window()
        else:
            self.showFullScreen()

    def _center_window(self) -> None:
        if not _PYQT_AVAILABLE:
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        frame_geometry = self.frameGeometry()
        center_point = screen.availableGeometry().center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def _build_header(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("headerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("⚛️ " + self.layout_spec.title)
        title.setObjectName("titleLabel")
        subtitle = QLabel("REACTOR SIMULATION MANAGEMENT SYSTEM • TS-010")
        subtitle.setObjectName("subtitleLabel")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.badge_mode = QLabel(f"Mode: {self.sim_mode.upper()}")
        self.badge_mode.setObjectName("badgeMode")
        layout.addWidget(self.badge_mode)

        self.badge_status = QLabel("ONLINE")
        self.badge_status.setObjectName("badgeStatus")
        layout.addWidget(self.badge_status)

        self.badge_connection = QLabel("LOCAL DEMO")
        self.badge_connection.setObjectName("badgeConnection")
        layout.addWidget(self.badge_connection)

        return frame

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(self._build_control_column(), 40)
        body.addLayout(self._build_status_column(), 60)
        return body

    def _build_control_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        # 1. Primary Pumps Control Group (Arranged in a grid)
        pumps_group = QGroupBox("Primary Coolant Pumps")
        pumps_layout = QGridLayout(pumps_group)
        pumps_layout.setContentsMargins(12, 16, 12, 12)
        pumps_layout.setSpacing(10)
        
        self.btn_pump_p1_on = QPushButton("P1 ON")
        self.btn_pump_p1_on.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_ON"))
        self.btn_pump_p1_off = QPushButton("P1 OFF")
        self.btn_pump_p1_off.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_OFF"))
        
        self.btn_pump_p2_on = QPushButton("P2 ON")
        self.btn_pump_p2_on.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_ON"))
        self.btn_pump_p2_off = QPushButton("P2 OFF")
        self.btn_pump_p2_off.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_OFF"))
        
        self.btn_pump_p3_on = QPushButton("P3 ON")
        self.btn_pump_p3_on.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_ON"))
        self.btn_pump_p3_off = QPushButton("P3 OFF")
        self.btn_pump_p3_off.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_OFF"))

        pumps_layout.addWidget(QLabel("Primary Loop (P1):"), 0, 0)
        pumps_layout.addWidget(self.btn_pump_p1_on, 0, 1)
        pumps_layout.addWidget(self.btn_pump_p1_off, 0, 2)
        
        pumps_layout.addWidget(QLabel("Secondary Loop (P2):"), 1, 0)
        pumps_layout.addWidget(self.btn_pump_p2_on, 1, 1)
        pumps_layout.addWidget(self.btn_pump_p2_off, 1, 2)
        
        pumps_layout.addWidget(QLabel("Tertiary Loop (P3):"), 2, 0)
        pumps_layout.addWidget(self.btn_pump_p3_on, 2, 1)
        pumps_layout.addWidget(self.btn_pump_p3_off, 2, 2)
        column.addWidget(pumps_group)

        # 2. Control Rods & Pressure Group (Holdable buttons)
        rods_group = QGroupBox("Reactor Adjustments (Press and Hold)")
        rods_layout = QGridLayout(rods_group)
        rods_layout.setContentsMargins(12, 16, 12, 12)
        rods_layout.setSpacing(8)

        # Safety Rod
        rods_layout.addWidget(QLabel("Safety Rod:"), 0, 0)
        btn_saf_up = HoldButton("▲ UP", "SAFETY_ROD_UP", self)
        btn_saf_down = HoldButton("▼ DOWN", "SAFETY_ROD_DOWN", self)
        rods_layout.addWidget(btn_saf_up, 0, 1)
        rods_layout.addWidget(btn_saf_down, 0, 2)

        # Shim Rod
        rods_layout.addWidget(QLabel("Shim Rod:"), 1, 0)
        btn_shim_up = HoldButton("▲ UP", "SHIM_ROD_UP", self)
        btn_shim_down = HoldButton("▼ DOWN", "SHIM_ROD_DOWN", self)
        rods_layout.addWidget(btn_shim_up, 1, 1)
        rods_layout.addWidget(btn_shim_down, 1, 2)

        # Regulating Rod
        rods_layout.addWidget(QLabel("Regulating Rod:"), 2, 0)
        btn_reg_up = HoldButton("▲ UP", "REGULATING_ROD_UP", self)
        btn_reg_down = HoldButton("▼ DOWN", "REGULATING_ROD_DOWN", self)
        rods_layout.addWidget(btn_reg_up, 2, 1)
        rods_layout.addWidget(btn_reg_down, 2, 2)

        # Pressurizer
        rods_layout.addWidget(QLabel("Pressurizer Pressure:"), 3, 0)
        btn_press_up = HoldButton("▲ INC", "PRESSURE_UP", self)
        btn_press_down = HoldButton("▼ DEC", "PRESSURE_DOWN", self)
        rods_layout.addWidget(btn_press_up, 3, 1)
        rods_layout.addWidget(btn_press_down, 3, 2)
        column.addWidget(rods_group)

        # 3. System Operations Group
        sys_group = QGroupBox("System Simulation Operations")
        sys_layout = QGridLayout(sys_group)
        sys_layout.setContentsMargins(12, 16, 12, 12)
        sys_layout.setSpacing(10)

        btn_start_auto = QPushButton("START AUTO")
        btn_start_auto.setProperty("emphasis", "primary")
        btn_start_auto.clicked.connect(lambda: self._on_button_click("START_AUTO_SIMULATION"))
        
        btn_reset = QPushButton("RESET PANEL")
        btn_reset.setProperty("emphasis", "secondary")
        btn_reset.clicked.connect(lambda: self._on_button_click("REACTOR_RESET"))

        btn_lofa_sim = QPushButton("LOFA SIMULATE")
        btn_lofa_sim.setProperty("emphasis", "warning")
        btn_lofa_sim.clicked.connect(lambda: self._on_button_click("LOFA_SIMULATE_PRIMARY"))

        btn_lofa_cancel = QPushButton("LOFA CANCEL")
        btn_lofa_cancel.setProperty("emphasis", "warning")
        btn_lofa_cancel.clicked.connect(lambda: self._on_button_click("LOFA_CANCEL"))

        btn_emergency = QPushButton("🚨 EMERGENCY SCRAM")
        btn_emergency.setProperty("emphasis", "danger")
        btn_emergency.setMinimumHeight(48)
        btn_emergency.clicked.connect(lambda: self._on_button_click("EMERGENCY"))

        sys_layout.addWidget(btn_start_auto, 0, 0)
        sys_layout.addWidget(btn_reset, 0, 1)
        sys_layout.addWidget(btn_lofa_sim, 1, 0)
        sys_layout.addWidget(btn_lofa_cancel, 1, 1)
        sys_layout.addWidget(btn_emergency, 2, 0, 1, 2)
        column.addWidget(sys_group)

        return column

    def _build_status_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        # 1. Main Telemetry Cards (3x2 Grid Layout)
        grid_group = QGroupBox("Reactor Diagnostic Displays")
        grid = QGridLayout(grid_group)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)

        self.card_val_pressurizer = QLabel("0.0 bar")
        self.card_val_pumps = QLabel("P1/P2/P3 OFF")
        self.card_val_rods = QLabel("0 / 0 / 0")
        self.card_val_power = QLabel("0 kW")
        self.card_val_status = QLabel("Ready")
        self.card_val_alarm = QLabel("None")

        grid.addWidget(self._make_card("🌡️ Pressurizer", self.card_val_pressurizer, "cyan"), 0, 0)
        grid.addWidget(self._make_card("⚙️ Pump Status", self.card_val_pumps, "blue"), 0, 1)
        grid.addWidget(self._make_card("🍢 Rod Position (S/S/R)", self.card_val_rods, "purple"), 1, 0)
        grid.addWidget(self._make_card("⚡ Thermal Power Output", self.card_val_power, "amber"), 1, 1)
        grid.addWidget(self._make_card("📡 Operational Mode", self.card_val_status, "green"), 2, 0)
        grid.addWidget(self._make_card("🚨 Active System Alarms", self.card_val_alarm, "danger"), 2, 1)
        
        column.addWidget(grid_group, 3)

        # 2. Control Rod Positions progress bars (Visual indicators)
        rods_progress_group = QGroupBox("Control Rod Height Indicators")
        rods_progress_layout = QVBoxLayout(rods_progress_group)
        rods_progress_layout.setContentsMargins(12, 16, 12, 12)
        rods_progress_layout.setSpacing(8)

        # Safety rod progress bar
        saf_layout = QHBoxLayout()
        saf_label = QLabel("Safety:")
        saf_label.setFixedWidth(70)
        self.progress_safety_rod = QProgressBar()
        self.progress_safety_rod.setValue(100)
        self.progress_safety_rod.setStyleSheet(self._progress_bar_style("#059669")) # Green
        saf_layout.addWidget(saf_label)
        saf_layout.addWidget(self.progress_safety_rod)
        rods_progress_layout.addLayout(saf_layout)

        # Shim rod progress bar
        shim_layout = QHBoxLayout()
        shim_label = QLabel("Shim:")
        shim_label.setFixedWidth(70)
        self.progress_shim_rod = QProgressBar()
        self.progress_shim_rod.setValue(75)
        self.progress_shim_rod.setStyleSheet(self._progress_bar_style("#2563eb")) # Blue
        shim_layout.addWidget(shim_label)
        shim_layout.addWidget(self.progress_shim_rod)
        rods_progress_layout.addLayout(shim_layout)

        # Regulating rod progress bar
        reg_layout = QHBoxLayout()
        reg_label = QLabel("Regulating:")
        reg_label.setFixedWidth(70)
        self.progress_regulating_rod = QProgressBar()
        self.progress_regulating_rod.setValue(60)
        self.progress_regulating_rod.setStyleSheet(self._progress_bar_style("#7c3aed")) # Purple
        reg_layout.addWidget(reg_label)
        reg_layout.addWidget(self.progress_regulating_rod)
        rods_progress_layout.addLayout(reg_layout)

        column.addWidget(rods_progress_group, 2)

        # 3. Active LOFA Monitoring workspace (Temperatures grid & alarms)
        lofa_group = QGroupBox("Coolant Temperature & LOFA Safety Monitors")
        lofa_layout = QGridLayout(lofa_group)
        lofa_layout.setContentsMargins(12, 16, 12, 12)
        lofa_layout.setHorizontalSpacing(16)
        lofa_layout.setVerticalSpacing(8)

        self.temp_val_primary = QLabel("295.5 °C")
        self.temp_val_secondary = QLabel("252.0 °C")
        self.temp_val_fuel = QLabel("420.0 °C")
        self.temp_val_condenser = QLabel("0.05 bar")

        self.temp_val_primary.setObjectName("diagValue")
        self.temp_val_secondary.setObjectName("diagValue")
        self.temp_val_fuel.setObjectName("diagValue")
        self.temp_val_condenser.setObjectName("diagValue")

        # Layout temperature sensors
        lofa_layout.addWidget(QLabel("Primary Coolant Temp:"), 0, 0)
        lofa_layout.addWidget(self.temp_val_primary, 0, 1)
        lofa_layout.addWidget(QLabel("Secondary Coolant Temp:"), 0, 2)
        lofa_layout.addWidget(self.temp_val_secondary, 0, 3)

        lofa_layout.addWidget(QLabel("Fuel Cladding Temp:"), 1, 0)
        lofa_layout.addWidget(self.temp_val_fuel, 1, 1)
        lofa_layout.addWidget(QLabel("Condenser Vacuum Pressure:"), 1, 2)
        lofa_layout.addWidget(self.temp_val_condenser, 1, 3)

        # Status lights indicators
        self.indicator_relief = QLabel("RELIEF VALVE: CLOSED")
        self.indicator_relief.setObjectName("statusIndicatorLabel")
        self.indicator_spray = QLabel("SPRAY VALVE: INACTIVE")
        self.indicator_spray.setObjectName("statusIndicatorLabel")
        self.indicator_lofa = QLabel("SAFE OPERATIONAL ZONE")
        self.indicator_lofa.setObjectName("statusIndicatorLabel")
        
        indicator_layout = QHBoxLayout()
        indicator_layout.addWidget(self.indicator_relief)
        indicator_layout.addWidget(self.indicator_spray)
        indicator_layout.addWidget(self.indicator_lofa)
        
        lofa_layout.addLayout(indicator_layout, 2, 0, 1, 4)

        column.addWidget(lofa_group, 2)
        return column

    def _make_card(self, title_text: str, value_widget: QLabel, accent_color: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statusCard")
        frame.setProperty("accent", accent_color)
        
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName("cardTitle")
        value_widget.setObjectName("cardValue")
        
        layout.addWidget(title)
        layout.addWidget(value_widget)

        # Apply drop shadow effect
        if _PYQT_AVAILABLE:
            shadow = QGraphicsDropShadowEffect(self)
            shadow.setBlurRadius(8)
            shadow.setColor(QColor(0, 0, 0, 120))
            shadow.setOffset(0, 2)
            frame.setGraphicsEffect(shadow)

        return frame

    def _build_footer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("footerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        self._footer_label = QLabel(self.layout_spec.footer_text)
        self._footer_label.setObjectName("footerLabel")
        self._footer_label.setWordWrap(True)
        layout.addWidget(self._footer_label)
        return frame

    # ============================================
    # Touch Input Event Processors
    # ============================================

    def _on_button_click(self, action: str) -> None:
        if self.input_handler is not None:
            try:
                self.input_handler.emit(action, duration=0.0)
            except Exception as e:
                logger.error("Failed to write input event: %s", e)

        # Log action to footer
        if self._footer_label is not None:
            self._footer_label.setText(f"Triggered action command: {action}")
        self._on_action(action)

        # Update local simulation variables
        self._update_local_simulation(action)
        self._update_ui_displays()

    def _on_button_press(self, action: str) -> None:
        if self.input_handler is not None:
            try:
                self.input_handler.begin_touch(action)
            except Exception as e:
                logger.error("Failed to begin touch for %s: %s", action, e)
        self._active_holds[action] = time.time()

        if self._footer_label is not None:
            self._footer_label.setText(f"Adjusting: {action}...")

    def _on_button_hold(self, action: str) -> None:
        # In local mode, apply gradual changes during hold timer tick
        if self.local_mode:
            self._update_local_simulation_hold(action)
            self._update_ui_displays()

    def _on_button_release(self, action: str) -> None:
        if action in self._active_holds:
            start_ts = self._active_holds.pop(action)
            duration = max(0.0, time.time() - start_ts)
            
            if self.input_handler is not None:
                try:
                    self.input_handler.end_touch(action)
                except Exception as e:
                    logger.error("Failed to end touch for %s: %s", action, e)

            if self._footer_label is not None:
                self._footer_label.setText(f"Adjusted: {action} (duration: {duration:.2f}s)")

    def _on_action(self, action: str) -> None:
        """Kept for backward compatibility and logging."""
        logger.info("Touch panel action: %s", action)

    # ============================================
    # Standalone Offline Simulator Logic
    # ============================================

    def _update_local_simulation(self, action: str) -> None:
        # Prevent any manual action if SCRAM active, except Reset
        if self.sim_emergency and action != "REACTOR_RESET":
            return

        if action == "PUMP_PRIMARY_ON":
            self.sim_pump_primary = 1
        elif action == "PUMP_PRIMARY_OFF":
            self.sim_pump_primary = 0
        elif action == "PUMP_SECONDARY_ON":
            self.sim_pump_secondary = 1
        elif action == "PUMP_SECONDARY_OFF":
            self.sim_pump_secondary = 0
        elif action == "PUMP_TERTIARY_ON":
            self.sim_pump_tertiary = 1
        elif action == "PUMP_TERTIARY_OFF":
            self.sim_pump_tertiary = 0
            
        elif action == "START_AUTO_SIMULATION":
            self.sim_auto_running = True
            self.sim_mode = "Auto"
            self.sim_alarm = "None"
        elif action == "LOFA_SIMULATE_PRIMARY":
            self.sim_alarm = "LOFA PRIMARY ACTIVE!"
            self.sim_pump_primary = 0
        elif action == "LOFA_CANCEL":
            self.sim_alarm = "None"
            self.sim_pump_primary = 1
            
        elif action == "REACTOR_RESET":
            self._init_simulation_state()
            
        elif action == "EMERGENCY":
            self.sim_emergency = True
            self.sim_mode = "SCRAM"
            self.sim_alarm = "EMERGENCY SCRAM!"
            self.sim_pump_primary = 0
            self.sim_pump_secondary = 0
            self.sim_pump_tertiary = 0

    def _update_local_simulation_hold(self, action: str) -> None:
        if self.sim_emergency:
            return

        # Gradual adjustment rate per tick (100ms)
        if action == "SAFETY_ROD_UP":
            self.sim_safety_rod = min(100, self.sim_safety_rod + 2)
        elif action == "SAFETY_ROD_DOWN":
            self.sim_safety_rod = max(0, self.sim_safety_rod - 2)
        elif action == "SHIM_ROD_UP":
            self.sim_shim_rod = min(100, self.sim_shim_rod + 2)
        elif action == "SHIM_ROD_DOWN":
            self.sim_shim_rod = max(0, self.sim_shim_rod - 2)
        elif action == "REGULATING_ROD_UP":
            self.sim_regulating_rod = min(100, self.sim_regulating_rod + 2)
        elif action == "REGULATING_ROD_DOWN":
            self.sim_regulating_rod = max(0, self.sim_regulating_rod - 2)
        elif action == "PRESSURE_UP":
            self.sim_pressure = min(200.0, self.sim_pressure + 0.8)
        elif action == "PRESSURE_DOWN":
            self.sim_pressure = max(0.0, self.sim_pressure - 0.8)

    def _run_local_simulation_step(self) -> None:
        self.tick_counter += 1
        
        # Flashing triggers every 5 ticks (500ms)
        if self.tick_counter % 5 == 0:
            self.flash_toggle = not self.flash_toggle

        if self.sim_emergency:
            # Drop control rods immediately
            self.sim_safety_rod = max(0, self.sim_safety_rod - 15)
            self.sim_shim_rod = max(0, self.sim_shim_rod - 15)
            self.sim_regulating_rod = max(0, self.sim_regulating_rod - 15)
            
            # Collapse thermal energy
            self.sim_thermal_kw = max(0.0, self.sim_thermal_kw * 0.6)
            self.sim_turbine_speed = max(0.0, self.sim_turbine_speed - 12.0)
            
            # Cooldown temperature profiles
            self.sim_fuel_cladding_temp = max(35.0, self.sim_fuel_cladding_temp - 15.0)
            self.sim_coolant_temp_primary = max(35.0, self.sim_coolant_temp_primary - 10.0)
            self.sim_coolant_temp_secondary = max(35.0, self.sim_coolant_temp_secondary - 8.0)
            self.sim_pressure = max(1.0, self.sim_pressure - 8.0)
            return

        if self.sim_auto_running:
            # Auto mode physics loop
            # Thermal power stabilizes based on rod position sum
            rod_sum = (self.sim_safety_rod + self.sim_shim_rod + self.sim_regulating_rod) / 3.0
            target_kw = 450000.0 * (rod_sum / 78.3)
            self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.1
            
            # Turbines follow power output
            self.sim_turbine_speed += ((self.sim_thermal_kw / 5000.0) - self.sim_turbine_speed) * 0.05
            
            # Stabilize pressure
            self.sim_pressure += (155.5 - self.sim_pressure) * 0.08
            
            # Simple temperature sinusoidal oscillations
            t = time.time()
            self.sim_fuel_cladding_temp = 420.0 + (self.sim_thermal_kw / 20000.0) + 1.2 * math.sin(t * 0.5)
            self.sim_coolant_temp_primary = 295.5 + 0.5 * math.sin(t * 0.3)
            self.sim_coolant_temp_secondary = 252.0 + 0.3 * math.sin(t * 0.25)
            
        else:
            # Manual Mode: Slowly decay power if rods are low
            rod_sum = (self.sim_safety_rod + self.sim_shim_rod + self.sim_regulating_rod) / 300.0
            target_kw = 450000.0 * rod_sum
            
            # Pump multiplier adjusts thermal output dissipation
            pumps_count = self.sim_pump_primary + self.sim_pump_secondary + self.sim_pump_tertiary
            if pumps_count == 0:
                # No coolant flow! Temperature spike warning!
                self.sim_fuel_cladding_temp += 3.5
                self.sim_alarm = "COOLANT LOSS FAULT!"
                if self.sim_fuel_cladding_temp > 650.0:
                    # Automatic Scram!
                    self._update_local_simulation("EMERGENCY")
                    return
            else:
                self.sim_fuel_cladding_temp += (420.0 * rod_sum - self.sim_fuel_cladding_temp) * 0.05
                
            self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.05
            self.sim_turbine_speed += ((self.sim_thermal_kw / 5000.0) - self.sim_turbine_speed) * 0.05

    # ============================================
    # IPC State Binder and UI Updating
    # ============================================

    def _check_and_load_state(self) -> None:
        # Look for active telemetry state exports
        paths = []
        if sys.platform == "win32":
            paths.append(Path("C:/temp/pltn_state.json"))
        else:
            paths.append(Path("/tmp/pltn_state.json"))
        paths.append(Path(tempfile.gettempdir()) / "pltn_state.json")

        state_loaded = False
        for path in paths:
            if path.exists():
                try:
                    # Verify modification age (must be refreshed within 4 seconds)
                    mtime = os.path.getmtime(path)
                    if time.time() - mtime < 4.0:
                        with open(path, "r", encoding="utf-8") as f:
                            state_data = json.load(f)

                        # Parse state keys
                        self.sim_pressure = state_data.get("pressure", self.sim_pressure)
                        self.sim_safety_rod = state_data.get("rod_safety", state_data.get("safety_rod", self.sim_safety_rod))
                        self.sim_shim_rod = state_data.get("rod_shim", state_data.get("shim_rod", self.sim_shim_rod))
                        self.sim_regulating_rod = state_data.get("rod_regulating", state_data.get("regulating_rod", self.sim_regulating_rod))
                        
                        self.sim_pump_primary = state_data.get("pump_primary", self.sim_pump_primary)
                        self.sim_pump_secondary = state_data.get("pump_secondary", self.sim_pump_secondary)
                        self.sim_pump_tertiary = state_data.get("pump_tertiary", self.sim_pump_tertiary)
                        
                        self.sim_thermal_kw = state_data.get("thermal_kw", self.sim_thermal_kw)
                        self.sim_turbine_speed = state_data.get("turbine_speed", self.sim_turbine_speed)
                        self.sim_emergency = state_data.get("emergency", state_data.get("emergency_active", self.sim_emergency))
                        
                        # Set mode
                        auto_running = state_data.get("auto_running", False)
                        if self.sim_emergency:
                            self.sim_mode = "SCRAM"
                        elif auto_running:
                            self.sim_mode = "Auto"
                        else:
                            self.sim_mode = "Manual"
                            
                        # Ext coolant variables
                        self.sim_coolant_temp_primary = state_data.get("coolant_temp_primary", self.sim_coolant_temp_primary)
                        self.sim_coolant_temp_secondary = state_data.get("coolant_temp_secondary", self.sim_coolant_temp_secondary)
                        self.sim_fuel_cladding_temp = state_data.get("fuel_cladding_temp", self.sim_fuel_cladding_temp)
                        self.sim_condenser_pressure = state_data.get("condenser_pressure", self.sim_condenser_pressure)

                        # Set alarm
                        is_lofa = (state_data.get("lofa_primary", False) or 
                                   state_data.get("lofa_secondary", False) or 
                                   state_data.get("lofa_tertiary", False))
                        if self.sim_emergency:
                            self.sim_alarm = "EMERGENCY SCRAM!"
                        elif is_lofa:
                            self.sim_alarm = "LOFA ACTIVE!"
                        else:
                            self.sim_alarm = "None"

                        self.local_mode = False
                        state_loaded = True
                        break
                except Exception as e:
                    logger.debug("Failed reading state from %s: %s", path, e)

        if not state_loaded:
            # Switch back to local demo sandbox
            self.local_mode = True

    def _on_timer_tick(self) -> None:
        # Load external state or process internal physics
        self._check_and_load_state()
        
        if self.local_mode:
            # Read active holds and tick simulation physics
            for action in list(self._active_holds.keys()):
                self._on_button_hold(action)
            self._run_local_simulation_step()
        else:
            self.tick_counter += 1
            if self.tick_counter % 5 == 0:
                self.flash_toggle = not self.flash_toggle

        # Refresh UI indicators
        self._update_ui_displays()

    def _update_ui_displays(self) -> None:
        # 1. Update Diagnostics Cards values
        self.card_val_pressurizer.setText(f"{self.sim_pressure:.1f} bar")
        
        self.card_val_pumps.setText(
            f"P1: {'ON' if self.sim_pump_primary else 'OFF'} | "
            f"P2: {'ON' if self.sim_pump_secondary else 'OFF'} | "
            f"P3: {'ON' if self.sim_pump_tertiary else 'OFF'}"
        )
        
        self.card_val_rods.setText(f"{self.sim_safety_rod} / {self.sim_shim_rod} / {self.sim_regulating_rod}")
        self.card_val_power.setText(f"{self.sim_thermal_kw:,.0f} kW")
        self.card_val_status.setText(self.sim_mode.upper())
        self.card_val_alarm.setText(self.sim_alarm)

        # 2. Update Rod Height Progress bars
        self.progress_safety_rod.setValue(int(self.sim_safety_rod))
        self.progress_shim_rod.setValue(int(self.sim_shim_rod))
        self.progress_regulating_rod.setValue(int(self.sim_regulating_rod))

        # 3. Update Pumps Control buttons active styles
        self._set_button_active(self.btn_pump_p1_on, self.sim_pump_primary == 1)
        self._set_button_active_off(self.btn_pump_p1_off, self.sim_pump_primary == 0)
        self._set_button_active(self.btn_pump_p2_on, self.sim_pump_secondary == 1)
        self._set_button_active_off(self.btn_pump_p2_off, self.sim_pump_secondary == 0)
        self._set_button_active(self.btn_pump_p3_on, self.sim_pump_tertiary == 1)
        self._set_button_active_off(self.btn_pump_p3_off, self.sim_pump_tertiary == 0)

        # 4. Update Header Badges
        self.badge_mode.setText(f"Mode: {self.sim_mode.upper()}")
        
        if self.local_mode:
            self.badge_connection.setText("LOCAL DEMO")
            self.badge_connection.setStyleSheet("background-color: #d97706; border: 1px solid #fb923c;") # Amber
        else:
            self.badge_connection.setText("SYNCED")
            self.badge_connection.setStyleSheet("background-color: #059669; border: 1px solid #34d399;") # Emerald Green

        if self.sim_emergency:
            self.badge_status.setText("SCRAMMED")
            self.badge_status.setStyleSheet("background-color: #b91c1c; border: 1px solid #f87171;") # Red
        elif self.sim_alarm != "None":
            self.badge_status.setText("WARNING")
            self.badge_status.setStyleSheet("background-color: #c2410c; border: 1px solid #fb923c;") # Orange
        else:
            self.badge_status.setText("SYSTEM OK")
            self.badge_status.setStyleSheet("background-color: #0d9488; border: 1px solid #2dd4bf;") # Teal

        # 5. Update Coolant details
        self.temp_val_primary.setText(f"{self.sim_coolant_temp_primary:.1f} °C")
        self.temp_val_secondary.setText(f"{self.sim_coolant_temp_secondary:.1f} °C")
        self.temp_val_fuel.setText(f"{self.sim_fuel_cladding_temp:.1f} °C")
        self.temp_val_condenser.setText(f"{self.sim_condenser_pressure:.3f} bar")

        # Set Valve labels
        self.indicator_relief.setText(
            f"RELIEF VALVE: {'OPEN' if self.sim_pressure > 175 else 'CLOSED'}"
        )
        self.indicator_relief.setStyleSheet(
            "color: #fb923c;" if self.sim_pressure > 175 else "color: #94a3b8;"
        )

        self.indicator_spray.setText(
            f"SPRAY VALVE: {'ACTIVE' if self.sim_pressure > 162 else 'INACTIVE'}"
        )
        self.indicator_spray.setStyleSheet(
            "color: #38bdf8;" if self.sim_pressure > 162 else "color: #94a3b8;"
        )

        # Alarm indicator styling
        if self.sim_emergency:
            self.indicator_lofa.setText("⚠️ REACTOR EMERGENCY SCRAM ACTIVE ⚠️")
            self.indicator_lofa.setStyleSheet(
                "color: #ffffff; background-color: #991b1b; border: 1px solid #ef4444; border-radius: 4px; padding: 2px;"
                if self.flash_toggle else
                "color: #ef4444; background-color: #450a0a; border: 1px solid #991b1b; border-radius: 4px; padding: 2px;"
            )
        elif self.sim_alarm != "None":
            self.indicator_lofa.setText(f"🚨 {self.sim_alarm.upper()} 🚨")
            self.indicator_lofa.setStyleSheet(
                "color: #ffffff; background-color: #9a3412; border: 1px solid #f97316; border-radius: 4px; padding: 2px;"
                if self.flash_toggle else
                "color: #f97316; background-color: #431407; border: 1px solid #9a3412; border-radius: 4px; padding: 2px;"
            )
        else:
            self.indicator_lofa.setText("✅ ALL MONITORING LOOPS SECURE")
            self.indicator_lofa.setStyleSheet("color: #34d399; background: transparent; border: none;")

        # Active alarm display card flashing style
        if self.sim_alarm != "None" or self.sim_emergency:
            bg_color = "#991b1b" if self.flash_toggle else "#1e1b4b"
            self.card_val_alarm.parentWidget().setStyleSheet(
                f"background-color: {bg_color}; border: 1px solid #ef4444; border-radius: 10px;"
            )
        else:
            self.card_val_alarm.parentWidget().setStyleSheet(
                "background-color: #0f172a; border: 1px solid #1e293b; border-radius: 10px;"
            )

    def _set_button_active(self, btn: QPushButton, is_active: bool) -> None:
        if not _PYQT_AVAILABLE:
            return
        btn.setProperty("active", "true" if is_active else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _set_button_active_off(self, btn: QPushButton, is_active: bool) -> None:
        if not _PYQT_AVAILABLE:
            return
        btn.setProperty("active_off", "true" if is_active else "false")
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def _progress_bar_style(self, color: str) -> str:
        return f"""
        QProgressBar {{
            border: 1px solid #1e293b;
            background-color: #020617;
            border-radius: 4px;
            text-align: center;
            color: #ffffff;
            font-size: 10px;
            font-weight: bold;
            height: 14px;
        }}
        QProgressBar::chunk {{
            background-color: {color};
            border-radius: 3px;
        }}
        """

    def _stylesheet(self) -> str:
        return """
        QWidget#centralWidget {
            background-color: #070a13;
            color: #e2e8f0;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        }
        
        /* Groups container styles */
        QGroupBox {
            font-size: 13px;
            font-weight: bold;
            color: #38bdf8;
            border: 1px solid #1e293b;
            border-radius: 12px;
            margin-top: 14px;
            background-color: #0b0f19;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 15px;
            padding: 0 8px;
            background-color: #070a13;
        }

        QLabel {
            font-size: 13px;
            color: #94a3b8;
        }
        QLabel#diagValue {
            font-size: 14px;
            font-weight: bold;
            color: #f1f5f9;
        }
        
        /* Button default styles */
        QPushButton {
            background-color: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 10px;
            color: #e2e8f0;
            font-size: 13px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #334155;
            border-color: #475569;
        }
        QPushButton:pressed {
            background-color: #0f172a;
            border-color: #38bdf8;
        }

        /* Active pump control button custom states */
        QPushButton[active="true"] {
            background-color: #065f46;
            border: 1px solid #34d399;
            color: #a7f3d0;
        }
        QPushButton[active_off="true"] {
            background-color: #7f1d1d;
            border: 1px solid #f87171;
            color: #fca5a5;
        }

        /* Accent classes */
        QPushButton[emphasis="primary"] {
            background-color: #065f46;
            border: 1px solid #34d399;
            color: #a7f3d0;
        }
        QPushButton[emphasis="primary"]:hover {
            background-color: #047857;
        }

        QPushButton[emphasis="secondary"] {
            background-color: #1e3a8a;
            border: 1px solid #60a5fa;
            color: #dbeafe;
        }
        QPushButton[emphasis="secondary"]:hover {
            background-color: #1d4ed8;
        }

        QPushButton[emphasis="warning"] {
            background-color: #7c2d12;
            border: 1px solid #fb923c;
            color: #ffedd5;
        }
        QPushButton[emphasis="warning"]:hover {
            background-color: #9a3412;
        }

        QPushButton[emphasis="danger"] {
            background-color: #991b1b;
            border: 2px solid #ef4444;
            color: #ffffff;
            font-size: 15px;
            font-weight: bold;
        }
        QPushButton[emphasis="danger"]:hover {
            background-color: #b91c1c;
        }

        /* Status Cards */
        QFrame#statusCard {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 10px;
        }
        
        QLabel#cardTitle {
            color: #94a3b8;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }
        QLabel#cardValue {
            color: #38bdf8;
            font-size: 18px;
            font-weight: bold;
        }

        /* Border highlights based on accent value */
        QFrame#statusCard[accent="cyan"] { border-left: 4px solid #00e5ff; }
        QFrame#statusCard[accent="blue"] { border-left: 4px solid #3b82f6; }
        QFrame#statusCard[accent="purple"] { border-left: 4px solid #7c3aed; }
        QFrame#statusCard[accent="amber"] { border-left: 4px solid #f59e0b; }
        QFrame#statusCard[accent="green"] { border-left: 4px solid #10b981; }
        QFrame#statusCard[accent="danger"] { border-left: 4px solid #ef4444; }

        /* Header frame & title typography */
        QFrame#headerFrame {
            background-color: #0b0f19;
            border: 1px solid #1e293b;
            border-radius: 10px;
        }
        QLabel#titleLabel {
            color: #00e5ff;
            font-size: 20px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }
        QLabel#subtitleLabel {
            color: #475569;
            font-size: 10px;
            font-weight: bold;
        }
        
        /* Badges */
        QLabel#badgeMode, QLabel#badgeStatus, QLabel#badgeConnection {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: bold;
            color: #ffffff;
            border: 1px solid #334155;
            background-color: #1e293b;
        }
        QLabel#badgeStatus {
            background-color: #0d9488;
            border-color: #2dd4bf;
        }

        /* Footer frame styling */
        QFrame#footerFrame {
            background-color: #0b0f19;
            border: 1px solid #1e293b;
            border-radius: 8px;
        }
        QLabel#footerLabel {
            color: #64748b;
            font-size: 11px;
        }
        QLabel#statusIndicatorLabel {
            font-size: 11px;
            font-weight: bold;
            text-align: center;
        }
        """


def build_touch_panel_app(windowed: bool = False) -> tuple[QApplication, TouchPanelBaseWindow]:
    if not _PYQT_AVAILABLE:
        raise RuntimeError("PyQt5 is not installed; touchscreen base app cannot be launched")

    app = QApplication.instance() or QApplication(sys.argv)
    window = TouchPanelBaseWindow(windowed=windowed)
    return app, window


def launch_touch_panel(windowed: bool = False) -> int:
    app, _window = build_touch_panel_app(windowed=windowed)
    return app.exec_()
