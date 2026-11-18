#!/bin/bash
# For the glue's test author: run a workspace's tests against the committed kernel glue and logic
# without putting their source in front of the author.
#   tools/cleanroom-glue-try.sh <tests workspace> [kernel commit, default HEAD] [cargo test args]
# The workspace holds Cargo.toml and tests/. Its tests reach the glue's Rust files and the logic
# as ../glue/<file>.rs and ../glue/logic/ (relative to tests/); this script puts them there in a
# temporary directory, runs the tests, prints only cargo's test output, and removes the directory.
set -euo pipefail
ws=${1:?tests workspace}; code=${2:-HEAD}; shift $(( $# > 2 ? 2 : $# ))
K=$HOME/Work/deepsleep-kernel; G=drivers/soc/apple/deepsleep
t=$(mktemp -d); trap 'chmod -R u+w "$t" 2>/dev/null; rm -rf "$t"' EXIT
rsync -a --exclude target --exclude .git --exclude interface --exclude spec "$ws"/ "$t"/ws/
mkdir -p "$t/glue"; git -C "$K" archive "$code" "$G" | tar -x -C "$t" ; cp -r "$t/$G/." "$t/glue/"; rm -rf "$t/drivers" "$t/glue/hosttest"
cd "$t/ws" && { cargo test --offline --no-fail-fast "$@" 2>&1 || true; } | grep -v -E '^\s+(Compiling|Finished|Running|Doc-tests)|^\s*-->|^\s*\|' | grep -v "$t/glue" | cut -c1-400
