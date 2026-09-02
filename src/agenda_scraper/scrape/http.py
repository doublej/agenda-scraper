"""Plain HTTP. Stdlib is enough here: one GET, one POST, no sessions, no retries."""

import json
import urllib.request
from typing import Any

from agenda_scraper.config import UA


def get(url: str, headers: dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=30).read().decode("utf8", "replace")


def post_json(
    url: str, payload: dict, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "User-Agent": UA,
            "Content-Type": "application/json",
            **(headers or {}),
        },
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read())
