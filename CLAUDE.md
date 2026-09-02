# agenda-scraper

> Concerts, club nights and festivals across the Netherlands, scraped and republished as static JSON/TSV

## What this is

A Python CLI that scrapes twenty-six sources, resolves them onto an entity model
of venues, cities and artists, deduplicates them, and writes the result as ~600
static JSON/TSV route files served by `python3 -m http.server` at
<https://agenda.jurrejan.com>. A systemd timer runs `refresh.sh` four times a day.
The same feed is served over MCP for clients that would rather call tools.

## Mental model

```
src/agenda_scraper/
├── cli.py            # Click entry point — scrape / sources / reachability / mcp
├── config.py         # every path, URL and knob, all env-overridable
├── reachability.py   # DNS → local server → public URL, in the order they break
├── mcp_server.py     # MCP tools search() / cities() / venues() over the feed
├── entities/         # the leaf package: it imports nothing else of ours
│   ├── slug.py       # slugify(): the one spelling rule, and every id is built on it
│   ├── models.py     # TypedDicts + SCHEMA_VERSION + the field order
│   ├── resolve.py    # venue/city alias tables → deterministic ids
│   └── artists.py    # extract_artists(): heuristic lineup split + confidence
├── publish/
│   ├── feed.py       # annotate → dedupe → horizon → TSV → health assessment
│   └── routes.py     # plan_routes → registries → route files → routes.json
└── scrape/
    ├── __init__.py   # collect(): run sources, normalise city, survive failures
    ├── http.py       # one GET, one POST
    ├── browser.py    # real Chrome over CDP, for Cloudflare and infinite scroll
    ├── parsers.py    # pure HTML → events: JSON-LD, microdata, Tivoli, Paradiso
    ├── cards.py      # a date next to a heading — the tier most NL venues leave
    └── sources.py    # every source and the SOURCES registry
```

The runtime path is `cli.scrape → scrape.collect → SOURCES[name]() → publish.write_out`.
Reading the feed (`mcp_server`) never touches the scrapers: it reads the
published route files, locally or over HTTPS.

## Invariants

- An event is a flat `dict[str, str]` (`agenda_scraper.Event`). A missing field is
  `""`, never absent — TSV columns and route files depend on it.
- Dedupe compares the act, not the room: podiuminfo writes "Gzuz @ Melkweg" for
  the gig Melkweg calls "GZUZ", so `_title_key` drops the tail after "@". The
  winner keeps every field it states and fills only its blanks from the copy it
  drops — which is where half the feed's start times come from.
- Cheapest tier first: API > JSON-LD > microdata > `<time datetime>` cards >
  rendered browser. Never add a Chrome-based scraper for a site that publishes
  structured data. `loop/probe_sources.py` answers which tier a candidate has.
- Read robots.txt before adding a source, with `RobotFileParser.parse()` on a body
  fetched through our own `get()`. `RobotFileParser.read()` reports "disallowed"
  for any host that 403s the fetch, which is four of the sites in `CARD_SOURCES`.
  stager.co, which runs the ticketing for most Dutch podia and publishes lovely
  JSON-LD, disallows crawling outright — hence the venue-by-venue card parsers.
- One bad source must not kill a run. `collect()` catches per source and reports it;
  `assess()` turns "returned far less than usual" into a non-zero exit.
- Filters are paths, not query strings — the static server ignores `?`. A new slice
  means a new route in `plan_routes()`.
- `slugify()` in `entities/slug.py` is the single spelling rule, re-exported by
  `publish`; `mcp_server` imports it rather than repeating it, or city routes stop
  resolving. Every entity id is that slug of a canonical name — derived, never stored.
- `entities/` imports nothing from `publish` or `scrape`. `publish` imports it to
  resolve ids, so the arrow only ever points that way.
- The nine legacy event keys keep their names and their TSV order; `venue_id`,
  `city_id` and `artist_ids` were appended after them. New fields append, full stop.
- `/venue/<slug>` stays keyed on the published label, not on `venue_id` — re-keying
  it would rename live URLs.
- Parsers stay pure and stay tested. Anything that needs the network belongs in
  `sources.py` or `browser.py`.
- A golden fixture proves a parser has not *changed*, never that it is *right* —
  captured from a buggy parser it asserts the bug. Every golden therefore has an
  invariant test beside it that asks whether the output makes sense: that is what
  `test_an_event_links_to_itself_and_not_to_the_card_above_it` is for. Add the
  invariant, not just the capture.
- `uv` owns the lockfile. Add deps with `uv add <pkg>`, never edit `[project.dependencies]`.

## Common change patterns

- **Add a source** → for a listing that is only a date next to a heading, one line
  in `CARD_SOURCES` (`scrape/cards.py`) and a rank in `publish.SOURCE_RANK`. Check
  which side the card keeps its link on: if the listing ends the card with a
  "Tickets & info" link rather than wrapping the card in one, add it to
  `LINKS_AFTER` or every event gets the *previous* card's URL;
  otherwise a function in `scrape/sources.py` returning `list[Event]`, an entry in
  `SOURCES`, a city in `SOURCE_CITY` if the source never says where it is, and the
  rank (venues before aggregators). Then capture its golden fixture:
  `uv run python loop/capture_fixture.py <name> <parser> <url> [venue] [dates]`.
- **A scraper went quiet** → `uv run agenda-scraper scrape <name>` prints its rows;
  the parser, not the transport, is almost always what broke.
- **Add a route** → `plan_routes()` in `publish/routes.py`; `_prune()` removes stale
  files, and its subdirectory list needs the new prefix.
- **A source publishes no times** → check where they are before adding requests.
  Some listings print the time above the date (bounded both ways already); some
  state it only on the event page — add the name to `DETAIL_TIMES`
  (`scrape/cards.py`) and `cards()` fetches each timeless event, a second apart,
  via `read_time()`. Sample five pages first: four of the ten candidates
  returned a time five times out of five and the rest returned none, and each
  entry costs one request per timeless event (~8 minutes a run today).
- **A venue is spelt two ways** → one line in `VENUE_ALIAS` (`entities/resolve.py`),
  keyed on the flattened slug. Check `_trim_venue` first: punctuation and room
  suffixes are already handled.
- **Probe a candidate source** → `uv run python loop/probe_sources.py <name>` reports
  the cheapest tier that answers.
- **Add an MCP tool** → a `@server.tool(description=...)` function in `mcp_server.py`.

## Verification

Run `just check` after every change. It composes:

`just-fmt-check` + `loc-check` + `dir-check` + `lint` + `format-check` + `typecheck` + `test`

`just test-live` adds the one test that talks to the published feed (`AGENDA_LIVE=1`).
`uv run agenda-scraper reachability` answers the deployment question instead.

Recipe reference:

- `just install` — `uv sync`
- `just run-cli` — run the CLI (alias `just run`)
- `just lint` / `just lint-fix` — ruff check / `--fix`
- `just format` / `just format-check` — ruff format / `--check`
- `just typecheck` — mypy
- `just test` / `just test-live` — pytest, without / with the network test
- `just loc-check` / `just dir-check` — file-size and per-directory thresholds from `.quality.json`
- `just clean` — remove build artifacts and caches
- `just update-scaffold` — pull updates from the cookiecutter template

## Related context

- [agent.md](agent.md) — verify loop, auto-fix commands, common tasks, boundaries
- [data/llm.txt](data/llm.txt) — the feed's contract, written for the agents that consume it
- `.claude/` — Claude Code settings, scaffold-update hook, library-freshness hook
- `.quality.json` — loc / dir thresholds (single source of truth)
- `schema/` — JSON Schema per entity plus the route envelope; `tests/test_entities.py`
  validates a generated feed against them, and `AGENDA_VALIDATE_DIR=<dir>` points the
  same walk at a real `scrape --all --out` run

### Shared agent journal

Use `./agent-log` (a shim for `atlas agent-log` — both are identical) for short-lived
operational awareness between concurrent agents. It is not chat and not a task tracker: the
issue tracker remains the source of truth for ownership, blockers, and durable findings.

- Run `./agent-log recent` before interpreting shared state.
- Before an action that can change another agent's observations, write an intent with every
  affected scope. This includes shared-worktree edits, generated artifacts, git/index
  mutations, and shared ports, processes, or services.
- Run builds, tests, and deployments through the wrapper so start, commit, dirty state,
  duration, exit code, and outcome are recorded even on failure:
  `./agent-log run build|test|deploy --scope <resource> [--bead <id>] -- <command...>`.
- For manual operations, use `./agent-log begin <operation> --scope <resource> [--bead <id>]
  -- <summary>` and always close the returned id with `./agent-log end <id> --outcome
  ok|failed|cancelled -- <result>`. `<operation>` is one of build, commit, deploy, edit, implement, investigate, merge, push, review, sync, test — what
  makes this particular run specific goes in the summary, never in an invented operation name.
- Record a temporary result-affecting discovery with `./agent-log finding --scope <resource>
  --evidence <fact> [--bead <id>] -- <summary>`. This is the entry that saves another agent a
  wasted run, and the one most often skipped — write one whenever you learn something that
  would change what a concurrent agent does next, especially a dead end. Promote lasting
  knowledge to the issue tracker or the relevant doc.
- At session end, write `./agent-log handoff -- <stopping point + next step>` — the durable
  baton the next session's briefing picks up. Handoffs never expire; the latest one is
  always shown by `recent`.
- Intents expire after 20 minutes and findings after 4 hours unless `--ttl` overrides them.
  Renew by closing and reopening an intent; never treat an expired entry as current.
- Keep summaries factual and short. Do not reply, ask questions, mention agents, narrate
  routine progress, or log isolated reads/edits/tests that cannot affect anyone else.

Canonical scopes are `path:<repo-relative-path>`, `artifact:<name>`, `service:<name>`,
`host:<name>`, `port:<number>`, and `git:<worktree-or-ref>`; a repo may define additional
canonical scopes of its own. Add multiple `--scope` flags when needed. The journal SQLite db
lives in the git common directory, so linked worktrees share it without dirtying the repo.
