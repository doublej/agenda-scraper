# Progress — BOEKING

## Honesty buckets
- DONE (with evidence):
- BLOCKED (reason + 3 approaches tried):
- CUT (what + why):

## Decision log (question → chosen answer → why)
| # | Question | Decision | Why |
|---|---|---|---|
| 1 | Static JSON registries or build-time SQLite? | *(loop fills before A2)* | |
| 2 | MusicBrainz MBIDs after the heuristic core? | Cut, not probed | Phase A ended with 3775 extracted names, most of them Dutch club-night brands rather than catalogued acts. A 50-name probe would have been measuring the wrong population, and an MBID adds nothing a consumer can act on while the *name* is still a guess. Spend the budget on sources instead; revisit when `confidence == "high"` is the majority. |

## Iteration log (newest first — one line: what moved, evidence, next)

### Phase A boundary — evidence

`just check` green (just-fmt, loc, dir, ruff, format, mypy 18 files, 25 passed 2 skipped).

Schema validation of the real `--all` run at /tmp/boeking/after:

    json files walked: 388
    problems: 0
    negative control errors: 12      # a deliberately broken health.json does fail

Full-run comparison against loop/BASELINE.json:

    total events     2268 ->   4687
    venue labels      485 ->    921   (913 distinct venue_ids)
    cities            106 ->    238
    routes            154 ->    385

**The whole gap is one source.** Per-source counts are identical except:

    podiuminfo    0 -> 2433     baseline run returned 0; the source was never broken
    ra-nl       639 ->  642     three nights announced between the two runs

podiuminfo's 0 in the baseline was a transient fetch failure, not a parser
breakage and not something this work changed: an unmodified `get()` +
`parse_jsonld()` probe of page 1 returned 100 rows (78 NL after the country
filter) with the Phase A code checked out. So the honest baseline for venue
labels is **921, not 485** — Phase B's "2x" bar is measured against 485 as the
mission words it, and against 921 as the number that means something. Both are
reported at the Phase B boundary.

Artist extraction, measured over the 4687 published titles: 3775 distinct
names, 1329 high / 3249 medium / 252 low confidence mentions. Two rules earned
their place after seeing real data: half the feed's titles are
"Artist @ Venue" (podiuminfo's format, 2411 of 4687), and a genre phrase that
loses two filler words is a fragment, not an act ("Hard Techno Rave" -> "Hard").
Top names before those fixes were "De Oosterpoort" (39) and "Lunchconcert" (8);
after, "Nona" (13), "Coldplay" (9), "Racoon", "Davina Michelle", "Snelle".

Not caused by this run, recorded so nobody chases it: `data/index.html` and
`data/events.json` were rewritten at 15:46 by a concurrent session. Left alone
and never staged.

### Phase B boundary — evidence

Full `--all` run at /tmp/boeking/final, `just check` green with
AGENDA_VALIDATE_DIR pointed at it (72 passed, 1 skipped):

    json files walked: 651
    problems: 0
    negative control errors: 12
    events with a bad date: 0
    events with the wrong key set: 0

Against loop/BASELINE.json:

    total events     2268 ->   7814   x3.45
    venue labels      485 ->   1281   x2.64   (1254 distinct venue_ids)
    cities            106 ->    312   x2.94
    routes            154 ->    649

**Read the venue multiple twice.** The mission's bar is 2x the figure in
BASELINE.json and 1281 clears it, but 485 was measured on a run where
podiuminfo returned 0. Like for like — against the 921 venue labels the same
code base produced once podiuminfo came back, before a single new source was
added — this run's fifteen new sources took venues from 921 to 1281, +39%.
Both numbers are the truth; the second is the one that measures Phase B.

Per-source counts on the final run:

    partyflock 1312   podiuminfo 2433   ra-nl 642   spot 595   festivalinfo 420
    paradiso    470   tivoli      420   patronaat 166   013 162   rotown 139
    melkweg     138   effenaar    132   hedon 131   muziekgieterij 113
    gebrdenobel 111   afaslive    110   neushoorn 103   victorie 100
    musicon      77   dehelling    69   dbstudio 62   burgerweeshuis 49
    gigant       39   ekko         34   annabel 22   vera 20

### What the tier sweep actually found

The backlog assumed the cheap tiers were there to be picked up. Over 45
candidate sites and 38 real agenda paths:

- **The Events Calendar REST** (B1): zero hits. Musicon and dB's are still the
  only two in the whole feed.
- **schema.org JSON-LD** (B2): zero hits on any venue site. Dutch podia do not
  publish it.
- **iCal**: zero. No `/events.ics`, `/agenda.ics`, `?ical=1` or `/feed/ical/`.
- **WordPress `event` post types**: seven sites have one, and on every one the
  only date exposed over REST is the post's publish date; ACF comes back `[]`.
- **stager.co**: the ticketing platform behind at least fifteen of these
  venues, and its shop pages publish the whole programme as one clean JSON-LD
  block — 20 to 50 events each, with venue and city. `robots.txt` is
  `User-agent: * / Disallow: /`, exempting only Googlebot and
  facebookexternalhit. Not fetched.
- **What is left**: a date next to a heading. `<time datetime>` on six sites, a
  Dutch date written into the card on eight, a date baked into the URL on one.
  That is `scrape/cards.py`, and it is why fifteen sources cost one parser.
- **Microdata**: Partyflock publishes schema.org as itemprop attributes rather
  than an ld+json block. One parser, 1312 Dutch events, and by far the widest
  venue coverage in the feed.

### Two things that cost real time, written down so they do not again

- `urllib.robotparser.RobotFileParser.read()` marks a host **disallowed** when
  the robots.txt fetch 403s, which four of the fifteen new hosts do to a plain
  urllib request. Fetching robots.txt through the project's own `get()` and
  feeding the body to `.parse()` gives the right answer. Checked that way,
  every host added here allows the path it is scraped on; Patronaat asks for a
  10 second crawl delay and gets one request per run.
- The baseline run's podiuminfo 0 was transient, not a breakage, and it made
  every later comparison ambiguous. A baseline taken while a source is down is
  worth re-taking.
