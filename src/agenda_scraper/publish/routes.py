"""The static route files: every slice worth a URL, plus the entity registries.

The site is served by `python3 -m http.server`, which ignores query strings —
so filtering has to be baked into paths, not parameters. Every slice an agent
might ask for (a city, a source, a venue, an artist, the next week) is written
as its own file at scrape time, and `routes.json` indexes the lot.
"""

import json
import time
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from agenda_scraper import Event, Report
from agenda_scraper.entities import (
    SCHEMA_VERSION,
    Artist,
    City,
    Venue,
    extract_artists,
    resolve_city,
    resolve_venue,
    slugify,
)
from agenda_scraper.publish.feed import (
    annotate,
    as_tsv,
    assess,
    current,
    dedupe,
    venue_id,
)

WINDOWS = (("today", 1), ("week", 7), ("month", 31))
CITY_WINDOW = 7  # cities also get a week view; nothing finer is useful
CITY_WINDOW_MIN = 20  # ... but only where a week actually holds something
VENUE_MIN_EVENTS = 10  # below this a venue route is noise, not a route
ARTIST_MIN_EVENTS = 5  # an artist route is only worth a file for a touring act


def _by_count(record: Mapping[str, Any]) -> tuple[int, str]:
    """Busiest first, then alphabetical — a registry is read top down."""
    return -int(record.get("count", 0)), str(record["name"]).lower()


def _window(events: list[Event], days: int) -> list[Event]:
    lo = str(date.today())
    hi = str(date.today() + timedelta(days=days - 1))
    return [e for e in events if lo <= e["date"] <= hi]


def _group(events: list[Event], key: str) -> dict[str, list[Event]]:
    out: dict[str, list[Event]] = {}
    for e in events:
        if e.get(key):
            out.setdefault(e[key], []).append(e)
    return out


def build_registries(
    events: list[Event],
) -> tuple[list[Venue], list[City], list[Artist]]:
    """Roll the published events up into the three entity registries.

    Names are re-derived rather than carried on the event rows: an event stays a
    flat dict of strings, so it can hold ids but not a nested artist record.
    """
    venues: dict[str, Venue] = {}
    cities: dict[str, City] = {}
    artists: dict[str, Artist] = {}
    for e in events:
        if e.get("venue"):
            v = resolve_venue(e["venue"], e.get("city", ""))
            hit = venues.setdefault(v["id"], {**v, "count": 0})
            hit["count"] = hit.get("count", 0) + 1
            if not hit["city"] and v["city"]:  # first source to name the city wins
                hit["city"], hit["city_id"] = v["city"], v["city_id"]
        if e.get("city"):
            c = resolve_city(e["city"])
            if c["id"]:
                seen_c = cities.setdefault(c["id"], {**c, "count": 0})
                seen_c["count"] = seen_c.get("count", 0) + 1
        for a in extract_artists(e.get("title", "")):
            seen_a = artists.setdefault(a["id"], {**a, "count": 0})
            seen_a["count"] = seen_a.get("count", 0) + 1
            if a["confidence"] == "high":  # the strongest sighting sets the field
                seen_a["confidence"] = "high"
    return (
        sorted(venues.values(), key=_by_count),
        sorted(cities.values(), key=_by_count),
        sorted(artists.values(), key=_by_count),
    )


def plan_routes(events: list[Event]) -> list[tuple[str, str, list[Event]]]:
    """Every slice worth its own URL, as (path, label, events)."""
    routes = [("all", "heel Nederland", events)]
    for name, days in WINDOWS:
        routes.append(
            (name, f"heel Nederland, komende {days} dagen", _window(events, days))
        )
    for city, rows in sorted(_group(events, "city").items()):
        routes.append((f"city/{slugify(city)}", city, rows))
        if len(rows) >= CITY_WINDOW_MIN:
            routes.append(
                (
                    f"city/{slugify(city)}/week",
                    f"{city}, komende week",
                    _window(rows, CITY_WINDOW),
                )
            )
    for source, rows in sorted(_group(events, "source").items()):
        routes.append((f"source/{source}", f"bron {source}", rows))
    # Venue routes stay keyed on the label a source published, not on venue_id:
    # re-keying them would rename URLs that already exist. Two labels can still
    # slugify to one path ("MEZZ" and "Mezz"), so merge them first — otherwise
    # routes.json advertises the route twice and the one file on disk answers
    # for whichever label was written last.
    merged: dict[str, tuple[str, list[Event]]] = {}
    for venue, rows in sorted(_group(events, "venue").items()):
        label, seen_rows = merged.get(slugify(venue), (venue, []))
        merged[slugify(venue)] = (label, seen_rows + rows)
    for slug, (label, rows) in sorted(merged.items()):
        if len(rows) >= VENUE_MIN_EVENTS:
            routes.append((f"venue/{slug}", label, rows))
    routes += _artist_routes(events)
    return routes


def _artist_routes(events: list[Event]) -> list[tuple[str, str, list[Event]]]:
    """One route per act with enough dates to be worth following."""
    names = {a["id"]: a["name"] for e in events for a in extract_artists(e["title"])}
    by_artist: dict[str, list[Event]] = {}
    for e in events:
        for aid in filter(None, e.get("artist_ids", "").split(",")):
            by_artist.setdefault(aid, []).append(e)
    return [
        (f"artist/{aid}", names.get(aid, aid), rows)
        for aid, rows in sorted(by_artist.items())
        if len(rows) >= ARTIST_MIN_EVENTS
    ]


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf8")
    tmp.replace(path)


def _prune(out_dir: Path, keep: set[Path]) -> None:
    """Delete route files from earlier runs whose slice no longer exists."""
    for sub in ("city", "source", "venue", "artist"):
        for old in sorted((out_dir / sub).rglob("*")):
            if old.is_file() and old not in keep:
                old.unlink()


def write_registries(out_dir: Path, events: list[Event], envelope: dict) -> list[dict]:
    """Write venues.json, cities.json and artists.json. Returns index entries."""
    venues, cities, artists = build_registries(events)
    # The registry key doubles as the file name, so a reader can tell a registry
    # from an event route without parsing the path.
    registries: list[tuple[str, list[Any]]] = [
        ("venues", list(venues)),
        ("cities", list(cities)),
        ("artists", list(artists)),
    ]
    index = []
    for name, records in registries:
        doc = {**envelope, "route": name, "label": name, "count": len(records)}
        doc[name] = records
        _write(out_dir / f"{name}.json", json.dumps(doc, ensure_ascii=False))
        index.append(
            {
                "route": name,
                "label": name,
                "count": len(records),
                "json": f"/{name}.json",
                "tsv": "",
            }
        )
    return index


def write_routes(out_dir: Path, events: list[Event], envelope: dict) -> list[dict]:
    """Write every route as JSON+TSV, plus the registries and routes.json."""
    out_dir = Path(out_dir)
    index: list[dict] = []
    written: set[Path] = set()
    for path, label, rows in plan_routes(events):
        doc = {
            **envelope,
            "route": path,
            "label": label,
            "count": len(rows),
            "events": rows,
        }
        for name, body in (
            (f"{path}.json", json.dumps(doc, ensure_ascii=False)),
            (f"{path}.tsv", as_tsv(rows)),
        ):
            _write(out_dir / name, body)
            written.add(out_dir / name)
        index.append(
            {
                "route": path,
                "label": label,
                "count": len(rows),
                "json": f"/{path}.json",
                "tsv": f"/{path}.tsv",
            }
        )
    _prune(out_dir, written)
    index += write_registries(out_dir, events, envelope)
    _write(
        out_dir / "routes.json",
        json.dumps(
            {**envelope, "count": len(events), "routes": index},
            ensure_ascii=False,
            indent=1,
        ),
    )
    return index


def write_out(
    out_dir: Path,
    events: list[Event],
    report: Report,
    history_path: Path,
    log: Callable[[str], None] = print,
) -> int:
    """Atomic publish of the full feed plus every route. Non-zero when unhealthy."""
    out_dir = Path(out_dir)
    problems = assess(report, history_path)
    events = dedupe(current(annotate(events)))
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "healthy": not problems,
        "problems": problems,
    }
    doc = {**envelope, "count": len(events), "sources": report, "events": events}
    for p in problems:
        log(f"# PROBLEM\t{p}")
    _write(out_dir / "events.json", json.dumps(doc, ensure_ascii=False, indent=1))
    _write(out_dir / "events.tsv", as_tsv(events))
    index = write_routes(out_dir, events, envelope)
    # One small file to poll: a monitor should not download the whole feed to
    # find out the timer stopped running.
    _write(
        out_dir / "health.json",
        json.dumps(
            {
                **envelope,
                "count": len(events),
                "routes": len(index),
                "sources": report,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )
    log(f"# wrote {len(events)} events and {len(index)} routes to {out_dir}")
    return 1 if problems else 0


__all__ = ["build_registries", "plan_routes", "venue_id", "write_out", "write_routes"]
