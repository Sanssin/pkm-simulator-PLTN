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
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple, Callable, Dict

if TYPE_CHECKING:  # pragma: no cover
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
    from PyQt5.QtGui import QColor, QPixmap

logger = logging.getLogger(__name__)

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
        QStackedWidget,
    )
    from PyQt5.QtGui import QColor, QPixmap
    _PYQT_AVAILABLE = True
except Exception:  # pragma: no cover - import guard for environments without PyQt5
    _PYQT_AVAILABLE = False

try:
    from .input_handler import TouchInputHandler, TouchInputWriter
except ImportError:  # pragma: no cover - fallback for direct execution
    try:
        from input_handler import TouchInputHandler, TouchInputWriter
    except ImportError:
        TouchInputHandler = None  # type: ignore[assignment]
        TouchInputWriter = None  # type: ignore[assignment]


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800


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
    title: str = "Panel Sentuh PLTN"
    subtitle: str = "Shell layar sentuh dasar untuk TS-010"
    top_badges: List[str] = field(default_factory=lambda: ["Mode: Manual", "1280x800", "PyQt5"])
    control_groups: List[List[PanelButtonSpec]] = field(
        default_factory=lambda: [
            [
                PanelButtonSpec("POMPA PRIMER NYALA", "PUMP_PRIMARY_ON"),
                PanelButtonSpec("POMPA PRIMER MATI", "PUMP_PRIMARY_OFF"),
                PanelButtonSpec("POMPA SEKUNDER NYALA", "PUMP_SECONDARY_ON"),
                PanelButtonSpec("POMPA SEKUNDER MATI", "PUMP_SECONDARY_OFF"),
                PanelButtonSpec("POMPA TERSIER NYALA", "PUMP_TERTIARY_ON"),
                PanelButtonSpec("POMPA TERSIER MATI", "PUMP_TERTIARY_OFF"),
            ],
            [
                PanelButtonSpec("BATANG PENGAMAN ▲", "SAFETY_ROD_UP"),
                PanelButtonSpec("BATANG PENGAMAN ▼", "SAFETY_ROD_DOWN"),
                PanelButtonSpec("BATANG SHIM ▲", "SHIM_ROD_UP"),
                PanelButtonSpec("BATANG SHIM ▼", "SHIM_ROD_DOWN"),
                PanelButtonSpec("BATANG PENGATUR ▲", "REGULATING_ROD_UP"),
                PanelButtonSpec("BATANG PENGATUR ▼", "REGULATING_ROD_DOWN"),
                PanelButtonSpec("TEKANAN ▲", "PRESSURE_UP"),
                PanelButtonSpec("TEKANAN ▼", "PRESSURE_DOWN"),
            ],
            [
                PanelButtonSpec("Simulasi LOFA", "LOFA_SIMULATE_PRIMARY", "primary"),
                PanelButtonSpec("ATUR ULANG", "REACTOR_RESET", "secondary"),
                PanelButtonSpec("DARURAT", "EMERGENCY", "danger"),
            ],
        ]
    )
    status_cards: List[StatusCardSpec] = field(
        default_factory=lambda: [
            StatusCardSpec("Pressurizer", "155.5 bar"),
            StatusCardSpec("Status Pompa", "P1/P2/P3 NYALA"),
            StatusCardSpec("Posisi Batang", "100 / 75 / 60"),
            StatusCardSpec("Daya Termal", "450000 kW"),
            StatusCardSpec("Status Sistem", "Siap"),
            StatusCardSpec("Alarm", "Tidak Ada"),
        ]
    )
    footer_text: str = "Ketuk kontrol di sebelah kiri. Tahan kontrol batang/tekanan untuk penyesuaian terus-menerus."


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
            self.press_time = 0.0
            self.is_held = False
            
            self.pressed.connect(self._on_pressed)
            self.released.connect(self._on_released)

        def _on_pressed(self) -> None:
            self.press_time = time.time()
            self.is_held = False
            # Rod controls should begin touch immediately
            if "ROD" in self.action:
                self.window_ref._on_button_press(self.action)
            self.hold_timer.start()

        def _on_timeout(self) -> None:
            if time.time() - self.press_time > 0.30:
                if not self.is_held:
                    self.is_held = True
                    # Pressure controls start their touch when hold is confirmed
                    if "ROD" not in self.action:
                        self.window_ref._on_button_press(self.action)
                self.window_ref._on_button_hold(self.action)

        def _on_released(self) -> None:
            self.hold_timer.stop()
            if self.is_held or "ROD" in self.action:
                self.window_ref._on_button_release(self.action)
            
            # If not held, trigger a click action
            if not self.is_held and (time.time() - self.press_time <= 0.30):
                self.window_ref._on_button_click(self.action)
else:
    class HoldButton:  # type: ignore[no-redef]
        pass


class TouchPanelBaseWindow(QMainWindow):
    """Fullscreen base window for the touchscreen panel."""

    def __init__(self, layout_spec: Optional[TouchPanelLayoutSpec] = None, windowed: bool = False, screen_idx: int = 0) -> None:
        super().__init__()
        self.layout_spec = layout_spec or get_layout_spec()
        self.windowed = windowed
        self.screen_idx = screen_idx
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
        self.input_writer = None
        self.input_handler = None

        if TouchInputHandler is None or TouchInputWriter is None:
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
        self.sim_pump_primary = 1.0
        self.target_pump_primary = 1.0
        self.sim_pump_secondary = 1.0
        self.target_pump_secondary = 1.0
        self.sim_pump_tertiary = 1.0
        self.target_pump_tertiary = 1.0
        self.sim_thermal_kw = 450000.0
        self.sim_turbine_speed = 85.0
        self.sim_mode = "Manual"
        self.sim_auto_running = False
        self.sim_emergency = False
        self.sim_alarm = "Tidak Ada"
        
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
        if not _PYQT_AVAILABLE:
            return
        self.setWindowTitle(self.layout_spec.title)
        if self.windowed:
            self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
            self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        self.stacked_widget = QStackedWidget()

        hud_widget = self._build_hud()

        root = QWidget()
        root.setObjectName("centralWidget")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        root_layout.addWidget(self._build_header())
        root_layout.addLayout(self._build_body())
        root_layout.addWidget(self._build_footer())

        self.stacked_widget.addWidget(hud_widget)
        self.stacked_widget.addWidget(root)

        self.setCentralWidget(self.stacked_widget)
        self.setStyleSheet(self._stylesheet())

        if self.windowed:
            self.show()
            self._center_window()
        else:
            if _PYQT_AVAILABLE:
                screens = QApplication.screens()
                target_screen = None
                
                # Deterministically detect HDMI-A-2 for touchscreen panel (Wayland name or XWayland resolution)
                for screen in screens:
                    if "HDMI-A-2" in screen.name() or (screen.size().width() == 1024 and screen.size().height() == 600):
                        target_screen = screen
                        logger.info(f"Detected target touchscreen: {screen.name()} with size {screen.size().width()}x{screen.size().height()}")
                        break
                
                if not target_screen and 0 <= self.screen_idx < len(screens):
                    target_screen = screens[self.screen_idx]
                    logger.info(f"Fallback to screen index {self.screen_idx}: {target_screen.name()}")
                
                if target_screen:
                    # For Wayland deterministic output assignment, we must create native window handle
                    self.setAttribute(Qt.WA_NativeWindow, True)
                    self.winId()  # Force creation of the platform window handle
                    window_handle = self.windowHandle()
                    if window_handle:
                        window_handle.setScreen(target_screen)
                    # For XWayland/X11 compatibility
                    self.move(target_screen.geometry().topLeft())
                    
            self.showFullScreen()

    def _build_hud(self) -> QWidget:
        hud = QWidget()
        hud.setObjectName("hudWidget")
        layout = QVBoxLayout(hud)
        layout.setAlignment(Qt.AlignCenter)
        
        title = QLabel("PLTN Simulator")
        title.setObjectName("hudTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 56px; font-weight: bold; color: #E2E8F0; margin-bottom: 20px;")
        
        subtitle = QLabel("Tekan tombol di bawah untuk memulai.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 24px; color: #94A3B8; margin-bottom: 50px;")
        
        btn_layout = QHBoxLayout()
        btn_layout.setAlignment(Qt.AlignCenter)
        btn_layout.setSpacing(30)
        
        start_btn = QPushButton("Mulai Mode Manual")
        start_btn.setObjectName("hudStartBtn")
        start_btn.setFixedSize(320, 80)
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                font-size: 24px;
                font-weight: bold;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #2563EB;
            }
            QPushButton:pressed {
                background-color: #1D4ED8;
            }
        """)
        start_btn.clicked.connect(self._start_manual_mode)
        
        auto_btn = QPushButton("Mulai Mode Otomatis")
        auto_btn.setObjectName("hudAutoBtn")
        auto_btn.setFixedSize(320, 80)
        auto_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 24px;
                font-weight: bold;
                border-radius: 12px;
            }
            QPushButton:hover {
                background-color: #059669;
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        auto_btn.clicked.connect(self._start_auto_mode)
        
        btn_layout.addWidget(start_btn)
        btn_layout.addWidget(auto_btn)
        
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        hud.setStyleSheet("background-color: #0F172A;")
        return hud

    def _start_manual_mode(self) -> None:
        self.stacked_widget.setCurrentIndex(1)
        import sys
        from pathlib import Path
        flag_path = Path("C:/temp/pltn_manual_started") if sys.platform == "win32" else Path("/tmp/pltn_manual_started")
        try:
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.touch()
        except Exception as e:
            logger.error("Failed to write manual started flag: %s", e)

    def _start_auto_mode(self) -> None:
        self.stacked_widget.setCurrentIndex(1)
        self._on_button_click("START_AUTO_SIMULATION")

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

        # Load BRIN logo in PyQt5
        logo_label = QLabel()
        logo_path = Path(__file__).resolve().parents[1] / "pltn_video_display" / "assets" / "logo-brin.png"
        logo_exists = logo_path.exists() and _PYQT_AVAILABLE
        if logo_exists:
            pixmap = QPixmap(str(logo_path))
            scaled_pixmap = pixmap.scaledToHeight(48, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        
        title_text = QLabel(self.layout_spec.title)
        title_text.setObjectName("titleLabel")
        title_block.addWidget(title_text)
        
        subtitle = QLabel("SISTEM MANAJEMEN SIMULASI REAKTOR • TS-010")
        subtitle.setObjectName("subtitleLabel")
        title_block.addWidget(subtitle)

        if logo_exists:
            layout.addWidget(logo_label, 0, Qt.AlignBottom)
        layout.addLayout(title_block)
        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self.badge_mode = QLabel(f"Mode: {self.sim_mode.upper()}")
        self.badge_mode.setObjectName("badgeMode")
        layout.addWidget(self.badge_mode)

        self.badge_status = QLabel("ONLINE")
        self.badge_status.setObjectName("badgeStatus")
        layout.addWidget(self.badge_status)

        self.badge_connection = QLabel("DEMO LOKAL")
        self.badge_connection.setObjectName("badgeConnection")
        layout.addWidget(self.badge_connection)

        return frame

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addLayout(self._build_control_column(), 100)
        return body

    def _build_control_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        # 1. Primary Pumps Control Group (Arranged vertically for each pump)
        pumps_group = QGroupBox("Pompa Pendingin Primer")
        pumps_layout = QHBoxLayout(pumps_group)
        pumps_layout.setContentsMargins(12, 2, 12, 8)
        pumps_layout.setSpacing(20)
        
        self.btn_pump_p1_on = QPushButton("P1 NYALA")
        self.btn_pump_p1_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p1_on.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_ON"))
        self.btn_pump_p1_off = QPushButton("P1 MATI")
        self.btn_pump_p1_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p1_off.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_OFF"))
        
        self.btn_pump_p2_on = QPushButton("P2 NYALA")
        self.btn_pump_p2_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p2_on.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_ON"))
        self.btn_pump_p2_off = QPushButton("P2 MATI")
        self.btn_pump_p2_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p2_off.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_OFF"))
        
        self.btn_pump_p3_on = QPushButton("P3 NYALA")
        self.btn_pump_p3_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p3_on.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_ON"))
        self.btn_pump_p3_off = QPushButton("P3 MATI")
        self.btn_pump_p3_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p3_off.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_OFF"))

        # P1 layout (Vertical)
        p1_layout = QVBoxLayout()
        p1_layout.setSpacing(12)
        lbl_p1 = QLabel("Sirkuit Primer (P1):")
        lbl_p1.setWordWrap(True)
        lbl_p1.setFixedHeight(36)
        p1_layout.addWidget(lbl_p1)
        p1_buttons_layout = QVBoxLayout()
        p1_buttons_layout.setContentsMargins(0, 0, 0, 0)
        p1_buttons_layout.setSpacing(8)
        p1_buttons_layout.addWidget(self.btn_pump_p1_on)
        p1_buttons_layout.addWidget(self.btn_pump_p1_off)
        p1_layout.addLayout(p1_buttons_layout)
        
        # P2 layout (Vertical)
        p2_layout = QVBoxLayout()
        p2_layout.setSpacing(12)
        lbl_p2 = QLabel("Sirkuit Sekunder (P2):")
        lbl_p2.setWordWrap(True)
        lbl_p2.setFixedHeight(36)
        p2_layout.addWidget(lbl_p2)
        p2_buttons_layout = QVBoxLayout()
        p2_buttons_layout.setContentsMargins(0, 0, 0, 0)
        p2_buttons_layout.setSpacing(8)
        p2_buttons_layout.addWidget(self.btn_pump_p2_on)
        p2_buttons_layout.addWidget(self.btn_pump_p2_off)
        p2_layout.addLayout(p2_buttons_layout)
        
        # P3 layout (Vertical)
        p3_layout = QVBoxLayout()
        p3_layout.setSpacing(12)
        lbl_p3 = QLabel("Sirkuit Tersier (P3):")
        lbl_p3.setWordWrap(True)
        lbl_p3.setFixedHeight(36)
        p3_layout.addWidget(lbl_p3)
        p3_buttons_layout = QVBoxLayout()
        p3_buttons_layout.setContentsMargins(0, 0, 0, 0)
        p3_buttons_layout.setSpacing(8)
        p3_buttons_layout.addWidget(self.btn_pump_p3_on)
        p3_buttons_layout.addWidget(self.btn_pump_p3_off)
        p3_layout.addLayout(p3_buttons_layout)
        
        pumps_layout.addLayout(p1_layout, 1)
        pumps_layout.addLayout(p2_layout, 1)
        pumps_layout.addLayout(p3_layout, 1)
        column.addWidget(pumps_group)

        # 2. Control Rods & Pressure Group (Holdable buttons in stacked layout)
        rods_group = QGroupBox("Penyesuaian Reaktor (Tekan dan Tahan)")
        rods_layout = QHBoxLayout(rods_group)
        rods_layout.setContentsMargins(12, 2, 12, 8)
        rods_layout.setSpacing(15)

        # Safety Rod
        saf_layout = QVBoxLayout()
        saf_layout.setSpacing(12)
        lbl_saf = QLabel("Batang Pengaman:")
        lbl_saf.setWordWrap(True)
        lbl_saf.setFixedHeight(36)
        saf_layout.addWidget(lbl_saf)
        saf_buttons_layout = QVBoxLayout()
        saf_buttons_layout.setContentsMargins(0, 0, 0, 0)
        saf_buttons_layout.setSpacing(8)
        btn_saf_up = HoldButton("▲ NAIK", "SAFETY_ROD_UP", self)
        btn_saf_up.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_saf_down = HoldButton("▼ TURUN", "SAFETY_ROD_DOWN", self)
        btn_saf_down.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        saf_buttons_layout.addWidget(btn_saf_up)
        saf_buttons_layout.addWidget(btn_saf_down)
        saf_layout.addLayout(saf_buttons_layout)
        rods_layout.addLayout(saf_layout, 1)

        # Shim Rod
        shim_layout = QVBoxLayout()
        shim_layout.setSpacing(12)
        lbl_shim = QLabel("Batang Shim:")
        lbl_shim.setWordWrap(True)
        lbl_shim.setFixedHeight(36)
        shim_layout.addWidget(lbl_shim)
        shim_buttons_layout = QVBoxLayout()
        shim_buttons_layout.setContentsMargins(0, 0, 0, 0)
        shim_buttons_layout.setSpacing(8)
        btn_shim_up = HoldButton("▲ NAIK", "SHIM_ROD_UP", self)
        btn_shim_up.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_shim_down = HoldButton("▼ TURUN", "SHIM_ROD_DOWN", self)
        btn_shim_down.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        shim_buttons_layout.addWidget(btn_shim_up)
        shim_buttons_layout.addWidget(btn_shim_down)
        shim_layout.addLayout(shim_buttons_layout)
        rods_layout.addLayout(shim_layout, 1)

        # Regulating Rod
        reg_layout = QVBoxLayout()
        reg_layout.setSpacing(12)
        lbl_reg = QLabel("Batang Pengatur:")
        lbl_reg.setWordWrap(True)
        lbl_reg.setFixedHeight(36)
        reg_layout.addWidget(lbl_reg)
        reg_buttons_layout = QVBoxLayout()
        reg_buttons_layout.setContentsMargins(0, 0, 0, 0)
        reg_buttons_layout.setSpacing(8)
        btn_reg_up = HoldButton("▲ NAIK", "REGULATING_ROD_UP", self)
        btn_reg_up.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_reg_down = HoldButton("▼ TURUN", "REGULATING_ROD_DOWN", self)
        btn_reg_down.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        reg_buttons_layout.addWidget(btn_reg_up)
        reg_buttons_layout.addWidget(btn_reg_down)
        reg_layout.addLayout(reg_buttons_layout)
        rods_layout.addLayout(reg_layout, 1)

        # Pressurizer
        press_layout = QVBoxLayout()
        press_layout.setSpacing(12)
        lbl_press = QLabel("Tekanan Pressurizer:")
        lbl_press.setWordWrap(True)
        lbl_press.setFixedHeight(36)
        press_layout.addWidget(lbl_press)
        press_buttons_layout = QVBoxLayout()
        press_buttons_layout.setContentsMargins(0, 0, 0, 0)
        press_buttons_layout.setSpacing(8)
        btn_press_up = HoldButton("▲ NAIK", "PRESSURE_UP", self)
        btn_press_up.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_press_down = HoldButton("▼ TURUN", "PRESSURE_DOWN", self)
        btn_press_down.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        press_buttons_layout.addWidget(btn_press_up)
        press_buttons_layout.addWidget(btn_press_down)
        press_layout.addLayout(press_buttons_layout)
        rods_layout.addLayout(press_layout, 1)
        column.addWidget(rods_group)

        # 3. System Operations Group
        sys_group = QGroupBox("Operasi Simulasi Sistem")
        sys_layout = QHBoxLayout(sys_group)
        sys_layout.setContentsMargins(16, 20, 16, 20)
        sys_layout.setSpacing(16)

        btn_lofa_sim = QPushButton("Simulasi LOFA")
        btn_lofa_sim.setProperty("emphasis", "primary")
        btn_lofa_sim.setProperty("sys_op", "true")
        btn_lofa_sim.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_lofa_sim.clicked.connect(lambda: self._on_button_click("LOFA_SIMULATE_PRIMARY"))
        
        btn_start_auto = QPushButton("Simulasi Otomatis")
        btn_start_auto.setProperty("emphasis", "primary")
        btn_start_auto.setProperty("sys_op", "true")
        btn_start_auto.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_start_auto.clicked.connect(lambda: self._on_button_click("START_AUTO_SIMULATION"))
        
        btn_reset = QPushButton("ATUR ULANG PANEL")
        btn_reset.setProperty("emphasis", "secondary")
        btn_reset.setProperty("sys_op", "true")
        btn_reset.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_reset.clicked.connect(lambda: self._on_button_click("REACTOR_RESET"))

        btn_emergency = QPushButton("🚨 SCRAM DARURAT")
        btn_emergency.setProperty("emphasis", "danger")
        btn_emergency.setProperty("sys_op", "true")
        btn_emergency.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_emergency.clicked.connect(lambda: self._on_button_click("EMERGENCY"))

        sys_layout.addWidget(btn_start_auto)
        sys_layout.addWidget(btn_lofa_sim)
        sys_layout.addWidget(btn_reset)
        sys_layout.addWidget(btn_emergency)
        column.addWidget(sys_group)

        return column

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
            self._footer_label.setText(f"Perintah aksi dipicu: {action}")
        self._on_action(action)
        
        if action == "REACTOR_RESET":
            import sys
            from pathlib import Path
            flag_path = Path("C:/temp/pltn_manual_started") if sys.platform == "win32" else Path("/tmp/pltn_manual_started")
            try:
                if flag_path.exists():
                    flag_path.unlink()
            except Exception:
                pass
            if hasattr(self, 'stacked_widget'):
                self.stacked_widget.setCurrentIndex(0)

        # Update local simulation variables
        self._update_local_simulation(action)
        self._update_ui_displays()

    def _on_button_press(self, action: str) -> None:
        self._active_holds[action] = time.time()
        
        # Emit one event immediately for rods, so they feel responsive instantly
        if "ROD" in action and self.input_handler is not None:
            try:
                self.input_handler.emit(action, duration=0.0)
            except Exception as e:
                logger.error("Failed to begin touch for %s: %s", action, e)

        if self._footer_label is not None:
            self._footer_label.setText(f"Menyesuaikan: {action}...")

    def _on_button_hold(self, action: str) -> None:
        # In local mode, apply gradual changes during hold timer tick
        if self.local_mode:
            self._update_local_simulation_hold(action)
            self._update_ui_displays()
            
        # Send IPC event periodically for real-time update
        if self.input_handler is not None:
            try:
                self.input_handler.emit(action, duration=0.0)
            except Exception as e:
                logger.error("Failed to write hold input event: %s", e)

    def _on_button_release(self, action: str) -> None:
        if action in self._active_holds:
            start_ts = self._active_holds.pop(action)
            duration = max(0.0, time.time() - start_ts)

            if self._footer_label is not None:
                self._footer_label.setText(f"Telah disesuaikan: {action} (durasi: {duration:.2f}d)")

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
            self.target_pump_primary = 1.0
        elif action == "PUMP_PRIMARY_OFF":
            self.target_pump_primary = 0.0
        elif action == "PUMP_SECONDARY_ON":
            self.target_pump_secondary = 1.0
        elif action == "PUMP_SECONDARY_OFF":
            self.target_pump_secondary = 0.0
        elif action == "PUMP_TERTIARY_ON":
            self.target_pump_tertiary = 1.0
        elif action == "PUMP_TERTIARY_OFF":
            self.target_pump_tertiary = 0.0
            
        elif action == "START_AUTO_SIMULATION":
            self.sim_auto_running = True
            self.sim_mode = "Otomatis"
            self.sim_alarm = "Tidak Ada"
        elif action == "LOFA_SIMULATE_PRIMARY":
            self.sim_auto_running = True
            self.sim_mode = "LOFA Otomatis"
            self.sim_alarm = "LOFA PRIMER AKTIF!"
            self.target_pump_primary = 0.0
        elif action == "LOFA_CANCEL":
            self.sim_alarm = "Tidak Ada"
            self.target_pump_primary = 1.0
            
        elif action == "REACTOR_RESET":
            self._init_simulation_state()
            
        elif action == "EMERGENCY":
            self.sim_emergency = True
            self.sim_mode = "SCRAM"
            self.sim_alarm = "SCRAM DARURAT!"
            self.target_pump_primary = 0.0
            self.target_pump_secondary = 0.0
            self.target_pump_tertiary = 0.0
            
        elif action == "PRESSURE_UP":
            self.sim_pressure = min(200.0, self.sim_pressure + 0.05)
        elif action == "PRESSURE_DOWN":
            self.sim_pressure = max(0.0, self.sim_pressure - 0.05)

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
            self.sim_pressure = min(200.0, self.sim_pressure + 0.05)
        elif action == "PRESSURE_DOWN":
            self.sim_pressure = max(0.0, self.sim_pressure - 0.05)

    def _run_local_simulation_step(self) -> None:
        self.tick_counter += 1
        
        # Flashing triggers every 5 ticks (500ms)
        if self.tick_counter % 5 == 0:
            self.flash_toggle = not self.flash_toggle

        # Pump ramping
        for pump_attr, target_attr in [
            ("sim_pump_primary", "target_pump_primary"),
            ("sim_pump_secondary", "target_pump_secondary"),
            ("sim_pump_tertiary", "target_pump_tertiary")
        ]:
            current = getattr(self, pump_attr, 0.0)
            target = getattr(self, target_attr, 0.0)
            if current < target:
                setattr(self, pump_attr, min(target, current + 0.1))
            elif current > target:
                setattr(self, pump_attr, max(target, current - 0.1))

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
            if self.sim_mode == "LOFA Auto":
                # LOFA mode physics loop
                rod_sum = (self.sim_safety_rod + self.sim_shim_rod + self.sim_regulating_rod) / 300.0
                target_kw = 450000.0 * rod_sum
                # Temperature spikes rapidly due to primary coolant loss
                self.sim_fuel_cladding_temp += 5.0
                self.sim_coolant_temp_primary += 3.5
                
                if self.sim_fuel_cladding_temp > 650.0:
                    # Automatic Scram!
                    self._update_local_simulation("EMERGENCY")
                    return
                    
                self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.05
                self.sim_turbine_speed += ((self.sim_thermal_kw / 5000.0) - self.sim_turbine_speed) * 0.05
                self.sim_pressure = min(200.0, self.sim_pressure + 0.5)
            else:
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
                self.sim_alarm = "GANGGUAN KEHILANGAN PENDINGIN!"
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
                            self.sim_mode = "Otomatis"
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
                            self.sim_alarm = "SCRAM DARURAT!"
                        elif is_lofa:
                            self.sim_alarm = "LOFA AKTIF!"
                        else:
                            self.sim_alarm = "Tidak Ada"

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
        # 1. Update Pumps Control buttons active styles
        self._apply_pump_state(self.btn_pump_p1_on, self.btn_pump_p1_off, self.sim_pump_primary)
        self._apply_pump_state(self.btn_pump_p2_on, self.btn_pump_p2_off, self.sim_pump_secondary)
        self._apply_pump_state(self.btn_pump_p3_on, self.btn_pump_p3_off, self.sim_pump_tertiary)

        # 2. Update Header Badges
        self.badge_mode.setText(f"Mode: {self.sim_mode.upper()}")
        self.badge_mode.setStyleSheet("background-color: #2c3e50; border: 2px solid #2c3e50; color: #ffffff;")
        
        if self.local_mode:
            self.badge_connection.setText("LOCAL DEMO")
            self.badge_connection.setStyleSheet("background-color: #ffb400; border: 2px solid #cc9000; color: #ffffff;")
        else:
            self.badge_connection.setText("TERINKRONISASI")
            self.badge_connection.setStyleSheet("background-color: #3cd21e; border: 2px solid #2da616; color: #ffffff;")

        if self.sim_emergency:
            self.badge_status.setText("SCRAM AKTIF")
            self.badge_status.setStyleSheet("background-color: #ff3b30; border: 2px solid #cc2f26; color: #ffffff;")
        elif self.sim_alarm != "Tidak Ada":
            self.badge_status.setText("PERINGATAN")
            self.badge_status.setStyleSheet("background-color: #ffb400; border: 2px solid #cc9000; color: #ffffff;")
        else:
            self.badge_status.setText("SISTEM NORMAL")
            self.badge_status.setStyleSheet("background-color: #298ed8; border: 2px solid #1e6fa8; color: #ffffff;")

    def _apply_pump_state(self, btn_on: QPushButton, btn_off: QPushButton, state_val: float) -> None:
        if not _PYQT_AVAILABLE:
            return
            
        if state_val <= 0.0:  # STOPPED
            btn_on.setProperty("active", "false")
            btn_on.setProperty("active_starting", "false")
            btn_on.setEnabled(True)
            
            btn_off.setProperty("active_off", "true")
            btn_off.setEnabled(False)
        elif state_val >= 1.0:  # RUNNING
            btn_on.setProperty("active", "true")
            btn_on.setProperty("active_starting", "false")
            btn_on.setEnabled(False)
            
            btn_off.setProperty("active_off", "false")
            btn_off.setEnabled(True)
        else:  # STARTING
            btn_on.setProperty("active", "false")
            btn_on.setProperty("active_starting", "true" if self.flash_toggle else "false")
            btn_on.setEnabled(False)
            
            btn_off.setProperty("active_off", "false")
            btn_off.setEnabled(False)
            
        btn_on.style().unpolish(btn_on)
        btn_on.style().polish(btn_on)
        btn_off.style().unpolish(btn_off)
        btn_off.style().polish(btn_off)

    def _progress_bar_style(self, color: str) -> str:
        return f"""
        QProgressBar {{
            border: 1px solid #1e293b;
            background-color: #020617;
            border-radius: 4px;
            text-align: center;
            color: #ffffff;
            font-size: 13px;
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
            background-color: #f5f8fa;
            color: #2c3e50;
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        }
        
        /* Groups container styles */
        QGroupBox {
            font-size: 22px;
            font-weight: bold;
            color: #2c3e50;
            border: 2px solid #969696;
            border-radius: 12px;
            margin-top: 20px;
            background-color: #ffffff;
            padding: 12px 14px 14px 14px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 15px;
            padding: 0 8px;
            background-color: #f5f8fa;
            color: #2c3e50;
        }

        QLabel {
            font-size: 20px;
            font-weight: bold;
            color: #2c3e50;
        }
        QLabel#diagValue {
            font-size: 26px;
            font-weight: bold;
            color: #3cd21e;
        }
        
        /* Button default styles */
        QPushButton {
            background-color: #ffffff;
            border: 2px solid #969696;
            border-radius: 8px;
            padding: 10px;
            color: #2c3e50;
            font-size: 20px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
            border-color: #7f8c8d;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
            border-color: #298ed8;
        }
        
        /* Hold buttons (Reactor adjustment up/down) pressed styles */
        HoldButton:pressed {
            background-color: #298ed8;
            border-color: #1e6fa8;
            color: #ffffff;
        }

        /* Active pump control button custom states */
        QPushButton:disabled {
            background-color: #e2e8f0;
            border: 2px solid #cbd5e1;
            color: #94a3b8;
        }
        QPushButton[active="true"], QPushButton[active="true"]:disabled {
            background-color: #3cd21e;
            border: 2px solid #2da616;
            color: #ffffff;
        }
        QPushButton[active_starting="true"], QPushButton[active_starting="true"]:disabled {
            background-color: #ffb400;
            border: 2px solid #cc9000;
            color: #ffffff;
        }
        QPushButton[active_off="true"], QPushButton[active_off="true"]:disabled {
            background-color: #ff3b30;
            border: 2px solid #cc2f26;
            color: #ffffff;
        }

        /* Accent classes */
        QPushButton[emphasis="primary"] {
            background-color: #298ed8;
            border: 2px solid #1e6fa8;
            color: #ffffff;
        }
        QPushButton[emphasis="primary"]:hover {
            background-color: #1e6fa8;
        }

        QPushButton[emphasis="secondary"] {
            background-color: #7f8c8d;
            border: 2px solid #636e6f;
            color: #ffffff;
        }
        QPushButton[emphasis="secondary"]:hover {
            background-color: #636e6f;
        }

        QPushButton[emphasis="warning"] {
            background-color: #ffb400;
            border: 2px solid #cc9000;
            color: #ffffff;
        }
        QPushButton[emphasis="warning"]:hover {
            background-color: #cc9000;
        }

        QPushButton[emphasis="danger"] {
            background-color: #ff3b30;
            border: 2px solid #cc2f26;
            color: #ffffff;
            font-size: 22px;
            font-weight: bold;
        }
        QPushButton[emphasis="danger"]:hover {
            background-color: #cc2f26;
        }

        /* System Operations large buttons */
        QPushButton[sys_op="true"] {
            font-size: 26px;
            padding: 16px;
            border-radius: 12px;
        }

        /* Header frame & title typography */
        QFrame#headerFrame {
            background-color: #ffffff;
            border: 2px solid #969696;
            border-radius: 10px;
        }
        QLabel#titleLabel {
            color: #2c3e50;
            font-size: 28px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }
        QLabel#subtitleLabel {
            color: #7f8c8d;
            font-size: 18px;
            font-weight: bold;
        }
        
        /* Badges */
        QLabel#badgeMode, QLabel#badgeStatus, QLabel#badgeConnection {
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 18px;
            font-weight: bold;
            color: #ffffff;
            border: 2px solid #969696;
            background-color: #2c3e50;
        }

        /* Footer frame styling */
        QFrame#footerFrame {
            background-color: #ffffff;
            border: 2px solid #969696;
            border-radius: 8px;
        }
        QLabel#footerLabel {
            color: #7f8c8d;
            font-size: 18px;
            font-weight: bold;
        }
        """


def build_touch_panel_app(windowed: bool = False, screen_idx: int = 0) -> Tuple[QApplication, TouchPanelBaseWindow]:
    if not _PYQT_AVAILABLE:
        raise RuntimeError("PyQt5 is not installed; touchscreen base app cannot be launched")

    # Pastikan aplikasi PyQt5 mensintesis event klik mouse dari event sentuhan (Penting untuk Wayland)
    QApplication.setAttribute(Qt.AA_SynthesizeMouseForUnhandledTouchEvents, True)
    QApplication.setAttribute(Qt.AA_SynthesizeTouchForUnhandledMouseEvents, True)

    app = QApplication.instance() or QApplication(sys.argv)
    window = TouchPanelBaseWindow(windowed=windowed, screen_idx=screen_idx)
    return app, window


def launch_touch_panel(windowed: bool = False, screen_idx: int = 0) -> int:
    app, _window = build_touch_panel_app(windowed=windowed, screen_idx=screen_idx)
    return app.exec_()