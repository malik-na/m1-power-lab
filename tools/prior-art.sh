#!/bin/bash
# Prior art for a component, before any probe or build: where our own evidence, the reference
# deep-dive and Aurora Silicon's repositories (usable as they are or modified) already cover it.
#   tools/prior-art.sh <word> [<word> ...]      e.g. tools/prior-art.sh pmp     tools/prior-art.sh wake rvbar
# Prints file hits with counts, most hits first; read the top ones. Read-only.
# (2026-11-19: pmp's set-up was rediscovered over six builds though Aurora's pmp_init.py had it.)
set -u
[ $# -ge 1 ] || { echo "usage: $0 <word> [<word> ...]"; exit 2; }
repo=$(cd "$(dirname "$0")/.." && pwd); ref=${AURORA_REF:-$HOME/Work/aurora-ref}
pat=$(IFS='|'; echo "$*")
count() { sort | uniq -c | sort -rn | head -"${1:-15}" | sed 's/^/  /'; }
echo "== fact cards (docs/cards)"
grep -rliE "$pat" "$repo/docs/cards" 2>/dev/null | sed "s|$repo/||;s/^/  /"
echo "== our evidence and experiments: sections naming it"
grep -rnE "^#+ .*($pat)" -i "$repo/docs/evidence" "$repo/docs/experiments" 2>/dev/null | sed "s|$repo/||" | cut -c1-170 | head -40 | sed 's/^/  /'
echo "== reference docs and spec: lines naming it (count per file)"
grep -rciE "$pat" "$repo/docs/reference" "$repo/docs/spec" 2>/dev/null | grep -v ':0$' | sed "s|$repo/||" | sort -t: -k2 -rn | head -10 | sed 's/^/  /'
echo "== Aurora Silicon checkouts ($ref): files naming it"
for d in "$ref"/*/; do [ -d "$d/.git" ] || continue
  git -C "$d" grep -liE "$pat" -- . 2>/dev/null | head -400 | sed "s|^|$(basename "$d")/|"
done | awk -F/ '{print}' | grep -E "\.(c|h|rs|py|S|md|rst|dtsi|yaml)$" | grep -viE "/(tegra|qcom|mediatek|rockchip|samsung|nvidia)" | head -60 | sed 's/^/  /'
echo "== Aurora Silicon bare repos ($ref/*.git): files naming it (default branch, plus aurora-wip and integration/aurora)"
for d in "$ref"/*.git; do [ -d "$d" ] || continue
  b=$(git --git-dir="$d" symbolic-ref -q --short HEAD 2>/dev/null || git --git-dir="$d" for-each-ref --format='%(refname:short)' refs/heads | head -1)
  [ -n "$b" ] || continue
  for br in $b $(git --git-dir="$d" for-each-ref --format='%(refname:short)' refs/heads | grep -E '^(aurora-wip|integration/aurora)$' | grep -vx "$b"); do
    git --git-dir="$d" grep -liE "$pat" "$br" -- . 2>/dev/null | head -40 | sed "s|^$br:|$(basename "$d") [$br] |"
  done
done | grep -E "\.(c|h|rs|py|S|md|rst)$" | head -90 | sed 's/^/  /'
