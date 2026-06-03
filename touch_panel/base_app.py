"""PyQt5 touchscreen base app for the PLTN simulator.

This module contains the TS-010 shell:
- fullscreen 1280x800 window
- baseline layout derived from the touchscreen planning docs
- placeholder controls and status panels that can be expanded in TS-011+
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from PyQt5.QtCore import Qt
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
    )
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
    Qt = None  # type: ignore[assignment]
    _PYQT_AVAILABLE = False


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


class TouchPanelBaseWindow(QMainWindow):
    """Fullscreen base window for the touchscreen panel."""

    def __init__(self, layout_spec: Optional[TouchPanelLayoutSpec] = None, windowed: bool = False) -> None:
        super().__init__()
        self.layout_spec = layout_spec or get_layout_spec()
        self.windowed = windowed
        self._footer_label = None
        self._mode_label = None
        self._build_window()

    def _build_window(self) -> None:
        self.setWindowTitle(self.layout_spec.title)
        self.setMinimumSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        root = QWidget()
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
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        title_block = QVBoxLayout()
        title = QLabel(self.layout_spec.title)
        title.setObjectName("titleLabel")
        subtitle = QLabel(self.layout_spec.subtitle)
        subtitle.setObjectName("subtitleLabel")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))

        self._mode_label = QLabel(self.layout_spec.top_badges[0])
        self._mode_label.setObjectName("modeBadge")
        layout.addWidget(self._mode_label)
        for badge_text in self.layout_spec.top_badges[1:]:
            badge = QLabel(badge_text)
            badge.setObjectName("topBadge")
            layout.addWidget(badge)

        return frame

    def _build_body(self) -> QHBoxLayout:
        body = QHBoxLayout()
        body.setSpacing(14)

        body.addLayout(self._build_control_column(), 36)
        body.addLayout(self._build_status_column(), 64)
        return body

    def _build_control_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        section_titles = ["Primary Controls", "Rod & Pressure", "LOFA / System"]
        for title, group in zip(section_titles, self.layout_spec.control_groups):
            column.addWidget(self._build_button_group(title, group))

        column.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        return column

    def _build_button_group(self, title: str, buttons: Sequence[PanelButtonSpec]) -> QGroupBox:
        group = QGroupBox(title)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(8)

        for button_spec in buttons:
            button = QPushButton(button_spec.label)
            button.setProperty("emphasis", button_spec.emphasis)
            button.clicked.connect(lambda _=False, action=button_spec.action: self._on_action(action))
            button.setMinimumHeight(42)
            layout.addWidget(button)

        return group

    def _build_status_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(12)

        grid_group = QGroupBox("Status & Displays")
        grid = QGridLayout(grid_group)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        for index, card in enumerate(self.layout_spec.status_cards):
            card_widget = self._make_card(card)
            grid.addWidget(card_widget, index // 2, index % 2)

        column.addWidget(grid_group, 1)

        lo_fa_group = QGroupBox("LOFA Workspace")
        lo_fa_layout = QVBoxLayout(lo_fa_group)
        lo_fa_layout.setContentsMargins(12, 16, 12, 12)
        lo_fa_hint = QLabel("Reserved for LOFA controls, temperature indicators, and alarm overlays.")
        lo_fa_hint.setWordWrap(True)
        lo_fa_layout.addWidget(lo_fa_hint)
        column.addWidget(lo_fa_group, 0)
        return column

    def _make_card(self, card: StatusCardSpec) -> QFrame:
        frame = QFrame()
        frame.setObjectName("statusCard")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel(card.title)
        title.setObjectName("cardTitle")
        value = QLabel(card.value)
        value.setObjectName("cardValue")
        layout.addWidget(title)
        layout.addWidget(value)
        return frame

    def _build_footer(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("footerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 8, 12, 8)
        self._footer_label = QLabel(self.layout_spec.footer_text)
        self._footer_label.setWordWrap(True)
        layout.addWidget(self._footer_label)
        return frame

    def _on_action(self, action: str) -> None:
        if self._footer_label is not None:
            self._footer_label.setText(f"Selected action: {action}")
        logger.info("Touch panel action: %s", action)

    def _stylesheet(self) -> str:
        return """
        QWidget {
            background-color: #0b1220;
            color: #e5eefc;
            font-family: Arial, Helvetica, sans-serif;
            font-size: 14px;
        }
        QFrame#headerFrame, QFrame#footerFrame, QGroupBox, QFrame#statusCard {
            background-color: #101a2d;
            border: 1px solid #20304f;
            border-radius: 10px;
        }
        QLabel#titleLabel {
            font-size: 26px;
            font-weight: bold;
        }
        QLabel#subtitleLabel {
            color: #a8b8d8;
        }
        QLabel#modeBadge, QLabel#topBadge {
            padding: 8px 12px;
            border-radius: 8px;
            background-color: #1d2a46;
            border: 1px solid #2f4270;
        }
        QLabel#modeBadge {
            background-color: #1f6feb;
        }
        QGroupBox {
            font-weight: bold;
            padding-top: 14px;
        }
        QGroupBox::title {
            left: 12px;
            padding: 0 6px;
        }
        QPushButton {
            background-color: #23314f;
            border: 1px solid #32486f;
            border-radius: 8px;
            padding: 10px;
            text-align: left;
        }
        QPushButton:hover {
            background-color: #2a3c61;
        }
        QPushButton[emphasis="primary"] {
            background-color: #0f766e;
        }
        QPushButton[emphasis="warning"] {
            background-color: #9a6700;
        }
        QPushButton[emphasis="danger"] {
            background-color: #b42318;
        }
        QLabel#cardTitle {
            color: #9ab0d3;
            font-size: 12px;
        }
        QLabel#cardValue {
            font-size: 18px;
            font-weight: bold;
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

