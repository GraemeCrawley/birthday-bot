"""Daily scheduled notifications + post-birthday gift-cycle close-out.

Runs once a day (09:00 by default) in the bot's configured timezone. Two passes:

  1. Notifications. For each upcoming person, decide whether to DM the user
     based on cycle status:
       bought   (≥1 gift purchased this cycle): 7 / 1 / 0 days before
       unbought (0 gifts purchased this cycle): 60 / 30 / 7 / 1 / 0 days before
     Unbought escalates earlier — gives the user more lead time when no gift
     has been arranged yet.

  2. Cycle close-out. For each person whose birthday was YESTERDAY (relative
     to the run date in the bot's tz), call /reset-gift-cycle, which soft-
     archives any purchased gifts so the new cycle starts clean. Unpurchased
     ideas carry over to next year.

The yesterday-detection uses the actual birthday date from the dashboard,
not a `days_until == 364` heuristic — robust to leap-year edges.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from api_client import APIClient
from config import DAILY_CHECK_HOUR, DAILY_CHECK_MINUTE, TZ as TZ_NAME
from cron import Cron

log = logging.getLogger(__name__)

TRIGGERS_BOUGHT = {7, 1, 0}
TRIGGERS_UNBOUGHT = {60, 30, 7, 1, 0}
TZ = ZoneInfo(TZ_NAME)

# Optional uptime monitoring. Only does anything if HEALTHCHECKS_API_KEY is
# set (see cron.py and .env.example); otherwise it is a silent no-op.
DAILY_CHECK_CRON = Cron(
    name="birthday-bot-daily-check",
    schedule=f"{DAILY_CHECK_MINUTE} {DAILY_CHECK_HOUR} * * *",
    grace_seconds=1800,
    description="Birthday-bot daily notifications + post-birthday cycle close-out",
)


def _is_yesterday_birthday(birthday_iso: str | None, today: date) -> bool:
    """True if the birthday's month/day matches yesterday (in the run tz).
    Year-agnostic — handles leap-year edges by comparing month/day only."""
    if not birthday_iso:
        return False
    try:
        bday = date.fromisoformat(birthday_iso)
    except ValueError:
        return False
    yesterday = today - timedelta(days=1)
    return bday.month == yesterday.month and bday.day == yesterday.day


async def daily_check(bot: Bot, api: APIClient, chat_id: int) -> None:
    async with DAILY_CHECK_CRON.run():
        await _daily_check_body(bot, api, chat_id)


async def _daily_check_body(bot: Bot, api: APIClient, chat_id: int) -> None:
    log.info("daily_check: starting")
    today = datetime.now(TZ).date()

    try:
        people = await api.dashboard()
    except Exception as e:
        log.exception("daily_check: dashboard fetch failed: %s", e)
        return

    notified = 0
    archived = 0

    for p in people:
        # ---- Cycle close-out (yesterday's birthdays) ----
        if _is_yesterday_birthday(p.birthday, today):
            try:
                count = await api.reset_gift_cycle(p.id)
                if count > 0:
                    log.info("archived %d purchased gift(s) for %s after birthday", count, p.name)
                    archived += 1
            except Exception as e:
                log.exception("close-out failed for %s: %s", p.name, e)

        # ---- Upcoming-birthday notifications ----
        if p.days_until is None:
            continue
        try:
            gifts = await api.list_gifts(p.id)
        except Exception as e:
            log.exception("list_gifts failed for %s: %s", p.name, e)
            continue

        any_purchased = any(g.purchased for g in gifts)
        triggers = TRIGGERS_BOUGHT if any_purchased else TRIGGERS_UNBOUGHT
        if p.days_until not in triggers:
            continue

        try:
            text, markup = _format_notification(p, gifts, any_purchased)
            await bot.send_message(chat_id=chat_id, text=text, reply_markup=markup, parse_mode="Markdown")
            notified += 1
        except Exception as e:
            log.exception("send_message failed for %s: %s", p.name, e)

    log.info("daily_check: complete — %d notifications, %d cycle close-outs", notified, archived)


def _purchase_date(iso: str | None) -> str:
    """'2026-08-16T14:26:00' → ' (Aug 16)'. Empty string if absent or unparseable
    — a missing timestamp shouldn't cost us the gift name."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime(" (%b %-d)")
    except ValueError:
        return ""


def _status_block(gifts, purchased, unpurchased, days: int) -> list[str]:
    """The purchase-status lines. Every branch states the status outright —
    the old version only warned within 7 days and otherwise left you to infer
    it from a bare 'Gift ideas on file:' heading."""
    if purchased:
        if len(purchased) == 1:
            g = purchased[0]
            lines = [f"✓ Bought — {g.idea}{_purchase_date(g.purchased_at)}"]
        else:
            lines = [f"✓ Bought ({len(purchased)}):"]
            lines += [f"  ✓ {g.idea}{_purchase_date(g.purchased_at)}" for g in purchased[:6]]
        if unpurchased:
            lines.append("\nStill on the list:")
            lines += [f"  ○ {g.idea}" for g in unpurchased[:4]]
        return lines

    if not gifts:
        return ["○ Nothing bought yet, and no ideas captured."]

    marker = "⚠" if days <= 7 else "○"
    noun = "idea" if len(unpurchased) == 1 else "ideas"
    lines = [f"{marker} Nothing bought yet — {len(unpurchased)} {noun} on file:"]
    lines += [f"  ○ {g.idea}" for g in unpurchased[:6]]
    return lines


def _format_notification(person, gifts, bought: bool):
    """Return (markdown_text, InlineKeyboardMarkup) for a notification."""
    days = person.days_until
    age_part = f", turning {person.age_turning}" if person.age_turning else ""
    purchased = [g for g in gifts if g.purchased]
    unpurchased = [g for g in gifts if not g.purchased]

    if days == 0:
        turning = f" — turning {person.age_turning}" if person.age_turning else ""
        header = f"🎉 *{person.name}*'s birthday is today{turning}!"
    else:
        when = "is tomorrow" if days == 1 else f"is in {days} days"
        emoji = "🎂" if days <= 7 else "📅"
        header = f"{emoji} *{person.name}*'s birthday {when}{age_part}."

    body_lines = [header, ""] + _status_block(gifts, purchased, unpurchased, days)

    # Mark buttons for whatever is still unbought — offered whether or not
    # something has already been purchased, so a second gift can be recorded.
    rows = [
        [InlineKeyboardButton(f"✓ Mark {g.idea[:24]}",
                              callback_data=f"toggle_gift:{g.id}:{person.id}:1")]
        for g in unpurchased[:3]
    ]
    rows.append(
        [
            InlineKeyboardButton("➕ Add idea", callback_data=f"add_gift_for:{person.id}"),
            InlineKeyboardButton("📅 All upcoming", callback_data="upcoming"),
        ]
    )

    return "\n".join(body_lines), InlineKeyboardMarkup(rows)
