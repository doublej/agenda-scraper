#!/usr/bin/env python3
"""SessionStart hook: flag when the upstream cookiecutter template has advanced.

Reads .template-meta.json in the project root, compares its template_version
against the upstream cookiecutter.json _version, and prints a single line to
stdout so Claude Code surfaces it as additional session context. Any failure
is silent (exit 0) so the hook never blocks a session.

Each invocation also phones home via _diag.log() so the upstream repo can audit
hook health on a schedule.

Opt-out:
  - env NO_TEMPLATE_UPDATE_CHECK=1
  - sentinel file .claude/no-template-update-check
"""

from __future__ import annotations

import sys

# Windows defaults stdout to cp1252, which can't encode the notice's emoji —
# force utf-8 so the print never lands in the silent catch-all as an error.
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import os
import re
import time
from pathlib import Path

HOOK = "check_template_update"

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


def _parse(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.strip().split("."))


def _extract_entries(changelog_text: str, local: str, upstream: str) -> str:
    """Return concatenated changelog sections for versions > local and <= upstream."""
    pattern = re.compile(r"^## \[(\d+\.\d+\.\d+)\].*$", flags=re.MULTILINE)
    matches = list(pattern.finditer(changelog_text))
    if not matches:
        return ""
    local_t = _parse(local)
    upstream_t = _parse(upstream)
    collected: list[str] = []
    for i, m in enumerate(matches):
        try:
            v = _parse(m.group(1))
        except Exception:
            continue
        if local_t < v <= upstream_t:
            end = (
                matches[i + 1].start() if i + 1 < len(matches) else len(changelog_text)
            )
            collected.append(changelog_text[m.start() : end].rstrip())
    return "\n\n".join(collected).strip()


def main() -> None:
    started = time.monotonic()

    def elapsed_ms() -> int:
        return int((time.monotonic() - started) * 1000)

    try:
        if os.environ.get("NO_TEMPLATE_UPDATE_CHECK"):
            _diag_log("noop", elapsed_ms(), meta={"reason": "env-opt-out"})
            return

        root = Path.cwd()
        if (root / ".claude" / "no-template-update-check").is_file():
            _diag_log("noop", elapsed_ms(), meta={"reason": "sentinel-opt-out"})
            return

        meta_path = root / ".template-meta.json"
        if not meta_path.is_file():
            _diag_log("noop", elapsed_ms(), meta={"reason": "no-meta"})
            return

        meta = json.loads(meta_path.read_text())
        local = meta.get("template_version")
        template = meta.get("template")
        source = meta.get("template_source") or {}
        src_path = source.get("path")
        if not (local and template and src_path):
            _diag_log("noop", elapsed_ms(), meta={"reason": "incomplete-meta"})
            return

        upstream_cc = Path(src_path) / template / "cookiecutter.json"
        if not upstream_cc.is_file():
            _diag_log(
                "noop",
                elapsed_ms(),
                meta={"reason": "upstream-missing", "src_path": src_path},
            )
            return

        upstream = json.loads(upstream_cc.read_text()).get("_version")
        if not upstream:
            _diag_log("noop", elapsed_ms(), meta={"reason": "upstream-no-version"})
            return

        if _parse(upstream) <= _parse(local):
            _diag_log(
                "noop", elapsed_ms(), meta={"reason": "up-to-date", "version": local}
            )
            return

        changelog_path = Path(src_path) / template / "CHANGELOG.md"
        entries = ""
        if changelog_path.is_file():
            entries = _extract_entries(changelog_path.read_text(), local, upstream)

        changes_block = f"\n\nChanges since v{local}:\n\n{entries}\n" if entries else ""
        print(
            f"[template-update] ⚠️ TEMPLATE UPDATE AVAILABLE: {template} {local} -> {upstream}."
            f"{changes_block}\n"
            f"DO THIS NOW, before responding to anything else: invoke the `/update-scaffold` skill — "
            f"it walks the user through applying this update safely (non-destructive by default: "
            f"tooling is overwritten; your edited seed files become `<file>.upstream` sidecars to merge). "
            f"If that skill is not installed, fall back to previewing with `just update-scaffold --diffs`, "
            f"then — once the user confirms — `just update-scaffold --apply` "
            f"(add `--force` only if they explicitly want their seed edits overwritten). "
            f"Do not start any other task until the user has decided."
        )
        _diag_log(
            "ok",
            elapsed_ms(),
            meta={"local": local, "upstream": upstream, "has_changelog": bool(entries)},
        )
    except Exception as e:
        _diag_log("error", elapsed_ms(), error=e)
        return


if __name__ == "__main__":
    main()
