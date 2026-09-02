#!/usr/bin/env python3
"""Answer one question: can an agent on the internet read this feed right now?

Written after Claude web reported 404s on a site that answered fine from the
LAN. Each check names the layer that broke, because the failure modes look
identical from the outside: a stale A record, a dead server, a Caddy that no
longer proxies, and a missing file all read as "the host is up, the file is
not there".

    python3 system/automation/reachability.py            # exit 1 if unreachable
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

HOST = "agenda.jurrejan.com"
LOCAL = "http://127.0.0.1:5181"
PATHS = ("/health.json", "/routes.json", "/llm.txt", "/")


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "agenda-reachability/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(200_000)


def dns_matches_wan():
    """The A record is static at the registrar; the home IP is not."""
    record = subprocess.run(["dig", "+short", "A", HOST, "@1.1.1.1"],
                            capture_output=True, text=True, timeout=20).stdout.split()
    wan = _get("https://api.ipify.org")[1].decode().strip()
    if not record:
        return [f"DNS: {HOST} has no A record"]
    if wan not in record:
        return [f"DNS: {HOST} points at {', '.join(record)}, this line is {wan} — "
                "the ISP lease changed and nothing updates the record"]
    return []


def serves_locally():
    try:
        status, body = _get(f"{LOCAL}/health.json")
    except OSError as exc:
        return [f"local: {LOCAL} is not serving — agenda-serve.service down? ({exc})"]
    doc = json.loads(body)
    if not doc.get("healthy"):
        return [f"local: feed reports problems — {'; '.join(doc.get('problems', []))}"]
    return []


def serves_publicly():
    problems = []
    for path in PATHS:
        try:
            status, _ = _get(f"https://{HOST}{path}")
        except urllib.error.HTTPError as exc:
            problems.append(f"public: {path} -> HTTP {exc.code}")
        except OSError as exc:
            problems.append(f"public: {path} unreachable — {exc}")
    return problems


def main():
    problems = dns_matches_wan() + serves_locally() + serves_publicly()
    for p in problems:
        print(p)
    print("unreachable" if problems else f"ok — https://{HOST} serves {len(PATHS)} paths")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
