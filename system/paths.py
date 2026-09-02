"""Single source of truth for every path in _life.

Restructure #1 (March 2026) decayed because path literals were scattered
across ~23 files and nothing updated them when folders moved. Six months
later the git hooks were still validating deleted folders. This module
exists so that never happens again: move a folder, change it here, and
`system/tests/test_paths.py` fails loudly if anything is left dangling.

Import from anywhere under system/ with:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from paths import MAIL, WORK, mail_folder
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ─── the four zones ──────────────────────────────────────────────────────────
NOW = ROOT / "now"          # volatile working memory
RAW = ROOT / "raw"          # immutable, append-only, never rewritten
WIKI = ROOT / "wiki"        # curated, Claude-maintained, compounds
SYSTEM = ROOT / "system"    # schema + code, user-edited

# ─── now ─────────────────────────────────────────────────────────────────────
FOCUS = NOW / "focus.md"
RULES = NOW / "rules.md"

# ─── raw ─────────────────────────────────────────────────────────────────────
MAIL = RAW / "mail"
TRANSCRIPTS = RAW / "transcripts"
CAPTURE = RAW / "capture"

ACCOUNTS = ("personal", "poolsuite")
MAIL_FOLDERS = ("inbox", "triage", "filed", "drafts", "sent")

# ─── wiki ────────────────────────────────────────────────────────────────────
WORK = WIKI / "work"            # clients and client relationships
MONEY = WIKI / "money"          # money only
MATTERS = WIKI / "matters"      # disputes and claims with evidence trails
PERSONAL = WIKI / "personal"    # travel, people, hobbies, projects
TOPICS = WIKI / "topics"
DECISIONS = WIKI / "decisions"
QUERIES = WIKI / "queries"
WIKI_INDEX = WIKI / "index.md"
WIKI_LOG = WIKI / "log.md"
ME = WIKI / "me.md"

# ─── system ──────────────────────────────────────────────────────────────────
AUTOMATION = SYSTEM / "automation"
DOCS = SYSTEM / "docs"
APP = SYSTEM / "app"
RULES_DIR = AUTOMATION / "rules"

# ─── tool-owned dotfolders (fixed at root by the tools that own them) ────────
APPROVALS = ROOT / ".approvals"
LOGS = ROOT / ".logs"
CLAUDE_DIR = ROOT / ".claude"
SCRAPE_CACHE = LOGS / "scrape"   # rendered agenda HTML, machine-local


def mail_folder(account: str, folder: str) -> Path:
    """Path to one mail folder, e.g. mail_folder("personal", "inbox")."""
    return MAIL / account / folder


def attachments(account: str) -> Path:
    return MAIL / account / "attachments"
