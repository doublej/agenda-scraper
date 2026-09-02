"""One golden test per source: the page as it was fetched, and what it parsed to.

Adding a source adds two files under tests/fixtures/ and nothing here — the
list is the directory. Capture them with

    uv run python loop/capture_fixture.py <name> <parser> <url> [venue]

which trims the page to the smallest snippet that still reproduces the parse.
"""

import json
from pathlib import Path

import pytest

from agenda_scraper.entities import resolve_city, resolve_venue
from agenda_scraper.scrape.cards import parse_cards
from agenda_scraper.scrape.parsers import parse_jsonld, parse_microdata
from agenda_scraper.scrape.sources import SOURCE_CITY, SOURCES

FIXTURES = Path(__file__).parent / "fixtures"
GOLDENS = sorted(FIXTURES.glob("*.expected.json"))

PARSERS = {
    "cards": lambda html, a: parse_cards(
        html, a.get("venue", ""), a.get("origin", ""), a.get("dates", "time")
    ),
    "jsonld": lambda html, a: parse_jsonld(html),
    "microdata": lambda html, a: parse_microdata(html),
}


def _golden(path: Path) -> tuple[str, dict, list]:
    doc = json.loads(path.read_text(encoding="utf8"))
    name = path.name.removesuffix(".expected.json")
    html = (FIXTURES / f"{name}.html").read_text(encoding="utf8")
    return name, doc, PARSERS[doc["parser"]](html, doc["args"])


def test_there_is_a_fixture_to_walk():
    """A directory that quietly emptied would make every test below vacuous."""
    assert GOLDENS, f"no *.expected.json in {FIXTURES}"


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.name.split(".")[0])
def test_a_saved_page_still_parses_to_its_golden(path):
    _, doc, got = _golden(path)
    assert got == doc["events"]


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.name.split(".")[0])
def test_a_parsed_event_carries_a_date_a_title_and_a_resolvable_venue(path):
    name, _, got = _golden(path)
    assert got, f"{name} parsed to nothing"
    city = SOURCE_CITY.get(name, "")
    for e in got:
        assert len(e["date"]) == 10 and e["date"][4] == "-", e
        assert e["title"].strip(), e
        assert resolve_venue(e["venue"], city)["id"], e
    assert resolve_city(city)["id"] or name not in SOURCE_CITY


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.name.split(".")[0])
def test_the_fixture_belongs_to_a_registered_source(path):
    assert path.name.split(".")[0] in SOURCES
