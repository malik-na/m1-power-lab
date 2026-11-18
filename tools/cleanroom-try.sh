#!/bin/bash
# For a test author: run the tests of a workspace that holds no driver against the driver's
# committed src/, without putting the driver's source in front of the author.
#   tools/cleanroom-try.sh <tests workspace> <driver repo> [driver commit, default HEAD] [cargo test args]
# The two are put together in a temporary directory that is removed afterwards; only cargo's
# test output is printed (each test's result and the failing tests' own messages).
set -euo pipefail
ws=${1:?tests workspace}; repo=${2:?driver repo}; code=${3:-HEAD}; shift $(( $# > 3 ? 3 : $# ))
t=$(mktemp -d); trap 'chmod -R u+w "$t" 2>/dev/null; rm -rf "$t"' EXIT
rsync -a --exclude target --exclude .git --exclude src "$ws"/ "$t"/
git -C "$repo" archive "$code" src | tar -x -C "$t"
cd "$t" && { cargo test --offline --no-fail-fast "$@" 2>&1 || true; } | grep -v -E '^\s+(Compiling|Finished|Running|Doc-tests)|^\s*-->|^\s*\|' | grep -v "$t/src" | cut -c1-400
