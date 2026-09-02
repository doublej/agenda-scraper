"""Pure HTML → events. No network, no browser, so every one of these is testable.

Regex rather than a DOM parser on purpose: each site is matched on exactly one
stable landmark (a JSON-LD block, a dated URL slug, a day heading), which
survives the markup reshuffles that break selector-based scrapers.
"""

import html as html_entities
import json
import re
from datetime import date, timedelta

from agenda_scraper import Event

MONTH_NAMES = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip
MONTHS = {m: i + 1 for i, m in enumerate(MONTH_NAMES)}


def unescape(s: str) -> str:
    """Every HTML entity, not the four we happened to hit first."""
    return html_entities.unescape(s).strip()


_TAGS_ONLY = re.compile(r"<[^>]+>")


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


# Partyflock publishes schema.org too, as microdata rather than a JSON-LD block:
# every row is an itemscope with startDate, url, name, venue and city on it.
_MICRO_SPLIT = re.compile(
    r'itemtype="https?://schema\.org/(?:Music|Dance|Social)?Event"'
)
_MICRO_PROP = r'itemprop="{}"[^>]*content="([^"]*)"'
_MICRO_TEXT = re.compile(r'<span itemprop="name"[^>]*>(.*?)</span>', re.DOTALL)
# The country is a nested Country itemscope; its alternateName is the ISO code.
_MICRO_COUNTRY = re.compile(
    r'itemprop="addressCountry".{0,200}?itemprop="alternateName"[^>]*content="([^"]*)"',
    re.DOTALL,
)


def _overnight(start: str, closes: str) -> str:
    """A club night that ends at 04:59 is one night out, not a two-day festival."""
    if not closes[:10] or closes[:10] <= start[:10]:
        return ""
    next_day = date.fromisoformat(start[:10]) + timedelta(days=1)
    return "yes" if closes[:10] == str(next_day) and closes[11:16] < "12:00" else ""


def _micro(chunk: str, prop: str) -> str:
    m = re.search(_MICRO_PROP.format(prop), chunk)
    return unescape(m.group(1)) if m else ""


def parse_microdata(html: str) -> list[Event]:
    """schema.org Event as itemprop attributes instead of an ld+json block."""
    out = []
    for chunk in _MICRO_SPLIT.split(html)[1:]:
        start = _micro(chunk, "startDate")
        if not re.match(r"\d{4}-\d\d-\d\d", start):
            continue
        title = _MICRO_TEXT.search(chunk)
        closes = _micro(chunk, "endDate")
        end = "" if _overnight(start, closes) else closes[:10]
        out.append(
            {
                "date": start[:10],
                "end": end if end > start[:10] else "",
                "time": start[11:16],
                "title": unescape(_TAGS_ONLY.sub("", title.group(1))) if title else "",
                "venue": _micro(chunk, "name"),
                "city": _micro(chunk, "addressLocality"),
                "country": (m.group(1) if (m := _MICRO_COUNTRY.search(chunk)) else ""),
                "url": _micro(chunk, "url"),
            }
        )
    return [e for e in out if e["title"]]
