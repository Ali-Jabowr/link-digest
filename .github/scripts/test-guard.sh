#!/usr/bin/env bash
# CI backstop for the protect-tests hook. Usage: test-guard.sh <base-ref>
#
# Fails when this branch modifies or deletes lines in test files that already
# exist on the base branch, or adds skip/only markers to tests, UNLESS one of
# the branch's commits has the trailer:  Test-Change-Approved: <reason>
# Adding new tests (new lines only) is always fine.
set -euo pipefail
base="${1:?usage: test-guard.sh <base-ref>}"
mb=$(git merge-base "$base" HEAD)

TEST_RE='(_test\.go$|/testdata/|(^|/)test_[^/]*\.py$|_test\.py$|(^|/)conftest\.py$|(^|/)tests?/|\.(test|spec)\.[cm]?[jt]sx?$)'
SKIP_RE='(t\.Skip|b\.Skip|SkipNow|pytest\.mark\.(skip|xfail)|@unittest\.skip|pytest\.skip\(|\.skip\(|\bxit\(|\bxdescribe\(|\.only\()'

problems=()
while IFS=$'\t' read -r added deleted path; do
  [[ "$path" =~ $TEST_RE ]] || continue
  git cat-file -e "$mb:$path" 2>/dev/null || continue          # new file: fine
  [ "$deleted" = "-" ] && deleted=0
  [ "$deleted" -gt 0 ] && problems+=("$path: $deleted committed test line(s) changed or deleted")
done < <(git diff --numstat "$mb" HEAD)

while IFS= read -r line; do
  problems+=("skip/only marker added: $line")
done < <(git diff -U0 "$mb" HEAD | grep -E '^\+[^+]' | grep -E "$SKIP_RE" || true)

# Deleted test files show up in numstat as deletions, covered above.

if [ ${#problems[@]} -eq 0 ]; then
  echo "test-guard: approved tests untouched"
  exit 0
fi

printf 'test-guard: %s\n' "${problems[@]}"
approval=$(git log --format='%(trailers:key=Test-Change-Approved,valueonly)' "$mb..HEAD" | sed '/^$/d' | head -n1)
if [ -n "$approval" ]; then
  echo "test-guard: allowed by Test-Change-Approved: $approval"
  exit 0
fi
echo "test-guard: FAILED. Approved tests were changed. If this is intentional, add a commit"
echo "            with the trailer 'Test-Change-Approved: <why the old test was wrong>'."
exit 1
