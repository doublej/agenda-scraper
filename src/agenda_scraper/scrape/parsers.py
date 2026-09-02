"""Pure HTML → events. No network, no browser, so every one of these is testable.

Regex rather than a DOM parser on purpose: each site is matched on exactly one
stable landmark (a JSON-LD block, a dated URL slug, a day heading), which
survives the markup reshuffles that break selector-based scrapers.
"""

import json
import re
from datetime import date

from agenda_scraper import Event

MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip
MONTHS = {m: i + 1 for i, m in enumerate(MONTH_NAMES)}


def unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&#8217;", "’")
        .replace("&quot;", '"')
        .replace("&#039;", "'")
        .strip()
    )


def _as_dict(value: object) -> dict:
    """Sites nest location and address as a dict, a string, or not at all."""
    return value if isinstance(value, dict) else {}


def jsonld_nodes(html: str) -> list[dict]:
    """Every dict in every ld+json block, with @graph and ItemList flattened."""
    out = []
    for block in re.findall(
        r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL
    ):
        try:
            doc = json.loads(block)
        except ValueError:
            continue
        stack = list(doc) if isinstance(doc, list) else [doc]
        while stack:
            node = stack.pop(0)
            if not isinstance(node, dict):
                continue
            if node.get("@type") == "ListItem":
                stack.insert(0, node.get("item") or {})
                continue
            out.append(node)
            for key in ("@graph", "itemListElement"):
                stack = list(node.get(key) or []) + stack
    return out


def parse_jsonld(html: str) -> list[Event]:
    """schema.org Event/Festival nodes, whatever shape the site nests them in."""
    out = []
    for node in jsonld_nodes(html):
        if not re.search(r"Event|Festival", str(node.get("@type", ""))):
            continue
        start = (node.get("startDate") or "")[:16].replace("T", " ")
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", start[:10]):
            continue  # unrendered template placeholders, e.g. "{{ date }}"
        end = (node.get("endDate") or "")[:10]
        loc = _as_dict(node.get("location"))
        addr = _as_dict(loc.get("address"))
        out.append(
            {
                "date": start[:10],
                "end": end if end > start[:10] else "",
                "time": start[11:16],
                "title": unescape(node.get("name", "")),
                "venue": unescape(loc.get("name", "")),
                "city": addr.get("addressLocality", "").strip(),
                "country": addr.get("addressCountry", ""),
                "url": node.get("url", ""),
            }
        )
    return [e for e in out if e["title"]]


def parse_tivoli(html: str) -> list[Event]:
    """Tivoli encodes the date in the slug: /agenda/<id>/<slug>-<dd-mm-yyyy>."""
    seen, out = set(), []
    for m in re.finditer(
        r'href="[^"]*?/agenda/(\d+)/([a-z0-9-]+?)-(\d{2})-(\d{2})-(\d{4})"', html
    ):
        eid, slug, d, mo, y = m.groups()
        if eid in seen:
            continue
        seen.add(eid)
        out.append(
            {
                "date": f"{y}-{mo}-{d}",
                "time": "",
                "title": slug.replace("-", " ").strip(),
                "venue": "TivoliVredenburg",
                "url": f"https://www.tivolivredenburg.nl/agenda/{eid}/{slug}-{d}-{mo}-{y}",
            }
        )
    return sorted(out, key=lambda e: e["date"])


_PARADISO = re.compile(
    r">(?:Mo|Tu|We|Th|Fr|Sa|Su)\s+(\d{1,2})\s+([A-Z][a-z]{2})<"
    r'|<a[^>]+href="(/(?:programma|en/program)/[a-z0-9-]+/\d+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)


def parse_paradiso(html: str, start_year: int | None = None) -> list[Event]:
    """Day headings ("Su 15 Nov") precede each group of event anchors."""
    year = start_year or date.today().year
    cur, prev_month, seen, out = None, 0, set(), []
    for m in _PARADISO.finditer(html):
        if m.group(1):
            month = MONTHS[m.group(2)]
            if month < prev_month:
                year += 1
            prev_month = month
            cur = f"{year}-{month:02d}-{int(m.group(1)):02d}"
        elif m.group(3) and cur:
            parts = [
                p.strip()
                for p in re.sub(r"<[^>]+>", "|", m.group(4)).split("|")
                if p.strip()
            ]
            if not parts:
                continue
            title = unescape(parts[0])
            if (cur, title) in seen:
                continue
            seen.add((cur, title))
            # The card's last slot holds either a start time or a status badge —
            # "Sold out", "Postponed". Those events genuinely have no time shown.
            tail = parts[-1] if len(parts) > 1 else ""  # never the title itself
            clock = re.search(r"\b([0-2]?\d:[0-5]\d)\b", tail)
            out.append(
                {
                    "date": cur,
                    "time": clock.group(1) if clock else "",
                    "status": "" if clock else unescape(tail)[:20],
                    "title": title,
                    "venue": "Paradiso",
                    "url": "https://www.paradiso.nl" + m.group(3),
                }
            )
    return out


# The one landmark a modern Dutch venue site does still publish: <time datetime>.
# None of them serve schema.org, but the semantic element is in every listing
# template, and the heading next to it is the act.
_TIME = re.compile(r'<time[^>]*\bdatetime="(20\d\d-\d\d-\d\d)(?:T(\d\d:\d\d))?[^"]*"')
_HEADING = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.DOTALL)
_ANCHOR = re.compile(r'<a[^>]+href="([^"#]+)"')
# Spot runs two buildings off one listing and says which on the card itself.
_LOCATION = re.compile(r'data-location="([^"]+)"')
_TAGS = re.compile(r"<[^>]+>")
NEAR = 3000  # a heading further than this from its <time> belongs to another card


def _last_before(items: list[tuple[int, str]], pos: int, default: str) -> str:
    """The last value whose match started before `pos` — the card's own attribute."""
    found = default
    for start, value in items:
        if start > pos:
            break
        found = value
    return found


def _heading_text(inner: str) -> str:
    """The act, not the support act: everything before the first nested tag."""
    lead = inner.split("<", 1)[0].strip()
    return unescape(lead or _TAGS.sub(" ", inner))


def parse_time_cards(html: str, venue: str = "", origin: str = "") -> list[Event]:
    """Pair every <time datetime> with the heading nearest to it.

    Listings put the date before the title (013) or after it (Spot, Victorie),
    so position, not order, decides which heading belongs to which date. Each
    heading is claimed once, nearest date first, which keeps the pairing stable
    when a card is missing one of the two.
    """
    times = [(m.start(), m.group(1), m.group(2) or "") for m in _TIME.finditer(html)]
    heads = [
        (m.start(), text)
        for m in _HEADING.finditer(html)
        if (text := _heading_text(m.group(1)))
    ]
    anchors = [(m.start(), m.group(1)) for m in _ANCHOR.finditer(html)]
    rooms = [(m.start(), m.group(1)) for m in _LOCATION.finditer(html)]
    pairs = sorted(
        ((abs(tp - hp), tp, hp) for tp, _, _ in times for hp, _ in heads),
        key=lambda x: x[:2],
    )
    taken_h: set[int] = set()
    chosen: dict[int, int] = {}
    for gap, tp, hp in pairs:
        if gap > NEAR or tp in chosen or hp in taken_h:
            continue
        chosen[tp] = hp
        taken_h.add(hp)

    by_pos = dict(heads)
    out = []
    for pos, day, clock in times:
        head_pos = chosen.get(pos)
        if head_pos is None:
            continue
        opened = min(pos, head_pos)
        url = _last_before(anchors, opened, "")
        room = _last_before(rooms, opened, "")
        out.append(
            {
                "date": day,
                "time": clock,
                "title": by_pos[head_pos],
                "venue": room.replace("-", " ").title() if room else venue,
                "url": url if url.startswith("http") else origin.rstrip("/") + url,
            }
        )
    return sorted(out, key=lambda e: (e["date"], e["title"]))
