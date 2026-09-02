#!/usr/bin/env python3
"""Agenda scrapers for every stage in the Netherlands.

Two nationwide aggregators carry the country; venue scrapers exist only where
they add something the aggregators lack (ticket status, the venue's own detail
URL, a hall name). Cheapest tier first — never reach for a browser when an API
exists:

  api    Resident Advisor's public GraphQL, area 176 = "Netherlands All". One
         paginated query covers every club night in the country, so Garage
         Noord, Shelter, BRET, Radio Radio, Lofi and Thuishaven need no
         scraper of their own.
  jsonld One GET, schema.org blocks in the HTML. Podiuminfo (every concert in
         NL) and Festivalinfo (every festival) paginate; De Helling, Rotown
         and Muziekgieterij publish their whole agenda on one page. The
         Events Calendar's REST API (Musicon, dB\'s) is the same idea with
         less HTML.
  render Real Chrome over CDP. Only TivoliVredenburg (Cloudflare managed
         challenge — curl, headless Chrome and WebFetch all get 403) and
         Paradiso (no agenda route at all; the homepage is an infinite
         scroll and only 23 highlights exist in the served HTML).

Usage:
    uv run --with websocket-client python system/automation/scrape.py ra-nl
    uv run --with websocket-client python system/automation/scrape.py --all
    python3 system/automation/scrape.py --selfcheck     # no network, no Chrome
"""
import atexit
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import SCRAPE_CACHE  # noqa: E402
from publish import assess, current, dedupe, slugify, write_out  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CHROME = os.environ.get(
    "LIFE_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CDP_PORT = int(os.environ.get("LIFE_CDP_PORT", "9333"))
MONTHS = {m: i + 1 for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}


# ── transport ────────────────────────────────────────────────────────────────

def get(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf8", "replace")


def post_json(url, payload, headers=None):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json", **(headers or {})})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def render(url, scroll_rounds=0, settle=6.0):
    """DOM of `url` after JS, from a real (non-headless) Chrome.

    Headless is fingerprinted and fails Cloudflare's managed challenge; a
    normal Chrome with a persistent profile passes it. The window is parked
    offscreen so it does not steal focus.
    """
    import websocket  # only needed on this path

    _launch_chrome()
    if True:
        req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new",
                                     method="PUT")
        tab = json.load(urllib.request.urlopen(req, timeout=15))
        ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=90)
        nxt = iter(range(1, 10_000)).__next__
        # Navigate explicitly: Chrome >=150 ignores the ?url= on /json/new.
        ws.send(json.dumps({"id": nxt(), "method": "Page.navigate",
                            "params": {"url": url}}))
        time.sleep(settle)

        def ev(expr):
            i = nxt()
            ws.send(json.dumps({"id": i, "method": "Runtime.evaluate", "params": {
                "expression": expr, "returnByValue": True, "awaitPromise": True}}))
            while True:
                m = json.loads(ws.recv())
                if m.get("id") == i:
                    return m["result"]["result"].get("value")

        ev("(()=>{const b=document.getElementById("
           "'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')"
           "||document.getElementById('CybotCookiebotDialogBodyButtonAccept');"
           "if(b)b.click()})()")
        seen, stale = -1, 0
        for _ in range(scroll_rounds):
            n = ev(
                "(()=>{window.scrollTo(0,document.body.scrollHeight);"
                "const re=/toon volgende|laad meer|toon meer|load more|show more/i;"
                "const b=[...document.querySelectorAll('button,a')].find("
                "e=>re.test((e.textContent||'').trim())&&e.offsetParent!==null);"
                "if(b)b.click();"
                "return document.querySelectorAll('a[href]').length})()")
            if n == seen:
                stale += 1
                if stale >= 2:      # a slow box can miss one round's fetch
                    break
            else:
                stale = 0
            seen = n
            time.sleep(2.5)
        html = ev("document.documentElement.outerHTML") or ""
        ws.close()
        urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/close/{tab['id']}",
                               timeout=15)
        return html


_CHROME_PROC = None


def _cdp(ws, method, params=None, _n=[0]):
    _n[0] += 1
    i = _n[0]
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == i:
            return m.get("result") or {}


def _new_tab():
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new", method="PUT")
    return json.load(urllib.request.urlopen(req, timeout=15))


def _close_tab(tab):
    urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/close/{tab['id']}", timeout=15)


def browser_credentials(origin):
    """Cookie header + UA from the running Chrome.

    Once the browser has solved a Cloudflare challenge, its `cf_clearance`
    cookie lets ordinary urllib through the same edge — so detail pages can be
    fetched hundreds at a time instead of one browser navigation each.
    """
    import websocket

    _launch_chrome()
    tab = _new_tab()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        cookies = _cdp(ws, "Network.getCookies", {"urls": [origin]}).get("cookies", [])
        ua = _cdp(ws, "Runtime.evaluate",
                  {"expression": "navigator.userAgent", "returnByValue": True}
                  )["result"]["value"]
    finally:
        ws.close()
        _close_tab(tab)
    return {"Cookie": "; ".join(f"{c['name']}={c['value']}" for c in cookies),
            "User-Agent": ua, "Accept-Language": "nl-NL,nl;q=0.9"}


def _launch_chrome():
    """One Chrome per process, reused across renders and killed at exit."""
    global _CHROME_PROC
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", CDP_PORT)) == 0:
            return _CHROME_PROC  # already listening
    profile = SCRAPE_CACHE / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [CHROME, "--no-first-run", "--no-default-browser-check",
         f"--user-data-dir={profile}", f"--remote-debugging-port={CDP_PORT}",
         "--remote-allow-origins=*", "--window-position=-3000,-3000",
         "--lang=en-US",  # parse_paradiso reads English day/month labels
         "--window-size=1400,1000", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2)
            _CHROME_PROC = proc
            atexit.register(proc.terminate)
            return proc
        except OSError:
            continue
    proc.terminate()
    raise RuntimeError("Chrome did not expose CDP — is LIFE_CHROME correct?")


# ── parsers (pure, self-checkable) ───────────────────────────────────────────

def jsonld_nodes(html):
    """Every dict in every ld+json block, with @graph and ItemList flattened."""
    out = []
    for block in re.findall(
            r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
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


def parse_jsonld(html):
    """schema.org Event/Festival nodes, whatever shape the site nests them in."""
    out = []
    for node in jsonld_nodes(html):
        if not re.search(r"Event|Festival", str(node.get("@type", ""))):
            continue
        start = (node.get("startDate") or "")[:16].replace("T", " ")
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", start[:10]):
            continue          # unrendered template placeholders, e.g. "{{ date }}"
        end = (node.get("endDate") or "")[:10]
        loc = node.get("location") if isinstance(node.get("location"), dict) else {}
        addr = loc.get("address")
        out.append({
            "date": start[:10],
            "end": end if end > start[:10] else "",
            "time": start[11:16],
            "title": _unescape(node.get("name", "")),
            "venue": _unescape(loc.get("name", "")),
            "city": addr.get("addressLocality", "").strip() if isinstance(addr, dict) else "",
            "country": addr.get("addressCountry", "") if isinstance(addr, dict) else "",
            "url": node.get("url", ""),
        })
    return [e for e in out if e["title"]]


def paged_jsonld(url_template, days, country="NL", cap=60, delay=1.0):
    """Walk `?page=N` until the listing runs past the horizon.

    Both aggregators sort ascending by date and ask for a one second crawl
    delay in robots.txt, which is the only reason this is not threaded. They
    also both cover Belgium, hence the country filter.
    """
    horizon = str(date.today() + timedelta(days=days))
    out, seen = [], set()
    for page in range(1, cap + 1):
        rows = [e for e in parse_jsonld(get(url_template.format(page=page)))
                if e["url"] not in seen and e.get("country", country) == country]
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


def tribe_events(base, venue, per_page=50, cap=10):
    """The Events Calendar REST API — the default agenda plugin on WordPress."""
    out = []
    for page in range(1, cap + 1):
        doc = json.loads(get(f"{base}/wp-json/tribe/events/v1/events"
                             f"?per_page={per_page}&page={page}"
                             f"&start_date={date.today()}"))
        for ev in doc.get("events", []):
            start = (ev.get("start_date") or "")[:16]
            out.append({
                "date": start[:10], "time": start[11:16],
                "title": _unescape(re.sub(r"<[^>]+>", "", ev.get("title", ""))),
                "venue": venue, "url": ev.get("url", ""),
            })
        if page >= (doc.get("total_pages") or 1):
            break
    return out


def jsonld_page(url, venue):
    """A venue that publishes its whole agenda as JSON-LD on one page."""
    return [{**e, "venue": e["venue"] or venue} for e in parse_jsonld(get(url))]


def parse_tivoli(html):
    """Tivoli encodes the date in the slug: /agenda/<id>/<slug>-<dd-mm-yyyy>."""
    seen, out = set(), []
    for m in re.finditer(
            r'href="[^"]*?/agenda/(\d+)/([a-z0-9-]+?)-(\d{2})-(\d{2})-(\d{4})"', html):
        eid, slug, d, mo, y = m.groups()
        if eid in seen:
            continue
        seen.add(eid)
        out.append({
            "date": f"{y}-{mo}-{d}", "time": "",
            "title": slug.replace("-", " ").strip(),
            "venue": "TivoliVredenburg",
            "url": f"https://www.tivolivredenburg.nl/agenda/{eid}/{slug}-{d}-{mo}-{y}",
        })
    return sorted(out, key=lambda e: e["date"])


def parse_paradiso(html, start_year=None):
    """Day headings ("Su 15 Nov") precede each group of event anchors."""
    year = start_year or date.today().year
    pat = re.compile(
        r'>(?:Mo|Tu|We|Th|Fr|Sa|Su)\s+(\d{1,2})\s+([A-Z][a-z]{2})<'
        r'|<a[^>]+href="(/(?:programma|en/program)/[a-z0-9-]+/\d+)"[^>]*>(.*?)</a>', re.S)
    cur, prev_month, seen, out = None, 0, set(), []
    for m in pat.finditer(html):
        if m.group(1):
            month = MONTHS[m.group(2)]
            if month < prev_month:
                year += 1
            prev_month = month
            cur = f"{year}-{month:02d}-{int(m.group(1)):02d}"
        elif m.group(3) and cur:
            parts = [p.strip() for p in
                     re.sub(r"<[^>]+>", "|", m.group(4)).split("|") if p.strip()]
            if not parts:
                continue
            title = _unescape(parts[0])
            key = (cur, title)
            if key in seen:
                continue
            seen.add(key)
            # The card's last slot holds either a start time or a status badge —
            # "Sold out", "Postponed". Those events genuinely have no time shown.
            tail = parts[-1] if len(parts) > 1 else ""     # never the title itself
            clock = re.search(r"\b([0-2]?\d:[0-5]\d)\b", tail)
            out.append({
                "date": cur,
                "time": clock.group(1) if clock else "",
                "status": "" if clock else _unescape(tail)[:20],
                "title": title,
                "venue": "Paradiso",
                "url": "https://www.paradiso.nl" + m.group(3),
            })
    return out


def enrich_from_detail(events, origin, workers=8):
    """Fill in time / real title / hall from each event's own JSON-LD.

    The agenda index only carries the date, and the title only as a URL slug.
    Every detail page has a proper schema.org MusicEvent, and it is reachable
    over plain HTTP using the browser's Cloudflare cookie.
    """
    from concurrent.futures import ThreadPoolExecutor

    headers = browser_credentials(origin)

    def one(e):
        try:
            found = parse_jsonld(get(e["url"], headers))
        except OSError:
            return e
        if not found:
            return e
        d = found[0]
        return {**e,
                "time": d["time"] or e["time"],
                "title": d["title"] or e["title"],
                "venue": d["venue"] or e["venue"]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, events))


def _unescape(s):
    return (s.replace("&amp;", "&").replace("&#8217;", "’")
             .replace("&quot;", '"').replace("&#039;", "'").strip())


# ── sources ──────────────────────────────────────────────────────────────────

RA_NL = 176        # RA's own "Netherlands All" area: every NL city in one query
RA_QUERY = """query($f:FilterInputDtoInput,$p:Int,$ps:Int){
  eventListings(filters:$f,page:$p,pageSize:$ps){ totalResults data{
    event{ title date startTime contentUrl area{name} venue{name area{name}} } } } }"""


def ra_events(area=RA_NL, days=45, page_size=100):
    """RA's GraphQL is public and un-challenged. Introspection is open too."""
    lo, hi = date.today(), date.today() + timedelta(days=days)
    out, page = [], 1
    while True:
        res = post_json("https://ra.co/graphql", {
            "query": RA_QUERY,
            "variables": {"f": {
                "areas": {"eq": area},
                "listingDate": {"gte": f"{lo}T00:00:00.000Z", "lte": f"{hi}T00:00:00.000Z"},
            }, "p": page, "ps": page_size},
        }, {"Referer": "https://ra.co/events/nl/all"})
        block = res["data"]["eventListings"]
        for row in block["data"]:
            e = row["event"]
            venue = e.get("venue") or {}
            # Events outside RA's six city areas come back as area "All"; their
            # venue carries no city either, so the city stays unknown.
            named = (e.get("area") or {}).get("name") or (venue.get("area") or {}).get("name")
            out.append({
                "date": e["date"][:10],
                "time": (e.get("startTime") or "")[11:16],
                "title": e["title"],
                "venue": venue.get("name", ""),
                "city": "" if named in (None, "All") else named,
                "url": "https://ra.co" + e["contentUrl"],
            })
        if len(out) >= block["totalResults"] or not block["data"]:
            return out
        page += 1


def wp_events(base, venue, per_page=100):
    """WordPress REST `event` post type. EKKO mirrors its Stager programming here."""
    rows = json.loads(get(f"{base}/wp-json/wp/v2/event?per_page={per_page}&orderby=date"))
    today, seen, out = str(date.today()), set(), []
    for r in rows:
        when = (r.get("acf") or {}).get("date_time") if isinstance(r.get("acf"), dict) else None
        if not when or when[:10] < today or r.get("lang") not in (None, "nl"):
            continue
        key = (when[:10], r["title"]["rendered"])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date": when[:10], "time": when[11:16],
            "title": _unescape(r["title"]["rendered"]),
            "venue": venue, "url": r["link"],
        })
    return sorted(out, key=lambda e: e["date"])


SOURCES = {
    # nationwide
    "ra-nl":         lambda: ra_events(),
    "podiuminfo":    lambda: paged_jsonld(
        "https://www.podiuminfo.nl/concertagenda/?page={page}", days=45),
    "festivalinfo":  lambda: paged_jsonld(
        "https://www.festivalinfo.nl/festivals/?page={page}", days=120),
    # venues, for the ticket status and detail URLs the aggregators drop
    "dehelling":     lambda: parse_jsonld(get("https://dehelling.nl/agenda/")),
    "ekko":          lambda: wp_events("https://ekko.nl", "EKKO"),
    "rotown":        lambda: jsonld_page("https://www.rotown.nl/", "Rotown"),
    "muziekgieterij": lambda: jsonld_page("https://www.muziekgieterij.nl/",
                                          "Muziekgieterij"),
    "musicon":       lambda: tribe_events("https://www.musicon.nl", "Musicon"),
    "dbstudio":      lambda: tribe_events("https://www.dbstudio.nl", "dB\'s"),
    "tivoli":        lambda: enrich_from_detail(
        parse_tivoli(render("https://www.tivolivredenburg.nl/agenda/", scroll_rounds=20)),
        "https://www.tivolivredenburg.nl/"),
    "paradiso":      lambda: parse_paradiso(
        render("https://www.paradiso.nl/", scroll_rounds=20)),
}

# Where a source's events happen, when the source itself never says.
SOURCE_CITY = {
    "dehelling": "Utrecht", "ekko": "Utrecht", "dbstudio": "Utrecht",
    "tivoli": "Utrecht", "paradiso": "Amsterdam", "rotown": "Rotterdam",
    "muziekgieterij": "Maastricht", "musicon": "Den Haag",
}

# One spelling per city, so /city/<slug> does not split in two.
CITY_ALIAS = {"The Hague": "Den Haag", "\'s-Gravenhage": "Den Haag",
              "Den Bosch": "\'s-Hertogenbosch", "Amsterdam-Zuidoost": "Amsterdam"}


# ── self-check ───────────────────────────────────────────────────────────────

def selfcheck():
    tv = parse_tivoli(
        '<a href="https://www.tivolivredenburg.nl/agenda/57200310/hush-aat-29-08-2026">x</a>'
        '<a href="/agenda/57200310/hush-aat-29-08-2026">dup</a>')
    assert tv == [{"date": "2026-08-29", "time": "", "title": "hush aat",
                   "venue": "TivoliVredenburg",
                   "url": "https://www.tivolivredenburg.nl/agenda/57200310/"
                          "hush-aat-29-08-2026"}], tv

    par = parse_paradiso(
        '<div>Su 15 Nov</div>'
        '<a href="/en/program/bokoesam/2908023"><h2> Bokoesam</h2>'
        '<span>20:30</span></a>'
        '<a href="/en/program/bokoesam/2908023"><h2> Bokoesam</h2></a>'
        '<div>Fr 2 Jan</div>'
        '<a href="/programma/nyx/1"><h2>NYX</h2></a>', start_year=2026)
    assert [(e["date"], e["title"], e["time"], e["status"]) for e in par] == [
        ("2026-11-15", "Bokoesam", "20:30", ""),
        ("2027-01-02", "NYX", "", "")], par          # lone title is not a status
    sold = parse_paradiso(
        '<div>Fr 2 Jan</div><a href="/programma/x/2"><h2>X</h2>'
        '<span>Sold out</span></a>', start_year=2026)
    assert (sold[0]["time"], sold[0]["status"]) == ("", "Sold out"), sold

    ld = parse_jsonld(
        '<script type="application/ld+json">{"@type":"MusicEvent",'
        '"name":"Cyberia &amp; Rotersand","startDate":"2026-08-28 20:50:00",'
        '"location":{"name":"De Helling"},"url":"https://x"}</script>')
    assert ld == [{"date": "2026-08-28", "end": "", "time": "20:50",
                   "title": "Cyberia & Rotersand", "venue": "De Helling",
                   "city": "", "country": "", "url": "https://x"}], ld

    # a festival nested in an ItemList, with its city in a PostalAddress
    fest = parse_jsonld(
        '<script type="application/ld+json">{"@type":"ItemList",'
        '"itemListElement":[{"@type":"ListItem","item":{"@type":"Festival",'
        '"name":"Zomerterras","startDate":"2026-08-14","endDate":"2026-08-30",'
        '"location":{"@type":"Place","name":"Zomerterras","address":'
        '{"addressLocality":"Vlaardingen"}},"url":"https://f"}}]}</script>')
    assert fest == [{"date": "2026-08-14", "end": "2026-08-30", "time": "",
                     "title": "Zomerterras", "venue": "Zomerterras",
                     "city": "Vlaardingen", "country": "", "url": "https://f"}], fest
    # an unrendered Twig template is not an event
    assert parse_jsonld(
        '<script type="application/ld+json">{"@type":"Event","name":"x",'
        '"startDate":"{{ event.date }}"}</script>') == []

    assert slugify("Den Haag") == "den-haag"
    assert slugify("\'s-Hertogenbosch") == "s-hertogenbosch"

    # the venue's own listing beats the aggregator's copy of the same night
    rows = [{"date": "2026-09-01", "time": "20:00", "title": "Bokoesam!",
             "venue": "Paradiso", "city": "Amsterdam", "source": "podiuminfo"},
            {"date": "2026-09-01", "time": "20:30", "title": "Bokoesam",
             "venue": "Paradiso", "city": "Amsterdam", "source": "paradiso"},
            {"date": "2026-09-01", "time": "22:00", "title": "Bokoesam",
             "venue": "Doornroosje", "city": "Nijmegen", "source": "podiuminfo"}]
    kept = dedupe(rows)
    assert [(e["source"], e["city"]) for e in kept] == [
        ("paradiso", "Amsterdam"), ("podiuminfo", "Nijmegen")], kept

    # a festival that started yesterday is still running today
    assert len(current([{"date": "2026-08-01", "end": "2026-09-30"},
                        {"date": "2026-08-01", "end": ""}],
                       today="2026-09-01")) == 1
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        hist = Path(td) / "baseline.json"
        good = {"a": {"ok": True, "count": 100}}
        assert assess(good, hist) == []                     # first run: no norm yet
        for _ in range(3):
            assess(good, hist)
        assert assess({"a": {"ok": True, "count": 40}}, hist) == [
            "a: 40 events, normally ~100"]                  # regression caught
        assert assess({"a": {"ok": True, "count": 0}}, hist) == ["a: returned 0 events"]
        assert assess({"a": {"ok": False, "count": 0, "error": "boom"}}, hist) == [
            "a: failed — boom"]
        # a bad run must not drag the norm down
        assert assess({"a": {"ok": True, "count": 95}}, hist) == []
    print("selfcheck ok")


def collect(names):
    """Run each source, keeping going when one fails. Returns (events, report)."""
    events, report = [], {}
    for name in names:
        try:
            rows = SOURCES[name]()
        except Exception as exc:                      # one bad source must not kill the run
            report[name] = {"ok": False, "count": 0, "error": str(exc)}
            print(f"# {name}\tFAILED\t{exc}", file=sys.stderr)
            continue
        for e in rows:
            e["source"] = name
            e.setdefault("status", "")
            e.setdefault("end", "")
            e.pop("country", None)          # every published event is Dutch
            city = e.get("city") or SOURCE_CITY.get(name, "")
            e["city"] = CITY_ALIAS.get(city, city)
        events += rows
        report[name] = {"ok": True, "count": len(rows)}
        print(f"# {name}\t{len(rows)} events", file=sys.stderr)
    events.sort(key=lambda e: (e["date"], e["time"], e["title"]))
    return events, report


def main(argv):
    if "--selfcheck" in argv:
        return selfcheck()
    out_dir = None
    if "--out" in argv:
        i = argv.index("--out")
        out_dir = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    names = list(SOURCES) if "--all" in argv else [a for a in argv if a in SOURCES]
    if not names:
        print(__doc__)
        print("sources:", " ".join(SOURCES))
        return
    events, report = collect(names)
    if out_dir:
        return write_out(out_dir, events, report,   # non-zero exit if unhealthy
                         SCRAPE_CACHE / "baseline.json", log=_stderr)
    for e in dedupe(events):
        print("\t".join((e["source"], e["date"], e["time"], e["title"],
                         e["venue"], e["city"], e["status"], e["url"])))


def _stderr(msg):
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
