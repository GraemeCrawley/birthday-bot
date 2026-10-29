"""Runtime settings read from environment variables (leaf module, no internal deps).

Everything a person running their own copy might want to change lives here.
See ../.env.example for documentation of each variable.
"""

from __future__ import annotations

import os

# Timezone for the daily reminder and all "what day is it" maths.
TZ = os.environ.get("TZ") or "UTC"

# Where the web app is reachable *from your phone/browser*. Shown in bot
# messages that point you at the web app (e.g. to add a new person).
WEB_APP_URL = (os.environ.get("WEB_APP_URL") or "http://localhost:8000").rstrip("/")

# Local time (24h clock) at which the daily reminder check runs.
DAILY_CHECK_HOUR = int(os.environ.get("DAILY_CHECK_HOUR") or "9")
DAILY_CHECK_MINUTE = int(os.environ.get("DAILY_CHECK_MINUTE") or "0")
