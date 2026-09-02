"""What the feed says about an event: its entity ids, its horizon, its health.

Everything here is pure — it takes rows and returns rows — so the route writer
in `routes.py` never has to know how a duplicate or an id is decided.
"""

import json
import re
from datetime import date
from pathlib import Path

from agenda_scraper import Event, Report
from agenda_scraper.entities import (
    ENTITY_FIELDS,
    LEGACY_FIELDS,
    extract_artists,
    resolve_city,
    resolve_venue,
)

# Aggregators list the same night as the venue itself. Lower index wins, so a
# duplicate keeps the venue's own page (real ticket status, real detail URL).
SOURCE_RANK = (
    "paradiso",
    "tivoli",
    "dehelling",
    "ekko",
    "rotown",
    "musicon",
    "dbstudio",
    "muziekgieterij",
    "013",
    "spot",
    "spot",
    "victorie",
    "gebrdenobel",
    "gigant",
    "annabel",
    "melkweg",
    "effenaar",
    "patronaat",
    "hedon",
    "neushoorn",
    "burgerweeshuis",
    "vera",
    "afaslive",
    "ra-nl",
    "partyflock",
    "podiuminfo",
    "festivalinfo",
)

# The nine legacy columns first, in their original order, then the entity ids.
# Appending is the only change a consumer splitting on tabs survives.
FIELDS = LEGACY_FIELDS + ENTITY_FIELDS


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def venue_id(event: Event) -> str:
    """The event's venue id, resolving it on the spot if it was never annotated."""
    return (
        event.get("venue_id")
        or resolve_venue(event.get("venue", ""), event.get("city", ""))["id"]
    )


def annotate(events: list[Event]) -> list[Event]:
    """Add venue_id, city_id and artist_ids. Idempotent, and never rewrites a key."""
    out = []
    for e in events:
        artists = extract_artists(e.get("title", ""))
        out.append(
            {
                **e,
                "venue_id": resolve_venue(e.get("venue", ""), e.get("city", ""))["id"],
                "city_id": resolve_city(e.get("city", ""))["id"],
                "artist_ids": ",".join(a["id"] for a in artists),
            }
        )
    return out


def dedupe(events: list[Event]) -> list[Event]:
    """Drop the aggregator's copy of an event a venue source already reported.

    Same day, same venue, same title. Keying on the resolved venue rather than
    on free-text city catches the pair the old key missed — one source naming
    the city, the other not — without merging two different rooms in one city.
    """
    rank = {name: i for i, name in enumerate(SOURCE_RANK)}
    best: dict = {}
    for e in events:
        key = (e["date"], venue_id(e), _title_key(e["title"]))
        if not key[1] or not key[2]:  # unknown venue or empty title
            best[id(e)] = e
            continue
        cur = best.get(key)
        if cur is None or rank.get(e["source"], 99) < rank.get(cur["source"], 99):
            best[key] = e
    return sorted(best.values(), key=lambda e: (e["date"], e["time"], e["title"]))


def current(events: list[Event], today: str | None = None) -> list[Event]:
    """Events that have not finished yet; a multi-day festival stays until its end."""
    today = today or str(date.today())
    return [e for e in events if (e.get("end") or e["date"]) >= today]


def as_tsv(events: list[Event]) -> str:
    return "\n".join("\t".join(e.get(f, "") for f in FIELDS) for e in events)


def assess(report: Report, history_path: Path) -> list[str]:
    """Compare this run against recent ones and name what looks wrong.

    A scraper's normal failure is silent: the site reshuffles its markup, the
    parser matches nothing, and the run still exits 0 with an empty list. So a
    source is a problem when it throws, when it returns nothing, and when it
    returns far less than it usually does — the last one is what caught
    Paradiso dropping from 348 to 174.
    """
    history_path = Path(history_path)
    try:
        hist = json.loads(history_path.read_text())
    except (OSError, ValueError):
        hist = {}
    problems = []
    for name, r in sorted(report.items()):
        past = hist.get(name, [])
        if not r["ok"]:
            problems.append(f"{name}: failed — {r.get('error', '')[:120]}")
        elif r["count"] == 0:
            problems.append(f"{name}: returned 0 events")
        elif past:
            norm = sorted(past)[len(past) // 2]
            if r["count"] < norm * 0.5:
                problems.append(f"{name}: {r['count']} events, normally ~{norm}")
        if r["ok"] and r["count"]:
            hist[name] = (past + [r["count"]])[-7:]  # only good runs set the norm
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(hist, indent=1))
    return problems
