"""Run the sources and normalise what they return."""

import sys

from agenda_scraper import Event, Report
from agenda_scraper.scrape.sources import CITY_ALIAS, SOURCE_CITY, SOURCES

__all__ = ["SOURCES", "collect"]


def collect(names: list[str]) -> tuple[list[Event], Report]:
    """Run each source, keeping going when one fails. Returns (events, report)."""
    events: list[Event] = []
    report: Report = {}
    for name in names:
        try:
            rows = SOURCES[name]()
        except Exception as exc:  # noqa: BLE001 — one bad source must not kill the run
            report[name] = {"ok": False, "count": 0, "error": str(exc)}
            print(f"# {name}\tFAILED\t{exc}", file=sys.stderr)
            continue
        for e in rows:
            e["source"] = name
            e.setdefault("status", "")
            e.setdefault("end", "")
            e.pop("country", None)  # every published event is Dutch
            city = e.get("city") or SOURCE_CITY.get(name, "")
            e["city"] = CITY_ALIAS.get(city, city)
        events += rows
        report[name] = {"ok": True, "count": len(rows)}
        print(f"# {name}\t{len(rows)} events", file=sys.stderr)
    events.sort(key=lambda e: (e["date"], e["time"], e["title"]))
    return events, report
