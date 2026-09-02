"""Listings whose only structure is a date sitting next to a heading.

No Dutch venue site publishes schema.org, none run The Events Calendar, and
none serve an iCal feed — a 40-site sweep in loop/ has the counts; only the
three nationwide aggregators carry structured data. What their templates do emit is a date: an HTML5 <time datetime>, a
Dutch date spelt out in the card, or a date baked into the event's own URL.
Pair that with the nearest heading and you have the event.
"""

import re
from bisect import bisect_left, bisect_right
from datetime import date, timedelta
from urllib.parse import urljoin

from agenda_scraper import Event
from agenda_scraper.scrape.parsers import unescape

# The landmarks a modern Dutch venue site does still publish. None of them serve
# schema.org, so a listing is read as cards: a date, and the heading next to it.
_TIME = re.compile(r'<time[^>]*\bdatetime="(20\d\d-\d\d-\d\d)(?:T(\d\d:\d\d))?[^"]*"')
_HEADING = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.DOTALL)
_ANCHOR = re.compile(r'<a[^>]+href="([^"#]+)"')
# Spot runs three buildings off one listing and says which on the card itself.
_LOCATION = re.compile(r'data-location="([^"]+)"')
_CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
_TAGS = re.compile(r"<[^>]+>")
# Gebr. de Nobel repeats the day as an <h3> above each group. A heading that is
# only a date names no act, and left in it wins the pairing over the real title.
_DATE_HEADING = re.compile(
    r"^(?:[a-z]{2,9}\.?,?\s+)?\d{0,2}\s*(?:jan|feb|mrt|maa|apr|mei|jun|jul|aug|"
    r"sep|okt|oct|nov|dec)[a-z]*\.?(?:\s+20\d\d)?$",
    re.IGNORECASE,
)

NL_MONTHS = {
    "jan": 1, "feb": 2, "mrt": 3, "maa": 3, "apr": 4, "mei": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_NL_DATE = re.compile(
    r"\b(\d{1,2})\s+(jan|feb|mrt|maa|apr|mei|jun|jul|aug|sep|okt|oct|nov|dec)"
    r"[a-z]*\.?(?:\s+(20\d\d))?\b",
    re.IGNORECASE,
)
# Gebr. de Nobel dates the slug and nothing else: /agenda/swingo-02-sep-2026.
# Its <time datetime> is the post's publish date, which is a different day.
_SLUG_DATE = re.compile(
    r'href="[^"]*-(\d{1,2})-(jan|feb|mrt|maa|apr|mei|jun|jul|aug|sep|okt|oct|nov|dec)'
    r'[a-z]*-(20\d\d)"',
    re.IGNORECASE,
)

NEAR = 3000  # a heading further than this from its date belongs to another card
CLOCK_NEAR = 400  # ... and a time further than this is somebody else's start


def _heading_text(inner: str) -> str:
    """The act, not the support act: everything before the first nested tag."""
    lead = inner.split("<", 1)[0].strip()
    return unescape(lead or _TAGS.sub(" ", inner))


def _in_text(html: str, pos: int, back: int = 300) -> bool:
    """True when `pos` sits in visible text rather than inside a tag.

    "15:01" out of datetime="2026-02-24T07:15:01+0100" is a publish timestamp,
    and Gebr. de Nobel published 46 of those as door times before this check.
    """
    seg = html[max(0, pos - back) : pos]
    return seg.rfind(">") >= seg.rfind("<")


def _last_before(items: list[tuple[int, str]], pos: int) -> str:
    """The card's own attribute: the last value that started at or before `pos`."""
    i = bisect_right(items, (pos, "\uffff")) - 1
    return items[i][1] if i >= 0 else ""


def _first_after(items: list[tuple[int, str]], pos: int, within: int) -> str:
    """The first value starting within `within` characters after `pos`."""
    i = bisect_left(items, (pos, ""))
    return items[i][1] if i < len(items) and items[i][0] - pos <= within else ""


def _iso_dates(html: str) -> list[tuple[int, str, str]]:
    return [(m.start(), m.group(1), m.group(2) or "") for m in _TIME.finditer(html)]


BACK = 40  # days a listing may still show behind today
AHEAD = 400  # ... and how far ahead a bare "3 jan" can plausibly mean


def _fill_year(month: int, day: int, today: date) -> str:
    """The year that puts a bare "3 jan" inside the window a listing can cover.

    Reading the year off the order of the page is what breaks on a nav block or
    a footer: one stray month earlier than the rest and every date after it
    jumps a year. A window does not care what order the page is in.
    """
    for year in (today.year, today.year + 1, today.year - 1):
        try:
            when = date(year, month, day)
        except ValueError:
            continue
        if today - timedelta(days=BACK) <= when <= today + timedelta(days=AHEAD):
            return str(when)
    return ""


def _written_dates(pattern: re.Pattern[str], text: str) -> list[tuple[int, str, str]]:
    """Dates spelt out in Dutch, with the year filled in when the page omits it."""
    today = date.today()
    out = []
    for m in pattern.finditer(text):
        day, name, spelt = int(m.group(1)), m.group(2).lower(), m.group(3)
        month = NL_MONTHS[name[:3]]
        when = (
            f"{spelt}-{month:02d}-{day:02d}" if spelt else _fill_year(month, day, today)
        )
        if when:
            out.append((m.start(), when, ""))
    return out


def parse_cards(
    html: str, venue: str = "", origin: str = "", dates: str = "time"
) -> list[Event]:
    """Pair every date on a listing page with the heading nearest to it.

    `dates` picks where the date comes from: "time" for <time datetime>,
    "dutch" for a written-out date in the card, "slug" for a date baked into
    the event's own URL. Listings put the date before the title (013) or after
    it (Spot, Victorie), so position, not order, decides which heading belongs
    to which date, and each heading is claimed once, nearest date first.
    """
    if dates == "time":
        found = _iso_dates(html)
    elif dates == "dutch":
        found = _written_dates(_NL_DATE, html)
    else:
        found = _written_dates(_SLUG_DATE, html)
    heads = [
        (m.start(), text)
        for m in _HEADING.finditer(html)
        if (text := _heading_text(m.group(1))) and not _DATE_HEADING.match(text)
    ]
    anchors = [(m.start(), m.group(1)) for m in _ANCHOR.finditer(html)]
    rooms = [(m.start(), m.group(1)) for m in _LOCATION.finditer(html)]
    clocks = [
        (m.start(), m.group(0))
        for m in _CLOCK.finditer(html)
        if _in_text(html, m.start())
    ]

    # Only headings within NEAR of a date can win it, and both lists are already
    # in document order — so bisect the window instead of building the full cross
    # product. A 5000-card page took 37 seconds that way; it takes 0.3 now.
    head_at = [hp for hp, _ in heads]
    pairs = [
        (abs(dp - head_at[i]), dp, head_at[i])
        for dp, _, _ in found
        for i in range(
            bisect_left(head_at, dp - NEAR), bisect_right(head_at, dp + NEAR)
        )
    ]
    pairs.sort(key=lambda x: x[:2])
    taken_h: set[int] = set()
    chosen: dict[int, int] = {}
    for gap, dp, hp in pairs:
        if gap > NEAR or dp in chosen or hp in taken_h:
            continue
        chosen[dp] = hp
        taken_h.add(hp)

    by_pos = dict(heads)
    seen: set[tuple[str, str]] = set()
    out = []
    for pos, day, clock in found:
        head_pos = chosen.get(pos)
        if head_pos is None:
            continue
        title = by_pos[head_pos]
        if (day, title) in seen:
            continue
        seen.add((day, title))
        opened = min(pos, head_pos)
        url = _last_before(anchors, opened)
        room = _last_before(rooms, opened)
        out.append(
            {
                "date": day,
                "time": clock or _first_after(clocks, pos, CLOCK_NEAR),
                "title": title,
                "venue": room.replace("-", " ").title() if room else venue,
                # urljoin, not concatenation: `origin` is the listing page, so
                # "/agenda/x" off /agenda gave /agenda/agenda/x on two sites.
                "url": urljoin(origin, url),
            }
        )
    return sorted(out, key=lambda e: (e["date"], e["title"]))


# Venues whose listing is only a date next to a heading — the tier that is left
# once schema.org, The Events Calendar, iCal and the ticketing platforms are
# gone. One line each: where to read it, what to call the room, which city, and
# where the date is written. Every one of these was checked against its own
# robots.txt; the ticketing platform they mostly share, stager.co, forbids
# crawling outright, which is why the venue's own page is what gets fetched.
CARD_SOURCES = {
    # name: (url, venue, city, date source)
    "013": ("https://www.013.nl/programma", "013", "Tilburg", "time"),
    "spot": ("https://www.spotgroningen.nl/programma/", "", "Groningen", "time"),
    "victorie": (
        "https://www.podiumvictorie.nl/programma/",
        "Victorie",
        "Alkmaar",
        "time",
    ),
    "gebrdenobel": (
        "https://www.gebrdenobel.nl/agenda",
        "Gebr. de Nobel",
        "Leiden",
        "slug",
    ),
    "gigant": ("https://www.gigant.nl/concerten/", "Gigant", "Apeldoorn", "dutch"),
    "annabel": ("https://www.annabel.nu/agenda", "Annabel", "Rotterdam", "dutch"),
    "melkweg": ("https://www.melkweg.nl/nl/agenda/", "Melkweg", "Amsterdam", "dutch"),
    "effenaar": ("https://www.effenaar.nl/agenda", "Effenaar", "Eindhoven", "dutch"),
    "patronaat": (
        "https://www.patronaat.nl/programma/",
        "Patronaat",
        "Haarlem",
        "dutch",
    ),
    "hedon": ("https://www.hedon-zwolle.nl/", "Hedon", "Zwolle", "dutch"),
    "neushoorn": (
        "https://www.neushoorn.nl/programma",
        "Neushoorn",
        "Leeuwarden",
        "dutch",
    ),
    "burgerweeshuis": (
        "https://www.burgerweeshuis.nl/",
        "Burgerweeshuis",
        "Deventer",
        "dutch",
    ),
    "vera": ("https://www.vera-groningen.nl/programma/", "Vera", "Groningen", "dutch"),
    "afaslive": ("https://www.afaslive.nl/agenda", "AFAS Live", "Amsterdam", "dutch"),
}
