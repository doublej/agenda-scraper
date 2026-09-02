set shell := ["zsh", "-uo", "pipefail", "-c"]
set unstable := true

default:
    @just --list
    @echo ''
    @echo "branch: $(git branch --show-current 2>/dev/null || echo 'n/a')"

[group('setup')]
install:
    uv sync

[group('develop')]
run-cli *ARGS:
    uv run agenda-scraper {{ ARGS }}

alias run := run-cli

[group('quality')]
lint:
    uv run ruff check .

[group('quality')]
lint-fix:
    uv run ruff check --fix .

[group('quality')]
format:
    uv run ruff format .

[group('quality')]
format-check:
    uv run ruff format --check .

[group('quality')]
typecheck:
    uv run mypy src/

[group('quality')]
test:
    uv run pytest

# Adds the one test that talks to the published feed over the network.
[group('quality')]
test-live:
    AGENDA_LIVE=1 uv run pytest

[group('quality')]
loc-check:
    #!/usr/bin/env zsh
    setopt null_glob
    eval "$(python3 -c "
    import json, shlex
    c = json.load(open('.quality.json'))
    print(f'WARN={c[\"loc\"][\"warn\"]}')
    print(f'ERROR={c[\"loc\"][\"error\"]}')
    g = c['globs']
    print(f'GLOBS=({shlex.join(g)})')
    ")"
    err=0
    for pattern in $GLOBS; do
        for f in ${~pattern}; do
            lines=$(wc -l < "$f")
            if (( lines > ERROR )); then echo "error: $f ($lines lines, max $ERROR)"; err=1
            elif (( lines > WARN )); then echo "warn: $f ($lines lines, target ≤$WARN — don't trim, split the file!)"; fi
        done
    done
    exit $err

[group('quality')]
dir-check:
    #!/usr/bin/env zsh
    setopt null_glob
    eval "$(python3 -c "
    import json, shlex
    c = json.load(open('.quality.json'))
    print(f'MAX={c[\"dir\"][\"max_files\"]}')
    g = c['globs']
    print(f'GLOBS=({shlex.join(g)})')
    ")"
    err=0
    typeset -A counts
    for pattern in $GLOBS; do
        for f in ${~pattern}; do
            dir=${f:h}
            counts[$dir]=$(( ${counts[$dir]:-0} + 1 ))
        done
    done
    for dir count in ${(kv)counts}; do
        if (( count > MAX )); then
            echo "error: $dir ($count files, max $MAX)"
            err=1
        fi
    done
    exit $err

[group('quality')]
just-fmt-check:
    just --fmt --check

[group('quality')]
check:
    @echo '→ Checking Justfile format...'
    just just-fmt-check
    @echo '→ Checking file lengths...'
    just loc-check
    @echo '→ Checking directory sizes...'
    just dir-check
    @echo '→ Running lint...'
    just lint
    @echo '→ Running format check...'
    just format-check
    @echo '→ Running typecheck...'
    just typecheck
    @echo '→ Running tests...'
    just test

[group('cleanup')]
clean:
    rm -rf dist/ .mypy_cache/ .pytest_cache/ .ruff_cache/
    find . -type d -name __pycache__ -exec rm -rf {} +

# Open this project's CLAUDE.md tree in the project-atlas viewer, https://github.com/doublej/project-atlas (via the global `atlas` CLI)
[group('docs')]
claude-tree:
    atlas tree

[group('scaffold')]
update-scaffold *ARGS:
    #!/usr/bin/env zsh
    set -euo pipefail
    repo="${COOKIECUTTER_TEMPLATES:-}"
    if [[ -z "$repo" && -f .template-meta.json ]]; then
        repo=$(python3 -c "import json; print(json.load(open('.template-meta.json'))['template_source']['path'])" 2>/dev/null || true)
    fi
    if [[ -z "$repo" || ! -d "$repo" ]]; then
        echo "error: cookiecutter-templates repo not found — set \$COOKIECUTTER_TEMPLATES or fix template_source.path in .template-meta.json" >&2
        exit 1
    fi
    python3 "$repo/tools/update_scaffold.py" {{ ARGS }}
