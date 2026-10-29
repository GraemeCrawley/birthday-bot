"""End-to-end tests for the soft-archive cycle close-out endpoint and the
dashboard's archive filter.

These are the two pieces most likely to silently break: a refactor could
re-include archived gifts in the dashboard, or change what reset-gift-cycle
considers "purchased". Both bugs would show up only in production after a
real birthday.

Strategy: spin up the FastAPI app against a sqlite in-memory DB, exercise
the public HTTP surface via TestClient. No JSONB columns in models.py, so
sqlite is sufficient.
"""

import os
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

# Force a sqlite URL BEFORE importing main/database so create_engine() picks it up.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database  # noqa: E402
import main as app_main  # noqa: E402
from database import Base  # noqa: E402


# Override the engine to use a single in-memory connection across the
# TestClient and any direct DB access. StaticPool keeps the same conn so
# the in-memory DB persists for the test lifetime.
TEST_ENGINE = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=TEST_ENGINE)
database.engine = TEST_ENGINE
database.SessionLocal = TestSession


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


from fastapi.testclient import TestClient  # noqa: E402

app_main.app.dependency_overrides[database.get_db] = _override_get_db


class ResetGiftCycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=TEST_ENGINE)
        cls.client = TestClient(app_main.app)

    def setUp(self):
        # Wipe between tests for isolation
        from models import GiftIdea, Person
        s = TestSession()
        s.query(GiftIdea).delete()
        s.query(Person).delete()
        s.commit()
        s.close()

    def _create_person(self, name="Test Person", birthday="1990-04-27"):
        r = self.client.post("/api/people", json={"name": name, "birthday": birthday})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["id"]

    def _add_gift(self, person_id, idea, purchased=False):
        r = self.client.post(f"/api/people/{person_id}/gifts", json={"idea": idea})
        self.assertEqual(r.status_code, 200, r.text)
        gid = r.json()["id"]
        if purchased:
            r2 = self.client.put(f"/api/gifts/{gid}", json={"purchased": True})
            self.assertEqual(r2.status_code, 200, r2.text)
        return gid

    def test_archives_only_purchased(self):
        pid = self._create_person()
        self._add_gift(pid, "fake A", purchased=True)
        self._add_gift(pid, "fake B", purchased=True)
        self._add_gift(pid, "fake C unbought")

        r = self.client.post(f"/api/people/{pid}/reset-gift-cycle")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["archived_count"], 2)

        # Default list excludes archived
        active = self.client.get(f"/api/people/{pid}/gifts").json()
        self.assertEqual([g["idea"] for g in active], ["fake C unbought"])

        # include_archived=true returns all
        all_g = self.client.get(f"/api/people/{pid}/gifts?include_archived=true").json()
        self.assertEqual(len(all_g), 3)

    def test_idempotent_second_call(self):
        pid = self._create_person()
        self._add_gift(pid, "fake A", purchased=True)
        self.client.post(f"/api/people/{pid}/reset-gift-cycle")

        r2 = self.client.post(f"/api/people/{pid}/reset-gift-cycle")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.json()["archived_count"], 0)

    def test_no_purchased_gifts_returns_zero(self):
        pid = self._create_person()
        self._add_gift(pid, "only an idea")
        r = self.client.post(f"/api/people/{pid}/reset-gift-cycle")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["archived_count"], 0)

    def test_dashboard_hides_archived(self):
        pid = self._create_person()
        self._add_gift(pid, "active idea")
        self._add_gift(pid, "bought thing", purchased=True)

        before = self.client.get("/api/dashboard").json()
        self.assertEqual(len(next(p for p in before if p["id"] == pid)["gifts"]), 2)

        self.client.post(f"/api/people/{pid}/reset-gift-cycle")

        after = self.client.get("/api/dashboard").json()
        person = next(p for p in after if p["id"] == pid)
        self.assertEqual([g["idea"] for g in person["gifts"]], ["active idea"])

    def test_unknown_person_returns_404(self):
        r = self.client.post("/api/people/99999/reset-gift-cycle")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
