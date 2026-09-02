"""The parsers, on the markup shapes that actually broke them once."""

from agenda_scraper.scrape.cards import parse_cards
from agenda_scraper.scrape.parsers import (
    parse_jsonld,
    parse_paradiso,
    parse_tivoli,
    read_time,
)


def test_tivoli_reads_the_date_from_the_slug_and_drops_duplicates():
    html = (
        '<a href="https://www.tivolivredenburg.nl/agenda/57200310/hush-aat-29-08-2026">x</a>'
        '<a href="/agenda/57200310/hush-aat-29-08-2026">dup</a>'
    )
    assert parse_tivoli(html) == [
        {
            "date": "2026-08-29",
            "time": "",
            "title": "hush aat",
            "venue": "TivoliVredenburg",
            "url": "https://www.tivolivredenburg.nl/agenda/57200310/hush-aat-29-08-2026",
        }
    ]


def test_paradiso_groups_events_under_day_headings_and_rolls_the_year():
    html = (
        "<div>Su 15 Nov</div>"
        '<a href="/en/program/bokoesam/2908023"><h2> Bokoesam</h2><span>20:30</span></a>'
        '<a href="/en/program/bokoesam/2908023"><h2> Bokoesam</h2></a>'
        "<div>Fr 2 Jan</div>"
        '<a href="/programma/nyx/1"><h2>NYX</h2></a>'
    )
    rows = parse_paradiso(html, start_year=2026)
    assert [(e["date"], e["title"], e["time"], e["status"]) for e in rows] == [
        ("2026-11-15", "Bokoesam", "20:30", ""),
        ("2027-01-02", "NYX", "", ""),  # a lone title is not a status
    ]


def test_paradiso_reads_a_status_badge_where_a_time_would_be():
    html = '<div>Fr 2 Jan</div><a href="/programma/x/2"><h2>X</h2><span>Sold out</span></a>'
    row = parse_paradiso(html, start_year=2026)[0]
    assert (row["time"], row["status"]) == ("", "Sold out")


def test_jsonld_unescapes_and_splits_a_flat_event():
    html = (
        '<script type="application/ld+json">{"@type":"MusicEvent",'
        '"name":"Cyberia &amp; Rotersand","startDate":"2026-08-28 20:50:00",'
        '"location":{"name":"De Helling"},"url":"https://x"}</script>'
    )
    assert parse_jsonld(html) == [
        {
            "date": "2026-08-28",
            "end": "",
            "time": "20:50",
            "title": "Cyberia & Rotersand",
            "venue": "De Helling",
            "city": "",
            "country": "",
            "url": "https://x",
        }
    ]


def test_jsonld_flattens_an_itemlist_and_reads_a_postal_address():
    html = (
        '<script type="application/ld+json">{"@type":"ItemList",'
        '"itemListElement":[{"@type":"ListItem","item":{"@type":"Festival",'
        '"name":"Zomerterras","startDate":"2026-08-14","endDate":"2026-08-30",'
        '"location":{"@type":"Place","name":"Zomerterras","address":'
        '{"addressLocality":"Vlaardingen"}},"url":"https://f"}}]}</script>'
    )
    assert parse_jsonld(html) == [
        {
            "date": "2026-08-14",
            "end": "2026-08-30",
            "time": "",
            "title": "Zomerterras",
            "venue": "Zomerterras",
            "city": "Vlaardingen",
            "country": "",
            "url": "https://f",
        }
    ]


def test_jsonld_ignores_an_unrendered_template():
    html = (
        '<script type="application/ld+json">{"@type":"Event","name":"x",'
        '"startDate":"{{ event.date }}"}</script>'
    )
    assert parse_jsonld(html) == []


def test_a_card_takes_a_time_written_above_it():
    """AFAS Live prints all eighteen of its start times before the date.

    Looking only forward from the date found none of them, so the listing
    published 110 events without a single time.
    """
    html = (
        '<div class="card"><h3>Some Act</h3><time>19:00</time>'
        "<p>zaterdag 5 sep 2026</p></div>"
    )
    (e,) = parse_cards(html, "AFAS Live", "https://x.nl/agenda", "dutch")
    assert e["time"] == "19:00"


def test_a_clock_in_a_script_block_is_not_a_door_time():
    """Melkweg's listing holds 809 clocks in JSON metadata and 2 real ones."""
    html = (
        '<script>{"datePublished":"2025-10-19T21:58:06+00:00"}</script>'
        "<div><h3>Some Act</h3><p>zaterdag 5 sep 2026</p></div>"
    )
    (e,) = parse_cards(html, "Melkweg", "https://x.nl/agenda", "dutch")
    assert e["time"] == "", f"picked a publish timestamp: {e['time']}"


def test_a_time_only_datetime_attribute_wins():
    """Hedon states the door time outright: <time datetime="19:30">."""
    html = (
        "<div><h3>Some Act</h3><p>zaterdag 5 sep 2026</p>"
        '<time datetime="19:30">19:30</time></div>'
    )
    (e,) = parse_cards(html, "Hedon", "https://x.nl/", "dutch")
    assert e["time"] == "19:30"


def test_read_time_prefers_structured_over_prose():
    """A JSON-LD startDate is the site's own answer; the Dutch sentence is a guess."""
    html = (
        '<script type="application/ld+json">{"@type":"Event","name":"x",'
        '"startDate":"2026-09-03T21:00:00+01:00"}</script><p>Deuren open 19:00</p>'
    )
    assert read_time(html) == "21:00"


def test_read_time_reads_the_dutch_sentence_when_there_is_no_json_ld():
    assert read_time("<p>Aanvang 14:00</p>") == "14:00"
    assert read_time("<p>Deuren open om 18:30</p>") == "18:30"
    # Gebr. de Nobel writes "Start Swingo 23:30" — words between cue and clock.
    assert read_time("<p>Start Swingo 23:30</p>") == "23:30"


def test_read_time_ignores_a_timestamp_in_a_script_block():
    html = '<script>{"datePublished":"2020-01-01T09:15:00"}</script><p>geen tijd</p>'
    assert read_time(html) == ""


def test_read_time_says_nothing_rather_than_guessing():
    assert read_time("<p>Een avond vol muziek.</p>") == ""
