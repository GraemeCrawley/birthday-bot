"""Optional Healthchecks.io monitoring for the daily job.

Healthchecks.io (https://healthchecks.io) is a free service that emails you if
a scheduled job stops running. It is entirely OPTIONAL:

  * If HEALTHCHECKS_API_KEY is not set (the default), Cron silently does
    nothing — no registration, no pings, no errors. The job runs normally.
  * If it is set, the check is created/updated automatically on start-up
    and pinged each time the job starts, succeeds, or fails.

Usage:

    from cron import Cron

    DAILY = Cron(name="birthday-bot-daily-check", schedule="0 9 * * *")

    async def daily_check(...):
        async with DAILY.run():
            ...  # job body
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx

log = logging.getLogger(__name__)
# httpx logs request URLs at INFO; the Telegram API URL embeds the bot token — pin to
# WARNING so a scheduled send (this cron) can't write the token to logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

HC_API = "https://healthchecks.io/api/v1/checks/"
DEFAULT_TZ = os.getenv("TZ") or "UTC"
DEFAULT_TAGS = os.getenv("HEALTHCHECKS_TAGS", "birthday-bot")


class Cron:
    """One scheduled job. Self-registers with Healthchecks on construction."""

    def __init__(
        self,
        name: str,
        schedule: str,
        grace_seconds: int = 1800,
        tz: str = DEFAULT_TZ,
        tags: str = DEFAULT_TAGS,
        description: str = "",
    ):
        self.name = name
        self.schedule = schedule
        self.grace_seconds = grace_seconds
        self.tz = tz
        self.tags = tags
        self.description = description
        self.ping_url = self._register()

    def _register(self) -> str | None:
        """Create-or-update the Healthchecks check. Returns ping URL or None."""
        api_key = (os.getenv("HEALTHCHECKS_API_KEY") or "").strip()
        if not api_key:
            log.info("HEALTHCHECKS_API_KEY not set — cron monitoring disabled for %s", self.name)
            return None
        try:
            r = httpx.post(
                HC_API,
                headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
                json={
                    "name": self.name,
                    "schedule": self.schedule,
                    "tz": self.tz,
                    "grace": self.grace_seconds,
                    "tags": self.tags,
                    "desc": self.description,
                    "unique": ["name"],
                },
                timeout=10.0,
            )
            r.raise_for_status()
            url = r.json().get("ping_url")
            log.info("healthchecks: registered %r → %s", self.name, url)
            return url
        except Exception as e:
            log.warning("healthchecks register failed for %s: %s", self.name, e)
            return None

    async def _ping(self, suffix: str = "") -> None:
        if not self.ping_url:
            return
        url = f"{self.ping_url}{suffix}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                await c.get(url)
        except Exception as e:
            log.warning("healthchecks ping failed (%s): %s", url, e)

    @asynccontextmanager
    async def run(self):
        """Wrap a job body so start/success/fail pings are sent automatically.

        Pings are best-effort — failures are logged but never block or
        re-raise. Job exceptions still propagate to the caller.
        """
        await self._ping("/start")
        try:
            yield
        except Exception:
            await self._ping("/fail")
            raise
        else:
            await self._ping("")
