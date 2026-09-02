# agenda-scraper

Concerts, club nights and festivals across the Netherlands, scraped four times a
day and published as static JSON/TSV: <https://agenda.jurrejan.com>.

The feed's own documentation, written for agents rather than humans, is
[`data/llm.txt`](data/llm.txt) — schema, routes, health semantics and caveats.

## How it works

    system/automation/scrape.py    the scrapers and the source registry
    system/automation/publish.py   dedupe, health assessment, route files
    system/automation/reachability.py  is the feed readable from the internet?
    system/mcp/uitagenda_mcp.py    MCP server (stdio) over the published feed
    refresh.sh                     what the systemd timer runs

Three tiers, cheapest first: Resident Advisor's GraphQL for the whole country,
schema.org JSON-LD for the two nationwide aggregators and the venues that
publish it, and a real (non-headless) Chrome over CDP for the two sites that
serve a Cloudflare challenge or no agenda route at all.

Filtering is baked into paths, because the feed is served by
`python3 -m http.server`, which ignores query strings: `/city/utrecht/week.json`,
`/venue/paradiso.json`, `/source/festivalinfo.tsv`. `/routes.json` indexes them.

## Running it

    python3 system/automation/scrape.py --selfcheck        # no network, no Chrome
    python3 system/automation/scrape.py ra-nl podiuminfo   # one or more sources to stdout
    ./refresh.sh                                           # everything, into data/

Requires python3 (stdlib only), plus Chrome and xvfb for the two rendered
sources. `websocket-client` is needed only on that path.
