"""Unit tests for views.person_detail — the canonical single-person view.

This view is reached from three surfaces (bare-name typing, Browse → person,
and the Add-gift name search), so it's the one place that has to answer both
questions a user can have about a person: *when is their birthday* and *what
gift ideas do I have*. It previously answered only the second one, which made
a name search look like a gift-entry form with no way out.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import views  # noqa: E402
from api_client import GiftIdea, Person  # noqa: E402


class StubAPI:
    """Minimal stand-in for APIClient — only the two calls views uses."""

    def __init__(self, people, gifts=None):
        self._people = people
        self._gifts = gifts or {}

    async def dashboard(self):
        return list(self._people)

    async def list_gifts(self, person_id):
        return list(self._gifts.get(person_id, []))


REX = Person(id=65, name="Rex Placeholder", days_until=316, age_turning=31, birthday="1990-03-14")
JO = Person(id=66, name="Jo Testcase", days_until=164, age_turning=31, birthday="1991-11-02")


def button_labels(keyboard):
    return [b.text for row in keyboard.inline_keyboard for b in row]


def callbacks(keyboard):
    return [b.callback_data for row in keyboard.inline_keyboard for b in row]


class PersonDetailBirthdayTests(unittest.IsolatedAsyncioTestCase):
    """The regression this change exists for: the birthday must be visible."""

    async def test_shows_birthday_date(self):
        text, _ = await views.person_detail(StubAPI([REX, JO]), 65)
        self.assertIn("March 14", text)

    async def test_shows_countdown(self):
        text, _ = await views.person_detail(StubAPI([REX, JO]), 65)
        self.assertIn("316 days", text)

    async def test_shows_age_turning(self):
        text, _ = await views.person_detail(StubAPI([REX, JO]), 65)
        self.assertIn("31", text)

    async def test_shows_name(self):
        text, _ = await views.person_detail(StubAPI([REX, JO]), 65)
        self.assertIn("Rex Placeholder", text)

    async def test_birthday_shown_even_with_no_gifts(self):
        # The empty-gift-list branch is the exact case that used to render
        # nothing but "no ideas yet" + an Add button.
        text, _ = await views.person_detail(StubAPI([REX]), 65)
        self.assertIn("March 14", text)
        self.assertIn("316 days", text)


class PersonDetailCountdownWordingTests(unittest.IsolatedAsyncioTestCase):
    async def test_today(self):
        p = Person(id=1, name="A", days_until=0, age_turning=40, birthday="1986-08-13")
        text, _ = await views.person_detail(StubAPI([p]), 1)
        self.assertIn("today", text)

    async def test_tomorrow(self):
        p = Person(id=1, name="A", days_until=1, age_turning=40, birthday="1986-08-14")
        text, _ = await views.person_detail(StubAPI([p]), 1)
        self.assertIn("tomorrow", text)

    async def test_near_future_is_days(self):
        p = Person(id=1, name="A", days_until=9, age_turning=40, birthday="1986-08-22")
        text, _ = await views.person_detail(StubAPI([p]), 1)
        self.assertIn("in 9 days", text)


class PersonDetailGiftSectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.gifts = {
            65: [
                GiftIdea(id=1, person_id=65, idea="cutting board", purchased=False),
                GiftIdea(id=2, person_id=65, idea="wine glasses", purchased=True),
            ]
        }

    async def test_lists_gifts_with_state_markers(self):
        text, _ = await views.person_detail(StubAPI([REX], self.gifts), 65)
        self.assertIn("○ cutting board", text)
        self.assertIn("✓ wine glasses", text)

    async def test_toggle_buttons_carry_person_and_new_state(self):
        _, kb = await views.person_detail(StubAPI([REX], self.gifts), 65)
        cbs = callbacks(kb)
        self.assertIn("toggle_gift:1:65:1", cbs)  # unpurchased → mark purchased
        self.assertIn("toggle_gift:2:65:0", cbs)  # purchased → unmark

    async def test_add_idea_button_present_with_gifts(self):
        _, kb = await views.person_detail(StubAPI([REX], self.gifts), 65)
        self.assertIn("add_gift_for:65", callbacks(kb))

    async def test_add_idea_button_present_without_gifts(self):
        _, kb = await views.person_detail(StubAPI([REX]), 65)
        self.assertIn("add_gift_for:65", callbacks(kb))

    async def test_empty_list_says_so(self):
        text, _ = await views.person_detail(StubAPI([REX]), 65)
        self.assertIn("no gift ideas", text.lower())

    async def test_navigation_available_in_both_branches(self):
        # Escaping the view mattered: the old empty branch had no Menu button,
        # so a name search with no gifts was a dead end.
        for gifts in (None, self.gifts):
            _, kb = await views.person_detail(StubAPI([REX], gifts), 65)
            self.assertIn("menu", callbacks(kb), f"no Menu button (gifts={bool(gifts)})")


class ToggleCoverageTests(unittest.IsolatedAsyncioTestCase):
    """Every idea must be markable from Telegram, not just the first six.

    Lena Sample has 7 ideas; her 7th ("Poetry book") had no button, so it
    could only be marked from the web app.
    """

    def gifts_for(self, n):
        return {60: [GiftIdea(id=100 + i, person_id=60, idea=f"idea {i}", purchased=False)
                     for i in range(n)]}

    async def test_seventh_gift_has_a_toggle(self):
        api = StubAPI([Person(id=60, name="Lena Sample", days_until=317,
                              age_turning=30, birthday="1993-02-10")], self.gifts_for(7))
        _, kb = await views.person_detail(api, 60)
        self.assertIn("toggle_gift:106:60:1", callbacks(kb))

    async def test_toggle_count_matches_gift_count(self):
        for n in (1, 6, 7, 12):
            api = StubAPI([Person(id=60, name="L", days_until=10, age_turning=30,
                                  birthday="1993-02-10")], self.gifts_for(n))
            _, kb = await views.person_detail(api, 60)
            toggles = [c for c in callbacks(kb) if c and c.startswith("toggle_gift:")]
            self.assertEqual(len(toggles), n, f"{n} gifts should give {n} toggles")


class UpcomingWindowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.people = [
            Person(id=1, name="Soon", days_until=15, age_turning=37, birthday="1988-05-05"),
            Person(id=2, name="Midway", days_until=160, age_turning=31, birthday="1991-11-02"),
            Person(id=3, name="Far", days_until=312, age_turning=31, birthday="1990-03-14"),
        ]

    async def test_default_window_is_180_days(self):
        text, _ = await views.upcoming(StubAPI(self.people))
        self.assertIn("Soon", text)
        self.assertIn("Midway", text, "160d person should be inside the default window")
        self.assertNotIn("Far", text, "312d person needs Show all")

    async def test_90_day_window_narrows(self):
        text, _ = await views.upcoming(StubAPI(self.people), window_days=90)
        self.assertIn("Soon", text)
        self.assertNotIn("Midway", text)

    async def test_all_window_includes_everyone(self):
        text, _ = await views.upcoming(StubAPI(self.people), window_days=None)
        for name in ("Soon", "Midway", "Far"):
            self.assertIn(name, text)

    async def test_toggle_offers_the_other_windows(self):
        _, kb = await views.upcoming(StubAPI(self.people))
        cbs = callbacks(kb)
        self.assertIn("upcoming:90", cbs)
        self.assertIn("upcoming:all", cbs)
        self.assertNotIn("upcoming:180", cbs, "shouldn't offer the window you're on")

    async def test_all_view_offers_narrower_windows(self):
        _, kb = await views.upcoming(StubAPI(self.people), window_days=None)
        cbs = callbacks(kb)
        self.assertIn("upcoming:90", cbs)
        self.assertIn("upcoming:180", cbs)
        self.assertNotIn("upcoming:all", cbs)

    async def test_header_states_the_window_and_count(self):
        text, _ = await views.upcoming(StubAPI(self.people))
        self.assertIn("180", text)
        self.assertIn("2", text)

    async def test_empty_window_still_navigable(self):
        text, kb = await views.upcoming(StubAPI([]), window_days=90)
        self.assertIn("No birthdays", text)
        self.assertIn("menu", callbacks(kb))


class PersonDetailEdgeCaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_person_returns_none(self):
        self.assertIsNone(await views.person_detail(StubAPI([REX]), 999))

    async def test_missing_countdown_fields_do_not_crash(self):
        # /api/people-shaped Person (no birthday/days_until/age_turning).
        bare = Person(id=7, name="Bare Row")
        text, kb = await views.person_detail(StubAPI([bare]), 7)
        self.assertIn("Bare Row", text)
        self.assertIn("add_gift_for:7", callbacks(kb))

    async def test_malformed_birthday_does_not_crash(self):
        p = Person(id=7, name="Bad Date", days_until=5, age_turning=30, birthday="not-a-date")
        text, _ = await views.person_detail(StubAPI([p]), 7)
        self.assertIn("Bad Date", text)
        self.assertIn("in 5 days", text)


if __name__ == "__main__":
    unittest.main()
