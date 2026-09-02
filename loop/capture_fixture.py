"""Capture a source's page as the smallest snippet that still reproduces the parse.

    uv run python loop/capture_fixture.py <name> <parser> <url> [venue] [dates] [links]

Writes tests/fixtures/<name>.html and <name>.expected.json. The snippet keeps
the first few cards and nothing else, so a fixture stays a few kB and a diff on
it is readable.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agenda_scraper.scrape.cards import parse_cards
from agenda_scraper.scrape.http import get
from agenda_scraper.scrape.parsers import parse_jsonld, parse_microdata

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CARDS = 6  # enough rows that a URL-attribution slip shows up as a pattern
LEAD = 3000  # bytes kept before the first <time>, so its card stays whole


MARKS = {
    "time": r"<time[^>]*\bdatetime=",
    "dutch": r"\b\d{1,2}\s+(?:jan|feb|mrt|maa|apr|mei|jun|jul|aug|sep|okt|nov|dec)",
    "slug": r'href="[^"]*-\d{1,2}-(?:jan|feb|mrt|apr|mei|jun|jul|aug|sep|okt|nov|dec)',
    "microdata": r'itemtype="https?://schema\.org/(?:Music|Dance|Social)?Event"',
}


def trim(
    html: str, parser: str, dates: str, venue: str, url: str, links: str = "before"
) -> str:
    """The smallest window that still parses to a full set of cards.

    Cutting at the first date on the page is not enough: a footer copyright or
    a news teaser can hold the first few, and the snippet then parses to
    nothing. So walk the dates and keep the first window that actually yields
    cards — a fixture that parses to zero events tests nothing.
    """
    if parser == "microdata":
        marks = [m.start() for m in re.finditer(MARKS["microdata"], html)]
        return html[marks[0] : marks[CARDS + 1]] if len(marks) > CARDS else html
    if parser == "jsonld":
        blocks = re.findall(
            r'<script type="application/ld\+json"[^>]*>.*?</script>', html, re.DOTALL
        )
        return "\n".join(blocks)
    marks = [m.start() for m in re.finditer(MARKS[dates], html, re.IGNORECASE)]
    if len(marks) <= CARDS:
        return html
    # Smallest window, not the first: on a page whose dates are far apart the
    # first hit can be 178kB, and a fixture nobody can read in a diff is a
    # fixture nobody checks. Settle for fewer cards before keeping a whole page.
    for want in range(CARDS, 2, -1):
        found = [
            snippet
            for i in range(len(marks) - want)
            if len(
                parse_cards(
                    (snippet := html[max(0, marks[i] - LEAD) : marks[i + want]]),
                    venue,
                    url,
                    dates,
                    links,
                )
            )
            >= want
        ]
        if found:
            return min(found, key=len)
    return html


def main() -> None:
    name, parser, url = sys.argv[1], sys.argv[2], sys.argv[3]
    venue = sys.argv[4] if len(sys.argv) > 4 else ""
    dates = sys.argv[5] if len(sys.argv) > 5 else "time"
    links = sys.argv[6] if len(sys.argv) > 6 else "before"
    snippet = trim(get(url), parser, dates, venue, url, links)
    args = {"venue": venue, "origin": url, "dates": dates, "links": links}
    events = {
        "cards": lambda: parse_cards(snippet, venue, url, dates, links),
        "microdata": lambda: parse_microdata(snippet),
        "jsonld": lambda: parse_jsonld(snippet),
    }[parser]()
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.html").write_text(snippet, encoding="utf8")
    (FIXTURES / f"{name}.expected.json").write_text(
        json.dumps(
            {"parser": parser, "args": args, "events": events},
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf8",
    )
    print(f"{name}: {len(snippet)} bytes, {len(events)} events")


if __name__ == "__main__":
    main()
