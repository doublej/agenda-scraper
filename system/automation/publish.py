#!/usr/bin/env python3
"""Health assessment, deduplication and the static route files.

The site is served by `python3 -m http.server`, which ignores query strings —
so filtering has to be baked into paths, not parameters. Every slice an agent
might ask for (a city, a source, a venue, the next week) is written as its own
JSON+TSV file at scrape time, and `routes.json` indexes the lot.
"""
import json
import re
import time
import unicodedata
from datetime import date, timedelta
from pathlib import Path

# Aggregators list the same night as the venue itself. Lower index wins, so a
# duplicate keeps the venue's own page (real ticket status, real detail URL).
SOURCE_RANK = ("paradiso", "tivoli", "dehelling", "ekko", "rotown", "musicon",
               "dbstudio", "muziekgieterij", "ra-nl", "podiuminfo", "festivalinfo")

WINDOWS = (("today", 1), ("week", 7), ("month", 31))
CITY_WINDOW = 7          # cities also get a week view; nothing finer is useful
CITY_WINDOW_MIN = 20     # ... but only where a week actually holds something
VENUE_MIN_EVENTS = 10    # below this a venue route is noise, not a route


def slugify(name):
    """"Den Haag" -> "den-haag". Stable enough to be part of a URL."""
    flat = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", flat.lower())).strip("-")


def _title_key(title):
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def dedupe(events):
    """Drop the aggregator's copy of an event a venue source already reported.

    Same day, same city, same title is the only claim confident enough to act
    on: promoters brand club nights differently per platform, so a looser key
    would merge events that are genuinely separate.
    """
    rank = {name: i for i, name in enumerate(SOURCE_RANK)}
    best = {}
    for e in events:
        key = (e["date"], e.get("city", ""), _title_key(e["title"]))
        if not key[1] or not key[2]:                  # unknown city or empty title
            best[id(e)] = e
            continue
        cur = best.get(key)
        if cur is None or rank.get(e["source"], 99) < rank.get(cur["source"], 99):
            best[key] = e
    return sorted(best.values(), key=lambda e: (e["date"], e["time"], e["title"]))


def current(events, today=None):
    """Events that have not finished yet; a multi-day festival stays until its end."""
    today = today or str(date.today())
    return [e for e in events if (e.get("end") or e["date"]) >= today]


FIELDS = ("source", "date", "end", "time", "title", "venue", "city", "status", "url")


def as_tsv(events):
    return "\n".join("\t".join(e.get(f, "") for f in FIELDS) for e in events)


def _window(events, days):
    lo = str(date.today())
    hi = str(date.today() + timedelta(days=days - 1))
    return [e for e in events if lo <= e["date"] <= hi]


def _group(events, key):
    out = {}
    for e in events:
        if e.get(key):
            out.setdefault(e[key], []).append(e)
    return out


def plan_routes(events):
    """Every slice worth its own URL, as (path, label, events)."""
    routes = [("all", "heel Nederland", events)]
    for name, days in WINDOWS:
        routes.append((name, f"heel Nederland, komende {days} dagen",
                       _window(events, days)))
    for city, rows in sorted(_group(events, "city").items()):
        routes.append((f"city/{slugify(city)}", city, rows))
        if len(rows) >= CITY_WINDOW_MIN:
            routes.append((f"city/{slugify(city)}/week", f"{city}, komende week",
                           _window(rows, CITY_WINDOW)))
    for source, rows in sorted(_group(events, "source").items()):
        routes.append((f"source/{source}", f"bron {source}", rows))
    for venue, rows in sorted(_group(events, "venue").items()):
        if len(rows) >= VENUE_MIN_EVENTS:
            routes.append((f"venue/{slugify(venue)}", venue, rows))
    return routes


def _write(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf8")
    tmp.replace(path)


def _prune(out_dir, keep):
    """Delete route files from earlier runs whose slice no longer exists."""
    for sub in ("city", "source", "venue"):
        for old in sorted((out_dir / sub).rglob("*")):
            if old.is_file() and old not in keep:
                old.unlink()


def write_routes(out_dir, events, envelope):
    """Write every route as JSON+TSV, plus routes.json. Returns the index."""
    out_dir, index, written = Path(out_dir), [], set()
    for path, label, rows in plan_routes(events):
        doc = {**envelope, "route": path, "label": label,
               "count": len(rows), "events": rows}
        for name, body in ((f"{path}.json", json.dumps(doc, ensure_ascii=False)),
                           (f"{path}.tsv", as_tsv(rows))):
            _write(out_dir / name, body)
            written.add(out_dir / name)
        index.append({"route": path, "label": label, "count": len(rows),
                      "json": f"/{path}.json", "tsv": f"/{path}.tsv"})
    _prune(out_dir, written)
    _write(out_dir / "routes.json",
           json.dumps({**envelope, "count": len(events), "routes": index},
                      ensure_ascii=False, indent=1))
    return index


def assess(report, history_path):
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
            hist[name] = (past + [r["count"]])[-7:]   # only good runs set the norm
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(hist, indent=1))
    return problems


def write_out(out_dir, events, report, history_path, log=print):
    """Atomic publish of the full feed plus every route. Non-zero when unhealthy."""
    out_dir = Path(out_dir)
    problems = assess(report, history_path)
    events = dedupe(current(events))
    envelope = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "healthy": not problems, "problems": problems}
    doc = {**envelope, "count": len(events), "sources": report, "events": events}
    for p in problems:
        log(f"# PROBLEM\t{p}")
    _write(out_dir / "events.json", json.dumps(doc, ensure_ascii=False, indent=1))
    _write(out_dir / "events.tsv", as_tsv(events))
    index = write_routes(out_dir, events, envelope)
    # One small file to poll: a monitor should not download the whole feed to
    # find out the timer stopped running.
    _write(out_dir / "health.json",
           json.dumps({**envelope, "count": len(events), "routes": len(index),
                       "sources": report}, ensure_ascii=False, indent=1))
    log(f"# wrote {len(events)} events and {len(index)} routes to {out_dir}")
    return 1 if problems else 0
