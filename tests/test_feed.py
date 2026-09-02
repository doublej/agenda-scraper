"""The MCP server's query helpers, plus one live check against the real feed."""

import os
from datetime import date

import pytest

from agenda_scraper.mcp_server import (
    MAX_LIMIT,
    _matches,
    _window,
    cities,
    search,
    venues,
)

live = pytest.mark.skipif(
    not os.environ.get("AGENDA_LIVE"),
    reason="set AGENDA_LIVE=1 to hit the published feed",
)


def test_window_defaults_to_today_and_honours_both_ends():
    assert _window(7, None, None)[0] == str(date.today())
    assert _window(7, "2026-09-01", None) == ("2026-09-01", "2026-09-07")
    assert _window(7, "2026-09-01", "2026-12-01")[1] == "2026-12-01"


def test_matches_needs_every_word_and_a_venue_substring():
    ev = {"title": "Bokoesam", "venue": "Paradiso", "city": "Amsterdam"}
    assert _matches(ev, "bokoesam amsterdam", None)
    assert not _matches(ev, "bokoesam rotterdam", None)
    assert not _matches(ev, None, "melkweg")


@live
def test_the_published_feed_answers_a_real_question():
    cs = cities()
    assert cs["cities"] and cs["cities"][0]["events"] > 0
    assert "generated_at" in cs["feed"]
    top = cs["cities"][0]["city"]

    found = search(city=top, days=30, limit=5)
    assert found["events"], f"no events in {top} in 30 days"
    assert all(e["city"] == top for e in found["events"])
    assert found["returned"] <= 5 <= found["matched"]
    assert search(city=top, days=30, limit=999)["returned"] <= MAX_LIMIT

    assert "coverage" in search(days=400, limit=1), "long windows must warn"
    assert "note" in search(city="Bruxelles", days=7), "unknown city must say so"

    v = venues(city=top, limit=3)
    assert v["venues"] and v["venues"][0]["events"] > 0
    named = v["venues"][0]["venue"]
    assert search(venue=named, city=top, days=90, limit=3)["matched"] > 0
