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
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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
    from PyQt5.QtCore import Qt, QTimer, pyqtSignal
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
    title: str = "ALAT PERAGA SIMULATOR PEMBANGKIT LISTRIK TENAGA NUKLIR (PLTN)"
    subtitle: str = "Panel Kontrol Utama Reaktor Tipe Pressurized Water Reactor (PWR)"
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
    class ClickableLabel(QLabel):
        clicked = pyqtSignal()
        def mousePressEvent(self, event):
            self.clicked.emit()
            super().mousePressEvent(event)

    class HoldButton(QPushButton):
        """Button that triggers touch press and release using Qt's native auto-repeat for rods/pressure."""

        def __init__(self, text: str, action: str, parent_window: TouchPanelBaseWindow) -> None:
            super().__init__(text)
            self.action = action
            self.window_ref = parent_window
            
            self.setAutoRepeat(True)
            self.setAutoRepeatDelay(300)
            self.setAutoRepeatInterval(50)  # 20 Hz
            
            self.clicked.connect(self._on_clicked)

        def _on_clicked(self) -> None:
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
        
        # Initialize Audio
        # Ditunda selama development — lihat juga _play_alarm()
        # self._init_audio()
        self.audio_enabled = False
        self.current_alarm = None
        self.scram_sound = None
        self.lofa_sound = None
        
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

        # Setup UDP IPC for Output (Sending user input)
        self.input_writer = TouchInputWriter(port=9999)
        self.input_handler = TouchInputHandler(writer=self.input_writer)
        
        # Setup UDP IPC for Input (Receiving simulation state)
        import socket
        try:
            self.state_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.state_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.state_sock.bind(("0.0.0.0", 9998))
            self.state_sock.setblocking(False)
        except Exception as e:
            logger.error(f"Gagal membuka UDP port 9998 untuk status reaktor: {e}")
            self.state_sock = None

    def _reset_sim_state_for_auto(self) -> None:
        """Resets target and history to prevent false failures when starting automatic simulations"""
        self.last_pump_states = {}
        self.target_pump_primary = 0.0
        self.target_pump_secondary = 0.0
        self.target_pump_tertiary = 0.0
        self.sim_pump_primary = 0.0
        self.sim_pump_secondary = 0.0
        self.sim_pump_tertiary = 0.0
        if hasattr(self, 'Primary_failed'): self.Primary_failed = False
        if hasattr(self, 'Secondary_failed'): self.Secondary_failed = False
        if hasattr(self, 'Tersier_failed'): self.Tersier_failed = False
        
    def _init_simulation_state(self) -> None:
        # Default state
        self.sim_pressure = 155.5
        self.sim_safety_rod = 100
        self.sim_shim_rod = 75
        self.sim_regulating_rod = 60
        self.sim_pump_primary = 0.0
        self.target_pump_primary = 0.0
        self.sim_pump_secondary = 0.0
        self.target_pump_secondary = 0.0
        self.sim_pump_tertiary = 0.0
        self.target_pump_tertiary = 0.0
        self.sim_thermal_kw = 450000.0
        self.sim_turbine_speed = 85.0
        self.sim_mode = "Manual"
        self.sim_auto_running = False
        self.sim_emergency = False
        self.sim_alarm = "Tidak Ada"
        self.sim_show_credits = False
        
        # Extended coolant & temperatures
        self.sim_coolant_temp_primary = 295.5
        self.sim_coolant_temp_secondary = 252.0
        self.sim_fuel_cladding_temp = 420.0
        self.sim_condenser_pressure = 0.05
        
        # Active holds and timers
        self.hold_timers: Dict[str, Tuple[QTimer, int]] = {}
        self._active_holds: Dict[str, float] = {}
        
        # Tick counter and display state
        self.tick_counter = 0
        self.flash_toggle = False
        self.local_mode = True
        
    def _init_audio(self) -> None:
        self.audio_enabled = False
        self.current_alarm = None
        # Audio alarm dimatikan sementara sesuai permintaan

    def _play_alarm(self, alarm_type: str) -> None:
        # Audio alarm dimatikan sementara sesuai permintaan
        pass
            
    def _stop_alarm(self) -> None:
        # Audio alarm dimatikan sementara sesuai permintaan
        pass

    def _update_audio_state(self) -> None:
        if self.sim_mode == "Otomatis":
            self._stop_alarm()
            return
            
        is_lofa = self.sim_alarm == "LOFA AKTIF!"
        if self.sim_emergency:
            self._play_alarm("SCRAM")
        elif is_lofa:
            self._play_alarm("LOFA")
        else:
            self._stop_alarm()

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
        # Footer disembunyikan agar lebih bersih
        # root_layout.addWidget(self._build_footer())

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
                    self._target_screen_name = target_screen.name()
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
        self._hud_widget = hud
        layout = QVBoxLayout(hud)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        start_btn = QPushButton("Mulai Mode\nManual")
        start_btn.setObjectName("hudStartBtn")
        start_btn.setFixedSize(360, 140)
        start_btn.setStyleSheet("""
            QPushButton {
                background-color: #3B82F6;
                color: white;
                font-size: 32px;
                font-weight: bold;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #2563EB; }
            QPushButton:pressed { background-color: #1D4ED8; }
        """)
        start_btn.clicked.connect(self._start_manual_mode)
        
        auto_btn = QPushButton("Mulai Mode\nOtomatis")
        auto_btn.setObjectName("hudAutoBtn")
        auto_btn.setFixedSize(360, 140)
        auto_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 32px;
                font-weight: bold;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:pressed { background-color: #047857; }
        """)
        auto_btn.clicked.connect(lambda: self._show_confirmation_overlay("auto"))
        
        lofa_btn = QPushButton("Simulasi\nLOFA")
        lofa_btn.setObjectName("hudLofaBtn")
        lofa_btn.setFixedSize(360, 140)
        lofa_btn.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-size: 32px;
                font-weight: bold;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #DC2626; }
            QPushButton:pressed { background-color: #B91C1C; }
        """)
        lofa_btn.clicked.connect(lambda: self._show_confirmation_overlay("lofa"))
        
        btn_layout.addWidget(start_btn)
        btn_layout.addWidget(auto_btn)
        btn_layout.addWidget(lofa_btn)
        
        # Spacer widget untuk layout utama agar form ada di tengah
        main_content = QWidget()
        main_content_layout = QVBoxLayout(main_content)
        main_content_layout.addStretch()
        main_content_layout.addWidget(title)
        main_content_layout.addWidget(subtitle)
        main_content_layout.addLayout(btn_layout)
        
        main_content_layout.addSpacing(40)
        
        credits_btn = QPushButton("Daftar Pengembang")
        credits_btn.setObjectName("hudCreditsBtn")
        credits_btn.setFixedSize(300, 60)
        credits_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                font-size: 20px;
                border: 2px solid #94A3B8;
                border-radius: 10px;
            }
            QPushButton:hover { background-color: rgba(148, 163, 184, 0.2); }
            QPushButton:pressed { background-color: rgba(148, 163, 184, 0.4); }
        """)
        credits_btn.clicked.connect(lambda: self._on_button_click("TOGGLE_CREDITS"))
        
        credits_layout = QHBoxLayout()
        credits_layout.setAlignment(Qt.AlignCenter)
        credits_layout.addWidget(credits_btn)
        
        main_content_layout.addLayout(credits_layout)
        main_content_layout.addStretch()
        
        layout.addWidget(main_content)
        
        # OVERLAY KONFIRMASI
        self._confirmation_overlay = QWidget(self)
        self._confirmation_overlay.setObjectName("confirmationOverlay")
        self._confirmation_overlay.setVisible(False)
        self._confirmation_overlay.setStyleSheet("background-color: rgba(2, 6, 23, 0.75);")
        self._confirmation_overlay.setGeometry(0, 0, self.width(), self.height())

        overlay_layout = QVBoxLayout(self._confirmation_overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        overlay_layout.setAlignment(Qt.AlignCenter)

        overlay_card = QWidget(self._confirmation_overlay)
        overlay_card.setObjectName("confirmationCard")
        overlay_card.setStyleSheet("""
            QWidget#confirmationCard {
                background-color: rgba(15, 23, 42, 0.96);
                border: 2px solid rgba(148, 163, 184, 0.5);
                border-radius: 30px;
            }
        """)
        overlay_card.setFixedSize(850, 420)

        card_layout = QVBoxLayout(overlay_card)
        card_layout.setContentsMargins(40, 40, 40, 40)
        card_layout.setSpacing(25)

        self._overlay_title = QLabel("Konfirmasi")
        self._overlay_title.setObjectName("overlayTitle")
        self._overlay_title.setAlignment(Qt.AlignCenter)
        self._overlay_title.setStyleSheet("font-size: 42px; font-weight: bold; color: #F8FAFC;")

        self._overlay_text = QLabel("...")
        self._overlay_text.setObjectName("overlayText")
        self._overlay_text.setAlignment(Qt.AlignCenter)
        self._overlay_text.setWordWrap(True)
        self._overlay_text.setStyleSheet("font-size: 26px; color: #E2E8F0; line-height: 1.5;")

        button_row = QHBoxLayout()
        button_row.setSpacing(20)
        button_row.setAlignment(Qt.AlignCenter)

        continue_btn = QPushButton("Lanjutkan")
        continue_btn.setFixedSize(260, 80)
        continue_btn.setStyleSheet("""
            QPushButton {
                background-color: #10B981;
                color: white;
                font-size: 26px;
                font-weight: bold;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:pressed { background-color: #047857; }
        """)
        continue_btn.clicked.connect(self._confirm_mode)

        cancel_btn = QPushButton("Batal")
        cancel_btn.setFixedSize(260, 80)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #475569;
                color: white;
                font-size: 26px;
                font-weight: bold;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #334155; }
            QPushButton:pressed { background-color: #1E293B; }
        """)
        cancel_btn.clicked.connect(self._cancel_confirmation)

        button_row.addWidget(cancel_btn)
        button_row.addWidget(continue_btn)

        card_layout.addStretch()
        card_layout.addWidget(self._overlay_title)
        card_layout.addWidget(self._overlay_text)
        card_layout.addLayout(button_row)
        card_layout.addStretch()
        overlay_layout.addWidget(overlay_card, 0, Qt.AlignCenter)
        
        hud.setStyleSheet("background-color: #0F172A;")
        return hud

    def _show_confirmation_overlay(self, mode: str) -> None:
        self._pending_mode = mode
        if mode == "auto":
            self._overlay_title.setText("Mode Otomatis Dipilih")
            self._overlay_text.setText("Layar akan berpindah ke simulasi otomatis. Tekan Lanjutkan untuk masuk, atau Batal untuk tetap di menu awal.")
        elif mode == "lofa":
            self._overlay_title.setText("Mode LOFA Dipilih")
            self._overlay_text.setText("Layar akan berpindah ke simulasi kegagalan aliran utama (LOFA). Tekan Lanjutkan untuk masuk, atau Batal untuk tetap di menu awal.")
        elif mode == "exit_auto":
            self._overlay_title.setText("Batalkan Otomatis?")
            self._overlay_text.setText("Yakin ingin membatalkan simulasi otomatis dan kembali ke menu utama?")
            
        if hasattr(self, '_confirmation_overlay') and self._confirmation_overlay is not None:
            self._confirmation_overlay.setGeometry(0, 0, self.width(), self.height())
            self._confirmation_overlay.setVisible(True)
            self._confirmation_overlay.raise_()

    def _cancel_confirmation(self) -> None:
        self._pending_mode = None
        if hasattr(self, '_confirmation_overlay') and self._confirmation_overlay is not None:
            self._confirmation_overlay.setVisible(False)

    def _confirm_mode(self) -> None:
        mode = getattr(self, '_pending_mode', None)
        self._cancel_confirmation()
        if mode == "auto":
            self._start_auto_mode()
        elif mode == "lofa":
            self._start_lofa_mode()
        elif mode == "exit_auto":
            self._execute_action("REACTOR_RESET")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_confirmation_overlay') and self._confirmation_overlay is not None:
            self._confirmation_overlay.setGeometry(0, 0, self.width(), self.height())

    def _start_manual_mode(self) -> None:
        import sys
        from pathlib import Path
        flag_path = Path("C:/temp/pltn_manual_started") if sys.platform == "win32" else Path("/tmp/pltn_manual_started")
        try:
            flag_path.parent.mkdir(parents=True, exist_ok=True)
            flag_path.touch()
        except Exception as e:
            logger.error("Failed to write manual started flag: %s", e)
            
        if _PYQT_AVAILABLE:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(250, lambda: self.stacked_widget.setCurrentIndex(1))
        else:
            self.stacked_widget.setCurrentIndex(1)

    def _start_auto_mode(self) -> None:
        self._on_button_click("START_AUTO_SIMULATION")
        
        if _PYQT_AVAILABLE:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(250, lambda: self.stacked_widget.setCurrentIndex(1))
        else:
            self.stacked_widget.setCurrentIndex(1)
        
    def _start_lofa_mode(self) -> None:
        self._on_button_click("START_CINEMATIC_LOFA")
        
        if _PYQT_AVAILABLE:
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(250, lambda: self.stacked_widget.setCurrentIndex(1))
        else:
            self.stacked_widget.setCurrentIndex(1)

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
        
        subtitle = QLabel("Panel Kontrol Utama Reaktor Tipe Pressurized Water Reactor (PWR)")
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
        
        if _PYQT_AVAILABLE:
            from PyQt5.QtWidgets import QStackedWidget
            self.body_stack = QStackedWidget()
            
            control_page = QWidget()
            control_layout = QVBoxLayout(control_page)
            control_layout.setContentsMargins(0, 0, 0, 0)
            control_layout.addLayout(self._build_control_column())
            
            status_page = self._build_status_dashboard()
            
            self.body_stack.addWidget(control_page)
            self.body_stack.addWidget(status_page)
            
            body.addWidget(self.body_stack, 100)
        else:
            body.addLayout(self._build_control_column(), 100)
            
        return body

    def _build_status_dashboard(self) -> QWidget:
        widget = QWidget()
        layout = QGridLayout(widget)
        layout.setContentsMargins(30, 40, 30, 40)
        layout.setSpacing(30)

        # 1. Parameter Termal (Left Column)
        self.lbl_dash_power = QLabel("0 kW")
        self.lbl_dash_pressure = QLabel("0 bar")
        self.lbl_dash_temp_pri = QLabel("0 °C")
        self.lbl_dash_temp_sec = QLabel("0 °C")
        
        param_group = QGroupBox("Parameter Utama")
        param_layout = QVBoxLayout(param_group)
        param_layout.setSpacing(15)
        param_layout.addWidget(QLabel("Daya Output Termal:"))
        param_layout.addWidget(self.lbl_dash_power)
        param_layout.addWidget(QLabel("Tekanan Pressurizer:"))
        param_layout.addWidget(self.lbl_dash_pressure)
        param_layout.addWidget(QLabel("Suhu Pendingin Primer:"))
        param_layout.addWidget(self.lbl_dash_temp_pri)
        param_layout.addWidget(QLabel("Suhu Pendingin Sekunder:"))
        param_layout.addWidget(self.lbl_dash_temp_sec)
        param_layout.addStretch()
        layout.addWidget(param_group, 0, 0)

        # 2. Batang Kendali (Middle Column)
        self.bar_safety = QProgressBar()
        self.bar_shim = QProgressBar()
        self.bar_reg = QProgressBar()
        
        for bar in [self.bar_safety, self.bar_shim, self.bar_reg]:
            bar.setMinimum(0)
            bar.setMaximum(100)
            bar.setTextVisible(True)
        
        rod_group = QGroupBox("Posisi Batang Kendali")
        rod_layout = QVBoxLayout(rod_group)
        rod_layout.setSpacing(15)
        rod_layout.addWidget(QLabel("Pengaman (Safety)"))
        rod_layout.addWidget(self.bar_safety)
        rod_layout.addWidget(QLabel("Kasar (Shim)"))
        rod_layout.addWidget(self.bar_shim)
        rod_layout.addWidget(QLabel("Halus (Regulating)"))
        rod_layout.addWidget(self.bar_reg)
        rod_layout.addStretch()
        layout.addWidget(rod_group, 0, 1)

        # 3. Status Pompa (Right Column)
        self.lbl_dash_pump1 = QLabel("Primer: OFF")
        self.lbl_dash_pump2 = QLabel("Sekunder: OFF")
        self.lbl_dash_pump3 = QLabel("Tersier: OFF")
        
        for lbl in [self.lbl_dash_pump1, self.lbl_dash_pump2, self.lbl_dash_pump3]:
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setProperty("is_pump", True)
            
        pump_group = QGroupBox("Status Pompa Pendingin")
        pump_layout = QVBoxLayout(pump_group)
        pump_layout.setSpacing(20)
        pump_layout.addWidget(self.lbl_dash_pump1)
        pump_layout.addWidget(self.lbl_dash_pump2)
        pump_layout.addWidget(self.lbl_dash_pump3)
        pump_layout.addStretch()
        layout.addWidget(pump_group, 0, 2)
        
        # Exit Auto Mode Button
        self.btn_exit_auto = QPushButton("Batalkan Simulasi Otomatis (Kembali ke Utama)")
        self.btn_exit_auto.setMinimumHeight(100)
        self.btn_exit_auto.setStyleSheet("""
            QPushButton {
                background-color: #EF4444;
                color: white;
                font-weight: bold;
                font-size: 28px;
                border-radius: 12px;
                margin-top: 20px;
            }
            QPushButton:pressed { background-color: #DC2626; }
        """)
        self.btn_exit_auto.clicked.connect(lambda: self._show_confirmation_overlay("exit_auto"))
        layout.addWidget(self.btn_exit_auto, 1, 0, 1, 3)
        
        # Style (Light Theme ala Pygame Display)
        widget.setStyleSheet("""
            QWidget {
                background-color: #F5F7FA;
            }
            QGroupBox {
                font-size: 22px;
                font-weight: bold;
                border: 2px solid #CBD5E1;
                border-radius: 12px;
                margin-top: 30px;
                padding: 20px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 10px;
                color: #0369A1; /* Light Blue/Navy */
                background-color: transparent;
            }
            QLabel {
                font-size: 24px;
                color: #334155;
                font-weight: bold;
            }
            QLabel[is_pump="true"] {
                font-size: 26px;
                color: #FFFFFF;
                background-color: #94A3B8;
                padding: 15px;
                border-radius: 8px;
            }
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                text-align: center;
                height: 40px;
                font-size: 20px;
                background-color: #F1F5F9;
                color: #0F172A;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #0EA5E9; /* Bright Blue */
                border-radius: 7px;
            }
        """)
        return widget

    def _build_control_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        # 1. Primary Pumps Control Group (Arranged vertically for each pump)
        pumps_group = QGroupBox("Kontrol Pompa Pendingin")
        pumps_layout = QHBoxLayout(pumps_group)
        pumps_layout.setContentsMargins(12, 2, 12, 8)
        pumps_layout.setSpacing(20)
        
        self.btn_pump_p1_on = QPushButton("POMPA PRIMER ON")
        self.btn_pump_p1_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p1_on.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_ON"))
        self.btn_pump_p1_off = QPushButton("POMPA PRIMER OFF")
        self.btn_pump_p1_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p1_off.clicked.connect(lambda: self._on_button_click("PUMP_PRIMARY_OFF"))
        
        self.btn_pump_p2_on = QPushButton("POMPA SEKUNDER ON")
        self.btn_pump_p2_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p2_on.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_ON"))
        self.btn_pump_p2_off = QPushButton("POMPA SEKUNDER OFF")
        self.btn_pump_p2_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p2_off.clicked.connect(lambda: self._on_button_click("PUMP_SECONDARY_OFF"))
        
        self.btn_pump_p3_on = QPushButton("POMPA TERSIER ON")
        self.btn_pump_p3_on.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p3_on.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_ON"))
        self.btn_pump_p3_off = QPushButton("POMPA TERSIER OFF")
        self.btn_pump_p3_off.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_pump_p3_off.clicked.connect(lambda: self._on_button_click("PUMP_TERTIARY_OFF"))

        # P1 layout (Vertical)
        p1_layout = QVBoxLayout()
        p1_layout.setSpacing(12)
        lbl_p1 = QLabel("Aliran Primer:")
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
        lbl_p2 = QLabel("Aliran Sekunder:")
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
        lbl_p3 = QLabel("Aliran Tersier:")
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

        self.btn_lofa_sim = QPushButton("Simulasi LOFA")
        self.btn_lofa_sim.setProperty("emphasis", "primary")
        self.btn_lofa_sim.setProperty("sys_op", "true")
        self.btn_lofa_sim.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_lofa_sim.clicked.connect(lambda: self._on_button_click("LOFA_SIMULATE_PRIMARY"))
        
        btn_reset = QPushButton("ATUR ULANG PANEL")
        btn_reset.setProperty("emphasis", "secondary")
        btn_reset.setProperty("sys_op", "true")
        btn_reset.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        btn_reset.clicked.connect(lambda: self._on_button_click("REACTOR_RESET"))

        self.btn_emergency = QPushButton("[!] SCRAM DARURAT")
        self.btn_emergency.setProperty("emphasis", "danger")
        self.btn_emergency.setProperty("sys_op", "true")
        self.btn_emergency.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_emergency.clicked.connect(lambda: self._on_button_click("EMERGENCY"))

        sys_layout.addWidget(self.btn_lofa_sim)
        sys_layout.addWidget(btn_reset)
        sys_layout.addWidget(self.btn_emergency)
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



    def _is_auto_running(self) -> bool:
        return self.sim_mode in ["Otomatis", "Simulasi LOFA", "LOFA Otomatis"] or getattr(self, 'last_auto_running', False)

    def _on_button_click(self, action: str) -> None:
        if self._is_auto_running():
            if self._footer_label is not None:
                self._footer_label.setText("Sistem terkunci. Input dinonaktifkan selama simulasi otomatis berjalan.")
            return
        self._execute_action(action)

    def _execute_action(self, action: str) -> None:
        if self.input_handler is not None:
            try:
                self.input_handler.emit(action)
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
            self._reset_sim_state_for_auto()
        elif action == "LOFA_SIMULATE_PRIMARY":
            self.sim_auto_running = True
            self.sim_mode = "LOFA Otomatis"
            self.sim_alarm = "LOFA PRIMER AKTIF!"
            self._reset_sim_state_for_auto()
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
            
        elif action == "TOGGLE_CREDITS":
            self.sim_show_credits = not getattr(self, 'sim_show_credits', False)
            if self.sim_show_credits and _PYQT_AVAILABLE:
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(16000, lambda: setattr(self, 'sim_show_credits', False))
            
        elif action == "PRESSURE_UP":
            if self.sim_pressure < 200.0:
                self.sim_pressure += 0.05
                self.sim_fuel_cladding_temp = min(self.sim_fuel_cladding_temp + 0.05, 350.0)
        elif action == "PRESSURE_DOWN":
            self.sim_pressure = max(0.0, self.sim_pressure - 0.05)
        elif action == "SAFETY_ROD_UP":
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
                setattr(self, pump_attr, min(target, current + 0.0143))
            elif current > target:
                setattr(self, pump_attr, max(target, current - 0.0143))

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
                effective_rod = (self.sim_shim_rod * 0.8 + self.sim_regulating_rod * 0.2) / 100.0
                if self.sim_safety_rod < 95.0:
                    effective_rod = 0.0
                target_kw = 450000.0 * effective_rod
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
                effective_rod = (self.sim_shim_rod * 0.8 + self.sim_regulating_rod * 0.2) / 100.0
                if self.sim_safety_rod < 95.0:
                    effective_rod = 0.0
                # Di auto mode lama pakai 450000 * (rod_sum/78.3), kita ganti langsung ke efektif
                target_kw = 450000.0 * effective_rod
                self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.1
                
                # Turbines follow power output
                self.sim_turbine_speed += ((self.sim_thermal_kw / 5000.0) - self.sim_turbine_speed) * 0.05
                
                # Stabilize pressure
                self.sim_pressure += (140.0 - self.sim_pressure) * 0.08
                
                # Simple temperature sinusoidal oscillations
                t = time.time()
                self.sim_fuel_cladding_temp = 420.0 + (self.sim_thermal_kw / 20000.0) + 1.2 * math.sin(t * 0.5)
                self.sim_coolant_temp_primary = 295.5 + 0.5 * math.sin(t * 0.3)
                self.sim_coolant_temp_secondary = 252.0 + 0.3 * math.sin(t * 0.25)
            
        else:
            # Manual Mode: Slowly decay power if rods are low
            effective_rod = (self.sim_shim_rod * 0.8 + self.sim_regulating_rod * 0.2) / 100.0
            if self.sim_safety_rod < 95.0:
                effective_rod = 0.0
            target_kw = 300000.0 * effective_rod
            
            # Pump multiplier adjusts thermal output dissipation
            pumps_count = self.sim_pump_primary + self.sim_pump_secondary + self.sim_pump_tertiary
            
            old_temp = self.sim_fuel_cladding_temp
            if pumps_count == 0:
                if effective_rod > 0.05:
                    # No coolant flow while active! Temperature spike warning!
                    self.sim_fuel_cladding_temp += 3.5
                    self.sim_alarm = "GANGGUAN KEHILANGAN PENDINGIN!"
                    if self.sim_fuel_cladding_temp > 650.0:
                        # Automatic Scram!
                        self._update_local_simulation("EMERGENCY")
                        return
                else:
                    # Cools down slowly to ambient
                    self.sim_fuel_cladding_temp += (35.0 - self.sim_fuel_cladding_temp) * 0.02
            else:
                self.sim_fuel_cladding_temp += (420.0 * effective_rod - self.sim_fuel_cladding_temp) * 0.05
                
            delta_temp = self.sim_fuel_cladding_temp - old_temp
            
            # Simulasi Pressurizer: Tekanan melonjak saat suhu naik (pemuaian)
            # Dihapus: auto-stabilisasi ke 140 bar agar tekanan murni manual / pemuaian termodinamika
            if effective_rod > 0.0:
                self.sim_pressure += (delta_temp * 1.5)
                
            # Turbin dan Daya baru dihasilkan jika panas melewati batas uap (80C)
            if self.sim_fuel_cladding_temp > 80.0:
                target_turbine = ((self.sim_fuel_cladding_temp - 80.0) / 340.0) * 100.0
                target_turbine = min(max(target_turbine, 0.0), 100.0)
            else:
                target_turbine = 0.0
                
            self.sim_turbine_speed += (target_turbine - self.sim_turbine_speed) * 0.05
            
            target_kw = (self.sim_turbine_speed / 100.0) * 300000.0
            if target_kw > self.sim_thermal_kw:
                self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.05
            else:
                self.sim_thermal_kw += (target_kw - self.sim_thermal_kw) * 0.15

    # ============================================
    # IPC State Binder and UI Updating
    # ============================================

    def _check_and_load_state(self) -> None:
        if not hasattr(self, 'state_sock') or self.state_sock is None:
            return
            
        latest_data = None
        while True:
            try:
                data, _ = self.state_sock.recvfrom(4096)
                latest_data = data
            except BlockingIOError:
                break
            except Exception as e:
                break
                
        if latest_data:
            try:
                state_data = json.loads(latest_data.decode("utf-8"))
                
                # Verify age (timestamp from backend)
                if time.time() - state_data.get("timestamp", 0) > 4.0:
                    self.local_mode = True
                    return
                    
                self.local_mode = False
                
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
                json_mode = state_data.get("mode", "")
                
                if not hasattr(self, 'last_auto_running'):
                    self.last_auto_running = False
                    
                # Detect any transition into an automatic simulation (Normal Auto, LOFA, Cinematic LOFA)
                is_any_auto = auto_running or json_mode == "cinematic_lofa"
                
                # If we just started any auto simulation, clear pump states to prevent false failures
                if is_any_auto and not self.last_auto_running:
                    self._reset_sim_state_for_auto()
                elif not is_any_auto and self.last_auto_running:
                    if hasattr(self, 'stacked_widget'):
                        self.stacked_widget.setCurrentIndex(0)
                    
                self.last_auto_running = is_any_auto
                
                if self.sim_emergency:
                    self.sim_mode = "SCRAM"
                elif json_mode == "cinematic_lofa":
                    self.sim_mode = "Simulasi LOFA"
                elif auto_running:
                    self.sim_mode = "Otomatis"
                else:
                    self.sim_mode = "Manual"
                    
                # Ext coolant variables
                self.sim_coolant_temp_primary = state_data.get("temperature_coolant", state_data.get("coolant_temp_primary", self.sim_coolant_temp_primary))
                self.sim_coolant_temp_secondary = state_data.get("temperature_coolant_secondary", state_data.get("coolant_temp_secondary", self.sim_coolant_temp_secondary))
                self.sim_fuel_cladding_temp = state_data.get("temperature_fuel_cladding", state_data.get("fuel_cladding_temp", self.sim_fuel_cladding_temp))
                self.sim_condenser_pressure = state_data.get("condenser_pressure", self.sim_condenser_pressure)
                self.sim_show_credits = state_data.get("show_credits", False)

                # Auto-clear pump failures if the reactor is fully reset/cold
                if self.sim_thermal_kw < 1.0 and self.sim_pressure < 10.0:
                    self.Primer_failed = False
                    self.Sekunder_failed = False
                    self.Tersier_failed = False
                    self.last_pump_states = {}
                    
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

            except Exception as e:
                logger.error(f"Error parsing UDP state JSON: {e}")
                pass
        else:
            self.local_mode = True
    def _on_timer_tick(self) -> None:
        # Check if our target monitor was disconnected
        if _PYQT_AVAILABLE:
            from PyQt5.QtWidgets import QApplication
            
            # Check if the screen we bound to initially is still in the screens list
            if hasattr(self, '_target_screen_name') and self._target_screen_name:
                screen_still_exists = any(s.name() == self._target_screen_name for s in QApplication.screens())
                if not screen_still_exists:
                    logger.error(f"Target screen {self._target_screen_name} disconnected! Exiting for watchdog restart.")
                    import sys
                    sys.exit(1)
            else:
                # Fallback to len check if we somehow don't have a specific name
                if len(QApplication.screens()) <= self.screen_idx:
                    logger.error(f"Screen {self.screen_idx} disconnected! Exiting for watchdog restart.")
                    import sys
                    sys.exit(1)

        # Load external state or process internal physics
        self._check_and_load_state()
        
        # Update Audio Alarms
        self._update_audio_state()
        
        # Update dynamic components:
        if self.local_mode:
            # Read active holds and tick simulation physics
            for action in list(self._active_holds.keys()):
                self._on_button_hold(action)
            self._run_local_simulation_step()
            self._broadcast_local_state()
        else:
            self.tick_counter += 1
            if self.tick_counter % 5 == 0:
                self.flash_toggle = not self.flash_toggle

        # Refresh UI indicators
        self._update_ui_displays()

    def _broadcast_local_state(self) -> None:
        if not hasattr(self, 'local_broadcast_sock'):
            import socket
            self.local_broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        state = {
            "timestamp": time.time(),
            "mode": self.sim_mode,
            "auto_running": self.sim_auto_running,
            "pressure": self.sim_pressure,
            "safety_rod": self.sim_safety_rod,
            "shim_rod": self.sim_shim_rod,
            "regulating_rod": self.sim_regulating_rod,
            "pump_primary": self.sim_pump_primary,
            "pump_secondary": self.sim_pump_secondary,
            "pump_tertiary": self.sim_pump_tertiary,
            "thermal_kw": self.sim_thermal_kw,
            "turbine_speed": self.sim_turbine_speed,
            "emergency": self.sim_emergency,
            "show_credits": getattr(self, 'sim_show_credits', False)
        }
        import json
        try:
            self.local_broadcast_sock.sendto(json.dumps(state).encode('utf-8'), ("127.0.0.1", 9997))
        except Exception:
            pass

    def _update_ui_displays(self) -> None:
        if hasattr(self, 'body_stack'):
            if self._is_auto_running():
                self.body_stack.setCurrentIndex(1)
            else:
                self.body_stack.setCurrentIndex(0)
                
            # Update Dashboard Values
            def pump_status_str(val):
                if val == 2: return "ON"
                elif val == 1: return "STARTING"
                elif val == 3: return "STOPPING"
                else: return "OFF"
                
            if hasattr(self, 'lbl_dash_pump1'):
                p1_str = "FAILED" if getattr(self, "Primer_failed", False) else pump_status_str(self.sim_pump_primary)
                p2_str = "FAILED" if getattr(self, "Sekunder_failed", False) else pump_status_str(self.sim_pump_secondary)
                p3_str = "FAILED" if getattr(self, "Tersier_failed", False) else pump_status_str(self.sim_pump_tertiary)
                
                self.lbl_dash_pump1.setText(f"Primer: {p1_str}")
                self.lbl_dash_pump2.setText(f"Sekunder: {p2_str}")
                self.lbl_dash_pump3.setText(f"Tersier: {p3_str}")
                
                def get_pump_color(status_str):
                    if status_str == "ON": return "#16A34A" # Green
                    if status_str == "FAILED": return "#DC2626" # Red
                    if status_str in ["STARTING", "STOPPING"]: return "#D97706" # Orange/Yellow
                    return "#475569" # Gray for OFF
                    
                self.lbl_dash_pump1.setStyleSheet(f"background-color: {get_pump_color(p1_str)};")
                self.lbl_dash_pump2.setStyleSheet(f"background-color: {get_pump_color(p2_str)};")
                self.lbl_dash_pump3.setStyleSheet(f"background-color: {get_pump_color(p3_str)};")
                
                self.bar_safety.setValue(int(self.sim_safety_rod))
                self.bar_shim.setValue(int(self.sim_shim_rod))
                self.bar_reg.setValue(int(self.sim_regulating_rod))
                
                self.lbl_dash_power.setText(f"{int(self.sim_thermal_kw):,} kW")
                self.lbl_dash_pressure.setText(f"{self.sim_pressure:.1f} bar")
                self.lbl_dash_temp_pri.setText(f"{self.sim_coolant_temp_primary:.1f} °C")
                self.lbl_dash_temp_sec.setText(f"{self.sim_coolant_temp_secondary:.1f} °C")

        # 1. Update Pumps Control buttons active styles
        self._apply_pump_state("Primer", self.btn_pump_p1_on, self.btn_pump_p1_off, self.sim_pump_primary, self.target_pump_primary)
        self._apply_pump_state("Sekunder", self.btn_pump_p2_on, self.btn_pump_p2_off, self.sim_pump_secondary, self.target_pump_secondary)
        self._apply_pump_state("Tersier", self.btn_pump_p3_on, self.btn_pump_p3_off, self.sim_pump_tertiary, self.target_pump_tertiary)

        # 1.5 Update System Operation buttons (SCRAM & LOFA) enabled states
        if hasattr(self, 'btn_emergency') and hasattr(self, 'btn_lofa_sim'):
            # Reaktor dianggap beroperasi jika ada batang kendali yang ditarik atau ada daya thermal
            reactor_operating = (self.sim_safety_rod > 0 or 
                                 self.sim_shim_rod > 0 or 
                                 self.sim_regulating_rod > 0 or 
                                 self.sim_thermal_kw > 0)
                                 
            # Ketiga pompa dianggap hidup jika nilainya 2 (ON)
            pumps_all_on = (self.sim_pump_primary == 2 and 
                            self.sim_pump_secondary == 2 and 
                            self.sim_pump_tertiary == 2)
            
            self.btn_emergency.setEnabled(reactor_operating)
            self.btn_lofa_sim.setEnabled(reactor_operating and pumps_all_on)

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

    def _apply_pump_state(self, pump_name: str, btn_on: QPushButton, btn_off: QPushButton, state_val: float, target_val: float) -> None:
        if not _PYQT_AVAILABLE:
            return
            
        if not hasattr(self, 'last_pump_states'):
            self.last_pump_states = {}
            
        last_state = self.last_pump_states.get(pump_name, 0.0)
        self.last_pump_states[pump_name] = state_val
        
        # Determine logical status
        # Backend values: 0=OFF, 1=STARTING, 2=ON, 3=SHUTTING_DOWN
        is_starting = (state_val == 1) or (0.0 < state_val < 1.0 and target_val > state_val)
        is_shutting_down = (state_val == 3) or (0.0 < state_val < 1.0 and target_val < state_val)
        is_on = (state_val == 2) or (state_val >= 1.0 and not is_starting and not is_shutting_down)
        is_off = (state_val == 0) or (state_val <= 0.0)
        
        # Determine if pump failed (went from ON/STARTING directly to OFF without SHUTTING_DOWN)
        pump_failed = False
        if is_off and (last_state == 2 or last_state == 1 or (last_state > 0.0 and last_state < 1.0 and target_val >= 1.0)):
            pump_failed = True
            
        failed_attr = f"{pump_name}_failed"
        if pump_failed:
            setattr(self, failed_attr, True)
        if is_starting or is_on or is_shutting_down:
            setattr(self, failed_attr, False)
            
        is_failed = getattr(self, failed_attr, False)

        # Update Text
        base_name = f"POMPA {pump_name.upper()}"
        if is_failed:
            btn_on.setText(f"{base_name} (GAGAL)")
            btn_off.setText(f"{base_name} OFF")
        elif is_starting:
            btn_on.setText(f"{base_name} (START UP)")
            btn_off.setText(f"{base_name} OFF")
        elif is_shutting_down:
            btn_on.setText(f"{base_name} ON")
            btn_off.setText(f"{base_name} (SHUT DOWN)")
        elif is_on:
            btn_on.setText(f"{base_name} ON")
            btn_off.setText(f"{base_name} OFF")
        else: # OFF
            btn_on.setText(f"{base_name} ON")
            btn_off.setText(f"{base_name} OFF")

        if is_off:
            btn_on.setProperty("active", "false")
            btn_on.setProperty("active_starting", "false")
            btn_on.setEnabled(True)
            
            btn_off.setProperty("active_off", "true" if not is_failed else "false")
            btn_off.setEnabled(False)
            
            if is_failed:
                btn_on.setProperty("active_off", "true" if self.flash_toggle else "false") # Flash red on failure!
            else:
                btn_on.setProperty("active_off", "false")
                
        elif is_on:
            btn_on.setProperty("active", "true")
            btn_on.setProperty("active_starting", "false")
            btn_on.setEnabled(False)
            
            btn_off.setProperty("active_off", "false")
            btn_off.setEnabled(True)
            btn_on.setProperty("active_off", "false")
        elif is_starting:
            btn_on.setProperty("active", "false")
            btn_on.setProperty("active_starting", "true" if self.flash_toggle else "false")
            btn_on.setEnabled(False)
            
            btn_off.setProperty("active_off", "false")
            btn_off.setEnabled(False)
            btn_on.setProperty("active_off", "false")
        elif is_shutting_down:
            btn_on.setProperty("active", "false")
            btn_on.setProperty("active_starting", "false")
            btn_on.setProperty("active_off", "false")
            btn_on.setEnabled(False)
            
            btn_off.setProperty("active_off", "true" if self.flash_toggle else "false")
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
            font-size: 24px;
            font-weight: 900;
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
        QPushButton[emphasis="primary"]:disabled {
            background-color: rgba(41, 142, 216, 128); /* Transparan */
            border: 2px solid rgba(30, 111, 168, 128);
            color: rgba(255, 255, 255, 128);
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
        QPushButton[emphasis="danger"]:disabled {
            background-color: rgba(255, 59, 48, 128); /* Transparan */
            border: 2px solid rgba(204, 47, 38, 128);
            color: rgba(255, 255, 255, 128);
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