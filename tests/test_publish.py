"""Dedupe, the horizon and the health assessment."""

from agenda_scraper.publish import (
    VENUE_MIN_EVENTS,
    annotate,
    as_tsv,
    assess,
    current,
    dedupe,
    plan_routes,
    slugify,
    write_out,
)
from agenda_scraper.publish.archive import ARCHIVE_FILE, dump, load, merge


def test_slugify_flattens_a_city_into_a_url_segment():
    assert slugify("Den Haag") == "den-haag"
    assert slugify("'s-Hertogenbosch") == "s-hertogenbosch"


def test_dedupe_keeps_the_venue_over_the_aggregator():
    rows = [
        {
            "date": "2026-09-01",
            "time": "20:00",
            "title": "Bokoesam!",
            "venue": "Paradiso",
            "city": "Amsterdam",
            "source": "podiuminfo",
        },
        {
            "date": "2026-09-01",
            "time": "20:30",
            "title": "Bokoesam",
            "venue": "Paradiso",
            "city": "Amsterdam",
            "source": "paradiso",
        },
        {
            "date": "2026-09-01",
            "time": "22:00",
            "title": "Bokoesam",
            "venue": "Doornroosje",
            "city": "Nijmegen",
            "source": "podiuminfo",
        },
    ]
    assert [(e["source"], e["city"]) for e in dedupe(rows)] == [
        ("paradiso", "Amsterdam"),
        ("podiuminfo", "Nijmegen"),
    ]


def test_current_keeps_a_festival_that_is_still_running():
    rows = [
        {"date": "2026-08-01", "end": "2026-09-30"},
        {"date": "2026-08-01", "end": ""},
    ]
    assert len(current(rows, today="2026-09-01")) == 1


def test_assess_learns_a_norm_and_then_catches_a_silent_regression(tmp_path):
    hist = tmp_path / "baseline.json"
    good = {"a": {"ok": True, "count": 100}}
    assert assess(good, hist) == []  # first run: no norm yet
    for _ in range(3):
        assess(good, hist)

    assert assess({"a": {"ok": True, "count": 40}}, hist) == [
        "a: 40 events, normally ~100"
    ]
    assert assess({"a": {"ok": True, "count": 0}}, hist) == ["a: returned 0 events"]
    assert assess({"a": {"ok": False, "count": 0, "error": "boom"}}, hist) == [
        "a: failed — boom"
    ]
    # a bad run must not drag the norm down
    assert assess({"a": {"ok": True, "count": 95}}, hist) == []


def test_the_tsv_row_still_starts_with_the_nine_legacy_columns():
    row = {
        "source": "paradiso",
        "date": "2026-09-01",
        "end": "",
        "time": "20:30",
        "title": "Bokoesam",
        "venue": "Paradiso",
        "city": "Amsterdam",
        "status": "",
        "url": "https://www.paradiso.nl/x",
    }
    legacy = as_tsv([row]).split("\t")
    assert legacy[:9] == [
        "paradiso",
        "2026-09-01",
        "",
        "20:30",
        "Bokoesam",
        "Paradiso",
        "Amsterdam",
        "",
        "https://www.paradiso.nl/x",
    ]
    # The ids append after them, so a consumer splitting on tabs keeps working.
    assert as_tsv(annotate([row])).split("\t")[9:] == [
        "paradiso",
        "amsterdam",
        "bokoesam",
    ]


def test_two_spellings_of_one_venue_plan_a_single_route():
    """routes.json promised venue/mezz twice and only one file could exist.

    "MEZZ" and "Mezz" are different labels and one slug, so both planned a
    route, the second overwrote the first on disk, and the index advertised a
    route count one higher than the number of files. Merging them also means
    the per-venue minimum sees the combined count, which is what it meant.
    """
    rows = annotate(
        [
            {
                "source": "x",
                "date": f"2026-09-{i % 28 + 1:02d}",
                "end": "",
                "time": "",
                "title": f"Act {i}",
                "venue": "MEZZ" if i % 2 else "Mezz",
                "city": "Breda",
                "status": "",
                "url": f"https://example.nl/{i}",
            }
            for i in range(VENUE_MIN_EVENTS + 2)
        ]
    )
    routes = plan_routes(rows)
    paths = [path for path, _, _ in routes]
    assert len(paths) == len(set(paths)), "a route path is advertised twice"
    venues = [(path, len(evs)) for path, _, evs in routes if path.startswith("venue/")]
    assert venues == [("venue/mezz", VENUE_MIN_EVENTS + 2)]


def _pair():
    """The same gig from a venue that states no time and an aggregator that does."""
    base = {
        "source": "",
        "date": "2026-09-05",
        "end": "",
        "time": "",
        "title": "Bokoesam",
        "venue": "Paradiso",
        "city": "",
        "status": "",
        "url": "",
    }
    return (
        {**base, "source": "paradiso", "url": "https://paradiso.nl/x"},
        {
            **base,
            "source": "podiuminfo",
            "time": "20:30",
            "city": "Amsterdam",
            "url": "https://podiuminfo.nl/y",
        },
    )


def test_dedupe_takes_the_time_from_the_copy_it_drops():
    """Half the venue listings print no door time; the aggregators nearly always do.

    Dropping the duplicate outright published the gig timeless because the more
    trustworthy source was the quieter one. The venue still wins every field it
    actually states — only its blanks get filled.
    """
    venue, aggregator = _pair()
    (e,) = dedupe(annotate([venue, aggregator]))
    assert e["source"] == "paradiso"
    assert e["url"] == "https://paradiso.nl/x"  # never the aggregator's link
    assert e["time"] == "20:30"
    assert e["city"] == "Amsterdam" and e["city_id"] == "amsterdam"


def test_the_fill_does_not_depend_on_which_copy_arrives_first():
    venue, aggregator = _pair()
    for order in ([venue, aggregator], [aggregator, venue]):
        (e,) = dedupe(annotate(order))
        assert (e["source"], e["time"], e["url"]) == (
            "paradiso",
            "20:30",
            "https://paradiso.nl/x",
        )


def _gig(**fields):
    base = {
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
    return annotate([{**base, **fields}])[0]


def test_an_archived_event_survives_a_run_that_no_longer_scrapes_it(tmp_path):
    report = {"paradiso": {"ok": True, "count": 1}}
    gone, kept = _gig(title="Gone"), _gig(title="Kept")
    write_out(tmp_path, [gone, kept], report, tmp_path / "h.json", log=lambda _: None)
    write_out(tmp_path, [kept], report, tmp_path / "h.json", log=lambda _: None)
    titles = {r["title"] for r in load(tmp_path / ARCHIVE_FILE).values()}
    assert titles == {"Gone", "Kept"}


def test_a_later_sighting_updates_a_field_but_never_blanks_one():
    first = merge({}, [_gig(status="")], "2026-09-01T10:00:00Z")
    later = merge(first, [_gig(time="", status="Sold out")], "2026-09-02T10:00:00Z")
    (row,) = later.values()
    assert (row["time"], row["status"]) == ("20:30", "Sold out")
    assert (row["first_seen"], row["last_seen"]) == (
        "2026-09-01T10:00:00Z",
        "2026-09-02T10:00:00Z",
    )


def test_the_venue_copy_and_the_aggregator_copy_archive_as_one_row():
    rows = merge({}, [_gig()], "2026-09-01T10:00:00Z")
    rows = merge(rows, [_gig(title="Bokoesam @ Paradiso")], "2026-09-02T10:00:00Z")
    assert len(rows) == 1


def test_merging_is_idempotent_and_survives_a_round_trip(tmp_path):
    once = merge({}, [_gig()], "2026-09-01T10:00:00Z")
    assert merge(once, [_gig()], "2026-09-01T10:00:00Z") == once
    (tmp_path / ARCHIVE_FILE).write_text(dump(once))
    assert load(tmp_path / ARCHIVE_FILE) == once


def test_an_older_snapshot_fills_gaps_but_does_not_overwrite_newer_facts():
    newer = merge({}, [_gig(status="Sold out", time="")], "2026-09-02T10:00:00Z")
    (row,) = merge(newer, [_gig(status="")], "2026-08-20T10:00:00Z").values()
    assert (row["status"], row["time"]) == ("Sold out", "20:30")
    assert (row["first_seen"], row["last_seen"]) == (
        "2026-08-20T10:00:00Z",
        "2026-09-02T10:00:00Z",
    )
