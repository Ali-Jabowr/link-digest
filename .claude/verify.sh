#!/usr/bin/env bash
# Verify gate (Python, uv). The single definition of "the code is OK".
# Runs locally (Claude Code Stop hook: the agent cannot finish while this fails)
# and in CI (required check: nothing merges while this fails).
# Tools come from the project's dev dependency group (see pyproject.verify.toml).
# Change it on purpose, in its own commit, never to make a failing change pass.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

command -v uv >/dev/null || { echo "MISSING TOOL: uv (https://docs.astral.sh/uv/)"; exit 1; }
run() { uv run --frozen "$@"; }
step() { echo; echo "==> $*"; }

step "ruff format --check"; run ruff format --check .
step "ruff check";          run ruff check .
step "mypy (strict)";       run mypy .
step "pytest";              run pytest -q -p no:cacheprovider
step "pip-audit";           run pip-audit --progress-spinner off || { echo "Vulnerable dependency found"; exit 1; }

echo; echo "verify: OK"
