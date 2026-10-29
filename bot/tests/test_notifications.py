"""Unit tests for notifications._is_yesterday_birthday — the day-after detector.

The function exists to drive cycle close-out (archive purchased gifts the
day after each birthday). Robustness matters: a wrong answer here either
double-archives or fails to archive, both of which are user-visible.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from notifications import _is_yesterday_birthday  # noqa: E402


class IsYesterdayBirthdayTests(unittest.TestCase):
    def test_birthday_was_yesterday(self):
        self.assertTrue(_is_yesterday_birthday("1985-04-26", date(2026, 4, 27)))

    def test_birthday_today_is_not_yesterday(self):
        self.assertFalse(_is_yesterday_birthday("1985-04-27", date(2026, 4, 27)))

    def test_birthday_tomorrow_is_not_yesterday(self):
        self.assertFalse(_is_yesterday_birthday("1985-04-28", date(2026, 4, 27)))

    def test_year_does_not_matter(self):
        # Person born 2010, run date 2026 — only month/day count.
        self.assertTrue(_is_yesterday_birthday("2010-01-04", date(2026, 1, 5)))

    def test_month_boundary_yesterday(self):
        # Yesterday was the last day of the previous month.
        self.assertTrue(_is_yesterday_birthday("1990-04-30", date(2026, 5, 1)))

    def test_year_boundary_yesterday(self):
        # Today is Jan 1; "yesterday" is Dec 31.
        self.assertTrue(_is_yesterday_birthday("1990-12-31", date(2026, 1, 1)))

    def test_leap_year_birthday_after_feb29(self):
        # Born Feb 29; in a non-leap year today=Mar 1, "yesterday"=Feb 28
        # — so it should NOT match Feb 29 (correct: cycle closes on Mar 1
        # when the actual celebration day was Feb 28 in non-leap years.
        # The bot is intentionally conservative: only trigger on real
        # month/day equality with yesterday.)
        self.assertFalse(_is_yesterday_birthday("2000-02-29", date(2026, 3, 1)))

    def test_leap_year_birthday_in_leap_year(self):
        # On a leap year, March 1 yesterday = Feb 29, so a Feb-29 birthday
        # WAS yesterday — should match.
        self.assertTrue(_is_yesterday_birthday("2000-02-29", date(2024, 3, 1)))

    def test_none_birthday_returns_false(self):
        self.assertFalse(_is_yesterday_birthday(None, date(2026, 4, 27)))

    def test_empty_birthday_returns_false(self):
        self.assertFalse(_is_yesterday_birthday("", date(2026, 4, 27)))

    def test_malformed_birthday_returns_false(self):
        self.assertFalse(_is_yesterday_birthday("not-a-date", date(2026, 4, 27)))
        self.assertFalse(_is_yesterday_birthday("2026-13-01", date(2026, 4, 27)))


if __name__ == "__main__":
    unittest.main()
