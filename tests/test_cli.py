"""The CLI wiring, without touching the network."""

from click.testing import CliRunner

from agenda_scraper.cli import main
from agenda_scraper.scrape import SOURCES


def test_sources_lists_every_registered_source():
    result = CliRunner().invoke(main, ["sources"])
    assert result.exit_code == 0
    assert result.output.split() == list(SOURCES)


def test_scrape_without_a_source_says_so_instead_of_scraping_everything():
    result = CliRunner().invoke(main, ["scrape"])
    assert result.exit_code == 2
    assert "name a source or pass --all" in result.output
