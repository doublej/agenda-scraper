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
