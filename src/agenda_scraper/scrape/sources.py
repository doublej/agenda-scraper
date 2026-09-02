"""Every source, cheapest tier first, and the registry that names them.

api    Resident Advisor's public GraphQL, area 176 = "Netherlands All". One
       paginated query covers every club night in the country, so Garage
       Noord, Shelter, BRET, Radio Radio, Lofi and Thuishaven need no
       scraper of their own.
jsonld One GET, schema.org blocks in the HTML. Podiuminfo (every concert in
       NL) and Festivalinfo (every festival) paginate; De Helling, Rotown
       and Muziekgieterij publish their whole agenda on one page. The Events
       Calendar's REST API (Musicon, dB's) is the same idea with less HTML.
cards  One GET, <time datetime> in the listing markup. The last cheap tier:
       no Dutch venue site outside the two aggregators serves schema.org, but
       the semantic time element is in every listing template. 013, Spot
       (three buildings off one page) and Victorie all answer on it.
render Real Chrome over CDP. Only TivoliVredenburg (Cloudflare managed
       challenge — curl, headless Chrome and WebFetch all get 403) and
       Paradiso (no agenda route at all; the homepage is an infinite scroll
       and only 23 highlights exist in the served HTML).
"""

import json
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import partial

from agenda_scraper import Event
from agenda_scraper.entities.resolve import CITY_ALIAS
from agenda_scraper.scrape.browser import browser_credentials, render
from agenda_scraper.scrape.cards import CARD_SOURCES, LINKS_AFTER, parse_cards
from agenda_scraper.scrape.http import get, post_json
from agenda_scraper.scrape.parsers import (
    parse_jsonld,
    parse_microdata,
    parse_paradiso,
    parse_tivoli,
    unescape,
)

RA_NL = 176  # RA's own "Netherlands All" area: every NL city in one query
RA_QUERY = """query($f:FilterInputDtoInput,$p:Int,$ps:Int){
  eventListings(filters:$f,page:$p,pageSize:$ps){ totalResults data{
    event{ title date startTime contentUrl area{name} venue{name area{name}} } } } }"""


def ra_events(area: int = RA_NL, days: int = 45, page_size: int = 100) -> list[Event]:
    """RA's GraphQL is public and un-challenged. Introspection is open too."""
    lo, hi = date.today(), date.today() + timedelta(days=days)
    out: list[Event] = []
    page = 1
    while True:
        res = post_json(
            "https://ra.co/graphql",
            {
                "query": RA_QUERY,
                "variables": {
                    "f": {
                        "areas": {"eq": area},
                        "listingDate": {
                            "gte": f"{lo}T00:00:00.000Z",
                            "lte": f"{hi}T00:00:00.000Z",
                        },
                    },
                    "p": page,
                    "ps": page_size,
                },
            },
            {"Referer": "https://ra.co/events/nl/all"},
        )
        block = res["data"]["eventListings"]
        for row in block["data"]:
            e = row["event"]
            venue = e.get("venue") or {}
            # Events outside RA's six city areas come back as area "All"; their
            # venue carries no city either, so the city stays unknown.
            named = (e.get("area") or {}).get("name") or (venue.get("area") or {}).get(
                "name"
            )
            out.append(
                {
                    "date": e["date"][:10],
                    "time": (e.get("startTime") or "")[11:16],
                    "title": e["title"],
                    "venue": venue.get("name", ""),
                    "city": "" if named in (None, "All") else named,
                    "url": "https://ra.co" + e["contentUrl"],
                }
            )
        if len(out) >= block["totalResults"] or not block["data"]:
            return out
        page += 1


def paged_jsonld(
    url_template: str,
    days: int,
    country: str = "NL",
    cap: int = 60,
    delay: float = 1.0,
) -> list[Event]:
    """Walk `?page=N` until the listing runs past the horizon.

    Both aggregators sort ascending by date and ask for a one second crawl
    delay in robots.txt, which is the only reason this is not threaded. They
    also both cover Belgium, hence the country filter.
    """
    horizon = str(date.today() + timedelta(days=days))
    out: list[Event] = []
    seen: set[str] = set()
    for page in range(1, cap + 1):
        rows = [
            e
            for e in parse_jsonld(get(url_template.format(page=page)))
            if e["url"] not in seen and e.get("country", country) == country
        ]
        if not rows:
            break
        seen.update(e["url"] for e in rows)
        out += [e for e in rows if e["date"] <= horizon]
        # A page can carry one far-future outlier, so stop on the earliest date
        # of a page, not the latest: listings are ascending by start date.
        if min(e["date"] for e in rows) > horizon:
            break
        time.sleep(delay)
    return out


def tribe_events(
    base: str, venue: str, per_page: int = 50, cap: int = 10
) -> list[Event]:
    """The Events Calendar REST API — the default agenda plugin on WordPress."""
    out: list[Event] = []
    for page in range(1, cap + 1):
        doc = json.loads(
            get(
                f"{base}/wp-json/tribe/events/v1/events"
                f"?per_page={per_page}&page={page}&start_date={date.today()}"
            )
        )
        for ev in doc.get("events", []):
            start = (ev.get("start_date") or "")[:16]
            out.append(
                {
                    "date": start[:10],
                    "time": start[11:16],
                    "title": unescape(re.sub(r"<[^>]+>", "", ev.get("title", ""))),
                    "venue": venue,
                    "url": ev.get("url", ""),
                }
            )
        if page >= (doc.get("total_pages") or 1):
            break
    return out


def wp_events(base: str, venue: str, per_page: int = 100) -> list[Event]:
    """WordPress REST `event` post type. EKKO mirrors its Stager programming here."""
    rows = json.loads(
        get(f"{base}/wp-json/wp/v2/event?per_page={per_page}&orderby=date")
    )
    today = str(date.today())
    seen, out = set(), []
    for r in rows:
        acf = r.get("acf")
        when = acf.get("date_time") if isinstance(acf, dict) else None
        if not when or when[:10] < today or r.get("lang") not in (None, "nl"):
            continue
        key = (when[:10], r["title"]["rendered"])
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "date": when[:10],
                "time": when[11:16],
                "title": unescape(r["title"]["rendered"]),
                "venue": venue,
                "url": r["link"],
            }
        )
    return sorted(out, key=lambda e: e["date"])


def cards(
    url: str, venue: str = "", dates: str = "time", links: str = "before"
) -> list[Event]:
    """A listing whose only structure is a date next to a heading."""
    return parse_cards(get(url), venue, url, dates, links)


def partyflock(months: int = 3) -> list[Event]:
    """Partyflock's month pages — schema.org as microdata, Dutch rows only.

    A nationwide dance agenda, so it reaches the bars, boats and one-off
    locations no venue scraper covers: three month pages carry more distinct
    venues than every other source in this file put together. robots.txt allows
    it and asks for no delay; it gets one request a page, a second apart.
    """
    today = str(date.today())
    year, month = date.today().year, date.today().month
    seen: set[str] = set()
    out: list[Event] = []
    for _ in range(months):
        for e in parse_microdata(get(f"https://partyflock.nl/agenda/{year}/{month}")):
            if e["country"] == "NL" and e["date"] >= today and e["url"] not in seen:
                seen.add(e["url"])
                out.append(e)
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        time.sleep(1)
    return out


def jsonld_page(url: str, venue: str) -> list[Event]:
    """A venue that publishes its whole agenda as JSON-LD on one page."""
    return [{**e, "venue": e["venue"] or venue} for e in parse_jsonld(get(url))]


def enrich_from_detail(
    events: list[Event], origin: str, workers: int = 8
) -> list[Event]:
    """Fill in time / real title / hall from each event's own JSON-LD.

    The agenda index only carries the date, and the title only as a URL slug.
    Every detail page has a proper schema.org MusicEvent, and it is reachable
    over plain HTTP using the browser's Cloudflare cookie.
    """
    headers = browser_credentials(origin)

    def one(e: Event) -> Event:
        try:
            found = parse_jsonld(get(e["url"], headers))
        except OSError:
            return e
        if not found:
            return e
        d = found[0]
        return {
            **e,
            "time": d["time"] or e["time"],
            "title": d["title"] or e["title"],
            "venue": d["venue"] or e["venue"],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, events))


SOURCES: dict[str, Callable[[], list[Event]]] = {
    # nationwide
    "ra-nl": ra_events,
    "partyflock": partyflock,
    "podiuminfo": lambda: paged_jsonld(
        "https://www.podiuminfo.nl/concertagenda/?page={page}", days=45
    ),
    "festivalinfo": lambda: paged_jsonld(
        "https://www.festivalinfo.nl/festivals/?page={page}", days=120
    ),
    # venues, for the ticket status and detail URLs the aggregators drop
    "dehelling": lambda: parse_jsonld(get("https://dehelling.nl/agenda/")),
    "ekko": lambda: wp_events("https://ekko.nl", "EKKO"),
    "rotown": lambda: jsonld_page("https://www.rotown.nl/", "Rotown"),
    "muziekgieterij": lambda: jsonld_page(
        "https://www.muziekgieterij.nl/", "Muziekgieterij"
    ),
    "musicon": lambda: tribe_events("https://www.musicon.nl", "Musicon"),
    "dbstudio": lambda: tribe_events("https://www.dbstudio.nl", "dB's"),
    "tivoli": lambda: enrich_from_detail(
        parse_tivoli(
            render("https://www.tivolivredenburg.nl/agenda/", scroll_rounds=20)
        ),
        "https://www.tivolivredenburg.nl/",
    ),
    "paradiso": lambda: parse_paradiso(
        render("https://www.paradiso.nl/", scroll_rounds=20)
    ),
}

# Where a source's events happen, when the source itself never says.
SOURCE_CITY = {
    "dehelling": "Utrecht",
    "ekko": "Utrecht",
    "dbstudio": "Utrecht",
    "tivoli": "Utrecht",
    "paradiso": "Amsterdam",
    "rotown": "Rotterdam",
    "muziekgieterij": "Maastricht",
    "musicon": "Den Haag",
}

__all__ = ["CITY_ALIAS", "SOURCES", "SOURCE_CITY"]

SOURCES.update(
    {
        name: partial(
            cards, url, venue, dates, "after" if name in LINKS_AFTER else "before"
        )
        for name, (url, venue, _, dates) in CARD_SOURCES.items()
    }
)
SOURCE_CITY.update({name: city for name, (_, _, city, _) in CARD_SOURCES.items()})
