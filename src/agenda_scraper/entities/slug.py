"""The one spelling rule. Anything that becomes a URL segment or an id goes through it.

It lives here rather than in publish because entity ids are built on it and
publish imports entities, not the other way round. `publish.slugify` still
re-exports it, so every existing caller keeps the same import.
"""

import re
import unicodedata

__all__ = ["slugify"]


def slugify(name: str) -> str:
    """ "Den Haag" -> "den-haag". Stable enough to be part of a URL."""
    flat = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", flat.lower())).strip("-")
