#!/usr/bin/env python3
"""Silence the library-check SessionStart reminder for N days (default 14).

Writes .claude/.library-check-snooze.json with an absolute UTC `until`
timestamp. Re-run to extend or shorten the window. Always exits 0.

Usage:
    python3 .claude/scripts/snooze_library_check.py [--days N]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    if not (1 <= args.days <= 365):
        print(
            f"[library-check] --days must be 1-365, got {args.days}",
            file=sys.stderr,
        )
        return

    now = datetime.now(UTC)
    until = now + timedelta(days=args.days)
    state_dir = Path.cwd() / ".claude"
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "until": until.isoformat(),
        "set_at": now.isoformat(),
        "days": args.days,
    }
    (state_dir / ".library-check-snooze.json").write_text(
        json.dumps(state, indent=2) + "\n"
    )
    print(f"[library-check] Snoozed until {until.date().isoformat()}")


if __name__ == "__main__":
    main()
