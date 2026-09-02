"""The parsers, on the markup shapes that actually broke them once."""

from agenda_scraper.scrape.parsers import parse_jsonld, parse_paradiso, parse_tivoli


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
