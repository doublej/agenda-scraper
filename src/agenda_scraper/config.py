"""Every path, URL and knob the rest of the package reads, in one place.

All of them are environment-overridable: the scrapers run from a checkout on a
Linux box, the MCP server runs from a laptop that may have no checkout at all,
and the tests run from neither.
"""

import os
from pathlib import Path

# src/agenda_scraper/config.py -> the checkout root (uv installs this editable).
ROOT = Path(os.environ.get("AGENDA_ROOT") or Path(__file__).resolve().parents[2])

DATA_DIR = Path(os.environ.get("AGENDA_DATA_DIR") or ROOT / "data")
CACHE_DIR = Path(os.environ.get("AGENDA_CACHE_DIR") or ROOT / ".logs" / "scrape")
BASELINE = CACHE_DIR / "baseline.json"

# Where the published feed lives when there is no local data dir.
BASE_URL = os.environ.get("AGENDA_BASE_URL", "https://agenda.jurrejan.com").rstrip("/")
# What reachability.py asks before it blames the internet.
LOCAL_URL = os.environ.get("AGENDA_LOCAL_URL", "http://127.0.0.1:5181").rstrip("/")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
CHROME = os.environ.get(
    "AGENDA_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)
CDP_PORT = int(os.environ.get("AGENDA_CDP_PORT", "9333"))
