"""Answer one question: can an agent on the internet read this feed right now?

Written after Claude web reported 404s on a site that answered fine from the
LAN. Each check names the layer that broke, because the failure modes look
identical from the outside: a stale A record, a dead server, a Caddy that no
longer proxies, and a missing file all read as "the host is up, the file is
not there".
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from agenda_scraper.config import BASE_URL, LOCAL_URL

HOST = urllib.parse.urlsplit(BASE_URL).hostname or ""
PATHS = ("/health.json", "/routes.json", "/llm.txt", "/")


def _get(url: str, timeout: int = 15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "agenda-reachability/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(200_000)


def dns_matches_wan() -> list[str]:
    """The A record is static at the registrar; the home IP is not."""
    record = subprocess.run(
        ["dig", "+short", "A", HOST, "@1.1.1.1"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    ).stdout.split()
    wan = _get("https://api.ipify.org").decode().strip()
    if not record:
        return [f"DNS: {HOST} has no A record"]
    if wan not in record:
        drifted = (
            f"DNS: {HOST} points at {', '.join(record)}, this line is {wan} — "
            "the ISP lease changed and nothing updates the record"
        )
        return [drifted]
    return []


def serves_locally() -> list[str]:
    try:
        body = _get(f"{LOCAL_URL}/health.json")
    except OSError as exc:
        return [
            f"local: {LOCAL_URL} is not serving — agenda-serve.service down? ({exc})"
        ]
    doc = json.loads(body)
    if not doc.get("healthy"):
        return [f"local: feed reports problems — {'; '.join(doc.get('problems', []))}"]
    return []


def serves_publicly() -> list[str]:
    problems = []
    for path in PATHS:
        try:
            _get(f"{BASE_URL}{path}")
        except urllib.error.HTTPError as exc:
            problems.append(f"public: {path} -> HTTP {exc.code}")
        except OSError as exc:
            problems.append(f"public: {path} unreachable — {exc}")
    return problems


def check() -> list[str]:
    """Every problem between the registrar and the file, in the order they break."""
    return dns_matches_wan() + serves_locally() + serves_publicly()
