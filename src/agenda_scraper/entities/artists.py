"""Performer names lifted out of an event title.

A title is the only artist signal the sources give: none of them publish a
lineup field. So this is a heuristic, and it says so — every name comes back
with a confidence, and the caller is free to ignore the low ones.

The rule, in order: cut bracketed noise, cut a promoter's "X presents" or
"Brand:" prefix, split on the separators promoters actually use, then drop the
parts that name a genre, a format or a night rather than a performer.
"""

import re

from agenda_scraper.entities.models import Artist
from agenda_scraper.entities.slug import slugify

__all__ = ["extract_artists"]

MAX_WORDS = 6  # longer than this and it is a sentence, not a name
MAX_CHARS = 60

# "(Metal-Punk-Goth)", "[sold out]", "(0,5+)" — never part of a name.
_NOISE = re.compile(r"\s*[(\[{][^)\]}]*[)\]}]")
# "Lucid Recordings presents - Rhythmism" -> everything after the handoff.
_PRESENTS = re.compile(
    r"^.{2,60}?\s+(?:presents?|presenteert|pres\.|invites|invite)\s*[-–—:]?\s+(?=\S)",
    re.IGNORECASE,
)
# "RAVING CHARLIE: Hard Techno / Rave" — a brand, then the actual bill.
_BRAND = re.compile(r"^[^:]{2,40}:\s*(?=\S)")
# Separators must have whitespace on both sides, so "R&B" and "Subs&Dubs" survive.
_SPLIT = re.compile(r"\s+(?:&|\+|//|/|x|b2b|vs\.?|w/|feat\.?|ft\.?)\s+", re.IGNORECASE)

# A part that is one of these names a genre, a format or a filler, never an act.
_STOP_WORDS = """
    live liveset dj djs djset bandje band support guests specialguest friends
    friendsandfamily more andmore aftershow afterparty warmup opening closing
    residents resident vj host hosts tba tbc unknown various variousartists
    allnightlong nightprogramme dayprogramme freeentry gratis entree
    techno hardtechno house deephouse technohouse trance hardstyle hardcore
    gabber rave dnb drumandbass jungle dubstep garage disco italodisco funk
    soul jazz blues folk metal punk goth rock indie pop hiphop rap rnb reggae
    dancehall afro afrohouse amapiano ambient experimental noise klassiek
    opera electro electronic minimal acid breaks psytrance
"""
_STOP_PART = frozenset(_STOP_WORDS.split())
# Titles that name an event format. Nobody performs at a pub quiz.
_SKIP_TITLE = re.compile(
    r"\b(?:pubquiz|pub quiz|quiz|bingo|karaoke|open podium|open mic|open stage|"
    r"jam ?sessie|spelletjes|filmavond|film|expo|expositie|workshop|lezing|"
    r"cursus|rondleiding|markt|borrel|dagje|matinee|silent disco|"
    r"battle of the bands|kerstborrel|nieuwjaars(?:borrel|receptie)|"
    r"vrijmibo|meet ?& ?greet|signeersessie)\b",
    re.IGNORECASE,
)


def _flat(name: str) -> str:
    return slugify(name).replace("-", "")


def _trim_part(part: str) -> str:
    """Drop a trailing "live" / "dj set" that qualifies the act, not names it."""
    words = part.split()
    while len(words) > 1 and _flat(words[-1]) in _STOP_PART:
        words.pop()
    return " ".join(words)


def _plausible(part: str) -> bool:
    return (
        2 <= len(part) <= MAX_CHARS
        and len(part.split()) <= MAX_WORDS
        and re.search(r"[a-zA-Z]", part) is not None
        and _flat(part) not in _STOP_PART
    )


def extract_artists(title: str) -> list[Artist]:
    """Names the title seems to promise, with how much the rule trusts each one."""
    if not title or _SKIP_TITLE.search(title):
        return []
    clean = _NOISE.sub("", title).strip(" -–—:|")
    trimmed = _PRESENTS.sub("", clean, count=1)
    if trimmed == clean:
        trimmed = _BRAND.sub("", clean, count=1)
    cut_a_prefix = trimmed != clean

    # Judge the part whole before trimming, or "Hard Techno" survives as "Hard".
    parts = [p.strip(" -–—:|.") for p in _SPLIT.split(trimmed)]
    parts = [_trim_part(p) for p in parts if _plausible(p)]
    parts = [p for p in parts if _plausible(p)]
    if not parts:
        return []
    confidence = "high" if len(parts) > 1 else "low" if cut_a_prefix else "medium"

    out: list[Artist] = []
    seen: set[str] = set()
    for part in parts:
        aid = slugify(part)
        if not aid or aid in seen:
            continue
        seen.add(aid)
        out.append({"id": aid, "name": part, "confidence": confidence})
    return out
