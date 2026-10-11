"""The archive: every event any run has scraped, kept after it is over.

The live feed drops an event the day it finishes; this keeps it. Storage is one
JSONL file in the data dir, rewritten whole each run through a temp file and a
rename. JSONL rather than SQLite because the merge needs every field of every
row in Python anyway (the never-blank rule is per field), the month routes read
whole months back, and a new event field needs no migration — an old row just
lacks it and is padded with "" on the way out. At ~100k rows (~40 MB) the
load-merge-rewrite is about a second, four times a day.

ponytail: whole-file rewrite each run; move to SQLite upserts past ~1M rows.
"""

import json
from pathlib import Path

from agenda_scraper import Event
from agenda_scraper.publish.feed import FIELDS, _title_key, venue_id

ARCHIVE_FILE = "archive.jsonl"
SEEN_FIELDS = ("first_seen", "last_seen")


def archive_key(e: Event) -> str:
    """Dedupe's own key, so the venue's copy and podiuminfo's "X @ Venue" stay one row."""
    return "|".join((venue_id(e), e["date"], _title_key(e["title"])))


def _fold(old: Event | None, new: Event) -> Event:
    """The later sighting wins every field it states; neither ever blanks one.

    Ordered on last_seen rather than on arrival, so a recovered snapshot older
    than the archive can be folded in without overwriting newer facts.
    """
    if old is None:
        return new
    early, late = sorted((old, new), key=lambda r: r["last_seen"])
    row = {**early, **{k: v for k, v in late.items() if v}}
    row["first_seen"] = min(old["first_seen"], new["first_seen"])
    return row


def merge(
    archive: dict[str, Event], events: list[Event], seen: str
) -> dict[str, Event]:
    """Fold one run's events into the archive. Nothing ever leaves it."""
    out = dict(archive)
    for e in events:
        key = archive_key(e)
        out[key] = _fold(out.get(key), {**e, "first_seen": seen, "last_seen": seen})
    return out


def load(path: Path) -> dict[str, Event]:
    """The archive on disk, keyed. Two rows the key now calls one are merged, not lost."""
    out: dict[str, Event] = {}
    if not path.exists():
        return out
    # Split on "\n" only: splitlines() also breaks on U+2028 and friends, which titles contain
    # and json.dumps(ensure_ascii=False) writes raw.
    for line in path.read_text(encoding="utf8").split("\n"):
        if line:
            row = json.loads(line)
            out[archive_key(row)] = _fold(out.get(archive_key(row)), row)
    return out


def dump(archive: dict[str, Event]) -> str:
    return "".join(
        json.dumps(archive[k], ensure_ascii=False) + "\n" for k in sorted(archive)
    )


def published(archive: dict[str, Event]) -> list[Event]:
    """Every archived row in the live feed's shape plus the two sighting stamps.

    A row archived before a field existed is padded with "", so every row has
    every key in the same order, whatever release wrote it.
    """
    rows = [{f: r.get(f, "") for f in FIELDS + SEEN_FIELDS} for r in archive.values()]
    return sorted(rows, key=lambda e: (e["date"], e["time"], e["title"]))


def by_month(rows: list[Event]) -> dict[str, list[Event]]:
    """Archived rows per start month ("2026-09"); a festival files under its first day."""
    out: dict[str, list[Event]] = {}
    for e in rows:
        out.setdefault(e["date"][:7], []).append(e)
    return out


def month_index(rows: list[Event]) -> list[dict]:
    """What /archive/index.json lists: one entry per month a reader can poll.

    `last_modified` is the newest last_seen in the month, which is the last run
    that could have changed it — a month whose events are all over stops moving.
    """
    return [
        {
            "month": month,
            "count": len(group),
            "last_modified": max(e["last_seen"] for e in group),
            "json": f"/archive/{month}.json",
        }
        for month, group in sorted(by_month(rows).items())
    ]
