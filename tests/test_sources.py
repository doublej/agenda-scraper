"""One golden test per source: the page as it was fetched, and what it parsed to.

Adding a source adds two files under tests/fixtures/ and nothing here — the
list is the directory. Capture them with

    uv run python loop/capture_fixture.py <name> <parser> <url> [venue] [dates] [links]

which trims the page to the smallest snippet that still reproduces the parse.
"""

import json
import re
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
        html,
        a.get("venue", ""),
        a.get("origin", ""),
        a.get("dates", "time"),
        a.get("links", "before"),
    ),
    "jsonld": lambda html, a: parse_jsonld(html),
    "microdata": lambda html, a: parse_microdata(html),
}


def _words(text: str) -> set[str]:
    """The words long enough to tie a URL slug to the title it came from."""
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) >= 4}


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
        # A relative href joined onto the listing path instead of the host gave
        # /agenda/agenda/<slug> on two sites, so every link 404'd.
        assert e["url"].startswith("https://"), e
        segments = [s for s in e["url"].split("/")[3:] if s]
        assert len(segments) < 2 or segments[0] != segments[1], e
    assert resolve_city(city)["id"] or name not in SOURCE_CITY


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.name.split(".")[0])
def test_an_event_links_to_itself_and_not_to_the_card_above_it(path):
    """The defect a golden cannot catch, because a golden records it as correct.

    Reading each card's <a> backwards is right for the eleven listings that
    wrap the card in a link and wrong for the three that end the card with one:
    there, every event got the previous card's URL. Neushoorn had 0 of 103
    right, and the fixtures captured from that parser asserted the shifted URLs
    were the expected output. `url` is one of the nine legacy keys, so this is
    published, deduplicated and served. Compare the link against its own title
    and against its neighbour's: the shift inverts the two.
    """
    name, _, got = _golden(path)
    own = neighbour = 0
    for i, e in enumerate(got):
        link = _words(e["url"])
        if link & _words(e["title"]):
            own += 1
        elif i and link & _words(got[i - 1]["title"]):
            neighbour += 1
    # Opaque links (Vera's ?p=152958, Neushoorn's stager ids) score 0 both ways
    # and cannot be judged here; only a genuine inversion fails.
    assert neighbour <= own, (
        f"{name}: {neighbour} of {len(got)} links match the previous card's "
        f"title and only {own} match their own — the card's <a> is being read "
        f"from the wrong side (see LINKS_AFTER in scrape/cards.py)"
    )


@pytest.mark.parametrize("path", GOLDENS, ids=lambda p: p.name.split(".")[0])
def test_the_fixture_belongs_to_a_registered_source(path):
    assert path.name.split(".")[0] in SOURCES
