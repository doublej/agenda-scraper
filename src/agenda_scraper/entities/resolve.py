"""Free-text venue and city labels -> deterministic ids.

An id is the slug of the canonical name: stable between runs, readable in a
URL, and derived rather than stored, so nothing has to be migrated when a new
source starts spelling a venue a fourth way.

Matching is done on a *flattened* key (the slug with its dashes removed) so
"TivoliVredenburg", "Tivoli Vredenburg" and "tivoli/vredenburg" all land on the
same entry without one alias line each.
"""

import re

from agenda_scraper.entities.models import City, Venue
from agenda_scraper.entities.slug import slugify

__all__ = ["CITY_ALIAS", "VENUE_ALIAS", "resolve_city", "resolve_venue"]

# One spelling per city, so /city/<slug> does not split in two. scrape.collect()
# applies it while normalising, and resolve_city() applies it again for callers
# that never went through the scrapers.
CITY_ALIAS = {
    "The Hague": "Den Haag",
    "'s-Gravenhage": "Den Haag",
    "Den Bosch": "'s-Hertogenbosch",
    "s-Hertogenbosch": "'s-Hertogenbosch",
    "Hertogenbosch": "'s-Hertogenbosch",
    "Amsterdam-Zuidoost": "Amsterdam",
    "Amsterdam Zuidoost": "Amsterdam",
    "Amsterdam-Noord": "Amsterdam",
    "Rotterdam-Zuid": "Rotterdam",
    "The Netherlands": "",
    "Nederland": "",
    "Netherlands": "",
}

# Venue spellings that differ by more than punctuation, keyed on the flattened
# form of what a source publishes. Only add a line when the flattening rules
# below genuinely cannot bridge the two spellings.
VENUE_ALIAS = {
    "tivolivredenburg": "TivoliVredenburg",
    "tivoli": "TivoliVredenburg",
    "vredenburg": "TivoliVredenburg",
    "dehelling": "De Helling",
    "helling": "De Helling",
    "ekko": "EKKO",
    "dbs": "dB's",
    "dbsstudio": "dB's",
    "dbstudio": "dB's",
    "musicon": "Musicon",
    "rotown": "Rotown",
    "muziekgieterij": "Muziekgieterij",
    "paradiso": "Paradiso",
    "paradisonoord": "Paradiso Noord",
    "melkweg": "Melkweg",
    "patronaat": "Patronaat",
    "doornroosje": "Doornroosje",
    "effenaar": "Effenaar",
    "013": "013",
    "poppodium013": "013",
    "013poppodium": "013",
    "paard": "Paard",
    "paardvantroje": "Paard",
    "vera": "Vera",
    "veragroningen": "Vera",
    "simplon": "Simplon",
    "hedon": "Hedon",
    "neushoorn": "Neushoorn",
    "metropool": "Metropool",
    "gebrdenobel": "Gebr. de Nobel",
    "gebrdenobelleiden": "Gebr. de Nobel",
    "bibelot": "Bibelot",
    "volt": "Volt",
    "tolhuistuin": "Tolhuistuin",
    "lantarenvenster": "LantarenVenster",
    "bitterzoet": "Bitterzoet",
    "burgerweeshuis": "Burgerweeshuis",
}

# Words a source glues onto a venue name that say what it is, not which it is.
_VENUE_PREFIX = re.compile(
    r"^(?:poppodium|podium|popcentrum|cultuurpodium|concertzaal|muziekcentrum)\s+",
    re.IGNORECASE,
)
# A room, hall or floor — the part of "Melkweg (Oude Zaal)" that is not the venue.
_ROOM = re.compile(
    r"\b(?:zaal|zalen|hal|foyer|kelder|bovenzaal|benedenzaal|upstairs|downstairs|"
    r"main\s*room|main\s*stage|small\s*room|club\s*room|stage|floor|balcony)\b",
    re.IGNORECASE,
)
# Only these two shapes are ever cut; anything else is treated as part of the name.
_BRACKET_TAIL = re.compile(r"\s*[(\[]([^()\[\]]*)[)\]]\s*$")
_DASH_TAIL = re.compile(r"\s+[-–—]\s+([^-–—]+)$")


def _flat(name: str) -> str:
    """Slug with its dashes removed — spelling differences fall away."""
    return slugify(name).replace("-", "")


def _trim_venue(name: str, city: str) -> str:
    """Strip the decoration a source hangs off a venue name, and nothing else.

    Deliberately timid: over-trimming merges two real venues into one id, which
    is a far worse failure than leaving "Melkweg Oude Zaal" as its own label.
    """
    out = _VENUE_PREFIX.sub("", " ".join(name.split())).strip()
    for pattern in (_BRACKET_TAIL, _DASH_TAIL):
        m = pattern.search(out)
        if m and _ROOM.search(m.group(1)):
            out = out[: m.start()].strip()
    # "Vera, Groningen" -> "Vera", but only when the tail is the city we were
    # handed; a comma inside a name ("Kade, Zaandam") is left alone otherwise.
    head, sep, tail = out.rpartition(",")
    if sep and city and _flat(tail) == _flat(city):
        out = head.strip()
    return out.strip(" -,|")


def resolve_city(name: str) -> City:
    """Canonical city record. An unknown or empty name resolves to id ""."""
    clean = CITY_ALIAS.get(name.strip(), name.strip())
    clean = CITY_ALIAS.get(clean, clean)
    return {"id": slugify(clean), "name": clean}


def resolve_venue(name: str, city: str = "") -> Venue:
    """Canonical venue record, with the city it sits in when a source named one.

    ponytail: the id is the venue slug alone, so two venues that share a name in
    different cities would merge. Prefix the id with the city slug if that ever
    turns up in the registry — nothing outside this function reads the shape.
    """
    trimmed = _trim_venue(name, city)
    canonical = VENUE_ALIAS.get(_flat(trimmed), trimmed)
    resolved_city = resolve_city(city)
    return {
        "id": slugify(canonical),
        "name": canonical,
        "city": resolved_city["name"],
        "city_id": resolved_city["id"],
    }
