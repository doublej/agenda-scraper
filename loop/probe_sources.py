"""Probe candidate venue sites for the cheapest tier that works.

Order is the repo's own rule: a documented API first, then schema.org JSON-LD in
the served HTML, then a WordPress REST endpoint. One host per worker, never more
than one request a second to the same host, robots.txt read first.

    uv run python loop/probe_sources.py [name ...]
"""

import json
import sys
import time
import urllib.error
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agenda_scraper.config import UA
from agenda_scraper.scrape.http import get
from agenda_scraper.scrape.parsers import parse_jsonld

AGENDA_PATHS = (
    "/agenda/",
    "/agenda",
    "/programma/",
    "/programma",
    "/events/",
    "/concerten/",
    "/",
)

CANDIDATES = {
    "melkweg": ("https://www.melkweg.nl", "Melkweg", "Amsterdam"),
    "013": ("https://www.013.nl", "013", "Tilburg"),
    "effenaar": ("https://www.effenaar.nl", "Effenaar", "Eindhoven"),
    "doornroosje": ("https://www.doornroosje.nl", "Doornroosje", "Nijmegen"),
    "patronaat": ("https://www.patronaat.nl", "Patronaat", "Haarlem"),
    "paard": ("https://www.paard.nl", "Paard", "Den Haag"),
    "vera": ("https://www.vera-groningen.nl", "Vera", "Groningen"),
    "simplon": ("https://www.simplon.nl", "Simplon", "Groningen"),
    "hedon": ("https://www.hedon-zwolle.nl", "Hedon", "Zwolle"),
    "neushoorn": ("https://www.neushoorn.nl", "Neushoorn", "Leeuwarden"),
    "metropool": ("https://www.metropool.nl", "Metropool", "Hengelo"),
    "gebrdenobel": ("https://www.gebrdenobel.nl", "Gebr. de Nobel", "Leiden"),
    "bibelot": ("https://www.bibelot.net", "Bibelot", "Dordrecht"),
    "volt": ("https://www.poppodiumvolt.nl", "Volt", "Sittard"),
    "spot": ("https://www.spotgroningen.nl", "Spot", "Groningen"),
    "tolhuistuin": ("https://www.tolhuistuin.nl", "Tolhuistuin", "Amsterdam"),
    "lantarenvenster": (
        "https://www.lantarenvenster.nl",
        "LantarenVenster",
        "Rotterdam",
    ),
    "bitterzoet": ("https://www.bitterzoet.com", "Bitterzoet", "Amsterdam"),
    "burgerweeshuis": ("https://www.burgerweeshuis.nl", "Burgerweeshuis", "Deventer"),
    "nieuwenor": ("https://www.nieuwenor.nl", "Nieuwe Nor", "Heerlen"),
    "willem2": ("https://www.w2.nl", "W2", "'s-Hertogenbosch"),
    "willemeen": ("https://www.willemeen.nl", "Willemeen", "Arnhem"),
    "luxorlive": ("https://www.luxorlive.nl", "Luxor Live", "Arnhem"),
    "gigant": ("https://www.gigant.nl", "Gigant", "Apeldoorn"),
    "atak": ("https://www.atak.nl", "ATAK", "Enschede"),
    "p60": ("https://www.p60.nl", "P60", "Amstelveen"),
    "victorie": ("https://www.podiumvictorie.nl", "Victorie", "Alkmaar"),
    "mezz": ("https://www.mezz.nl", "Mezz", "Breda"),
    "grenswerk": ("https://www.grenswerk.nl", "Grenswerk", "Venlo"),
    "boerderij": ("https://www.cultuurpodiumboerderij.nl", "Boerderij", "Zoetermeer"),
    "iduna": ("https://www.iduna.nl", "Iduna", "Drachten"),
    "baroeg": ("https://www.baroeg.nl", "Baroeg", "Rotterdam"),
    "worm": ("https://www.worm.org", "WORM", "Rotterdam"),
    "annabel": ("https://www.annabel.nu", "Annabel", "Rotterdam"),
    "paradox": ("https://www.paradox.nl", "Paradox", "Tilburg"),
    "extrapool": ("https://extrapool.nl", "Extrapool", "Nijmegen"),
    "qfactory": ("https://www.q-factory.nl", "Q-Factory", "Amsterdam"),
    "afaslive": ("https://www.afaslive.nl", "AFAS Live", "Amsterdam"),
    "asteriks": ("https://www.podiumasteriks.nl", "Asteriks", "Leeuwarden"),
    "hal4": ("https://www.hal4aandekade.nl", "Hal 4", "Rotterdam"),
    "podiumhoogeveen": (
        "https://www.podiumhoogeveen.nl",
        "Podium Hoogeveen",
        "Hoogeveen",
    ),
    "deflux": ("https://www.deflux.nl", "De Flux", "Zaandam"),
    "poppodiumemergo": ("https://www.emergo-nl.nl", "Emergo", "Etten-Leur"),
    "kroepoekfabriek": (
        "https://www.kroepoekfabriek.nl",
        "Kroepoekfabriek",
        "Vlaardingen",
    ),
    "stadsgehoorzaal": (
        "https://www.stadsgehoorzaalvlaardingen.nl",
        "Stadsgehoorzaal",
        "Vlaardingen",
    ),
}


def _robots_ok(base: str, path: str) -> bool:
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(f"{base}/robots.txt")
    try:
        parser.read()
    except Exception:  # noqa: BLE001 — no robots.txt means no rule
        return True
    return parser.can_fetch(UA, base + path)


def probe(name: str) -> dict:
    base, venue, city = CANDIDATES[name]
    out: dict = {"name": name, "base": base, "venue": venue, "city": city}
    try:
        doc = json.loads(
            get(
                f"{base}/wp-json/tribe/events/v1/events"
                f"?per_page=5&start_date={date.today()}"
            )
        )
        if doc.get("events"):
            out["tier"] = "tribe"
            out["total"] = doc.get("total") or len(doc["events"])
            out["sample"] = doc["events"][0].get("title", "")[:60]
            return out
    except Exception as exc:  # noqa: BLE001 — a miss is the normal answer here
        out["tribe_error"] = f"{type(exc).__name__}: {exc}"[:80]
    time.sleep(1)

    for path in AGENDA_PATHS:
        try:
            rows = parse_jsonld(get(base + path))
        except Exception as exc:  # noqa: BLE001
            out.setdefault("jsonld_error", f"{path} {type(exc).__name__}: {exc}"[:80])
            time.sleep(1)
            continue
        if len(rows) >= 5:
            out["tier"] = "jsonld"
            out["path"] = path
            out["total"] = len(rows)
            out["robots"] = _robots_ok(base, path)
            out["sample"] = rows[0]["title"][:60]
            out["dated"] = sum(1 for r in rows if r["date"])
            return out
        time.sleep(1)

    try:
        rows = json.loads(get(f"{base}/wp-json/wp/v2/event?per_page=5"))
        if isinstance(rows, list) and rows:
            out["tier"] = "wp"
            out["total"] = len(rows)
            return out
    except Exception as exc:  # noqa: BLE001
        out["wp_error"] = f"{type(exc).__name__}: {exc}"[:80]
    out.setdefault("tier", "none")
    return out


def main() -> None:
    names = sys.argv[1:] or list(CANDIDATES)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(probe, names))
    results.sort(key=lambda r: (r["tier"], -int(r.get("total") or 0)))
    Path("loop/probe.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1)
    )
    for r in results:
        print(
            f"{r['tier']:7s} {r['name']:16s} {r.get('total', '')!s:>5s} "
            f"{r.get('path', ''):12s} {r.get('sample', '') or r.get('jsonld_error', '')}"
        )


if __name__ == "__main__":
    main()
