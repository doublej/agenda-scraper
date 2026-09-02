# agenda-scraper

> Concerts, club nights and festivals across the Netherlands, scraped and republished as static JSON/TSV

## Stack

- Python 3.13, uv, ruff, mypy, pytest
- CLI framework: Click; MCP server: the official `mcp` SDK (`MCPServer`, stdio)
- Everything else is stdlib: urllib for HTTP, regex for parsing, `websocket-client` for CDP

## Commands

Use `just` as the task runner:

- `just check` — run all checks (just-fmt-check + loc-check + dir-check + lint + format-check + typecheck + test)
- `just install` — sync dependencies (`uv sync`)
- `just run <args>` — run the CLI
- `just lint` / `just lint-fix` — ruff check / --fix
- `just format` / `just format-check` — ruff format / --check
- `just typecheck` — mypy
- `just test` / `just test-live` — pytest, without / with the one network test
- `just loc-check` / `just dir-check` — file lengths / files per directory (`.quality.json`)
- `just clean` — remove build artifacts and caches
- `just update-scaffold` — pull updates from the cookiecutter template

## Project Structure

```
src/agenda_scraper/
├── cli.py            # Click entry point — scrape / sources / reachability / mcp
├── config.py         # every path, URL and knob, all env-overridable
├── publish.py        # dedupe, health assessment, route files
├── reachability.py   # is the published feed readable from the internet?
├── mcp_server.py     # MCP tools search() / cities() / venues()
└── scrape/           # http.py, browser.py, parsers.py, sources.py, collect()
tests/                # parsers, publish, feed helpers, CLI wiring
data/                 # the published feed (gitignored except the hand-written docs)
refresh.sh            # what the systemd timer runs
```

## Conventions

- src/ layout with hatchling build backend; entry point `agenda_scraper.cli:main`
- An event is a flat `dict[str, str]`; missing fields are `""`, never absent
- Parsers are pure and tested; anything networked lives in `sources.py` / `browser.py`
- Keep functions small (5–10 lines target, 20 max)
- Handle errors at boundaries; the one blind `except` (per-source failure) is deliberate

## Agent

### Verify Loop

Run after every change: `just check`

Step-by-step alternative:

1. `just lint-fix`
2. `just format`
3. `just typecheck`
4. `just test`

### Delegating verification

Don't block on `just check` while a feature is still in progress — hand it to the
`verify-runner` subagent and keep building. It applies safe auto-fixes itself and writes
anything it can't safely resolve to `.claude/tickets/` instead of stopping you. Read
`.claude/tickets/` before treating a feature as done, and delete a ticket once you've
confirmed its issue is fixed.

### Auto-fixable

- `uv run ruff check --fix src/ tests/` — auto-fix lint issues
- `uv run ruff format src/ tests/` — format code

### Common Tasks

- Add a source: a function in `scrape/sources.py` + an entry in `SOURCES` + a rank in
  `publish.SOURCE_RANK` (+ `SOURCE_CITY` when the source never names a city)
- Debug a quiet scraper: `uv run agenda-scraper scrape <name>` prints its rows to stdout
- Add a route: `plan_routes()` in `publish.py`
- Add an MCP tool: a `@server.tool(description=...)` function in `mcp_server.py`
- Add a dependency: `uv add <package>`

### Testing

- Test files: `tests/test_*.py`
- Use `click.testing.CliRunner` for CLI tests
- The live feed test is skipped unless `AGENDA_LIVE=1` (`just test-live`)
- Run a single test: `uv run pytest tests/test_parsers.py::test_name -v`

### Boundaries

- Do not deploy, publish, or push
- Do not modify `[tool.*]` sections in `pyproject.toml` without asking
- Do not hit a venue site in a loop: the aggregators ask for a 1s crawl delay and
  `paged_jsonld` honours it
