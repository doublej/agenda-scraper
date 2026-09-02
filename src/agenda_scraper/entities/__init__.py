"""The entity model behind the flat event rows: venues, cities and artists.

A leaf package on purpose — it imports nothing from `publish` or `scrape`, so
both of those can import it without a cycle. `slug.slugify` lives here for the
same reason: ids are built on it, and `publish` re-exports it unchanged.
"""

from agenda_scraper.entities.artists import extract_artists
from agenda_scraper.entities.models import (
    ENTITY_FIELDS,
    LEGACY_FIELDS,
    SCHEMA_VERSION,
    Artist,
    City,
    Event,
    Venue,
)
from agenda_scraper.entities.resolve import (
    CITY_ALIAS,
    VENUE_ALIAS,
    resolve_city,
    resolve_venue,
)
from agenda_scraper.entities.slug import slugify

__all__ = [
    "CITY_ALIAS",
    "ENTITY_FIELDS",
    "LEGACY_FIELDS",
    "SCHEMA_VERSION",
    "VENUE_ALIAS",
    "Artist",
    "City",
    "Event",
    "Venue",
    "extract_artists",
    "resolve_city",
    "resolve_venue",
    "slugify",
]
