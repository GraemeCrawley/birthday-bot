"""Inline-query handler — type-as-you-go name search.

Triggered when the user types `@<bot> <query>` (or, more typically, taps the
[🔍 Search by typing] button which auto-fills the @-prefix). Returns matching
people as inline result articles. Tapping a result sends that person's name
as a regular chat message; the text dispatcher (handlers/text.py) then handles
it as a bare-name search and shows the person's full view.

Auth: inline queries can come from any Telegram user; we filter to the bot's
configured chat-id and silently return empty results for everyone else.
"""

from __future__ import annotations

import logging
import os
from uuid import uuid4

from telegram import InlineQueryResultArticle, InputTextMessageContent, Update
from telegram.ext import ContextTypes

from api_client import APIClient

log = logging.getLogger(__name__)
CHAT_ID = int(os.environ["BIRTHDAY_BOT_CHAT_ID"])


def _format_days(days_until: int | None) -> str:
    if days_until is None:
        return ""
    if days_until == 0:
        return "🎉 today"
    if days_until == 1:
        return "tomorrow"
    if days_until < 30:
        return f"in {days_until}d"
    return f"in {round(days_until / 30)}mo"


async def on_inline_query(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    iq = update.inline_query
    if iq is None:
        return
    if iq.from_user.id != CHAT_ID:
        await iq.answer([], cache_time=0, is_personal=True)
        return

    api: APIClient = ctx.bot_data["api"]
    query = (iq.query or "").strip()
    if query:
        matches = await api.find_person_by_name(query)
    else:
        # Empty query: top upcoming as default suggestions
        people = await api.dashboard()
        matches = [p for p in people if p.days_until is not None][:8]

    results = []
    for p in matches[:25]:
        days_part = _format_days(getattr(p, "days_until", None))
        age_part = f" · turning {p.age_turning}" if getattr(p, "age_turning", None) else ""
        description = f"{days_part}{age_part}".strip(" ·") or "tap to open"
        results.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=p.name,
                description=description,
                input_message_content=InputTextMessageContent(p.name),
            )
        )

    await iq.answer(results, cache_time=0, is_personal=True)
