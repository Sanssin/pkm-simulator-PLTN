from __future__ import annotations

import unittest

from touch_panel.base_app import get_layout_spec


class TouchPanelBaseAppTests(unittest.TestCase):
    def test_layout_spec_has_core_sections(self) -> None:
        spec = get_layout_spec()

        self.assertEqual(spec.title, "Panel Sentuh PLTN")
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


if __name__ == "__main__":
    unittest.main()
