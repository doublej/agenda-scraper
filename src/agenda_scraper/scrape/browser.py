"""A real Chrome over CDP, for the two sites no HTTP request can reach.

Headless is fingerprinted and fails Cloudflare's managed challenge; a normal
Chrome with a persistent profile passes it. The window is parked offscreen so it
never steals focus. One browser per process, reused across renders, killed at exit.
"""

import atexit
import itertools
import json
import socket
import subprocess
import time
import urllib.request

import websocket

from agenda_scraper.config import CACHE_DIR, CDP_PORT, CHROME

_CHROME_PROC: subprocess.Popen | None = None
_ACCEPT_COOKIES = (
    "(()=>{const b=document.getElementById("
    "'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')"
    "||document.getElementById('CybotCookiebotDialogBodyButtonAccept');"
    "if(b)b.click()})()"
)
_SCROLL = (
    "(()=>{window.scrollTo(0,document.body.scrollHeight);"
    "const re=/toon volgende|laad meer|toon meer|load more|show more/i;"
    "const b=[...document.querySelectorAll('button,a')].find("
    "e=>re.test((e.textContent||'').trim())&&e.offsetParent!==null);"
    "if(b)b.click();"
    "return document.querySelectorAll('a[href]').length})()"
)


def render(url: str, scroll_rounds: int = 0, settle: float = 6.0) -> str:
    """DOM of `url` after JS, scrolling until the listing stops growing."""
    _launch_chrome()
    tab = _new_tab()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=90)
    try:
        # Navigate explicitly: Chrome >=150 ignores the ?url= on /json/new.
        _cdp(ws, "Page.navigate", {"url": url})
        time.sleep(settle)
        _eval(ws, _ACCEPT_COOKIES)
        _scroll_to_end(ws, scroll_rounds)
        return _eval(ws, "document.documentElement.outerHTML") or ""
    finally:
        ws.close()
        _close_tab(tab)


def _scroll_to_end(ws: websocket.WebSocket, rounds: int) -> None:
    seen, stale = -1, 0
    for _ in range(rounds):
        n = _eval(ws, _SCROLL)
        if n == seen:
            stale += 1
            if stale >= 2:  # a slow box can miss one round's fetch
                break
        else:
            stale = 0
        seen = n
        time.sleep(2.5)


def browser_credentials(origin: str) -> dict[str, str]:
    """Cookie header + UA from the running Chrome.

    Once the browser has solved a Cloudflare challenge, its `cf_clearance`
    cookie lets ordinary urllib through the same edge — so detail pages can be
    fetched hundreds at a time instead of one browser navigation each.
    """
    _launch_chrome()
    tab = _new_tab()
    ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=60)
    try:
        cookies = _cdp(ws, "Network.getCookies", {"urls": [origin]}).get("cookies", [])
        ua = _eval(ws, "navigator.userAgent")
    finally:
        ws.close()
        _close_tab(tab)
    return {
        "Cookie": "; ".join(f"{c['name']}={c['value']}" for c in cookies),
        "User-Agent": ua,
        "Accept-Language": "nl-NL,nl;q=0.9",
    }


_next_id = itertools.count(1).__next__


def _cdp(ws: websocket.WebSocket, method: str, params: dict | None = None) -> dict:
    i = _next_id()
    ws.send(json.dumps({"id": i, "method": method, "params": params or {}}))
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == i:
            return msg.get("result") or {}


def _eval(ws: websocket.WebSocket, expression: str):
    res = _cdp(
        ws,
        "Runtime.evaluate",
        {"expression": expression, "returnByValue": True, "awaitPromise": True},
    )
    return res["result"].get("value")


def _new_tab() -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new", method="PUT")
    return json.load(urllib.request.urlopen(req, timeout=15))


def _close_tab(tab: dict) -> None:
    urllib.request.urlopen(
        f"http://127.0.0.1:{CDP_PORT}/json/close/{tab['id']}", timeout=15
    )


def _launch_chrome() -> subprocess.Popen | None:
    global _CHROME_PROC
    with socket.socket() as s:
        if s.connect_ex(("127.0.0.1", CDP_PORT)) == 0:
            return _CHROME_PROC  # already listening
    profile = CACHE_DIR / "chrome-profile"
    profile.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        [
            CHROME,
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            f"--remote-debugging-port={CDP_PORT}",
            "--remote-allow-origins=*",
            "--window-position=-3000,-3000",
            "--lang=en-US",  # parse_paradiso reads English day/month labels
            "--window-size=1400,1000",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        time.sleep(0.5)
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=2
            )
        except OSError:
            continue
        _CHROME_PROC = proc
        atexit.register(proc.terminate)
        return proc
    proc.terminate()
    raise RuntimeError("Chrome did not expose CDP — is AGENDA_CHROME correct?")
