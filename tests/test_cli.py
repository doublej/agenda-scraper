"""The CLI wiring, without touching the network."""

import json

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


def test_archive_import_folds_a_saved_snapshot_in_at_its_own_time(tmp_path):
    event = {
        "source": "paradiso",
        "date": "2026-09-05",
        "end": "",
        "time": "20:30",
        "title": "Bokoesam",
        "venue": "Paradiso",
        "city": "Amsterdam",
        "status": "",
        "url": "https://paradiso.nl/x",
    }
    snap = tmp_path / "events.json"
    snap.write_text(
        json.dumps({"generated_at": "2026-09-02T18:20:22+0200", "events": [event]})
    )
    result = CliRunner().invoke(
        main, ["archive-import", str(snap), "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    (row,) = [json.loads(line) for line in (tmp_path / "archive.jsonl").open()]
    assert (row["title"], row["venue_id"]) == ("Bokoesam", "paradiso")
    assert row["first_seen"] == row["last_seen"] == "2026-09-02T16:20:22Z"
