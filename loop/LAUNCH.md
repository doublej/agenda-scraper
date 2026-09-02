# BOEKING — launch line

Run from /Users/jurrejan/Documents/development/python/agenda-scraper:

```
/loop Read loop/MISSION.md and execute it as the BOEKING run. Work until Phase B's definition of done is met or the 8-hour cap is hit. Track state in loop/PROGRESS.md and loop/BACKLOG.json.
```

Self-paced `/loop`, no interval — the work is goal-based and the agent paces its own
iterations. The 8-hour cap is stated identically here and in MISSION.md.

## Before launching
- `git checkout develop && git checkout -b feature/entity-model` (the loop does this at A1
  if it has not happened yet).
- Chrome must be available: A1's baseline `--all` run renders tivoli and paradiso.

## After the run
Remove the `"matcher": "compact"` SessionStart entry from .claude/settings.json — it
outlives the loop otherwise.

Morning review, in order:
1. `just check`
2. `uv run agenda-scraper scrape --all --out "$TMPDIR/after"`, diff counts against loop/BASELINE.json
3. `git log --oneline develop..feature/entity-model`, read the publish.py and data/llm.txt diff
4. Check every ✅ in PROGRESS.md against MISSION.md's original wording; keep the BLOCKED list
