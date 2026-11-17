#!/bin/bash
# The verdict on a clean-room driver: the tests exactly as their author committed them, run
# against the code as the implementer left it. Nothing the implementer did outside src/ can
# reach the result: tests, fixtures, simulator and Cargo.toml all come from the tests' commit.
#   tools/cleanroom-verdict.sh <repo> <tests-commit> [code-commit, default HEAD]
set -euo pipefail
repo=${1:?repo}; tests=${2:?tests commit}; code=${3:-HEAD}
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
git -C "$repo" archive "$tests" | tar -x -C "$t"
rm -rf "$t/src"; git -C "$repo" archive "$code" src | tar -x -C "$t"
echo "tests from $(git -C "$repo" rev-parse --short "$tests"), src from $(git -C "$repo" rev-parse --short "$code")"
echo "changed outside src/ between the two (reported; not used for the verdict):"
git -C "$repo" diff --stat "$tests" "$code" -- . ':!src' | sed 's/^/  /'
cd "$t" && { cargo test --offline --no-fail-fast 2>&1 || true; } | grep -E '^test result|^error' 
