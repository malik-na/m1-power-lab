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
  sudo scripts/release.sh check

install builds an immutable release from the current Git commit and switches
the current symlink. switch selects an already installed release (rollback).
Neither command starts the service. Quiesce the session and stop the service
before running either command on the ThinkPad.
EOF
  exit 2
}

[[ ${EUID} -eq 0 ]] || { echo "run this command with sudo" >&2; exit 1; }
[[ $# -ge 1 ]] || usage
action=$1
case $action in
  check)
    [[ $# -eq 1 ]] || usage
    release_id=
    ;;
  install|switch)
    [[ $# -eq 2 ]] || usage
    release_id=$2
    [[ $release_id =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] || {
      echo "release ID may contain only letters, digits, dot, underscore, and hyphen" >&2
      exit 2
    }
    ;;
  *) usage ;;
esac

source_root=
release_path=
schema_file=
if [[ $action == install ]]; then
  source_root=$(cd -- "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
  release_path="$APP_ROOT/releases/$release_id"
  schema_file="$source_root/src/m1lab/core/journal.py"
elif [[ $action == switch ]]; then
  release_path="$APP_ROOT/releases/$release_id"
  [[ -d "$release_path" && ! -L "$release_path" ]] || {
    echo "release must exist as a real directory: $release_path" >&2
    exit 1
  }
  schema_file="$release_path/src/m1lab/core/journal.py"
fi

supported_schema_min=
supported_schema_max=
if [[ -n $schema_file ]]; then
  schema_range=$(python3 - "$schema_file" <<'PY'
import ast
from pathlib import Path
import sys

tree = ast.parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
values = {}
for node in tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if isinstance(target, ast.Name) and target.id in {
        "MIN_SUPPORTED_SCHEMA_VERSION",
        "SCHEMA_VERSION",
    }:
        value = node.value
        if not isinstance(value, ast.Constant) or type(value.value) is not int:
            raise SystemExit("release schema version must be an integer literal")
        values[target.id] = value.value
if "SCHEMA_VERSION" not in values:
    raise SystemExit("release does not declare its journal schema version")
minimum = values.get("MIN_SUPPORTED_SCHEMA_VERSION", 2)
if minimum < 1 or minimum > values["SCHEMA_VERSION"]:
    raise SystemExit("release declares an invalid supported schema range")
print(f"{minimum}:{values['SCHEMA_VERSION']}")
PY
  ) || {
    echo "cannot determine the selected release's supported journal schema range" >&2
    exit 1
  }
  IFS=: read -r supported_schema_min supported_schema_max <<<"$schema_range"
fi

if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "$SERVICE_NAME is active; quiesce the session and stop it before switching releases" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  if [[ $action == install ]]; then
    useradd --system --home-dir "$STATE_ROOT" --create-home \
      --shell /usr/sbin/nologin "$SERVICE_USER"
  else
    echo "service account $SERVICE_USER is missing; cannot switch releases" >&2
    exit 1
  fi
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$STATE_ROOT"
lock_path="$STATE_ROOT/coordinator.lock"
if [[ -L $lock_path ]]; then
  echo "coordinator lock path must not be a symbolic link" >&2
  exit 1
fi
if [[ ! -e $lock_path ]]; then
  temporary_lock=$(mktemp /tmp/m1lab-coordinator-lock.XXXXXX)
  chown "$SERVICE_USER:$SERVICE_USER" "$temporary_lock"
  chmod 0600 "$temporary_lock"
  mv -n -- "$temporary_lock" "$lock_path"
  rm -f -- "$temporary_lock"
fi
exec {maintenance_lock_fd}>>"$lock_path"
flock -n "$maintenance_lock_fd" || {
  echo "coordinator lock is held; stop the service and all coordinator work first" >&2
  exit 1
}
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "$SERVICE_NAME became active while preparing the release switch" >&2
  exit 1
fi

database_path="$STATE_ROOT/m1lab.sqlite3"
if [[ -e $database_path ]]; then
  python3 - "$database_path" "${supported_schema_min:-0}" "${supported_schema_max:-0}" <<'PY'
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

path = Path(sys.argv[1]).resolve()
minimum_schema = int(sys.argv[2])
maximum_schema = int(sys.argv[3])
connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)
connection.row_factory = sqlite3.Row
try:
    connection.execute("BEGIN")
    check = connection.execute("PRAGMA quick_check").fetchone()[0]
    if check != "ok":
        raise SystemExit(f"release refused: journal quick_check failed: {check}")
    required = {
        "schema_migrations",
        "sessions",
        "jobs",
        "operations",
        "reservations",
        "active_segments",
    }
    tables = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing = required - tables
    if missing:
        raise SystemExit(
            "release refused: journal lacks required tables: " + ", ".join(sorted(missing))
        )
    versions = [
        row[0] for row in connection.execute("SELECT version FROM schema_migrations")
    ]
    if not versions or any(type(version) is not int or version < 1 for version in versions):
        raise SystemExit("release refused: journal has missing or invalid schema migration history")
    latest_schema = max(versions)
    if minimum_schema and not minimum_schema <= latest_schema <= maximum_schema:
        raise SystemExit(
            "release refused: journal schema version "
            f"{latest_schema} is outside the selected release's supported range "
            f"{minimum_schema}..{maximum_schema}"
        )
    active_sessions = connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE phase IN "
        "('investigating','executing','interpreting','recovering')"
    ).fetchone()[0]
    uncertain_usage = connection.execute(
        "SELECT COUNT(*) FROM sessions WHERE usage_uncertain != 0"
    ).fetchone()[0]
    unresolved_jobs = connection.execute(
        "SELECT COUNT(*) FROM jobs WHERE state IN ('admitted','running','unknown')"
    ).fetchone()[0]
    unresolved_operations = connection.execute(
        "SELECT COUNT(*) FROM operations WHERE state IN ('intent','dispatched','unknown_effect')"
    ).fetchone()[0]
    active_reservations = connection.execute(
        "SELECT COUNT(*) FROM reservations WHERE released_at IS NULL AND expires_at > ?",
        (datetime.now(timezone.utc).isoformat(),),
    ).fetchone()[0]
    open_active_segments = connection.execute(
        "SELECT COUNT(*) FROM active_segments WHERE ended_utc IS NULL"
    ).fetchone()[0]
    counts = {
        "active_sessions": active_sessions,
        "uncertain_usage": uncertain_usage,
        "unresolved_jobs": unresolved_jobs,
        "unresolved_operations": unresolved_operations,
        "active_reservations": active_reservations,
        "open_active_segments": open_active_segments,
    }
    blockers = [f"{name}={count}" for name, count in counts.items() if count]
    if blockers:
        raise SystemExit(
            "release refused: resolve or pause durable work before switching: "
            + ", ".join(blockers)
        )
finally:
    connection.close()
PY
fi

if [[ $action == check ]]; then
  echo "service is stopped and durable coordinator state is clear for maintenance"
  exit 0
fi

switch_release() {
  [[ -x "$release_path/.venv/bin/m1lab" ]] || {
    echo "release is missing its m1lab executable: $release_path" >&2
    exit 1
  }
  runuser -u "$SERVICE_USER" -- "$release_path/.venv/bin/m1lab" --help >/dev/null || {
    echo "service account cannot run the selected release: $release_path" >&2
    exit 1
  }
  temporary_link="$APP_ROOT/.current.$$.next"
  rm -f -- "$temporary_link"
  ln -s "releases/$release_id" "$temporary_link"
  mv -Tf -- "$temporary_link" "$APP_ROOT/current"
}

if [[ $action == switch ]]; then
  switch_release
  echo "selected release $release_id; service remains stopped"
  exit 0
fi

git_repo() {
  git -c "safe.directory=$source_root" -C "$source_root" "$@"
}
source_commit=$(git_repo rev-parse --verify HEAD) || {
  echo "release source is not a Git checkout" >&2
  exit 1
}
git_repo diff --quiet && git_repo diff --cached --quiet || {
  echo "working tree has tracked changes; commit the release source before installing" >&2
  exit 1
}
mkdir -p "$APP_ROOT/releases"
if [[ -e "$release_path" || -L "$release_path" ]]; then
  [[ -d $release_path && ! -L $release_path ]] || {
    echo "release path exists and is not a real directory: $release_path" >&2
    exit 1
  }
  recorded_commit=$(<"$release_path/.m1lab-release-commit") || {
    echo "release exists without a completion marker; inspect it and choose a new release ID: $release_path" >&2
    exit 1
  }
  [[ $recorded_commit == "$source_commit" && -x "$release_path/.venv/bin/m1lab" ]] || {
    echo "release ID belongs to a different or incomplete commit: $release_path" >&2
    exit 1
  }
  echo "resuming installation of completed release $release_id ($source_commit)"
else
  staging=$(mktemp -d "$APP_ROOT/releases/.staging.XXXXXX")
  created_release=
  cleanup() {
    if [[ -n ${staging:-} && -d $staging ]]; then rm -rf -- "$staging"; fi
    if [[ -n ${created_release:-} && -d $created_release ]]; then
      rm -rf -- "$created_release"
    fi
  }
  trap cleanup EXIT
  git_repo archive --format=tar HEAD | tar -xf - -C "$staging"

  install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
    "$STATE_ROOT" "$STATE_ROOT/workspace" "$STATE_ROOT/codex"
  install -d -o root -g root -m 0755 "$APP_ROOT/releases"
  mv -- "$staging" "$release_path"
  staging=
  created_release=$release_path
  python3 -m venv "$release_path/.venv"
  "$release_path/.venv/bin/python" -m pip install --requirement "$release_path/requirements.lock"
  "$release_path/.venv/bin/python" -m pip install --no-deps "$release_path"
  chown -R root:root "$release_path"
  chmod -R go-w "$release_path"
  chmod 0755 "$release_path"
  printf '%s\n' "$source_commit" > "$release_path/.m1lab-release-commit"
  created_release=
fi

# mktemp creates the staging directory as 0700. The root-owned release must be
# traversable by the unprivileged service account, including on a resumed install.
chmod 0755 "$release_path"

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
  "$STATE_ROOT" "$STATE_ROOT/workspace" "$STATE_ROOT/codex"

install -m 0644 "$release_path/systemd/m1-power-lab.service" "$UNIT_FILE"
if [[ ! -e $ENV_FILE ]]; then
  install -o root -g root -m 0600 "$release_path/config/m1-power-lab.env.example" "$ENV_FILE"
fi
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
switch_release
echo "installed release $release_id and selected it; configure $ENV_FILE, then run diagnostics before starting the service"
