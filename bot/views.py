"""View functions — produce (text, keyboard) tuples for rendering.

Pure transformation: given app state (people, gifts), return what to display.
No Telegram I/O here — the handler that calls a view decides whether to send
a fresh message or edit an existing one. That separation lets the same view
back both `cb_browse_person` (edits the message) and the bare-name search
result in the text dispatcher (replies fresh).
"""

from __future__ import annotations

from datetime import date, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from api_client import APIClient, GiftIdea, Person
from keyboards import SEARCH_BY_TYPING_BUTTON


# ---- Person detail view (used by Browse + bare-name search + toggle) ----

def _format_countdown(days: int | None) -> str:
    """Spelled-out countdown. Deliberately wordier than the list-view form in
    `_format_upcoming_line` — this view is about one person, so there's room."""
    if days is None:
        return ""
    if days == 0:
        return "today 🎉"
    if days == 1:
        return "tomorrow"
    if days < 60:
        return f"in {days} days"
    return f"in {days} days (~{round(days / 30)} months)"


def _format_birthday(iso: str | None) -> str:
    """'1996-06-25' → 'June 25'. The stored year is a placeholder for people
    added month/day-only, so it's never rendered — only the age-turning line
    (computed API-side) hints at it."""
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso).strftime("%B %-d")
    except ValueError:
        return ""


def person_header(person: Person) -> str:
    """Name + birthday facts. Answers 'when is their birthday' — the question a
    name search is usually asking. Every fact is optional: a Person built from
    /api/people carries only id+name, so each part is dropped if absent."""
    emoji = "🎉" if person.days_until == 0 else "🎂"
    facts = [
        _format_birthday(person.birthday),
        _format_countdown(person.days_until),
        f"turning {person.age_turning}" if person.age_turning else "",
    ]
    detail = " · ".join(f for f in facts if f)
    return f"{emoji} *{person.name}*\n{detail}" if detail else f"{emoji} *{person.name}*"


async def person_detail(api: APIClient, person_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    """Render the single-person view: birthday header, then the gift list, then
    an interactive keyboard (per-gift toggle, Add idea, Remove an idea, search,
    and back-to-people / Menu rows).

    Sourced from /api/dashboard rather than /api/people because only the
    dashboard carries birthday, days_until and age_turning — /api/people is
    id+name only, which is why this view used to show no birthday at all.

    Returns None if the person doesn't exist."""
    people = await api.dashboard()
    person = next((p for p in people if p.id == person_id), None)
    if not person:
        return None

    gifts = await api.list_gifts(person_id)
    lines = [person_header(person), ""]

    rows = []
    if not gifts:
        lines.append("🎁 No gift ideas yet.")
    else:
        lines.append(f"🎁 Gift ideas ({len(gifts)}):")
        for g in gifts:
            check = "✓" if g.purchased else "○"
            lines.append(f"  {check} {g.idea}")
        # A button for EVERY idea, not just the first six — one person's 7th used
        # to be printed above with no way to tap it.
        for g in gifts:
            new_state = 0 if g.purchased else 1
            check = "✓" if g.purchased else "○"
            rows.append(
                [InlineKeyboardButton(f"{check} {g.idea[:32]}",
                                      callback_data=f"toggle_gift:{g.id}:{person_id}:{new_state}")]
            )

    rows.append([InlineKeyboardButton("➕ Add idea", callback_data=f"add_gift_for:{person_id}")])
    if gifts:
        rows.append([InlineKeyboardButton("🗑 Remove an idea", callback_data=f"remove_pick:{person_id}")])
    rows.append([SEARCH_BY_TYPING_BUTTON])
    rows.append(
        [
            InlineKeyboardButton("← People", callback_data="browse_people"),
            InlineKeyboardButton("Menu", callback_data="menu"),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ---- Upcoming birthdays view (used by /upcoming + cb_upcoming) ----------

# 90 was too narrow to be the only view: 23 of 54 people fell outside it and
# appeared on no screen at all. 180 is the default; the other windows are one
# tap away rather than a code change.
UPCOMING_WINDOW_DAYS = 180
WINDOW_CHOICES = (90, 180, None)  # None == show everyone


def _format_upcoming_line(p: Person) -> str:
    if p.days_until is None:
        return f"🎂 {p.name}"
    target = date.today() + timedelta(days=p.days_until)
    date_str = target.strftime("%b %-d")
    when = (
        "today" if p.days_until == 0
        else "tomorrow" if p.days_until == 1
        else f"{p.days_until}d" if p.days_until < 30
        else f"{round(p.days_until / 30)}mo"
    )
    age = f"{p.age_turning}y" if p.age_turning else "?"
    emoji = "🎉" if p.days_until == 0 else "🎂"
    return f"{emoji} {p.name} · {date_str} ({when}) · {age}"


def _window_row(current: int | None, total: int) -> list[InlineKeyboardButton]:
    """Buttons for the windows you're NOT currently on — no button is ever a
    no-op, and the label says what you'd get."""
    row = []
    for choice in WINDOW_CHOICES:
        if choice == current:
            continue
        label = f"Show all {total}" if choice is None else f"Next {choice}d"
        row.append(InlineKeyboardButton(label, callback_data=f"upcoming:{choice or 'all'}"))
    return row


async def upcoming(api: APIClient,
                   window_days: int | None = UPCOMING_WINDOW_DAYS) -> tuple[str, InlineKeyboardMarkup]:
    """Upcoming-birthday list for a window. `window_days=None` shows everyone."""
    people = await api.dashboard()
    dated = [p for p in people if p.days_until is not None]
    upcoming_people = (
        dated if window_days is None else [p for p in dated if p.days_until <= window_days]
    )

    nav = [
        _window_row(window_days, len(dated)),
        [InlineKeyboardButton("➕ Add gift idea", callback_data="add_gift_pick_person")],
        [SEARCH_BY_TYPING_BUTTON],
        [InlineKeyboardButton("← Menu", callback_data="menu")],
    ]

    if not upcoming_people:
        return f"No birthdays in the next {window_days} days.", InlineKeyboardMarkup(nav)

    scope = "all" if window_days is None else f"next {window_days}d"
    header = (
        f"📅 *Upcoming* — {scope}, {len(upcoming_people)} "
        f"{'birthday' if len(upcoming_people) == 1 else 'birthdays'}\n"
    )
    body = "\n".join(_format_upcoming_line(p) for p in upcoming_people)
    return f"{header}\n{body}", InlineKeyboardMarkup(nav)
