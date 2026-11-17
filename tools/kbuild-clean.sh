#!/bin/bash
# Build the clean-room deep-sleep kernel: the committed HEAD of ~/Work/deepsleep-kernel, in the
# same offline build container as the earlier test kernels, with its own config and output folder.
#   tools/kbuild-clean.sh <tag>        e.g. ds1  ->  kernel release 7.2.11-ds1
# Output: ~/.cache/m1-s2r-kb/io-clean/out/kernel.tar.zst, log io-clean/build-<tag>.log.
# The config is io-clean/config (edit it to switch options). Uncommitted changes are not built.
set -uo pipefail
tag=${1:?tag}; K=$HOME/Work/deepsleep-kernel; C=$HOME/.cache/m1-s2r-kb; IO=$C/io-clean
[ -z "$(git -C "$K" status --porcelain --untracked-files=no)" ] || { echo "kbuild-clean: uncommitted changes in $K; commit first"; exit 2; }
SHA=$(git -C "$K" rev-parse HEAD)
sudo -n rsync -a --delete "$C/repo.git/" "$C/repo-root.git/" && sudo -n chown -R root:root "$C/repo-root.git" || { echo "kbuild-clean: could not copy the repository"; exit 2; }
sudo -n rm -rf "$IO/out"; echo "build $SHA as -$tag, start $(date +%T)"
sudo -n docker run --rm --network none --cpus 12 -e GIT_CONFIG_COUNT=3 -e GIT_CONFIG_KEY_0=gc.auto -e GIT_CONFIG_VALUE_0=0 \
  -e GIT_CONFIG_KEY_1=maintenance.auto -e GIT_CONFIG_VALUE_1=false -e GIT_CONFIG_KEY_2=fetch.autoMaintenance -e GIT_CONFIG_VALUE_2=false \
  -e URL=/repo -e SHA="$SHA" -e LABVER="-$tag" -v "$C/repo-root.git:/repo:ro" -v "$IO:/io" -v maclab-cache:/cache maclab-kbuild:1 > "$IO/build-$tag.log" 2>&1
rc=$?; echo "rc=$rc end $(date +%T)"
grep -n -B2 -A12 -E '^(error|warning: unused)|error:|Error [0-9]|undefined reference|not set in the config' "$IO/build-$tag.log" | head -80 | cut -c1-220
ls -la "$IO/out" 2>/dev/null | awk '{print $5, $9}' | tail -3; tail -2 "$IO/build-$tag.log" | cut -c1-160
exit $rc
