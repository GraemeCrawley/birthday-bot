"""Tests for _format_notification — the daily DM's wording and buttons.

The rule these lock in: a notification ALWAYS states the purchase status, in
every one of the four states (bought / unbought with ideas / unbought without
ideas / day-of). Before this, the 60- and 30-day nudges said only "Gift ideas
on file:" and left you to infer that nothing had been bought.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import GiftIdea, Person  # noqa: E402
from notifications import _format_notification  # noqa: E402


def person(days, age=37):
    return Person(id=32, name="Ada Example", days_until=days,
                  age_turning=age, birthday="1988-05-05")


def gift(gid, idea, purchased=False, at=None):
    return GiftIdea(id=gid, person_id=32, idea=idea, purchased=purchased, purchased_at=at)


IDEAS = [gift(2, "climbing shoes"), gift(3, "cookbook")]
BOUGHT_ONE = [gift(1, "cutting board", True, "2026-08-16T14:26:00")] + IDEAS
BOUGHT_TWO = [
    gift(1, "cutting board", True, "2026-08-16T14:26:00"),
    gift(4, "wine glasses", True, "2026-08-02T09:00:00"),
    gift(2, "climbing shoes"),
]


def render(p, gifts):
    return _format_notification(p, gifts, any(g.purchased for g in gifts))


def buttons(kb):
    return [b.text for row in kb.inline_keyboard for b in row]


class StatusAlwaysStatedTests(unittest.TestCase):
    """Every state says, in words, whether anything has been bought."""

    def test_unbought_at_60_days_says_nothing_bought(self):
        text, _ = render(person(60), IDEAS)
        self.assertIn("Nothing bought yet", text)

    def test_unbought_at_30_days_says_nothing_bought(self):
        text, _ = render(person(30), IDEAS)
        self.assertIn("Nothing bought yet", text)

    def test_no_ideas_at_all_still_states_status(self):
        text, _ = render(person(30), [])
        self.assertIn("Nothing bought yet", text)
        self.assertIn("no ideas captured", text)

    def test_bought_says_bought(self):
        text, _ = render(person(7), BOUGHT_ONE)
        self.assertIn("Bought", text)

    def test_urgency_marker_only_within_a_week(self):
        far, _ = render(person(30), IDEAS)
        near, _ = render(person(7), IDEAS)
        self.assertNotIn("⚠", far)
        self.assertIn("⚠", near)

    def test_idea_count_is_pluralised(self):
        one, _ = render(person(30), [gift(2, "cookbook")])
        two, _ = render(person(30), IDEAS)
        self.assertIn("1 idea on file", one)
        self.assertIn("2 ideas on file", two)


class BoughtGiftIsNamedTests(unittest.TestCase):
    """If something was bought, the message says what it was."""

    def test_single_purchase_named_inline_with_date(self):
        text, _ = render(person(7), BOUGHT_ONE)
        self.assertIn("cutting board", text)
        self.assertIn("Aug 16", text)

    def test_multiple_purchases_listed_with_count(self):
        text, _ = render(person(7), BOUGHT_TWO)
        self.assertIn("Bought (2)", text)
        self.assertIn("cutting board", text)
        self.assertIn("wine glasses", text)
        self.assertIn("Aug 2", text)

    def test_remaining_ideas_still_listed_when_bought(self):
        text, _ = render(person(7), BOUGHT_ONE)
        self.assertIn("Still on the list", text)
        self.assertIn("climbing shoes", text)

    def test_no_remaining_section_when_everything_bought(self):
        text, _ = render(person(7), [gift(1, "cutting board", True, "2026-08-16T14:26:00")])
        self.assertNotIn("Still on the list", text)

    def test_day_of_names_the_gift(self):
        text, _ = render(person(0), BOUGHT_ONE)
        self.assertIn("today", text)
        self.assertIn("cutting board", text)

    def test_missing_purchase_date_omits_parenthetical(self):
        text, _ = render(person(7), [gift(1, "cutting board", True, None)])
        self.assertIn("cutting board", text)
        self.assertNotIn("()", text)

    def test_malformed_purchase_date_does_not_crash(self):
        text, _ = render(person(7), [gift(1, "cutting board", True, "not-a-date")])
        self.assertIn("cutting board", text)


class MarkButtonsTests(unittest.TestCase):
    """Buying one gift must not remove the way to record the next one."""

    def test_mark_buttons_present_when_nothing_bought(self):
        _, kb = render(person(7), IDEAS)
        self.assertTrue(any("climbing shoes" in b for b in buttons(kb)))

    def test_mark_buttons_survive_a_purchase(self):
        # Regression: the old code hid these as soon as anything was bought.
        _, kb = render(person(7), BOUGHT_ONE)
        labels = buttons(kb)
        self.assertTrue(any("climbing shoes" in b for b in labels),
                        f"remaining ideas need mark buttons, got {labels}")

    def test_no_mark_buttons_when_everything_bought(self):
        _, kb = render(person(7), [gift(1, "cutting board", True, "2026-08-16T14:26:00")])
        self.assertFalse(any("Mark" in b for b in buttons(kb)))

    def test_always_offers_add_and_upcoming(self):
        for gifts in ([], IDEAS, BOUGHT_ONE):
            _, kb = render(person(30), gifts)
            labels = " ".join(buttons(kb))
            self.assertIn("Add idea", labels)
            self.assertIn("upcoming", labels.lower())


class HeaderTests(unittest.TestCase):
    def test_no_stray_period_before_comma(self):
        # Was rendering "is in 60 days., turning 37".
        text, _ = render(person(60), IDEAS)
        self.assertNotIn("days.,", text)
        self.assertIn("in 60 days, turning 37", text)

    def test_tomorrow_wording(self):
        text, _ = render(person(1), IDEAS)
        self.assertIn("tomorrow", text)
        self.assertNotIn("in 1 days", text)

    def test_today_wording(self):
        text, _ = render(person(0), IDEAS)
        self.assertIn("today", text)

    def test_missing_age_omits_turning(self):
        text, _ = render(person(30, age=None), IDEAS)
        self.assertNotIn("turning", text)
        self.assertIn("in 30 days", text)


if __name__ == "__main__":
    unittest.main()
