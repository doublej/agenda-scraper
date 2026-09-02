"""Dedupe, the horizon and the health assessment."""

from agenda_scraper.publish import annotate, as_tsv, assess, current, dedupe, slugify


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
