#!/usr/bin/env python3
"""SessionStart hook: prompt agent to audit external library freshness.

Detects dependency manifests in the project root and prints a single reminder
block to stdout so Claude Code surfaces it as additional session context. Any
failure is silent (exit 0) so the hook never blocks a session. Snoozeable for
N days via the companion `snooze_library_check.py` script.

Each invocation also phones home via _diag.log() so the upstream repo can audit
hook health on a schedule.

Opt-out:
  - env NO_LIBRARY_CHECK=1
  - sentinel file .claude/no-library-check
  - snooze state file .claude/.library-check-snooze.json (auto-managed)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HOOK = "check_library_freshness"

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _diag
except Exception:
    _diag = None


def _diag_log(
    status: str,
    duration_ms: int,
    meta: dict | None = None,
    error: BaseException | None = None,
) -> None:
    if _diag is None:
        return
    try:
        _diag.log(HOOK, status, duration_ms, meta=meta, error=error)
    except Exception:
        return


MANIFESTS = (
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "Package.swift",
    "Podfile",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
)


def _detect_manifests(root: Path) -> list[str]:
    found = [m for m in MANIFESTS if (root / m).is_file()]
    found.extend(sorted(p.name for p in root.glob("requirements*.txt")))
    return found


def main() -> None:
    started = time.monotonic()

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        if os.environ.get("NO_LIBRARY_CHECK"):
            _diag_log("noop", elapsed_ms(), meta={"reason": "env-opt-out"})
            return

        root = Path.cwd()
        if (root / ".claude" / "no-library-check").is_file():
            _diag_log("noop", elapsed_ms(), meta={"reason": "sentinel-opt-out"})
            return

        snooze_path = root / ".claude" / ".library-check-snooze.json"
        if snooze_path.is_file():
            try:
                data = json.loads(snooze_path.read_text())
                until = datetime.fromisoformat(data["until"])
                if until > datetime.now(UTC):
                    _diag_log(
                        "noop",
                        elapsed_ms(),
                        meta={"reason": "snoozed", "until": data["until"]},
                    )
                    return
            except Exception:
                pass

        manifests = _detect_manifests(root)
        if not manifests:
            _diag_log("noop", elapsed_ms(), meta={"reason": "no-manifests"})
            return

        print(
            f"[library-check] Audit external dependencies ({', '.join(manifests)}):\n"
            f"  1. Enumerate third-party deps from each manifest\n"
            f"  2. Compare pinned/installed versions vs latest upstream releases\n"
            f"  3. Skim release notes + security advisories for each outdated dep\n"
            f"  4. Flag unmaintained libraries / known CVEs / breaking-change notices\n"
            f"When done: python3 .claude/scripts/snooze_library_check.py [--days 14]"
        )
        _diag_log("ok", elapsed_ms(), meta={"manifests": manifests})
    except Exception as e:
        _diag_log("error", elapsed_ms(), error=e)
        return


if __name__ == "__main__":
    main()
