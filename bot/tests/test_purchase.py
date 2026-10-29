"""Tests for purchase capture — the `bought X Y` verb and match-or-add.

Two separate concerns are covered here:

  1. parser.parse() recognising the purchase verbs in their *separator* forms
     ("bought ada - cutting board"), which needs no database.
  2. gift.smart_parse_capture() / gift.resolve_purchase(), which resolve a name
     against real people and decide whether the named thing is an idea already
     on the list (mark it) or a new one (add it, then mark it).

The near-miss cases matter as much as the happy path: an add must never
silently become a purchase, and vice versa. Those live in IntentBoundaryTests.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from api_client import GiftIdea, Person  # noqa: E402
from parser import parse  # noqa: E402
import handlers.gift as gift  # noqa: E402


PEOPLE = [
    Person(id=32, name="Ada Example"),
    Person(id=60, name="Lena Sample"),
    Person(id=65, name="Rex Placeholder"),
]


class StubAPI:
    """Records the calls a purchase makes so tests can assert on them."""

    def __init__(self, people=None, gifts=None):
        self._people = people if people is not None else PEOPLE
        self._gifts = {k: list(v) for k, v in (gifts or {}).items()}
        self.added = []
        self.updated = []
        self._next_id = 900

    async def list_people(self):
        return list(self._people)

    async def dashboard(self):
        return list(self._people)

    async def list_gifts(self, person_id):
        return list(self._gifts.get(person_id, []))

    async def add_gift(self, person_id, idea, notes=None):
        self._next_id += 1
        g = GiftIdea(id=self._next_id, person_id=person_id, idea=idea, purchased=False)
        self._gifts.setdefault(person_id, []).append(g)
        self.added.append((person_id, idea))
        return g

    async def update_gift(self, gift_id, **fields):
        self.updated.append((gift_id, fields))
        for pid, gs in self._gifts.items():
            for i, g in enumerate(gs):
                if g.id == gift_id:
                    gs[i] = GiftIdea(id=g.id, person_id=g.person_id, idea=g.idea,
                                     purchased=fields.get("purchased", g.purchased))
                    return gs[i]
        raise KeyError(gift_id)

    async def find_person_by_name(self, query):
        q = query.strip().lower()
        return [p for p in self._people if q in p.name.lower()] if q else []


# ---- 1. Parser-level: purchase verbs with a separator ---------------------


class PurchaseParseTests(unittest.TestCase):
    def test_bought_with_dash(self):
        r = parse("bought ada - cutting board")
        self.assertEqual((r.name, r.idea, r.purchased), ("ada", "cutting board", True))

    def test_bought_with_colon(self):
        r = parse("bought ada: cutting board")
        self.assertEqual((r.name, r.idea, r.purchased), ("ada", "cutting board", True))

    def test_got_verb(self):
        r = parse("got mom - flowers")
        self.assertTrue(r.purchased)

    def test_purchased_verb(self):
        r = parse("purchased rex - wine glasses")
        self.assertTrue(r.purchased)

    def test_i_bought_prefix(self):
        r = parse("I bought ada - cutting board")
        self.assertEqual((r.name, r.purchased), ("ada", True))

    def test_bought_for_prefix(self):
        r = parse("bought for ada - cutting board")
        self.assertEqual((r.name, r.purchased), ("ada", True))

    def test_case_insensitive(self):
        self.assertTrue(parse("BOUGHT Ada - Cutting Board").purchased)


class IntentBoundaryTests(unittest.TestCase):
    """An add must not become a purchase, or the other way round."""

    def test_plain_add_is_not_purchased(self):
        self.assertFalse(parse("gift for ada - cutting board").purchased)

    def test_bare_colon_is_not_purchased(self):
        self.assertFalse(parse("mom: vase").purchased)

    def test_add_for_is_not_purchased(self):
        self.assertFalse(parse("add cutting board for mike").purchased)

    def test_idea_mentioning_bought_stays_an_add(self):
        # The word appears in the IDEA, not as the leading verb.
        r = parse("gift for mom - the book she bought last year")
        self.assertFalse(r.purchased)
        self.assertEqual(r.idea, "the book she bought last year")

    def test_name_colon_bought_something_is_an_add_not_a_purchase(self):
        # Documented footgun: "mike: bought the cutting board" reads as a
        # purchase to a human but matches the generic <name>: <idea> rule.
        # It must NOT be silently treated as a purchase — the verb has to lead.
        r = parse("mike: bought the cutting board")
        self.assertFalse(r.purchased)


# ---- 2. Name resolution for the separator-less form ----------------------


class SmartPurchaseParseTests(unittest.IsolatedAsyncioTestCase):
    async def test_bought_name_then_idea(self):
        got = await gift.smart_parse_capture("bought ada a cutting board", StubAPI())
        person, idea, purchased = got
        self.assertEqual((person.id, idea, purchased), (32, "cutting board", True))

    async def test_strips_leading_article(self):
        for phrase, expected in (
            ("bought ada a cutting board", "cutting board"),
            ("bought ada an apron", "apron"),
            ("bought ada the cookbook", "cookbook"),
        ):
            _, idea, _ = await gift.smart_parse_capture(phrase, StubAPI())
            self.assertEqual(idea, expected, phrase)

    async def test_got_verb_separatorless(self):
        _, idea, purchased = await gift.smart_parse_capture("got rex wine glasses", StubAPI())
        self.assertEqual((idea, purchased), ("wine glasses", True))

    async def test_first_name_only_resolves(self):
        person, _, _ = await gift.smart_parse_capture("bought lena yarn", StubAPI())
        self.assertEqual(person.id, 60)

    async def test_add_verb_still_returns_not_purchased(self):
        person, idea, purchased = await gift.smart_parse_capture(
            "gift for ada cutting board", StubAPI())
        self.assertEqual((person.id, idea, purchased), (32, "cutting board", False))

    async def test_unknown_person_returns_none(self):
        self.assertIsNone(await gift.smart_parse_capture("bought nobody a thing", StubAPI()))

    async def test_no_idea_returns_none(self):
        self.assertIsNone(await gift.smart_parse_capture("bought ada", StubAPI()))


# ---- 3. Match-or-add: the core purchase behaviour -----------------------


class ResolvePurchaseTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.existing = {
            60: [
                GiftIdea(id=22, person_id=60, idea="Yarn for hand knitting", purchased=False),
                GiftIdea(id=23, person_id=60, idea="Poetry book", purchased=False),
                GiftIdea(id=24, person_id=60, idea="Lemon Tree", purchased=True),
            ]
        }

    async def test_exact_match_marks_existing_without_adding(self):
        api = StubAPI(gifts=self.existing)
        g, matched = await gift.resolve_purchase(api, 60, "Poetry book")
        self.assertTrue(matched)
        self.assertEqual(g.id, 23)
        self.assertEqual(api.added, [], "should not add a duplicate")
        self.assertEqual(api.updated, [(23, {"purchased": True})])

    async def test_match_is_case_insensitive(self):
        api = StubAPI(gifts=self.existing)
        g, matched = await gift.resolve_purchase(api, 60, "poetry BOOK")
        self.assertTrue(matched)
        self.assertEqual(g.id, 23)
        self.assertEqual(api.added, [])

    async def test_substring_match_marks_existing(self):
        api = StubAPI(gifts=self.existing)
        g, matched = await gift.resolve_purchase(api, 60, "yarn")
        self.assertTrue(matched)
        self.assertEqual(g.id, 22)
        self.assertEqual(api.added, [])

    async def test_unmatched_idea_is_added_then_marked(self):
        api = StubAPI(gifts=self.existing)
        g, matched = await gift.resolve_purchase(api, 60, "cutting board")
        self.assertFalse(matched, "a brand-new idea is not a match")
        self.assertEqual(api.added, [(60, "cutting board")])
        self.assertEqual(api.updated, [(g.id, {"purchased": True})])

    async def test_already_purchased_gift_is_not_rematched(self):
        # "Lemon Tree" is already purchased; buying it again should add a new
        # row rather than silently re-marking the old one.
        api = StubAPI(gifts=self.existing)
        await gift.resolve_purchase(api, 60, "Lemon Tree")
        self.assertEqual(api.added, [(60, "Lemon Tree")])

    async def test_longest_match_wins(self):
        api = StubAPI(gifts={
            60: [
                GiftIdea(id=30, person_id=60, idea="book", purchased=False),
                GiftIdea(id=31, person_id=60, idea="poetry book", purchased=False),
            ]
        })
        g, _ = await gift.resolve_purchase(api, 60, "poetry book")
        self.assertEqual(g.id, 31)

    async def test_person_with_no_gifts_adds(self):
        api = StubAPI(gifts={})
        g, _ = await gift.resolve_purchase(api, 32, "cutting board")
        self.assertEqual(api.added, [(32, "cutting board")])
        self.assertTrue(g.id)


if __name__ == "__main__":
    unittest.main()
