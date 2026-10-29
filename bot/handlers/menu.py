"""Main menu — /start, /menu, /help, plus the cb_menu / cb_help callbacks."""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

import state
from config import WEB_APP_URL
from keyboards import main_menu

MENU_TEXT = (
    "👋 *Birthday Bot*\n\n"
    "Pick an action below, or just type something like:\n"
    "  • `gift for mike - cutting board`\n"
    "  • `mom: vase`\n\n"
    f"The web app at {WEB_APP_URL} is still the place to add new "
    "people and edit details."
)

HELP_TEXT = (
    "ℹ *How to use this bot*\n\n"
    "*Quick capture:* type a message like:\n"
    "  • `gift for mike - cutting board`\n"
    "  • `add gift for mom - vase`\n"
    "  • `mike: cutting board`\n\n"
    "*Search:* tap 🔍 *Search by typing* to get live typeahead. Or just type a "
    "name (e.g. `mike`) to look someone up.\n\n"
    "*Buttons:* tap /menu or /start anytime.\n\n"
    "*Commands:*\n"
    "  /menu — main menu\n"
    "  /upcoming — list upcoming birthdays\n"
    "  /help — this message\n\n"
    f"The web app at {WEB_APP_URL} is the place to add new people "
    "and edit details."
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state.clear(ctx.user_data)
    await update.effective_message.reply_text(
        MENU_TEXT, reply_markup=main_menu(), parse_mode="Markdown"
    )


async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, ctx)


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state.clear(ctx.user_data)
    await update.effective_message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cb_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state.clear(ctx.user_data)
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(HELP_TEXT, parse_mode="Markdown")


async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    state.clear(ctx.user_data)
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(MENU_TEXT, reply_markup=main_menu(), parse_mode="Markdown")
