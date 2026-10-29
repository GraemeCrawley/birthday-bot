"""Upcoming birthdays handlers — render the upcoming list view.

Both the /upcoming command and the menu callback share a single view function
in views.py; the only difference here is whether to reply with a fresh message
or edit the existing one.
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

import views
from api_client import APIClient


async def cmd_upcoming(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    api: APIClient = ctx.bot_data["api"]
    text, keyboard = await views.upcoming(api)
    await update.effective_message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")


def _window_from_callback(data: str) -> int | None:
    """`upcoming` → default window; `upcoming:90` → 90; `upcoming:all` → None."""
    _, _, arg = data.partition(":")
    if not arg:
        return views.UPCOMING_WINDOW_DAYS
    return None if arg == "all" else int(arg)


async def cb_upcoming(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    api: APIClient = ctx.bot_data["api"]
    text, keyboard = await views.upcoming(api, window_days=_window_from_callback(q.data))
    await q.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
