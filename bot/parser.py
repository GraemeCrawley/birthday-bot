"""Natural-language gift-capture parsing for the birthday bot.

Patterns, tried in order:

    gift for <name> [-–:] <idea>
    <name>: <idea>           (single colon, no leading "gift for")
    add <idea> for <name>

All matches are case-insensitive; whitespace is normalized.
Returns ParsedGift(name, idea) or None.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedGift:
    name: str   # candidate person name (case-preserved from the message)
    idea: str   # the gift idea text
    purchased: bool = False  # True when the message reported a completed purchase


# Purchase patterns run FIRST so a leading buy-verb is never swallowed by the
# generic "<name>: <idea>" rule — "bought ada: cutting board" must resolve
# to name=ada, not name="bought ada". The verb has to LEAD the message:
# "mike: bought the cutting board" stays an add, because the only reliable
# signal we have is position, and guessing from a mid-sentence verb would make
# adds silently become purchases.
_PURCHASE_VERBS = r"(?:bought|got|purchased)"

# Order matters — most specific first.
# The (?:add\s+)? optional prefix on the gift-for pattern accepts both:
#   gift for mike - cutting board
#   add gift for mike - cutting board
_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        rf"^(?:i\s+)?{_PURCHASE_VERBS}\s+(?:for\s+)?(?P<name>.+?)\s*[-–:]\s*(?P<idea>.+)$",
        re.IGNORECASE,
    ),
    re.compile(r"^(?:add\s+)?gift\s+for\s+(?P<name>.+?)\s*[-–:]\s*(?P<idea>.+)$", re.IGNORECASE),
    re.compile(r"^add\s+(?P<idea>.+?)\s+for\s+(?P<name>.+)$", re.IGNORECASE),
    # Last-resort: "<name>: <idea>" — must have exactly one colon and a non-empty
    # left side without internal colons (avoids matching emoji "::" style etc.)
    # Idea's first non-space char must NOT be a colon — rejects "x :: y" patterns
    re.compile(r"^(?P<name>[^:\n]{1,40}?)\s*:\s*(?P<idea>[^:\s][^\n]{0,199})$"),
]


def parse(message_text: str) -> ParsedGift | None:
    """Return ParsedGift if the message matches one of the gift-capture patterns.

    Caller is responsible for resolving `name` to an actual Person via the
    API (fuzzy substring match).
    """
    text = (message_text or "").strip()
    if not text:
        return None
    for i, pat in enumerate(_PATTERNS):
        m = pat.match(text)
        if not m:
            continue
        name = m.group("name").strip()
        idea = m.group("idea").strip()
        if not name or not idea:
            continue
        # Reject overly long captures (paste accidents)
        if len(name) > 60 or len(idea) > 200:
            continue
        # Index 0 is the purchase pattern; everything after it is an add.
        return ParsedGift(name=name, idea=idea, purchased=(i == 0))
    return None
