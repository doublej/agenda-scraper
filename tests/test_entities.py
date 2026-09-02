"""The entity model: ids, artist extraction, and the published feed's schemas.

The schema test is the one that matters. It builds a real feed with `write_out`
and validates every JSON file it produced, so a field that silently changes
shape fails here rather than in somebody's agent three days later. Point
AGENDA_VALIDATE_DIR at a `scrape --all --out` directory to run the same walk
over a live run.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from agenda_scraper.entities import (
    LEGACY_FIELDS,
    SCHEMA_VERSION,
    extract_artists,
    resolve_city,
    resolve_venue,
)
from agenda_scraper.publish import FIELDS, build_registries, write_out

SCHEMA_DIR = Path(__file__).resolve().parents[1] / "schema"


def _validator() -> Draft202012Validator:
    """The envelope schema, with the four entity schemas resolvable by file name."""
    resources = [
        (p.name, Resource.from_contents(json.loads(p.read_text())))
        for p in sorted(SCHEMA_DIR.glob("*.schema.json"))
    ]
    envelope = json.loads((SCHEMA_DIR / "envelope.schema.json").read_text())
    return Draft202012Validator(envelope, registry=Registry().with_resources(resources))


def validate_feed(out_dir: Path) -> list[str]:
    """Every published .json in `out_dir`, as a list of "file: problem" strings."""
    validator = _validator()
    problems = []
    for path in sorted(out_dir.rglob("*.json")):
        doc = json.loads(path.read_text(encoding="utf8"))
        for err in validator.iter_errors(doc):
            where = "/".join(str(p) for p in err.absolute_path) or "(root)"
            problems.append(f"{path.relative_to(out_dir)}: {where}: {err.message}")
    return problems


def _sample_events() -> list[dict]:
    soon = str(date.today() + timedelta(days=3))
    later = str(date.today() + timedelta(days=30))
    return [
        {
            "source": "paradiso",
            "date": soon,
            "end": "",
            "time": "20:30",
            "title": "Dixon b2b Jimi Jules + Gizem [sold out]",
            "venue": "Paradiso",
            "city": "Amsterdam",
            "status": "Sold out",
            "url": "https://www.paradiso.nl/programma/x/1",
        },
        {  # the aggregator's copy of the same night, spelt without a city
            "source": "podiuminfo",
            "date": soon,
            "end": "",
            "time": "21:00",
            "title": "Dixon b2b Jimi Jules + Gizem",
            "venue": "Paradiso",
            "city": "",
            "status": "",
            "url": "https://www.podiuminfo.nl/x",
        },
        {  # a festival that spans days, and a venue nobody named a city for
            "source": "festivalinfo",
            "date": soon,
            "end": later,
            "time": "",
            "title": "Down The Rabbit Hole",
            "venue": "",
            "city": "Ewijk",
            "status": "",
            "url": "https://www.festivalinfo.nl/y",
        },
        {
            "source": "ra-nl",
            "date": later,
            "end": "",
            "time": "23:00",
            "title": "Pubquiz",
            "venue": "Vera, Groningen",
            "city": "Groningen",
            "status": "",
            "url": "https://ra.co/events/1",
        },
    ]


def test_a_generated_feed_matches_every_schema(tmp_path):
    report = {"paradiso": {"ok": True, "count": 1}}
    write_out(
        tmp_path / "feed",
        _sample_events(),
        report,
        tmp_path / "history.json",
        log=lambda _: None,
    )
    assert validate_feed(tmp_path / "feed") == []
    envelope = json.loads((tmp_path / "feed" / "events.json").read_text())
    assert envelope["schema_version"] == SCHEMA_VERSION


def test_a_published_run_matches_every_schema():
    """Set AGENDA_VALIDATE_DIR to a real `scrape --all --out` directory."""
    out_dir = os.environ.get("AGENDA_VALIDATE_DIR")
    if not out_dir:
        pytest.skip("AGENDA_VALIDATE_DIR not set")
    assert validate_feed(Path(out_dir)) == []


def test_the_tsv_columns_are_the_nine_legacy_ones_then_the_new_ids():
    assert FIELDS[:9] == LEGACY_FIELDS
    assert LEGACY_FIELDS == (
        "source",
        "date",
        "end",
        "time",
        "title",
        "venue",
        "city",
        "status",
        "url",
    )
    assert FIELDS[9:] == ("venue_id", "city_id", "artist_ids")


def test_a_city_resolves_through_its_aliases_to_one_spelling():
    assert resolve_city("The Hague") == {"id": "den-haag", "name": "Den Haag"}
    assert resolve_city("Den Bosch")["id"] == "s-hertogenbosch"
    assert resolve_city("")["id"] == ""


def test_a_venue_loses_its_room_and_its_city_but_never_its_name():
    assert resolve_venue("Melkweg (Oude Zaal)", "Amsterdam")["id"] == "melkweg"
    assert resolve_venue("Vera, Groningen", "Groningen")["id"] == "vera"
    assert resolve_venue("Poppodium 013", "Tilburg")["id"] == "013"
    # A name that merely looks like a room suffix is left whole.
    assert resolve_venue("Paard van Troje", "Den Haag")["name"] == "Paard"
    assert resolve_venue("Gebr. de Nobel", "Leiden")["id"] == "gebr-de-nobel"
    assert resolve_venue("", "")["id"] == ""


def test_the_same_venue_spelt_three_ways_gets_one_id():
    ids = {
        resolve_venue(name, "Utrecht")["id"]
        for name in ("TivoliVredenburg", "Tivoli Vredenburg", "tivoli/vredenburg")
    }
    assert ids == {"tivolivredenburg"}


def test_a_lineup_splits_on_the_separators_promoters_actually_use():
    got = extract_artists("Dixon b2b Jimi Jules + Gizem [sold out]")
    assert [a["name"] for a in got] == ["Dixon", "Jimi Jules", "Gizem"]
    assert {a["confidence"] for a in got} == {"high"}


def test_a_promoter_prefix_is_cut_and_the_names_left_say_so():
    got = extract_artists("Lucid Recordings presents - Rhythmism")
    assert [(a["name"], a["confidence"]) for a in got] == [("Rhythmism", "low")]


def test_an_ampersand_inside_a_name_is_not_a_separator():
    assert [a["name"] for a in extract_artists("R&B Social")] == ["R&B Social"]


def test_a_genre_a_format_and_a_pub_quiz_are_not_artists():
    assert extract_artists("Pubquiz") == []
    names = [a["name"] for a in extract_artists("Hard Techno / Rave w/ STYC")]
    assert names == ["STYC"]


def test_the_registries_count_what_was_published(tmp_path):
    events = [
        {**e, "venue_id": "", "city_id": "", "artist_ids": ""}
        for e in _sample_events()[:1]
    ]
    venues, cities, artists = build_registries(events)
    assert [(v["id"], v["count"]) for v in venues] == [("paradiso", 1)]
    assert [(c["id"], c["count"]) for c in cities] == [("amsterdam", 1)]
    assert {a["id"] for a in artists} == {"dixon", "jimi-jules", "gizem"}
