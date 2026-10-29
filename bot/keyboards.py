"""Shared inline-keyboard builders.

Anywhere we'd otherwise repeat the same row-of-buttons pattern across handlers,
the builder lives here. Three things this consolidates:

  - The main menu inline keyboard (also referenced by /start, /menu, cb_menu)
  - The "search by typing" button (used in 3+ surfaces)
  - The "top upcoming people as quick picks" picker (used by Add gift idea
    and Browse gift lists — same shape, different callback prefix)

This module is dependency-free except for the data shapes from api_client,
so it's safe to import from any handler.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api_client import Person


# ---- Reusable building blocks -------------------------------------------

SEARCH_BY_TYPING_BUTTON = InlineKeyboardButton(
    "🔍 Search by typing", switch_inline_query_current_chat=""
)


def _format_when(days: int | None) -> str:
    if days is None:
        return ""
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days < 30:
        return f"{days}d"
    return f"{round(days / 30)}mo"


# ---- Composite keyboards -------------------------------------------------

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📅 Upcoming birthdays", callback_data="upcoming"),
                InlineKeyboardButton("🎁 Browse gift lists", callback_data="browse_people"),
            ],
            [
                InlineKeyboardButton("➕ Add gift idea", callback_data="add_gift_pick_person"),
                InlineKeyboardButton("❓ Help", callback_data="help"),
            ],
            [SEARCH_BY_TYPING_BUTTON],
        ]
    )


def people_picker(people: list[Person], callback_prefix: str, max_count: int = 8) -> InlineKeyboardMarkup:
    """Top-upcoming-people picker keyboard with the type-to-search and back rows.

    `callback_prefix` is what each person button's callback_data starts with —
    e.g. 'add_gift_for' for the Add Gift Idea flow, or 'browse_person' for
    Browse Gift Lists. The full callback is f"{callback_prefix}:{person.id}".
    """
    rows = []
    for p in people[:max_count]:
        when = _format_when(p.days_until)
        label = f"{p.name} · {when}" if when else p.name
        rows.append([InlineKeyboardButton(label, callback_data=f"{callback_prefix}:{p.id}")])
    rows.append([SEARCH_BY_TYPING_BUTTON])
    rows.append([InlineKeyboardButton("← Menu", callback_data="menu")])
    return InlineKeyboardMarkup(rows)


def disambiguation(people: list[Person], callback_template: str, cancel_text: str = "Cancel") -> InlineKeyboardMarkup:
    """Multi-match picker — render up to 6 buttons, each with the person.id
    substituted into `callback_template` (which must contain `{id}`)."""
    rows = [
        [InlineKeyboardButton(p.name, callback_data=callback_template.format(id=p.id))]
        for p in people[:6]
    ]
    rows.append([InlineKeyboardButton(cancel_text, callback_data="menu")])
    return InlineKeyboardMarkup(rows)
