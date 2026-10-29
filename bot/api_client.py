"""Async HTTP client wrapping the API service (FastAPI, ../api)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

API_URL = os.environ.get("BIRTHDAY_REMINDER_URL") or "http://api:8000"
TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    days_until: int | None = None
    age_turning: int | None = None
    # ISO date string (e.g. "1985-04-27"); only present from the dashboard
    # endpoint. Used by the bot's scheduler to detect day-after-birthday
    # without relying on a fragile `days_until == 364` heuristic.
    birthday: str | None = None


@dataclass(frozen=True)
class GiftIdea:
    id: int
    person_id: int
    idea: str
    purchased: bool
    purchased_at: str | None = None  # ISO datetime or None


class APIClient:
    """Thin async wrapper. One client instance per process is fine."""

    def __init__(self, base_url: str = API_URL):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=TIMEOUT)

    async def aclose(self) -> None:
        await self._client.aclose()

    # ---- People -----------------------------------------------------------

    async def list_people(self) -> list[Person]:
        r = await self._client.get("/api/people")
        r.raise_for_status()
        return [Person(id=p["id"], name=p["name"]) for p in r.json()]

    async def dashboard(self) -> list[Person]:
        """Returns people sorted by days_until (next birthday first)."""
        r = await self._client.get("/api/dashboard")
        r.raise_for_status()
        return [
            Person(
                id=p["id"],
                name=p["name"],
                days_until=p.get("days_until"),
                age_turning=p.get("age_turning"),
                birthday=p.get("birthday"),
            )
            for p in r.json()
        ]

    # ---- Gifts ------------------------------------------------------------

    async def list_gifts(self, person_id: int) -> list[GiftIdea]:
        r = await self._client.get(f"/api/people/{person_id}/gifts")
        r.raise_for_status()
        return [
            GiftIdea(
                id=g["id"],
                person_id=g["person_id"],
                idea=g["idea"],
                purchased=bool(g.get("purchased", False)),
                purchased_at=g.get("purchased_at"),
            )
            for g in r.json()
        ]

    async def add_gift(self, person_id: int, idea: str, notes: str | None = None) -> GiftIdea:
        body: dict[str, Any] = {"idea": idea}
        if notes:
            body["notes"] = notes
        r = await self._client.post(f"/api/people/{person_id}/gifts", json=body)
        r.raise_for_status()
        g = r.json()
        return GiftIdea(
            id=g["id"], person_id=g["person_id"], idea=g["idea"],
            purchased=bool(g.get("purchased", False)),
            purchased_at=g.get("purchased_at"),
        )

    async def delete_gift(self, gift_id: int) -> None:
        r = await self._client.delete(f"/api/gifts/{gift_id}")
        r.raise_for_status()

    async def update_gift(self, gift_id: int, **fields: Any) -> GiftIdea:
        r = await self._client.put(f"/api/gifts/{gift_id}", json=fields)
        r.raise_for_status()
        g = r.json()
        return GiftIdea(
            id=g["id"], person_id=g["person_id"], idea=g["idea"],
            purchased=bool(g.get("purchased", False)),
            purchased_at=g.get("purchased_at"),
        )

    async def reset_gift_cycle(self, person_id: int) -> int:
        """Close out the gift cycle: the API soft-archives purchased gifts.
        Returns the count of gifts that were archived."""
        r = await self._client.post(f"/api/people/{person_id}/reset-gift-cycle")
        r.raise_for_status()
        data = r.json()
        return int(data.get("archived_count", data.get("reset_count", 0)))

    # ---- Helpers ----------------------------------------------------------

    async def find_person_by_name(self, query: str) -> list[Person]:
        """Case-insensitive substring match against Person.name. Returns all matches."""
        q = query.strip().lower()
        if not q:
            return []
        people = await self.list_people()
        return [p for p in people if q in p.name.lower()]
