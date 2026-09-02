"""Health assessment, deduplication, the entity registries and the route files.

Split in two: `feed` decides what an event is (its ids, its horizon, whether it
is a duplicate, whether the run looks healthy), `routes` decides where it is
written. Every name the rest of the package imported from the old single module
is re-exported here, `slugify` included — it now lives in `entities.slug`,
because entity ids are built on it and this package imports entities.
"""

from agenda_scraper.entities.slug import slugify
from agenda_scraper.publish.feed import (
    FIELDS,
    SOURCE_RANK,
    annotate,
    as_tsv,
    assess,
    current,
    dedupe,
    venue_id,
)
from agenda_scraper.publish.routes import (
    ARTIST_MIN_EVENTS,
    CITY_WINDOW,
    CITY_WINDOW_MIN,
    VENUE_MIN_EVENTS,
    WINDOWS,
    build_registries,
    plan_routes,
    write_out,
    write_registries,
    write_routes,
)

__all__ = [
    "ARTIST_MIN_EVENTS",
    "CITY_WINDOW",
    "CITY_WINDOW_MIN",
    "FIELDS",
    "SOURCE_RANK",
    "VENUE_MIN_EVENTS",
    "WINDOWS",
    "annotate",
    "as_tsv",
    "assess",
    "build_registries",
    "current",
    "dedupe",
    "plan_routes",
    "slugify",
    "venue_id",
    "write_out",
    "write_registries",
    "write_routes",
]
