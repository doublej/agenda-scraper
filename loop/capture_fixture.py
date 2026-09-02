"""Capture a source's page as the smallest snippet that still reproduces the parse.

    uv run python loop/capture_fixture.py <name> <parser> <url> [venue]

Writes tests/fixtures/<name>.html and <name>.expected.json. The snippet keeps
the first few cards and nothing else, so a fixture stays a few kB and a diff on
it is readable.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agenda_scraper.scrape.http import get
from agenda_scraper.scrape.parsers import parse_jsonld, parse_time_cards

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
CARDS = 3
LEAD = 3000  # bytes kept before the first <time>, so its card stays whole


def trim(html: str, parser: str) -> str:
    if parser == "jsonld":
        blocks = re.findall(
            r'<script type="application/ld\+json"[^>]*>.*?</script>', html, re.DOTALL
        )
        return "\n".join(blocks)
    marks = [m.start() for m in re.finditer(r"<time[^>]*\bdatetime=", html)]
    if not marks:
        return html
    # The head of a page is 40 kB of nav and inline CSS the parser never reads.
    # Keep a run-up so the first card's own anchor and heading survive the cut.
    start = max(0, marks[0] - LEAD)
    end = marks[CARDS] if len(marks) > CARDS else len(html)
    return html[start:end]


def main() -> None:
    name, parser, url = sys.argv[1], sys.argv[2], sys.argv[3]
    venue = sys.argv[4] if len(sys.argv) > 4 else ""
    snippet = trim(get(url), parser)
    args = {"venue": venue, "origin": url}
    events = (
        parse_time_cards(snippet, venue, url)
        if parser == "time_cards"
        else parse_jsonld(snippet)
    )
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
