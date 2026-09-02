"""The one entry point: scrape, publish, serve over MCP, check reachability."""

import sys
from pathlib import Path

import click

from agenda_scraper.config import BASELINE, DATA_DIR
from agenda_scraper.publish import annotate, dedupe, write_out
from agenda_scraper.scrape import SOURCES, collect


@click.group()
@click.version_option(package_name="agenda-scraper")
def main() -> None:
    """Concerts, club nights and festivals across the Netherlands."""


@main.command()
@click.argument(
    "names", nargs=-1, type=click.Choice(list(SOURCES)), metavar="[SOURCE]..."
)
@click.option("--all", "every", is_flag=True, help="Run every source.")
@click.option(
    "--out",
    type=click.Path(file_okay=False, path_type=Path),
    is_flag=False,
    flag_value=str(DATA_DIR),
    help=f"Publish feed + routes into this directory (default {DATA_DIR}) "
    "instead of printing TSV. Exits 1 when a source looks unhealthy.",
)
def scrape(names: tuple[str, ...], every: bool, out: Path | None) -> None:
    """Run one or more sources. Without --out, print deduped events as TSV."""
    chosen = list(SOURCES) if every else list(names)
    if not chosen:
        raise click.UsageError(f"name a source or pass --all: {' '.join(SOURCES)}")
    events, report = collect(chosen)
    if out:
        sys.exit(write_out(out, events, report, BASELINE, log=_stderr))
    for e in dedupe(annotate(events)):
        click.echo(
            "\t".join(
                (
                    e["source"],
                    e["date"],
                    e["time"],
                    e["title"],
                    e["venue"],
                    e["city"],
                    e["status"],
                    e["url"],
                )
            )
        )


@main.command()
def sources() -> None:
    """List the source names `scrape` accepts."""
    for name in SOURCES:
        click.echo(name)


@main.command()
def reachability() -> None:
    """Check that the published feed is readable from the internet. Exits 1 if not."""
    from agenda_scraper.reachability import HOST, PATHS, check

    problems = check()
    for p in problems:
        click.echo(p)
    click.echo(
        "unreachable" if problems else f"ok — https://{HOST} serves {len(PATHS)} paths"
    )
    sys.exit(1 if problems else 0)


@main.command()
def mcp() -> None:
    """Serve the published feed over MCP on stdio."""
    from agenda_scraper.mcp_server import run  # heavy import, only this path needs it

    run()


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


if __name__ == "__main__":
    main()
