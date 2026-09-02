# Mission: BOEKING

Give the feed a real entity model — events, venues, artists, cities — then double the
number of stages it covers. Schema first: every new source lands on the new shape.

## Scope
- Repo: /Users/jurrejan/Documents/development/python/agenda-scraper
- Branch: feature/entity-model, cut from develop before the first edit
- OUT of scope, do not touch: pushing any branch; the Linux timer host and its systemd
  units; writing into ./data/ (scrape to a temp dir instead); removing or renaming an
  existing route, event key or TSV column; new accounts, paid APIs or API keys; a
  database as the *serving* layer; the refresh schedule; .quality.json thresholds.

## Phase A — the entity model
A1  Baseline first, before any edit. `uv run agenda-scraper scrape --all --out "$TMPDIR/baseline"`
    (needs Chrome for tivoli and paradiso; takes several minutes). Write loop/BASELINE.json:
    total events, per-source counts, distinct venue labels, distinct cities, route count.
    Every later comparison reads this file.
A2  src/agenda_scraper/entities/ — a NEW subpackage. models.py holds TypedDicts for Event,
    Venue, Artist, City plus SCHEMA_VERSION. The top-level package already has 6 .py files
    and .quality.json caps a directory at 6, so nothing new goes there.
A3  schema/*.schema.json — JSON Schema per entity plus the route envelope. `uv add --dev
    jsonschema`; a test validates a full run against them.
A4  entities/resolve.py + entities/artists.py — deterministic IDs built on publish.slugify
    (reuse it, do not re-implement the rule; mcp_server.py imports it for the same reason),
    alias tables for venues and cities, resolve_venue(name, city), resolve_city(name),
    extract_artists(title).
A5  Wire into publish.py: every event gains venue_id, city_id, artist_ids; every envelope
    gains schema_version. The nine existing keys stay, in place; new TSV columns append at
    the end only. If publish.py passes 300 lines, split it into a publish/ package — the
    Justfile says it: "don't trim, split the file!".
A6  Registry routes /venues.json, /artists.json, /cities.json, and /artist/<slug>.json for
    artists with >= 5 upcoming events, via plan_routes() in publish.py.
A7  dedupe() keys on (date, venue_id, title_key) instead of free-text city + title.
A8  Update data/llm.txt AND data/llms.txt (identical files) — new fields, new routes,
    schema_version. This is the feed's public contract; changing the output without it is
    the bug, not the paperwork.

Phase A is done when all of these hold:
- `just check` green
- the schema test validates a full --all run with 0 errors
- a test asserts the nine legacy event keys and the TSV column order are unchanged
- total events within 2% of loop/BASELINE.json, or every gap explained per source in
  PROGRESS.md with the count

## Phase B — expand the sources
One loop/BACKLOG.json item per iteration, top down; the list is ordered by leverage, with
platform sweeps before individual stages. Research each item before building and take the
cheapest tier that works, in this order: a documented API, then schema.org JSON-LD in the
served HTML, then a WordPress/tribe REST endpoint. Reach for Chrome only when a site
actually blocks the cheaper tiers, and say why in the commit.

A source is done when all five hold:
- >= 20 events on a live run, >= 95% with a valid ISO date
- its venue resolves to a Venue record and its city to a City record
- an offline golden test: the fetched page saved to tests/fixtures/<name>.{html,json} with
  a sibling <name>.expected.json, walked by ONE parametrised tests/test_sources.py. Do not
  add a test file per source — tests/ is capped at 6 .py files. Trim each fixture to the
  smallest snippet that still reproduces the parse.
- registered in SOURCES, in SOURCE_CITY if the source never names a city, and in
  publish.SOURCE_RANK (venues rank above aggregators)
- `just check` green, committed

Phase B is done when >= 12 backlog items are "done" AND distinct venues in a full run are
>= 2x the figure in loop/BASELINE.json.

## Two decisions to make, log, and move past
- Storage substrate: default to static JSON registries — it matches the feed's no-server
  identity and entity resolution over ~5k events is trivial in memory. Choose a build-time
  SQLite only if you can name the specific join that is impractical in memory. Decide
  before A2 and log which and why in PROGRESS.md.
- Artists: heuristic extraction is mandatory — split on +, &, w/, feat., x, b2b, //,
  presents; a stop-list for club-night brands and non-music titles (Pubquiz, Open Podium);
  a confidence field. MusicBrainz MBIDs only after Phase A is green, and only if a 50-name
  probe returns >= 80% correct matches at 1 req/s. If the probe misses, cut it and record
  the number.

## Verification
`just check` after every item — ruff, mypy, pytest, loc and dir caps. Paste the real
output into PROGRESS.md; a claim with no command output is not done. At each phase
boundary run exactly one fresh-context skeptic subagent (model: opus) given only the git
diff and the commands, reporting whether the phase criteria actually hold. That is the
only subagent this run spawns.

## Error budget
Any new failing test is fixed before the next item. Three consecutive iterations with a
rising failure count = stop and report. A source that fails for a reason outside this repo
(site down, needs a key, needs an account) is BLOCKED, not failed — record it, take the
next one.

## Never ask, always log
Do not stop to ask. Decide with research, log question + answer + why in PROGRESS.md.
Three distinct approaches failed on one item = mark it BLOCKED with what was tried and
move on. Blocked is never written up as done.

## Rules
- One backlog item per iteration. Search the codebase before writing anything new:
  paged_jsonld, tribe_events, wp_events, jsonld_page and parse_jsonld already cover most
  sites, so a new source is usually a registry entry, not a new function.
- Full --all runs hit every site and take minutes: run one for the baseline, one at each
  phase boundary, and one to prove a count claim. Iterate with single sources.
- Never hit a host faster than 1 request/second, and honour robots.txt — both aggregators
  ask for it explicitly.
- Commit every green step on feature/entity-model. Never push.
- Never edit or delete a test to make it pass. Never raise a .quality.json threshold.
- Long command output → redirect to a file and tail it.
- After a context compaction: re-read this file and PROGRESS.md, continue at the first
  unfinished BACKLOG.json item.
- Keep PROGRESS.md to one line per iteration plus the pasted evidence. No essays, no
  restating the mission back.

## Autonomy zones
- Free: read anything; create and edit under src/, tests/, schema/, loop/; uv add; run
  tests and single-source scrapes; git add and commit on the run branch.
- Log one line first: editing data/llm.txt, changing dedupe or route logic, adding a
  runtime dependency, touching more than three files in one step.
- Forbidden even with permissions skipped: git push, force-push, anything on main or
  develop; files outside the repo; secrets, .env, onenv; the timer host; writing into
  ./data/; deploy, publish, send, spend, delete.

## Hard stop
Stop when Phase B's definition of done is met, OR after 8 hours — whichever comes first.
Also stop if 5 consecutive iterations produce no status change in BACKLOG.json, or if every
remaining backlog item is BLOCKED.
