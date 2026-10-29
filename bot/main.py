"""Birthday Bot entry point — wires Application + handlers + scheduler.

Module dependency graph (no cycles):
    state, api_client, parser    : leaf modules, zero internal deps
    keyboards                     ← api_client
    views                         ← api_client, keyboards
    handlers/menu                 ← state, keyboards
    handlers/upcoming             ← views, api_client
    handlers/browse               ← views, api_client, keyboards
    handlers/gift                 ← state, views, api_client, keyboards
    handlers/text                 ← state, parser, api_client, handlers/gift (lazy)
    handlers/inline               ← api_client
    notifications                 ← api_client
    main                          ← all of the above
"""

from __future__ import annotations

import asyncio
import logging
import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

from api_client import APIClient
from config import DAILY_CHECK_HOUR, DAILY_CHECK_MINUTE, TZ
from handlers import browse, gift, inline, menu, text, upcoming
from notifications import daily_check

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
# httpx logs full request URLs at INFO; the Telegram API URL embeds the bot token in
# its path, so INFO would write the token to logs. Pin to WARNING.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("birthday-bot")

def _required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(
            f"{name} is not set. Copy .env.example to .env, fill it in, and restart."
        )
    return value


BOT_TOKEN = _required_env("BIRTHDAY_BOT_TOKEN")
CHAT_ID = int(_required_env("BIRTHDAY_BOT_CHAT_ID"))


async def auth_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch-all for messages from non-authorized chat IDs. Silently ignore."""
    chat = update.effective_chat
    if chat:
        log.info("ignored message from unauthorized chat_id=%s", chat.id)


def build_app() -> Application:
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.bot_data["api"] = APIClient()
    log.info("APIClient initialised")

    auth = filters.Chat(chat_id=CHAT_ID)

    # Commands
    app.add_handler(CommandHandler("start", menu.cmd_start, filters=auth))
    app.add_handler(CommandHandler("menu", menu.cmd_menu, filters=auth))
    app.add_handler(CommandHandler("help", menu.cmd_help, filters=auth))
    app.add_handler(CommandHandler("upcoming", upcoming.cmd_upcoming, filters=auth))

    # Menu navigation callbacks
    app.add_handler(CallbackQueryHandler(menu.cb_menu, pattern=r"^menu$"))
    app.add_handler(CallbackQueryHandler(menu.cb_help, pattern=r"^help$"))

    # Upcoming view
    app.add_handler(CallbackQueryHandler(upcoming.cb_upcoming, pattern=r"^upcoming(?::(?:90|180|all))?$"))

    # Browse + per-person view + toggle + delete
    app.add_handler(CallbackQueryHandler(browse.cb_browse_people, pattern=r"^browse_people$"))
    app.add_handler(CallbackQueryHandler(browse.cb_browse_person, pattern=r"^browse_person:\d+$"))
    app.add_handler(CallbackQueryHandler(browse.cb_toggle_gift, pattern=r"^toggle_gift:\d+:\d+:[01]$"))
    app.add_handler(CallbackQueryHandler(browse.cb_remove_pick, pattern=r"^remove_pick:\d+$"))
    app.add_handler(CallbackQueryHandler(browse.cb_delete_gift_confirm, pattern=r"^delete_gift:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(browse.cb_delete_gift_do, pattern=r"^delete_gift_do:\d+:\d+$"))

    # Add gift idea — pick person → ask for idea, plus disambiguation match
    app.add_handler(CallbackQueryHandler(gift.cb_add_gift_pick_person, pattern=r"^add_gift_pick_person$"))
    app.add_handler(CallbackQueryHandler(gift.cb_add_gift_for, pattern=r"^add_gift_for:\d+$"))
    app.add_handler(CallbackQueryHandler(gift.cb_add_gift_match, pattern=r"^(?:add_gift_match|bought_match):"))

    # Inline-query handler (typeahead via @<bot> <query>)
    app.add_handler(InlineQueryHandler(inline.on_inline_query))

    # Free-form text — single dispatcher with documented priority
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & auth, text.on_text_message))

    # Catch-all for unauthorised senders
    app.add_handler(MessageHandler(~auth, auth_block))

    return app


def schedule_daily(app: Application) -> AsyncIOScheduler:
    """Schedule the daily (default 09:00, TZ) notification + cycle-close-out check.

    Notifications fire at 9 AM local so the user reads them with morning
    coffee. Cycle close-out (archiving purchased gifts the day after each
    birthday) rides the same job — 9 AM "yesterday" still matches the
    actual previous day, just with a 10-hour later trigger than before.
    """
    scheduler = AsyncIOScheduler(timezone=TZ)

    async def job():
        await daily_check(app.bot, app.bot_data["api"], CHAT_ID)

    scheduler.add_job(job, CronTrigger(hour=DAILY_CHECK_HOUR, minute=DAILY_CHECK_MINUTE,
                                       timezone=TZ),
                      id="daily_check", name="daily_check")
    scheduler.start()
    log.info("scheduler started — daily_check at %02d:%02d %s",
             DAILY_CHECK_HOUR, DAILY_CHECK_MINUTE, TZ)
    return scheduler


async def main_async() -> None:
    app = build_app()
    scheduler = schedule_daily(app)

    log.info("starting polling for chat_id=%d (tz=%s)", CHAT_ID, TZ)
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            log.info("shutdown requested")
        finally:
            scheduler.shutdown(wait=False)
            await app.updater.stop()
            await app.stop()
            api: APIClient = app.bot_data.get("api")
            if api:
                await api.aclose()


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
