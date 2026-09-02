"""Uitagenda MCP server (stdio) over the published feed.

Reads the published route files rather than the scrapers: `data/` on this host
when it is there, else https://agenda.jurrejan.com. Both are the same documents,
so a laptop with no checkout still works. Routes exist per city and per venue, so
a city search parses ~40 KB instead of the 1.3 MB full feed.
"""

import json
import time
import urllib.request
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from agenda_scraper.config import BASE_URL, DATA_DIR
from agenda_scraper.publish import slugify

CACHE_TTL = 300.0  # the feed changes 4x a day; a turn asks several questions
STALE_HOURS = 8.0  # one missed refresh (they are 6h apart) plus slack
DENSE_DAYS = 45  # past this only the venues with long agendas are covered
MAX_LIMIT = 100

_cache: dict[str, tuple[float, dict]] = {}

server = MCPServer("uitagenda", version="1.0.0")


def _read(name: str) -> dict:
    path = DATA_DIR / name
    if path.exists():
        return json.loads(path.read_text(encoding="utf8"))
    with urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=20) as resp:
        return json.loads(resp.read().decode("utf8", "replace"))


def _doc(name: str) -> dict:
    hit = _cache.get(name)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    doc = _read(name)
    _cache[name] = (time.monotonic(), doc)
    return doc


def _routes() -> dict[str, dict]:
    return {r["route"]: r for r in _doc("routes.json")["routes"]}


def _feed_note(doc: dict) -> dict:
    """Freshness travels with every answer: a stale feed is the failure that lies."""
    gen = doc.get("generated_at", "")
    note = {"generated_at": gen, "healthy": doc.get("healthy", True)}
    if doc.get("problems"):
        note["problems"] = doc["problems"]
    age = (
        datetime.now().astimezone() - datetime.fromisoformat(gen)
    ).total_seconds() / 3600
    if age > STALE_HOURS:
        note["stale"] = f"feed is {age:.0f}h old — the refresh timer may have stopped"
    return note


def _events_for(city: str | None) -> dict:
    """The narrowest document that still answers the question."""
    if city:
        route = f"city/{slugify(city)}"
        if route in _routes():
            return _doc(f"{route}.json")
    return _doc("events.json")


def _matches(event: dict, query: str | None, venue: str | None) -> bool:
    if venue and venue.lower() not in event["venue"].lower():
        return False
    if not query:
        return True
    hay = f"{event['title']} {event['venue']} {event['city']}".lower()
    return all(word in hay for word in query.lower().split())


def _window(days: int, from_date: str | None, to_date: str | None) -> tuple[str, str]:
    lo = from_date or str(date.today())
    hi = to_date or str(date.fromisoformat(lo) + timedelta(days=max(days, 1) - 1))
    return lo, hi


def _slim(e: dict) -> dict:
    row = {
        k: e[k] for k in ("date", "time", "title", "venue", "city", "url") if e.get(k)
    }
    for extra in ("status", "end"):
        if e.get(extra):
            row[extra] = e[extra]
    return row


def _city_counts() -> dict[str, int]:
    return {
        r["label"]: r["count"]
        for route, r in _routes().items()
        if route.startswith("city/") and route.count("/") == 1
    }


@server.tool(
    description=(
        "Search upcoming concerts, club nights and festivals in the Netherlands. "
        "Returns date, time, title, venue, city, ticket status and a link, soonest "
        "first — no prices, no line-ups, no descriptions. Free and instant: it reads "
        "a pre-built feed, it does not visit venue sites. Defaults to the next 14 "
        "days nationwide; pass city for one place (call cities() for exact names), "
        "venue for one stage, query for words in the title. COVERAGE: dense for "
        "about six weeks, thin past three months, and 'status' is only set by the "
        "venue scrapers and can be up to 6 hours stale — confirm sold-out claims on "
        "the event url before stating them."
    )
)
def search(
    query: Annotated[
        str | None,
        Field(description="Words that must all appear in title, venue or city"),
    ] = None,
    city: Annotated[
        str | None, Field(description="Dutch city name, e.g. Amsterdam, Den Haag")
    ] = None,
    venue: Annotated[
        str | None, Field(description="Substring of the venue name, e.g. Paradiso")
    ] = None,
    days: Annotated[int, Field(description="Window length in days from today")] = 14,
    from_date: Annotated[
        str | None, Field(description="YYYY-MM-DD, defaults to today")
    ] = None,
    to_date: Annotated[
        str | None, Field(description="YYYY-MM-DD, overrides days")
    ] = None,
    limit: Annotated[int, Field(description="Max events to return, max 100")] = 20,
) -> dict[str, Any]:
    """Events matching every given filter, soonest first."""
    doc = _events_for(city)
    lo, hi = _window(days, from_date, to_date)
    wanted = slugify(city) if city else ""
    capped = max(1, min(limit, MAX_LIMIT))
    rows = [
        e
        for e in doc["events"]
        if (e.get("end") or e["date"]) >= lo
        and e["date"] <= hi
        and (not wanted or slugify(e["city"]) == wanted)
        and _matches(e, query, venue)
    ]
    out: dict[str, Any] = {
        "window": {"from": lo, "to": hi},
        "matched": len(rows),
        "returned": min(len(rows), capped),
        "events": [_slim(e) for e in rows[:capped]],
        "feed": _feed_note(doc),
    }
    if city and wanted not in {slugify(c) for c in _city_counts()}:
        out["note"] = f"no city named {city!r} in the feed — call cities() for the list"
    if hi > str(date.today() + timedelta(days=DENSE_DAYS)):
        out["coverage"] = (
            f"past {DENSE_DAYS} days only venues with long agendas are scraped, so a "
            "thin result there is missing data, not a quiet week"
        )
    return out


@server.tool(
    description=(
        "Every city the feed covers, with how many upcoming events each has, busiest "
        "first. Call this when a city search comes back empty or the user names a "
        "place you are unsure of — city matching is exact on the name."
    )
)
def cities() -> dict[str, Any]:
    """Every city in the feed with its event count, busiest first."""
    counts = sorted(_city_counts().items(), key=lambda kv: -kv[1])
    return {
        "cities": [{"city": c, "events": n} for c, n in counts],
        "feed": _feed_note(_doc("routes.json")),
    }


@server.tool(
    description=(
        "Venue names exactly as the feed spells them, with event counts, optionally "
        "narrowed to a city or a name fragment. Use it to turn a vague 'that place in "
        "Rotterdam' into the string search(venue=…) will match."
    )
)
def venues(
    city: Annotated[str | None, Field(description="Only venues in this city")] = None,
    query: Annotated[
        str | None, Field(description="Substring of the venue name")
    ] = None,
    limit: Annotated[int, Field(description="Max venues to return")] = 30,
) -> dict[str, Any]:
    """Venue names as the feed spells them — what search(venue=…) matches on."""
    doc = _events_for(city)
    wanted = slugify(city) if city else ""
    counts: dict[tuple[str, str], int] = {}
    for e in doc["events"]:
        if wanted and slugify(e["city"]) != wanted:
            continue
        if query and query.lower() not in e["venue"].lower():
            continue
        if e["venue"]:
            key = (e["venue"], e["city"])
            counts[key] = counts.get(key, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[: max(1, min(limit, MAX_LIMIT))]
    return {
        "venues": [{"venue": v, "city": c, "events": n} for (v, c), n in top],
        "distinct": len(counts),
        "feed": _feed_note(doc),
    }


def run() -> None:
    server.run()
