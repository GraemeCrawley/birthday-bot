"""Typed conversation state management for the birthday bot.

The bot has a small number of multi-step flows where the user is mid-conversation
(e.g. they've been asked "What's the gift idea?" and the next text message should
be treated as the answer, not a fresh capture).

Storing flow state as raw string keys in `ctx.user_data` is bug-bait — one typo
in a dict key is a silent failure. This module is the only place those keys are
defined; everywhere else uses these typed accessors.

Three states currently:
    AWAITING_IDEA_FOR    — user asked to type an idea for a specific person
    AWAITING_NAME_SEARCH — user asked to type a name to search for
    (none)               — neutral; next text is a fresh capture or bare-name search

State is per-user (PTB's `ctx.user_data` is per-user-per-bot); no global state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---- Keys (defined once) -------------------------------------------------

_AWAITING_IDEA_FOR = "awaiting_idea_for"
_AWAITING_NAME_SEARCH = "awaiting_name_search"


# ---- Typed payloads ------------------------------------------------------

@dataclass(frozen=True)
class AwaitingIdeaFor:
    person_id: int
    person_name: str


# ---- Accessors -----------------------------------------------------------

def set_awaiting_idea_for(user_data: dict[str, Any], person_id: int, person_name: str) -> None:
    user_data[_AWAITING_IDEA_FOR] = AwaitingIdeaFor(person_id=person_id, person_name=person_name)


def take_awaiting_idea_for(user_data: dict[str, Any]) -> AwaitingIdeaFor | None:
    """Pop and return the awaiting-idea state, or None if not set."""
    val = user_data.pop(_AWAITING_IDEA_FOR, None)
    if isinstance(val, AwaitingIdeaFor):
        return val
    if isinstance(val, tuple) and len(val) == 2:
        # Tolerate legacy tuple-shape stored by older bot versions
        return AwaitingIdeaFor(person_id=val[0], person_name=val[1])
    return None


def is_awaiting_idea_for(user_data: dict[str, Any]) -> bool:
    return user_data.get(_AWAITING_IDEA_FOR) is not None


def set_awaiting_name_search(user_data: dict[str, Any]) -> None:
    user_data[_AWAITING_NAME_SEARCH] = True


def take_awaiting_name_search(user_data: dict[str, Any]) -> bool:
    """Pop and return whether the awaiting-name-search state was set."""
    return bool(user_data.pop(_AWAITING_NAME_SEARCH, False))


def is_awaiting_name_search(user_data: dict[str, Any]) -> bool:
    return bool(user_data.get(_AWAITING_NAME_SEARCH))


def clear(user_data: dict[str, Any]) -> None:
    """Drop ALL conversation state. Used when the user navigates back to a
    neutral surface (main menu, help) — they're starting over."""
    user_data.pop(_AWAITING_IDEA_FOR, None)
    user_data.pop(_AWAITING_NAME_SEARCH, None)
