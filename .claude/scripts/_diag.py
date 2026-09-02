#!/usr/bin/env python3
"""Phone-home diagnostic logger for .claude hooks.

Each invocation appends one JSONL line to the upstream cookiecutter-templates
repo at <template_source.path>/_diagnostics/<template>/<YYYY-MM>.jsonl, so we
can review aggregate hook health on a scheduled basis.

Best-effort: any failure (missing meta, unwritable target, OS error) is
swallowed. Hooks must never fail because of this.

Opt-out (in addition to each hook's own opt-out):
  - env NO_TEMPLATE_DIAG=1
  - sentinel file .claude/no-template-diag
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_MAX_ERROR_CHARS = 800


def _opted_out(root: Path) -> bool:
    if os.environ.get("NO_TEMPLATE_DIAG"):
        return True
    if (root / ".claude" / "no-template-diag").is_file():
        return True
    return False


def _read_meta(root: Path) -> dict | None:
    meta_path = root / ".template-meta.json"
    if not meta_path.is_file():
        return None
    return json.loads(meta_path.read_text())


def _format_error(error: BaseException) -> str:
    tb = "".join(traceback.format_exception_only(type(error), error)).strip()
    return tb[:_MAX_ERROR_CHARS]


def log(
    hook: str,
    status: str,
    duration_ms: int,
    meta: dict[str, Any] | None = None,
    error: BaseException | None = None,
) -> None:
    """Append one diagnostic record. Never raises."""
    try:
        root = Path.cwd()
        if _opted_out(root):
            return
        m = _read_meta(root)
        if not m:
            return
        template = m.get("template")
        src_path = (m.get("template_source") or {}).get("path")
        if not (template and src_path):
            return
        diag_dir = Path(src_path) / "_diagnostics" / template
        diag_dir.mkdir(parents=True, exist_ok=True)
        month = datetime.now(UTC).strftime("%Y-%m")
        target = diag_dir / f"{month}.jsonl"
        record: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(),
            "template": template,
            "template_version": m.get("template_version"),
            "project_path": str(root),
            "hook": hook,
            "status": status,
            "duration_ms": duration_ms,
            "python": sys.version.split()[0],
            "platform": sys.platform,
        }
        if meta:
            record["meta"] = meta
        if error is not None:
            record["error"] = _format_error(error)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        # O_APPEND single-write keeps lines atomic for sub-PIPE_BUF payloads.
        fd = os.open(str(target), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:
        return
