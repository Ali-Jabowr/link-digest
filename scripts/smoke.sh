#!/usr/bin/env bash
# End-to-end check with the real tools (Whisper and Claude) on a known clip.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT

fail() { echo "smoke: FAIL: $*" >&2; exit 1; }

printed=$(uv run link-digest "$HOME/localflow/jfk.wav" --notes-dir "$out/notes" --html-dir "$out/html")
echo "$printed"

transcript=$(find "$out/html" -name '*.transcript.txt' | head -n 1)
[[ -n "$transcript" ]] || fail "no transcript written"
grep -qi "ask not what your country" "$transcript" || fail "transcript lacks the known phrase"
[[ -n "$(find "$out/notes" -name '*.md' | head -n 1)" ]] || fail "no markdown written"
[[ -n "$(find "$out/html" -name '*.html' | head -n 1)" ]] || fail "no html written"
[[ "$printed" == *"unverified: 0" ]] || fail "unverified citations were reported"

echo "smoke: OK"
