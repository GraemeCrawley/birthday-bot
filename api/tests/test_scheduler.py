"""Tests for scheduler.calculate_days_until — the function that powers
days-until on the dashboard and "is it tomorrow yet" in notifications.

Critical post-fix invariant: this function uses the bot owner's local tz,
not UTC. A regression here brings back the off-by-one we just chased
(birthday Apr 28 showing days_until=0 at 8:31 PM ET because the container
is on UTC and `date.today()` already returned tomorrow).
"""

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scheduler  # noqa: E402


class CalculateDaysUntilTests(unittest.TestCase):
    def _patch_now(self, when_local: datetime):
        """Force scheduler.datetime.now() to return a fixed local-tz instant."""
        class _FakeDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return when_local.astimezone(tz) if tz else when_local
        # Pin the scheduler's local tz to the test's tz too, so the "evening
        # local is already tomorrow in UTC" case is exercised regardless of
        # the TZ the suite happens to run under.
        from contextlib import ExitStack
        stack = ExitStack()
        stack.enter_context(patch.object(scheduler, "datetime", _FakeDateTime))
        stack.enter_context(patch.object(scheduler, "LOCAL_TZ", when_local.tzinfo))
        return stack

    def test_birthday_today(self):
        with self._patch_now(datetime(2026, 4, 27, 8, 0, tzinfo=ZoneInfo("America/New_York"))):
            self.assertEqual(scheduler.calculate_days_until(date(1990, 4, 27)), 0)

    def test_birthday_tomorrow(self):
        with self._patch_now(datetime(2026, 4, 27, 8, 0, tzinfo=ZoneInfo("America/New_York"))):
            self.assertEqual(scheduler.calculate_days_until(date(1990, 4, 28)), 1)

    def test_birthday_already_passed_this_year(self):
        # Mid-July: an April birthday wraps to next year.
        with self._patch_now(datetime(2026, 7, 15, 12, 0, tzinfo=ZoneInfo("America/New_York"))):
            d = scheduler.calculate_days_until(date(1990, 4, 27))
            # Apr 27, 2027 is 286 days after Jul 15, 2026
            self.assertEqual(d, (date(2027, 4, 27) - date(2026, 7, 15)).days)

    def test_evening_local_time_does_not_roll_to_tomorrow(self):
        # The original bug: at 20:31 ET it's 00:31 UTC tomorrow, so a UTC
        # `date.today()` returned tomorrow's date. With the fix in place,
        # an Apr 28 birthday should report days_until=1 at 20:31 ET on Apr 27.
        when = datetime(2026, 4, 27, 20, 31, tzinfo=ZoneInfo("America/New_York"))
        with self._patch_now(when):
            self.assertEqual(scheduler.calculate_days_until(date(1990, 4, 28)), 1)

    def test_birthday_yesterday_wraps_a_full_year(self):
        # Today Apr 27, birthday Apr 26 → next celebration is Apr 26, 2027.
        when = datetime(2026, 4, 27, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        with self._patch_now(when):
            d = scheduler.calculate_days_until(date(1985, 4, 26))
            self.assertEqual(d, (date(2027, 4, 26) - date(2026, 4, 27)).days)


if __name__ == "__main__":
    unittest.main()
