#!/usr/bin/env python3
"""Load birthdays from a CSV file into the Birthday Bot, via its API.

CSV columns (first row must be this header):

    name,birthday,notes,gift_ideas

  name        required, e.g. Ada Example
  birthday    required, YYYY-MM-DD, e.g. 1990-01-15
  notes       optional
  gift_ideas  optional, several ideas separated by ";"

Safe to run more than once: people whose name already exists are skipped.
Uses only the Python standard library.

Easiest way (no Python needed on your computer; runs inside the api container):

    docker compose exec api python /scripts/import_birthdays.py /samples/sample-birthdays.csv
    docker compose exec api python /scripts/import_birthdays.py /data/my-birthdays.csv

Or with Python installed on your computer:

    python3 scripts/import_birthdays.py samples/sample-birthdays.csv --api http://localhost:8000
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.error
import urllib.request
from datetime import date


def call(api: str, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"{api}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"null")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_file", help="path to the CSV file")
    ap.add_argument("--api", default="http://localhost:8000",
                    help="API address (default: http://localhost:8000)")
    args = ap.parse_args()
    api = args.api.rstrip("/")

    try:
        existing = {p["name"].strip().lower() for p in call(api, "GET", "/api/people")}
    except (urllib.error.URLError, OSError) as e:
        print(f"Could not reach the API at {api}: {e}\n"
              "Is it running? Try: docker compose ps", file=sys.stderr)
        return 1

    added = skipped = errors = 0
    with open(args.csv_file, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = {"name", "birthday"} - set(reader.fieldnames or [])
        if missing:
            print(f"CSV is missing column(s): {', '.join(sorted(missing))}", file=sys.stderr)
            return 1
        for line_no, row in enumerate(reader, start=2):
            name = (row.get("name") or "").strip()
            bday = (row.get("birthday") or "").strip()
            if not name and not bday:
                continue
            try:
                date.fromisoformat(bday)
            except ValueError:
                print(f"line {line_no}: skipped {name!r}: birthday {bday!r} is not YYYY-MM-DD")
                errors += 1
                continue
            if name.lower() in existing:
                print(f"line {line_no}: {name} already exists, skipped")
                skipped += 1
                continue
            person = call(api, "POST", "/api/people", {
                "name": name, "birthday": bday,
                "notes": (row.get("notes") or "").strip() or None,
            })
            existing.add(name.lower())
            ideas = [i.strip() for i in (row.get("gift_ideas") or "").split(";") if i.strip()]
            for idea in ideas:
                call(api, "POST", f"/api/people/{person['id']}/gifts", {"idea": idea})
            print(f"line {line_no}: added {name} ({bday}), {len(ideas)} gift idea(s)")
            added += 1

    print(f"\nDone: {added} added, {skipped} already there, {errors} with errors.")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
