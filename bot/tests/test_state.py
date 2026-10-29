"""Unit tests for state.py — typed conversation state accessors."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import state  # noqa: E402


class StateTests(unittest.TestCase):
    def test_awaiting_idea_for_set_take(self):
        ud = {}
        self.assertFalse(state.is_awaiting_idea_for(ud))
        state.set_awaiting_idea_for(ud, person_id=42, person_name="Mike")
        self.assertTrue(state.is_awaiting_idea_for(ud))
        v = state.take_awaiting_idea_for(ud)
        self.assertEqual((v.person_id, v.person_name), (42, "Mike"))
        # Take consumes
        self.assertFalse(state.is_awaiting_idea_for(ud))
        self.assertIsNone(state.take_awaiting_idea_for(ud))

    def test_awaiting_name_search_set_take(self):
        ud = {}
        self.assertFalse(state.is_awaiting_name_search(ud))
        state.set_awaiting_name_search(ud)
        self.assertTrue(state.is_awaiting_name_search(ud))
        self.assertTrue(state.take_awaiting_name_search(ud))
        # Take consumes
        self.assertFalse(state.is_awaiting_name_search(ud))
        self.assertFalse(state.take_awaiting_name_search(ud))

    def test_clear_drops_all(self):
        ud = {}
        state.set_awaiting_idea_for(ud, 1, "X")
        state.set_awaiting_name_search(ud)
        state.clear(ud)
        self.assertFalse(state.is_awaiting_idea_for(ud))
        self.assertFalse(state.is_awaiting_name_search(ud))

    def test_legacy_tuple_shape_tolerated(self):
        """Older bot versions stored awaiting_idea_for as a (person_id, name)
        tuple. The take() function should handle that gracefully so a deploy
        across the boundary doesn't trap users."""
        ud = {"awaiting_idea_for": (7, "Old Format")}
        v = state.take_awaiting_idea_for(ud)
        self.assertEqual((v.person_id, v.person_name), (7, "Old Format"))


if __name__ == "__main__":
    unittest.main()
