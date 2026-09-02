#!/usr/bin/env bash
# Refresh the feed. Kept as a script so systemd never has to quote xvfb-run's
# --server-args.
set -euo pipefail
cd "$(dirname "$0")"
export AGENDA_CHROME=${AGENDA_CHROME:-/usr/bin/google-chrome}
# Optional: ping an Uptime Kuma push monitor so a run that never happens is
# noticed. Without this nothing catches a dead timer — the old events.json just
# keeps being served with a 200.
if [ -f .env ]; then . ./.env; fi     # `[ -f ] &&` would trip set -e

rc=0
xvfb-run -a --server-args="-screen 0 1400x1000x24" \
    uv run --frozen agenda-scraper scrape --all --out "$PWD/data" || rc=$?

if [ -n "${KUMA_PUSH_URL:-}" ]; then
    # rc 1 means "ran, but a source looks wrong" — report it as down, with why.
    msg=$([ "$rc" -eq 0 ] && echo OK || python3 -c \
        'import json;d=json.load(open("data/events.json"));print("; ".join(d["problems"])[:180])')
    curl -fsS -m 15 --get "$KUMA_PUSH_URL" \
        --data-urlencode "status=$([ "$rc" -eq 0 ] && echo up || echo down)" \
        --data-urlencode "msg=$msg" >/dev/null || true
fi
exit "$rc"
