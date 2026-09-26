#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT=/opt/m1-power-lab
STATE_ROOT=/var/lib/m1-power-lab
SERVICE_NAME=m1-power-lab.service
SERVICE_USER=m1lab
ENV_FILE=/etc/m1-power-lab.env
UNIT_FILE=/etc/systemd/system/m1-power-lab.service

usage() {
  cat >&2 <<'EOF'
Usage:
  sudo scripts/release.sh install RELEASE_ID
  sudo scripts/release.sh switch RELEASE_ID

install builds an immutable release from the current Git commit and switches
the current symlink. switch selects an already installed release (rollback).
Neither command starts the service. Quiesce the session and stop the service
before running either command on the ThinkPad.
EOF
  exit 2
}

[[ ${EUID} -eq 0 ]] || { echo "run this command with sudo" >&2; exit 1; }
[[ $# -eq 2 ]] || usage
action=$1
release_id=$2
[[ $release_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || {
  echo "release ID may contain only letters, digits, dot, underscore, and hyphen" >&2
  exit 2
}
case $action in install|switch) ;; *) usage ;; esac

if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "$SERVICE_NAME is active; quiesce the session and stop it before switching releases" >&2
  exit 1
fi

release_path="$APP_ROOT/releases/$release_id"
switch_release() {
  [[ -x "$release_path/.venv/bin/m1lab" ]] || {
    echo "release is missing its m1lab executable: $release_path" >&2
    exit 1
  }
  temporary_link="$APP_ROOT/.current.$$.next"
  rm -f -- "$temporary_link"
  ln -s "releases/$release_id" "$temporary_link"
  mv -Tf -- "$temporary_link" "$APP_ROOT/current"
}

if [[ $action == switch ]]; then
  [[ -d "$release_path" ]] || { echo "release does not exist: $release_path" >&2; exit 1; }
  switch_release
  echo "selected release $release_id; service remains stopped"
  exit 0
fi

[[ ! -e "$release_path" && ! -L "$release_path" ]] || {
  echo "release already exists; release directories are immutable: $release_path" >&2
  exit 1
}
source_root=$(git -C "$(dirname "${BASH_SOURCE[0]}")/.." rev-parse --show-toplevel)
git -C "$source_root" diff --quiet && git -C "$source_root" diff --cached --quiet || {
  echo "working tree has tracked changes; commit the release source before installing" >&2
  exit 1
}
mkdir -p "$APP_ROOT/releases"
staging=$(mktemp -d "$APP_ROOT/releases/.staging.XXXXXX")
cleanup() {
  if [[ -n ${staging:-} && -d $staging ]]; then rm -rf -- "$staging"; fi
}
trap cleanup EXIT
git -C "$source_root" archive --format=tar HEAD | tar -xf - -C "$staging"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$STATE_ROOT" --create-home \
    --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
  "$STATE_ROOT" "$STATE_ROOT/workspace" "$STATE_ROOT/codex"
install -d -o root -g root -m 0755 "$APP_ROOT/releases"
python3 -m venv "$staging/.venv"
"$staging/.venv/bin/python" -m pip install --requirement "$staging/requirements.lock"
"$staging/.venv/bin/python" -m pip install --no-deps "$staging"
chown -R root:root "$staging"
chmod -R go-w "$staging"
mv -- "$staging" "$release_path"
staging=

install -m 0644 "$release_path/systemd/m1-power-lab.service" "$UNIT_FILE"
if [[ ! -e $ENV_FILE ]]; then
  install -o root -g root -m 0600 "$release_path/config/m1-power-lab.env.example" "$ENV_FILE"
fi
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
switch_release
echo "installed release $release_id and selected it; configure $ENV_FILE, then run diagnostics before starting the service"
