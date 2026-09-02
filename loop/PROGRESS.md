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

Not caused by this run, recorded so nobody chases it: `data/index.html` was
rewritten by a concurrent session working in the same checkout — its own
session summary reports "clicking a source chip now isolates it on the first
click", which is `fc2b171` word for word. **Correction to an earlier version of
this line, which said "never staged":** that was wrong. Because that session
shared the worktree while `feature/entity-model` was checked out, its two
commits (`f3b116c`, `fc2b171`) landed *on this branch*, mid-sequence, and rode
along in the merge. No content reached `main` that was not already there — it
had committed the same work to `main` directly as `f311aea` / `eb104cf`, and
`data/index.html` is byte-identical across all four. `data/events.json` is not
tracked in either branch, so its rewrite was working-tree churn only.
I did not author those two commits and did not stage them; they are in the
history regardless, and this run's own rule of touching nothing under `./data/`
except `llm.txt` / `llms.txt` held for every commit I made.

### Phase B boundary — evidence

Full `--all` run at /tmp/boeking/final4, taken at HEAD after every fix below,
so the numbers, the links and the code are the same thing. `just check` green
with AGENDA_VALIDATE_DIR pointed at it:

    json files walked: 651
    problems: 0
    negative control errors: 12
    events with a bad date: 0
    events with the wrong key set: 0
    urls repeating their first path segment: 0
    gebrdenobel times: [("", 111)]        # no publish timestamps left

One run in between (final3) exited 1 with muziekgieterij timed out and paradiso
404, and is not the artifact quoted here. Worth recording rather than hiding:
a full run touches 26 hosts and two of them will flake, which is exactly what
`assess()` and the non-zero exit are for. The rerun was clean.

Against loop/BASELINE.json:

    total events     2268 ->   7815   x3.45
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

Every one of the fifteen new sources, checked against the five per-source
criteria on /tmp/boeking/final — 100% valid ISO dates on all of them, venue and
city resolving to records, a fixture pair, and a name in SOURCES, SOURCE_RANK
and SOURCE_CITY (partyflock names its own city, so it is correctly absent
there). Two are worth naming rather than burying:

- **vera** sits exactly on the 20-event bar, not above it.
- **annabel** scraped 22 rows and publishes 15: the horizon filter and dedupe
  against podiuminfo take the rest. It is an extra, not one of the 13 backlog
  items, so the Phase B count does not lean on it — but 22 on the wire and 15
  in the feed is the honest pair of numbers.

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

### Three bugs this run introduced and then caught

Worth naming, because two of them shipped in a commit before they were found:

- **Relative links joined onto the listing path.** `origin + href` gave
  `/agenda/agenda/<slug>` on Effenaar and Gebr. de Nobel and
  `/nl/agenda/nl/agenda/<slug>` on Melkweg — 381 published events whose link
  404'd. `urllib.parse.urljoin` handles all three href shapes; the golden test
  now asserts a URL never repeats its first path segment. Found by checking the
  published feed rather than the parser, which is where it was visible.
- **A quadratic pairing.** The date/heading match built the full cross product.
  Spot's 616-card page took 0.13s, so nothing looked wrong; a synthetic
  5000-card page took 37 seconds. Both lists are in document order, so the
  window is a bisect: 0.34s.
- **The dev group reaching the timer host.** Moving ruff, mypy and pytest out
  of an extra and into a dependency group fixed `just check` locally and would
  have installed all three on the Linux box, because `uv run` takes default
  groups. `refresh.sh` passes `--no-dev`.

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

## Close-out

`just check` green at the merged tip: 71 passed, 2 skipped. The two skips are
the live-feed test (`AGENDA_LIVE=1`) and the schema walk over a real run
(`AGENDA_VALIDATE_DIR=<dir>`); the latter was run separately against
`/tmp/boeking/final4` and validated 651 files with 0 problems, against a
negative control that produces 12 errors.

Merged locally, no push, per the flow: `feature/entity-model` → `develop` →
`main`, both `--no-ff`. `git diff develop main` is empty. The only overlapping
file with the work another session committed straight onto main was
`data/index.html`, and both sides held byte-identical content
(`b242d117bf1f1f71687d84302b71fca1`), so the merge was clean. Nothing was
pushed; `origin/main` and `origin/develop` are untouched.

The `"matcher": "compact"` SessionStart hook that `loop/LAUNCH.md` asks to be
removed after the run is gone (`c97b495`).

### The skeptic passes did not report *(superseded — see the section below)*

At the time of writing this, both skeptics had gone idle without a verdict
after two and one follow-up prompts, and I recorded the phase boundaries as
unreviewed. **Both then reported.** They found a blocker I had missed, it was
real, and it is fixed. The section "The skeptic passes, and what they changed"
below is the accurate record; this paragraph is kept only so the sequence is
readable. The merge described above happened *before* that fix, so it was not
the last word — the run continued.

## The skeptic passes, and what they changed

Both skeptics eventually reported, long after I had recorded them as having
gone idle without a verdict. The close-out section above says the phase
boundaries went unreviewed; that is now wrong, and this section replaces it.
Both returned **HOLDS WITH CAVEATS** on the criteria, and the boundary skeptic
returned **FIX FIRST** overall on the strength of one blocker. It was right.

### The blocker: every card's link pointed at the card above it

`parse_cards` read the card's `<a>` backwards. Right for the eleven listings
that wrap a card in its link, wrong for the three that end the card with a
"Tickets & info" link — there each event took the *previous* card's URL.
Neushoorn 0 of 103 correct, Melkweg 4 of 138, Annabel 1 of 22. `url` is one of
the nine legacy keys, so this was published, deduplicated and served.

I reproduced it before fixing it, then fetched all fourteen listings and
measured four candidate rules over 1880 real rows:

| rule | links matching their own event |
|---|---|
| last anchor before the card (what shipped) | 78.7% |
| first anchor after the card | 28.4% |
| nearest anchor either way | 66.8% |
| first anchor in the card's own region | 59.3% |

No positional rule wins: reading backwards scores 92-97% on eleven sites and
0-5% on three, and reading forwards inverts that exactly. So it is per-site,
like `dates` — `LINKS_AFTER` in `scrape/cards.py`. After: **91.4%**, and
previous-card misattributions fall from **127 to 12**. The residue is Vera's
opaque `?p=152958` links, which no title check can score; its 20 rows carry 20
distinct URLs.

**The part worth remembering.** The goldens had been captured from the buggy
parser, so `test_a_saved_page_still_parses_to_its_golden` asserted the shifted
URLs were correct. A golden proves a parser has not changed; it never proves it
is right. Every fixture now has an invariant beside it —
`test_an_event_links_to_itself_and_not_to_the_card_above_it` — and I verified it
is not vacuous by regenerating the three goldens the old way and watching all
three fail. `CLAUDE.md` carries the rule now.

### Also fixed

- A heading that is only a date *range* ("do 09 jul - zo 20 sep") named no act,
  and `_fill_year` pushed it a year out — a phantom 2027 event in the feed and
  in Melkweg's golden. Both sides must now be dates, so the real event
  "Jimmy Carr - Laughs funny" survives the filter.
- `routes.json` advertised `venue/mezz` twice over one file ("MEZZ" and "Mezz",
  one slug): 649 routes promised, 648 on disk. Labels that share a slug are
  merged into one route rather than re-keyed on `venue_id`, which would rename
  live URLs.
- `SOURCE_RANK` listed `spot` twice, so every venue after it sat one place off
  its intended precedence. 26 names for 26 sources now, checked both ways.

### Accepted, not fixed — with the reason

- **`models.Event` is never used as an annotation.** Every module passes the
  loose `agenda_scraper.Event` (`dict[str, str]`), so the TypedDict buys no
  mypy coverage. Rather than delete an A2 deliverable or annotate late in the
  run, it is now tied to the two declarations that *are* enforced: a test
  asserts the TypedDict's field order, the TSV column order and
  `schema/event.schema.json`'s `required` and `properties` are the same tuple.
  Drift between them now fails.
- **A6 said "via `plan_routes()`" and the three registries do not go through
  it.** `/venues.json`, `/cities.json` and `/artists.json` are written by
  `write_registries()`, called from `write_routes()`. The intent is met — all
  three are published and indexed in `routes.json` — but the named mechanism is
  not, because `plan_routes()` returns event slices and a registry is not a
  slice of events. Logged here rather than forced.
- **`pyproject.toml` moved the dev deps** from `[project.optional-dependencies]`
  to `[dependency-groups]` and relaxed `mypy>=2.0.0` to `>=1.17.0`. Out of
  A1-A8 and previously only justified in an inline comment. It was not
  optional: `uv sync` does not install an extra, so ruff, mypy and pytest were
  resolving to system binaries and `just typecheck` was red at HEAD for
  reasons that had nothing to do with the code.
- **Two of the thirteen "done" Phase B items (B1, B2) are sweeps that found
  nothing**, so the backlog yields eleven sources and four more came from
  outside it. Thirteen is right by the letter and eleven by the stricter
  reading; both numbers are here so the reader can pick.
- **Artist extraction still emits non-artists** — `artist/amsterdam-techno-sessions`,
  `artist/antimatter`. Known ceiling of a heuristic with no ground truth; it is
  the piece most worth a human read.

### Evidence after the fixes — /tmp/boeking/fix1

Clean `--all` run at the post-fix HEAD, exit 0, no source flaked:

    json files on disk    : 652
    routes advertised     : 649   distinct: 649
    duplicate route paths : []                  # was venue/mezz twice
    advertised but absent : 0                   # was 1
    events                : 7816
    venue labels          : 1280   (1253 distinct venue_ids)
    cities                : 312
    bad dates             : 0
    wrong key set         : 0
    non-string values     : 0
    doubled url segments  : 0
    phantom date headings : 0

`AGENDA_VALIDATE_DIR=/tmp/boeking/fix1 uv run pytest tests/test_entities.py`
passes 12 tests against the real run, and `just check` is green: 88 passed,
2 skipped.

URL attribution in the published feed, counted as "does the link share a word
with its own event's title, or with the one above it" — old run (final4) versus
this one:

    source            OLD own/prev     NEW own/prev
    annabel                1/7             11/0     <-- fixed
    melkweg                4/55           130/1     <-- fixed
    neushoorn              0/45            95/0     <-- fixed
    013                  150/0            150/0
    spot                 544/9            544/9
    victorie              92/0             92/0
    gebrdenobel          108/0            109/0
    gigant                36/0             36/0
    effenaar             113/0            113/0
    patronaat            160/0            160/0
    hedon                116/1            116/1
    burgerweeshuis        46/0             46/0
    vera                   1/1              1/1     (opaque ?p= links)
    afaslive             102/0            102/0
    TOTAL own           1473             1705

Nothing regressed: every source other than the three is identical or better.
Melkweg drops 138 events to 137 — that is the phantom date-range row.

**The counts moved by one against the pre-fix run** (7815 -> 7816 events, 1281
-> 1280 venue labels). Two scrapes an hour apart never agree exactly; the
multiples against BASELINE.json are unchanged at x3.45 events and x2.64 venue
labels, and the like-for-like venue caveat above (921, not 485) still stands.
