"""Browse flows — list people, show a person's gifts, toggle/delete.

View rendering lives in views.py; this module is callbacks only.
"""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import views
from api_client import APIClient
from keyboards import people_picker


async def _render_or_404(q, api: APIClient, person_id: int) -> None:
    view = await views.person_detail(api, person_id)
    if view is None:
        await q.edit_message_text("Person not found.")
        return
    text, keyboard = view
    await q.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


# ---- People-picker entry point ------------------------------------------

async def cb_browse_people(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Browse — show top upcoming as quick picks + Search-by-typing."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    upcoming = [p for p in await api.dashboard() if p.days_until is not None]
    await q.edit_message_text(
        "Pick from upcoming, tap *Search* for live typeahead, or just *type a name* "
        "to browse anyone:",
        reply_markup=people_picker(upcoming, callback_prefix="browse_person"),
        parse_mode="Markdown",
    )


async def cb_browse_person(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a person's detail view — birthday + gift list (toggle/add/remove)."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    person_id = int(q.data.split(":", 1)[1])
    await _render_or_404(q, api, person_id)


# ---- Toggle purchased state ---------------------------------------------

async def cb_toggle_gift(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Set purchased=true|false on a single gift, then re-render the list."""
    q = update.callback_query
    api: APIClient = ctx.bot_data["api"]
    parts = q.data.split(":")
    if len(parts) < 4:
        await q.answer("Refresh the list — old button format")
        return
    gift_id = int(parts[1])
    person_id = int(parts[2])
    new_state = bool(int(parts[3]))

    try:
        await api.update_gift(gift_id, purchased=new_state)
        await q.answer("✓ Purchased" if new_state else "○ Unmarked")
    except Exception as e:
        await q.answer(f"Failed: {e}", show_alert=True)
        return

    await _render_or_404(q, api, person_id)


# ---- Delete flow (pick → confirm → do) ----------------------------------

async def cb_remove_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped 'Remove an idea' — show each gift as a pick button."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    person_id = int(q.data.split(":", 1)[1])
    gifts = await api.list_gifts(person_id)
    if not gifts:
        await q.edit_message_text("No gift ideas to remove.")
        return
    rows = [
        [InlineKeyboardButton(f"🗑 {g.idea[:40]}", callback_data=f"delete_gift:{g.id}:{person_id}")]
        for g in gifts
    ]
    rows.append([InlineKeyboardButton("← Back", callback_data=f"browse_person:{person_id}")])
    await q.edit_message_text(
        "Which idea to remove?", reply_markup=InlineKeyboardMarkup(rows)
    )


async def cb_delete_gift_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show 'Delete X?' confirmation."""
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    _, gift_id_s, person_id_s = q.data.split(":")
    gift_id = int(gift_id_s)
    person_id = int(person_id_s)

    gifts = await api.list_gifts(person_id)
    g = next((x for x in gifts if x.id == gift_id), None)
    if not g:
        await q.edit_message_text("Gift not found — refresh the list.")
        return

    rows = [
        [
            InlineKeyboardButton("🗑 Yes, delete", callback_data=f"delete_gift_do:{gift_id}:{person_id}"),
            InlineKeyboardButton("Cancel", callback_data=f"browse_person:{person_id}"),
        ],
    ]
    await q.edit_message_text(
        f"Delete *{g.idea}* from this gift list?",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="Markdown",
    )


async def cb_delete_gift_do(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """User confirmed — delete and re-render the gift list."""
    q = update.callback_query
    api: APIClient = ctx.bot_data["api"]
    _, gift_id_s, person_id_s = q.data.split(":")
    gift_id = int(gift_id_s)
    person_id = int(person_id_s)

    try:
        await api.delete_gift(gift_id)
        await q.answer("🗑 Deleted")
    except Exception as e:
        await q.answer(f"Failed: {e}", show_alert=True)
        return

    await _render_or_404(q, api, person_id)
