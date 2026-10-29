"""Gift add/capture flows — button paths + helpers used by the text dispatcher.

This module owns:
  - The 'Add gift idea' button flow (pick person → type idea)
  - Helpers the text dispatcher calls when a message resolves to a gift add
  - Multi-match disambiguation when a typed name matches >1 person

It does NOT own the text-dispatch *priority* logic (that's handlers/text.py)
or view rendering (that's views.py).
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import state
from config import WEB_APP_URL
import views
from api_client import APIClient, GiftIdea, Person
from keyboards import SEARCH_BY_TYPING_BUTTON, disambiguation, people_picker


# ---- Capture helpers (called from text dispatcher) ----------------------

# Longest first, so "i bought " wins over "bought " and "gift for " over "for ".
# Each entry is (prefix, purchased) — the verb decides the intent.
_LEADING_VERBS: tuple[tuple[str, bool], ...] = (
    ("i purchased ", True),
    ("i bought ", True),
    ("purchased for ", True),
    ("bought for ", True),
    ("purchased ", True),
    ("bought ", True),
    ("i got ", True),
    ("got for ", True),
    ("got ", True),
    ("gift for ", False),
    ("give ", False),
    ("add ", False),
    ("for ", False),
)

# Stripped off the front of the idea once the name is consumed, so
# "bought ada a cutting board" stores "cutting board", not "a cutting board".
_ARTICLES = ("a ", "an ", "the ")


async def smart_parse_capture(text: str, api: APIClient) -> tuple[Person, str, bool] | None:
    """Looser parse for messages like 'Gift for Mike cutting board' or
    'bought ada a cutting board' — strip a leading verb, then find the
    longest matching person-name prefix in the remainder.

    Returns (Person, idea, purchased) or None. `purchased` is True when the
    leading verb reported a completed purchase rather than an idea to capture.
    """
    t = text.strip()
    t_lower = t.lower()
    matched_prefix_len = 0
    purchased = False
    for verb, is_purchase in _LEADING_VERBS:
        if t_lower.startswith(verb):
            matched_prefix_len = len(verb)
            purchased = is_purchase
            break
    if matched_prefix_len == 0:
        return None
    rest = t[matched_prefix_len:].strip()
    if not rest:
        return None

    rest_lower = rest.lower()
    people = await api.list_people()
    best, best_len = None, 0
    for p in people:
        nlower = p.name.lower()
        if rest_lower.startswith(nlower) and len(nlower) > best_len:
            best, best_len = p, len(nlower)
        else:
            first_token = nlower.split()[0]
            if rest_lower.startswith(first_token + " ") and len(first_token) > best_len:
                best, best_len = p, len(first_token)

    if not best:
        return None
    idea = rest[best_len:].strip(" -–:,")
    for article in _ARTICLES:
        if idea.lower().startswith(article):
            idea = idea[len(article):].strip()
            break
    if not idea:
        return None
    return best, idea, purchased


# ---- Match-or-add: the core of a purchase capture ------------------------

async def resolve_purchase(api: APIClient, person_id: int, idea: str) -> tuple[GiftIdea, bool]:
    """Mark `idea` purchased for a person, matching an existing unpurchased
    idea where one fits rather than inserting a duplicate.

    Matching is case-insensitive and two-way (typed text inside a stored idea,
    or a stored idea inside the typed text), longest match wins — so "yarn"
    finds "Yarn for hand knitting". Already-purchased ideas are skipped: buying
    a second Lemon Tree should record a second gift, not re-tick the first.

    Returns (gift, matched_existing) — the caller needs the flag to say
    truthfully whether it ticked an idea already on the list or added one.
    """
    typed = idea.strip().lower()
    best, best_len = None, 0
    for g in await api.list_gifts(person_id):
        if g.purchased:
            continue
        stored = g.idea.strip().lower()
        if typed == stored or typed in stored or stored in typed:
            overlap = min(len(typed), len(stored))
            if overlap > best_len:
                best, best_len = g, overlap

    matched = best is not None
    target = best if matched else await api.add_gift(person_id, idea)
    return await api.update_gift(target.id, purchased=True), matched


async def handle_capture(send, api: APIClient, matches: list[Person], idea: str,
                         name_query: str, purchased: bool = False) -> None:
    """One or more people matched — capture directly if 1, otherwise show picker."""
    if len(matches) > 1:
        prefix = "bought_match" if purchased else "add_gift_match"
        await send(
            f"Multiple matches for *{name_query}* — pick one:",
            reply_markup=disambiguation(
                matches, callback_template=f"{prefix}:{{id}}:{idea[:50]}"
            ),
            parse_mode="Markdown",
        )
        return
    person = matches[0]
    matched = False
    if purchased:
        gift, matched = await resolve_purchase(api, person.id, idea)
    else:
        gift = await api.add_gift(person.id, idea)
    await _send_capture_confirmation(send, api, person, gift, purchased, matched)


async def handle_idea_text(send, api: APIClient, user_data: dict, idea: str) -> None:
    """User is in awaiting_idea_for state — their text is the gift idea."""
    pending = state.take_awaiting_idea_for(user_data)
    if not pending:
        await send("Empty idea — cancelled.")
        return
    idea = idea.strip()
    if not idea:
        await send("Empty idea — cancelled.")
        return
    gift = await api.add_gift(pending.person_id, idea)
    person = next((p for p in await api.list_people() if p.id == pending.person_id), None)
    if person:
        await _send_capture_confirmation(send, api, person, gift, purchased=False)


async def handle_name_search(send, api: APIClient, user_data: dict, query: str) -> None:
    """User is in awaiting_name_search state — their text is a name to look up."""
    state.take_awaiting_name_search(user_data)
    query = query.strip()
    if not query:
        await send("Empty search — cancelled.")
        return

    matches = await api.find_person_by_name(query)
    if not matches:
        await send(
            f"No one matching *{query}*. Add them in the web app:\n"
            f"{WEB_APP_URL}\n\n"
            "Or try /menu to start over.",
            parse_mode="Markdown",
        )
        return
    if len(matches) == 1:
        person = matches[0]
        # Show the full person view rather than only the "what's the idea?"
        # prompt. The user got here by tapping 'Add gift idea', so keep the
        # typed-idea shortcut armed — but a name search should still answer
        # "when is their birthday" and leave a way out other than adding a gift.
        view = await views.person_detail(api, person.id)
        if view is None:
            await send("Person not found.")
            return
        text, keyboard = view
        state.set_awaiting_idea_for(user_data, person.id, person.name)
        await send(
            f"{text}\n\n_Type a gift idea to add it, or use the buttons._",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return

    rows = [
        [InlineKeyboardButton(p.name, callback_data=f"add_gift_for:{p.id}")]
        for p in matches[:10]
    ]
    rows.append([InlineKeyboardButton("← Menu", callback_data="menu")])
    await send(
        f"{len(matches)} matches for *{query}* — pick one:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown",
    )


async def handle_bare_name_match(send, api: APIClient, matches: list[Person], query: str) -> None:
    """Bare name typed; show the full person view (for 1 match) or picker."""
    if len(matches) == 1:
        view = await views.person_detail(api, matches[0].id)
        if view is None:
            await send("Person not found.")
            return
        text, keyboard = view
        await send(text, reply_markup=keyboard, parse_mode="Markdown")
        return

    rows = [
        [InlineKeyboardButton(p.name, callback_data=f"browse_person:{p.id}")]
        for p in matches[:10]
    ]
    rows.append([InlineKeyboardButton("← Menu", callback_data="menu")])
    await send(
        f"{len(matches)} people match *{query}* — pick one:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown",
    )


# ---- Confirmation message after a successful add ------------------------

async def _send_capture_confirmation(send, api: APIClient, person: Person, gift: GiftIdea,
                                     purchased: bool, matched: bool = False) -> None:
    """Confirm a capture by showing the person's full view with a lead line.

    The old version rendered its own truncated list and offered no way to mark
    what had just been added — you had to leave, re-search the name, and find
    the idea again. Now the confirmation IS the person view, and the first
    button acts on the gift you just captured: mark it, or undo the purchase.
    """
    if purchased and matched:
        lead = f"✓ Marked *{gift.idea}* purchased — it was already on the list."
    elif purchased:
        lead = f"✓ Added *{gift.idea}* and marked it purchased."
    else:
        lead = f"✓ Added *{gift.idea}* to *{person.name}*'s list."

    view = await views.person_detail(api, person.id)
    if view is None:
        await send(lead, parse_mode="Markdown")
        return
    text, keyboard = view

    action = (
        InlineKeyboardButton(f"○ Undo purchased", callback_data=f"toggle_gift:{gift.id}:{person.id}:0")
        if purchased
        else InlineKeyboardButton(f"✓ Mark {gift.idea[:24]} purchased",
                                  callback_data=f"toggle_gift:{gift.id}:{person.id}:1")
    )
    rows = [[action]] + [list(r) for r in keyboard.inline_keyboard]

    await send(f"{lead}\n\n{text}", reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


# ---- Button-driven 'Add gift idea' flow ---------------------------------

async def cb_add_gift_pick_person(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped 'Add gift idea' — show top upcoming + Search-by-typing."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    upcoming = [p for p in await api.dashboard() if p.days_until is not None]

    state.set_awaiting_name_search(ctx.user_data)
    await q.edit_message_text(
        "Pick from upcoming, tap *Search* for live typeahead, or just *type a name* "
        "to search anyone:",
        reply_markup=people_picker(upcoming, callback_prefix="add_gift_for"),
        parse_mode="Markdown",
    )


async def cb_add_gift_for(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User picked a specific person — ask them to type the idea."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    person_id = int(q.data.split(":", 1)[1])
    people = await api.list_people()
    person = next((p for p in people if p.id == person_id), None)
    if not person:
        await q.edit_message_text("Person not found.")
        return

    state.set_awaiting_idea_for(ctx.user_data, person.id, person.name)
    await q.edit_message_text(
        f"What's the gift idea for *{person.name}*?\n"
        f"(Send the next message, or type /menu to cancel.)",
        parse_mode="Markdown",
    )


async def cb_add_gift_match(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Disambiguation — user picked one person from a multi-match list.

    Handles both `add_gift_match:` (capture an idea) and `bought_match:`
    (capture a completed purchase); the callback prefix carries the intent.
    """
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    prefix, person_id_s, idea = q.data.split(":", 2)
    purchased = prefix == "bought_match"
    person_id = int(person_id_s)
    people = await api.list_people()
    person = next((p for p in people if p.id == person_id), None)
    if not person:
        await q.edit_message_text("Person not found.")
        return
    matched = False
    if purchased:
        gift, matched = await resolve_purchase(api, person.id, idea)
    else:
        gift = await api.add_gift(person.id, idea)
    await _send_capture_confirmation(q.edit_message_text, api, person, gift, purchased, matched)
