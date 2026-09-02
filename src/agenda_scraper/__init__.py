"""Concerts, club nights and festivals across the Netherlands, as a static feed."""

# One scraped event. Every value is a string so a row survives JSON, TSV and the
# route files unchanged; a missing field is "" rather than absent.
Event = dict[str, str]

# What one source did in one run: {"ok": bool, "count": int, "error": str}.
Report = dict[str, dict]

__all__ = ["Event", "Report"]
