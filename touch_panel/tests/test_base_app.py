from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from touch_panel.base_app import TouchPanelBaseWindow, get_layout_spec, _PYQT_AVAILABLE


class TouchPanelBaseAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _PYQT_AVAILABLE:
            from PyQt5.QtWidgets import QApplication
            cls.app = QApplication.instance() or QApplication([])
        else:
            cls.app = None

    def test_layout_spec_has_core_sections(self) -> None:
        spec = get_layout_spec()

        self.assertIn("PLTN", spec.title)
        self.assertGreaterEqual(len(spec.control_groups), 3)
        self.assertGreaterEqual(len(spec.status_cards), 6)

    def test_layout_spec_contains_expected_controls(self) -> None:
        spec = get_layout_spec()
        labels = {button.label for group in spec.control_groups for button in group}

        self.assertIn("DARURAT", labels)
        self.assertIn("ATUR ULANG", labels)
        self.assertIn("BATANG PENGAMAN ▲", labels)

    def test_layout_spec_contains_expected_status_cards(self) -> None:
        spec = get_layout_spec()
        titles = {card.title for card in spec.status_cards}

        self.assertIn("Pressurizer", titles)
        self.assertIn("Daya Termal", titles)
        self.assertIn("Status Sistem", titles)

    def _create_mock_screen(self, name: str, width: int, height: int, x: int = 0, y: int = 0):
        screen = MagicMock()
        screen.name.return_value = name
        geom = MagicMock()
        geom.width.return_value = width
        geom.height.return_value = height
        geom.x.return_value = x
        geom.y.return_value = y
        geom.topLeft.return_value = MagicMock()
        geom.size.return_value = MagicMock()
        screen.geometry.return_value = geom
        return screen

    @patch("touch_panel.base_app._PYQT_AVAILABLE", True)
    @patch("PyQt5.QtWidgets.QApplication.screens")
    def test_detect_target_screen_10_01_inch_resolution(self, mock_screens) -> None:
        if not _PYQT_AVAILABLE:
            self.skipTest("PyQt5 not available")
        # Mock dual screen setup: TV (1920x1080) and 10.01" Touchscreen (1280x800)
        screen_tv = self._create_mock_screen("XWAYLAND0", 1920, 1080, 0, 0)
        screen_touch = self._create_mock_screen("XWAYLAND1", 1280, 800, 1920, 0)
        mock_screens.return_value = [screen_tv, screen_touch]

        win = TouchPanelBaseWindow(windowed=True)
        detected = win._detect_target_screen()

        self.assertEqual(detected, screen_touch)

    @patch("touch_panel.base_app._PYQT_AVAILABLE", True)
    @patch("PyQt5.QtWidgets.QApplication.screens")
    def test_detect_target_screen_by_hdmi_name(self, mock_screens) -> None:
        if not _PYQT_AVAILABLE:
            self.skipTest("PyQt5 not available")
        screen_hdmi1 = self._create_mock_screen("HDMI-A-1", 1920, 1080, 0, 0)
        screen_hdmi2 = self._create_mock_screen("HDMI-A-2", 1920, 1080, 1920, 0)
        mock_screens.return_value = [screen_hdmi1, screen_hdmi2]

        win = TouchPanelBaseWindow(windowed=True)
        detected = win._detect_target_screen()

        self.assertEqual(detected, screen_hdmi2)

    @patch("touch_panel.base_app._PYQT_AVAILABLE", True)
    @patch("PyQt5.QtWidgets.QApplication.screens")
    def test_detect_target_screen_relative_size(self, mock_screens) -> None:
        if not _PYQT_AVAILABLE:
            self.skipTest("PyQt5 not available")
        # 4K monitor (3840x2160) and 10.01" panel (1024x600 fallback or 1280x720)
        screen_4k = self._create_mock_screen(":0.0", 3840, 2160, 0, 0)
        screen_touch = self._create_mock_screen(":0.1", 1280, 720, 3840, 0)
        mock_screens.return_value = [screen_4k, screen_touch]

        win = TouchPanelBaseWindow(windowed=True)
        detected = win._detect_target_screen()

        self.assertEqual(detected, screen_touch)

    @patch("touch_panel.base_app._PYQT_AVAILABLE", True)
    @patch("PyQt5.QtWidgets.QApplication.screens")
    def test_detect_target_screen_single_screen(self, mock_screens) -> None:
        if not _PYQT_AVAILABLE:
            self.skipTest("PyQt5 not available")
        screen_single = self._create_mock_screen("HDMI-A-1", 1280, 800, 0, 0)
        mock_screens.return_value = [screen_single]

        win = TouchPanelBaseWindow(windowed=True)
        detected = win._detect_target_screen()

        self.assertEqual(detected, screen_single)


if __name__ == "__main__":
    unittest.main()
