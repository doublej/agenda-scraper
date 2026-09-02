"""The shapes the feed publishes: the event row, and the three registries behind it.

An event stays a flat `dict[str, str]` on the wire — the TSV columns and every
route file depend on it — so the new id fields are strings too and `artist_ids`
is a comma-separated list rather than a nested array. The registries are JSON
only, so they may carry integers.

SCHEMA_VERSION is the first version the feed has ever stamped on itself. Bump
the minor for an additive field, the major when an existing key changes meaning.
"""

from typing import NotRequired, TypedDict

SCHEMA_VERSION = "1.0.0"

# The nine keys every published event has carried since the feed existed. The
# entity fields append after them; nothing here moves or is renamed.
LEGACY_FIELDS = (
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
ENTITY_FIELDS = ("venue_id", "city_id", "artist_ids")

__all__ = [
    "ENTITY_FIELDS",
    "LEGACY_FIELDS",
    "SCHEMA_VERSION",
    "Artist",
    "City",
    "Event",
    "Venue",
]


class Event(TypedDict):
    """One published event row. Every value is a string; a missing one is ""."""

    source: str
    date: str
    end: str
    time: str
    title: str
    venue: str
    city: str
    status: str
    url: str
    venue_id: str
    city_id: str
    artist_ids: str  # comma-separated Artist ids, "" when none were extracted


class City(TypedDict):
    """A Dutch city, one spelling per city so /city/<slug> never splits in two."""

    id: str
    name: str
    count: NotRequired[int]


class Venue(TypedDict):
    """A room or building. `city` is where it is, "" when no source said."""

    id: str
    name: str
    city: str
    city_id: str
    count: NotRequired[int]


class Artist(TypedDict):
    """A performer name lifted out of an event title.

    `confidence` is how much the extraction rule trusts itself: "high" when an
    explicit separator (+, &, b2b, feat.) framed the name, "medium" when the
    whole title was one clean name, "low" when a brand prefix had to be cut off
    first.
    """

    id: str
    name: str
    confidence: str
    count: NotRequired[int]
