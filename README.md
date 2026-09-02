# agenda-scraper

Concerts, club nights and festivals across the Netherlands, scraped four times a
day and published as static JSON/TSV: <https://agenda.jurrejan.com>.

The feed's own documentation, written for agents rather than humans, is
[`data/llm.txt`](data/llm.txt) — schema, routes, health semantics and caveats.

## How it works

    src/agenda_scraper/cli.py       the entry point: scrape, sources, mcp, reachability
    src/agenda_scraper/scrape/      the scrapers and the source registry
    src/agenda_scraper/publish.py   dedupe, health assessment, route files
    src/agenda_scraper/reachability.py  is the feed readable from the internet?
    src/agenda_scraper/mcp_server.py    MCP server (stdio) over the published feed
    refresh.sh                      what the systemd timer runs

Three tiers, cheapest first: Resident Advisor's GraphQL for the whole country,
schema.org JSON-LD for the two nationwide aggregators and the venues that
publish it, and a real (non-headless) Chrome over CDP for the two sites that
serve a Cloudflare challenge or no agenda route at all.

Filtering is baked into paths, because the feed is served by
`python3 -m http.server`, which ignores query strings: `/city/utrecht/week.json`,
`/venue/paradiso.json`, `/source/festivalinfo.tsv`. `/routes.json` indexes them.

## Requirements

- Python >= 3.13 and [uv](https://docs.astral.sh/uv/)
- Chrome and xvfb, for the two rendered sources only

## Running it

```bash
uv sync                                    # once
uv run agenda-scraper sources              # what can be scraped
uv run agenda-scraper scrape ra-nl         # one or more sources, as TSV on stdout
uv run agenda-scraper scrape --all --out data   # publish the feed and every route
uv run agenda-scraper reachability         # can an agent on the internet read it?
uv run agenda-scraper mcp                  # serve the feed over MCP on stdio
./refresh.sh                               # everything, into data/, as the timer runs it
```

`scrape --out` exits 1 when a source failed, returned nothing, or returned far
less than it normally does — that non-zero is what the timer reports upstream.

## Common Commands

| Command | Description |
|---------|-------------|
| `just install` | `uv sync` |
| `just check` | lint + format + typecheck + tests + file-size thresholds |
| `just test` | `uv run pytest` |
| `just test-live` | also runs the one test that hits the published feed |
| `just run <args>` | run the CLI |

## Configuration

Every path and URL is environment-overridable; the defaults assume a checkout.

| Variable | Default | What it does |
|----------|---------|--------------|
| `AGENDA_DATA_DIR` | `<checkout>/data` | where the feed is written and read |
| `AGENDA_BASE_URL` | `https://agenda.jurrejan.com` | feed to read when there is no local copy |
| `AGENDA_LOCAL_URL` | `http://127.0.0.1:5181` | what `reachability` checks first |
| `AGENDA_CHROME` | the macOS Chrome path | browser for the two rendered sources |
| `AGENDA_CDP_PORT` | `9333` | debugging port that Chrome exposes |
