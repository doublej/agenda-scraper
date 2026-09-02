#!/usr/bin/env python3
"""Uitagenda MCP server (stdio). Stdlib only — the host has python3 and nothing else.

Serves the agenda-scraper feed: concerts, club nights and festivals across the
Netherlands, refreshed four times a day by agenda-scraper.timer.

Reads the published route files rather than the scrapers: `data/` on this host
when it is there, else https://agenda.jurrejan.com. Both are the same documents,
so a laptop with no checkout still works. Routes exist per city and per venue, so
a city search parses ~40 KB instead of the 1.3 MB full feed.

Three tools: search(), cities(), venues().
Self-check: python3 uitagenda_mcp.py --selftest
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

DATA_DIR = os.environ.get("AGENDA_DATA_DIR", "/home/jurrejan/development/agenda-scraper/data")
BASE_URL = os.environ.get("AGENDA_BASE_URL", "https://agenda.jurrejan.com").rstrip("/")
CACHE_TTL = 300.0        # the feed changes 4x a day; a turn asks several questions
STALE_HOURS = 8.0        # one missed refresh (they are 6h apart) plus slack
DENSE_DAYS = 45          # past this only the venues with long agendas are covered
MAX_LIMIT = 100

_cache = {}


def slugify(name):
    """Same rule as publish.py, so a city name reaches its route file."""
    flat = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", flat.lower())).strip("-")


def _read(name):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        with open(path, encoding="utf8") as fh:
            return json.load(fh)
    with urllib.request.urlopen(f"{BASE_URL}/{name}", timeout=20) as resp:
        return json.loads(resp.read().decode("utf8", "replace"))


def _doc(name):
    hit = _cache.get(name)
    if hit and time.monotonic() - hit[0] < CACHE_TTL:
        return hit[1]
    doc = _read(name)
    _cache[name] = (time.monotonic(), doc)
    return doc


def _routes():
    return {r["route"]: r for r in _doc("routes.json")["routes"]}


def _feed_note(doc):
    """Freshness travels with every answer: a stale feed is the failure that lies."""
    gen = doc.get("generated_at", "")
    note = {"generated_at": gen, "healthy": doc.get("healthy", True)}
    if doc.get("problems"):
        note["problems"] = doc["problems"]
    age = (datetime.now().astimezone() - datetime.fromisoformat(gen)).total_seconds() / 3600
    if age > STALE_HOURS:
        note["stale"] = f"feed is {age:.0f}h old — the refresh timer may have stopped"
    return note


def _events_for(city):
    """The narrowest document that still answers the question."""
    if city:
        route = f"city/{slugify(city)}"
        if route in _routes():
            return _doc(f"{route}.json")
    return _doc("events.json")


def _matches(event, query, venue):
    if venue and venue.lower() not in event["venue"].lower():
        return False
    if not query:
        return True
    hay = f"{event['title']} {event['venue']} {event['city']}".lower()
    return all(word in hay for word in query.lower().split())


def _window(days, from_date, to_date):
    lo = from_date or str(date.today())
    hi = to_date or str(date.fromisoformat(lo) + timedelta(days=max(days, 1) - 1))
    return lo, hi


def search(query=None, city=None, venue=None, days=14,
           from_date=None, to_date=None, limit=20):
    """Events matching every given filter, soonest first."""
    doc = _events_for(city)
    lo, hi = _window(days, from_date, to_date)
    wanted = slugify(city) if city else ""
    rows = [e for e in doc["events"]
            if (e.get("end") or e["date"]) >= lo and e["date"] <= hi
            and (not wanted or slugify(e["city"]) == wanted)
            and _matches(e, query, venue)]
    out = {
        "window": {"from": lo, "to": hi},
        "matched": len(rows),
        "returned": min(len(rows), max(1, min(limit, MAX_LIMIT))),
        "events": [_slim(e) for e in rows[:max(1, min(limit, MAX_LIMIT))]],
        "feed": _feed_note(doc),
    }
    if city and not wanted in {slugify(c) for c in _cities()}:
        out["note"] = f"no city named {city!r} in the feed — call cities() for the list"
    if hi > str(date.today() + timedelta(days=DENSE_DAYS)):
        out["coverage"] = (f"past {DENSE_DAYS} days only venues with long agendas are "
                           "scraped, so a thin result there is missing data, not a quiet week")
    return out


def _slim(e):
    row = {k: e[k] for k in ("date", "time", "title", "venue", "city", "url") if e.get(k)}
    if e.get("status"):
        row["status"] = e["status"]
    if e.get("end"):
        row["end"] = e["end"]
    return row


def _cities():
    return {r["label"]: r["count"] for route, r in _routes().items()
            if route.startswith("city/") and route.count("/") == 1}


def cities():
    """Every city in the feed with its event count, busiest first."""
    counts = sorted(_cities().items(), key=lambda kv: -kv[1])
    return {"cities": [{"city": c, "events": n} for c, n in counts],
            "feed": _feed_note(_doc("routes.json"))}


def venues(city=None, query=None, limit=30):
    """Venue names as the feed spells them — what search(venue=…) matches on."""
    doc = _events_for(city)
    wanted = slugify(city) if city else ""
    counts = {}
    for e in doc["events"]:
        if wanted and slugify(e["city"]) != wanted:
            continue
        if query and query.lower() not in e["venue"].lower():
            continue
        if e["venue"]:
            counts[(e["venue"], e["city"])] = counts.get((e["venue"], e["city"]), 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:max(1, min(limit, MAX_LIMIT))]
    return {"venues": [{"venue": v, "city": c, "events": n} for (v, c), n in top],
            "distinct": len(counts), "feed": _feed_note(doc)}


# ------------------------------------------------------------------ MCP stdio

TOOLS = [
    {
        "name": "search",
        "description": (
            "Search upcoming concerts, club nights and festivals in the Netherlands. "
            "Returns date, time, title, venue, city, ticket status and a link, soonest "
            "first — no prices, no line-ups, no descriptions. Free and instant: it reads "
            "a pre-built feed, it does not visit venue sites. Defaults to the next 14 "
            "days nationwide; pass city for one place (call cities() for exact names), "
            "venue for one stage, query for words in the title. COVERAGE: dense for "
            "about six weeks, thin past three months, and 'status' is only set by the "
            "venue scrapers and can be up to 6 hours stale — confirm sold-out claims on "
            "the event url before stating them."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words that must all appear in title, venue or city"},
                "city": {"type": "string", "description": "Dutch city name, e.g. Amsterdam, Den Haag"},
                "venue": {"type": "string", "description": "Substring of the venue name, e.g. Paradiso"},
                "days": {"type": "integer", "description": "Window length in days from today (default 14)"},
                "from_date": {"type": "string", "description": "YYYY-MM-DD, defaults to today"},
                "to_date": {"type": "string", "description": "YYYY-MM-DD, overrides days"},
                "limit": {"type": "integer", "description": "Max events to return (default 20, max 100)"},
            },
        },
    },
    {
        "name": "cities",
        "description": (
            "Every city the feed covers, with how many upcoming events each has, busiest "
            "first. Call this when a city search comes back empty or the user names a "
            "place you are unsure of — city matching is exact on the name."),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "venues",
        "description": (
            "Venue names exactly as the feed spells them, with event counts, optionally "
            "narrowed to a city or a name fragment. Use it to turn a vague 'that place in "
            "Rotterdam' into the string search(venue=…) will match."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Only venues in this city"},
                "query": {"type": "string", "description": "Substring of the venue name"},
                "limit": {"type": "integer", "description": "Max venues to return (default 30)"},
            },
        },
    },
]
HANDLERS = {"search": search, "cities": cities, "venues": venues}


def _reply(rid, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    msg["error" if error else "result"] = error or result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        method, rid = req.get("method"), req.get("id")
        if method == "initialize":
            _reply(rid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "uitagenda", "version": "1.0.0"},
            })
        elif method == "tools/list":
            _reply(rid, {"tools": TOOLS})
        elif method == "tools/call":
            params = req.get("params", {})
            fn = HANDLERS.get(params.get("name"))
            if not fn:
                _reply(rid, error={"code": -32601, "message": f"no tool {params.get('name')!r}"})
                continue
            try:
                payload = fn(**params.get("arguments", {}))
            except (OSError, urllib.error.URLError, ValueError, TypeError, KeyError) as exc:
                # Correctable text, not an exception: a thrown error costs the whole turn.
                payload = {"error": f"{type(exc).__name__}: {exc}",
                           "hint": f"feed unreachable at {DATA_DIR} and {BASE_URL}"}
            _reply(rid, {"content": [{"type": "text",
                                      "text": json.dumps(payload, ensure_ascii=False)}]})
        elif rid is not None:
            _reply(rid, error={"code": -32601, "message": f"unknown method {method!r}"})


def selftest():
    assert slugify("Den Haag") == "den-haag"
    assert slugify("'s-Hertogenbosch") == "s-hertogenbosch"
    assert _window(7, None, None)[0] == str(date.today())
    assert _window(7, "2026-09-01", None) == ("2026-09-01", "2026-09-07")
    assert _window(7, "2026-09-01", "2026-12-01")[1] == "2026-12-01"
    ev = {"title": "Bokoesam", "venue": "Paradiso", "city": "Amsterdam"}
    assert _matches(ev, "bokoesam amsterdam", None)
    assert not _matches(ev, "bokoesam rotterdam", None)
    assert not _matches(ev, None, "melkweg")

    cs = cities()
    assert cs["cities"] and cs["cities"][0]["events"] > 0, cs
    assert "generated_at" in cs["feed"]
    top = cs["cities"][0]["city"]

    s = search(city=top, days=30, limit=5)
    assert s["events"], f"no events in {top} in 30 days"
    assert all(e["city"] == top for e in s["events"]), s["events"]
    assert s["returned"] <= 5 and s["matched"] >= s["returned"]
    assert search(city=top, days=30, limit=999)["returned"] <= MAX_LIMIT

    far = search(days=400, limit=1)
    assert "coverage" in far, "long windows must warn about thinning coverage"
    assert "note" in search(city="Bruxelles", days=7), "unknown city must say so"

    v = venues(city=top, limit=3)
    assert v["venues"] and v["venues"][0]["events"] > 0, v
    named = v["venues"][0]["venue"]
    assert search(venue=named, city=top, days=90, limit=3)["matched"] > 0, named
    print(f"selftest ok — {len(cs['cities'])} cities, {top} has {s['matched']} events "
          f"in 30 days, top venue {named}")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
