"""Unit tests for parser.py — regex gift-capture patterns.

Run with: python -m unittest tests.test_parser
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from parser import parse  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_gift_for_dash(self):
        r = parse("gift for mike - cutting board")
        self.assertEqual((r.name, r.idea), ("mike", "cutting board"))

    def test_gift_for_em_dash(self):
        r = parse("gift for mom – flowers")
        self.assertEqual((r.name, r.idea), ("mom", "flowers"))

    def test_gift_for_colon(self):
        r = parse("Gift For Sarah: Wine glasses")
        self.assertEqual((r.name, r.idea), ("Sarah", "Wine glasses"))

    def test_add_for(self):
        r = parse("add cutting board for mike")
        self.assertEqual((r.name, r.idea), ("mike", "cutting board"))

    def test_short_colon(self):
        r = parse("mom: vase")
        self.assertEqual((r.name, r.idea), ("mom", "vase"))

    def test_extra_whitespace(self):
        r = parse("  gift for   mike    -    cutting board  ")
        self.assertEqual((r.name, r.idea), ("mike", "cutting board"))

    def test_case_insensitive_keyword(self):
        r = parse("GIFT FOR mike - thing")
        self.assertEqual((r.name, r.idea), ("mike", "thing"))

    def test_empty_input(self):
        self.assertIsNone(parse(""))
        self.assertIsNone(parse(None))
        self.assertIsNone(parse("   "))

    def test_no_pattern_match(self):
        self.assertIsNone(parse("hello there"))
        self.assertIsNone(parse("how are you?"))

    def test_overly_long_name_rejected(self):
        long = "x" * 80
        self.assertIsNone(parse(f"gift for {long} - thing"))

    def test_overly_long_idea_rejected(self):
        long = "y" * 250
        self.assertIsNone(parse(f"gift for mike - {long}"))

    def test_short_colon_with_internal_colon_rejected(self):
        # "::" emoji-like patterns shouldn't match
        self.assertIsNone(parse("nope :: foo"))

    def test_short_colon_no_idea(self):
        self.assertIsNone(parse("mike:"))

    def test_multi_word_name(self):
        r = parse("gift for Aunt Example - travel mug")
        self.assertEqual((r.name, r.idea), ("Aunt Example", "travel mug"))

    def test_idea_with_dollar_amount(self):
        r = parse("gift for dad - watch ($50)")
        self.assertEqual((r.name, r.idea), ("dad", "watch ($50)"))

    # Regression: parser used to require leading "gift for", which made users
    # typing the more natural "add gift for X - Y" fall through to the
    # bare-name-search path and end up saving the entire phrase as the idea.
    def test_add_prefix_dash(self):
        r = parse("add gift for Eve - homemade earrings")
        self.assertEqual((r.name, r.idea), ("Eve", "homemade earrings"))

    def test_add_prefix_colon(self):
        r = parse("Add gift for Sarah: wine glasses")
        self.assertEqual((r.name, r.idea), ("Sarah", "wine glasses"))

    def test_add_prefix_em_dash(self):
        r = parse("ADD gift for mom – flowers")
        self.assertEqual((r.name, r.idea), ("mom", "flowers"))


if __name__ == "__main__":
    unittest.main()
