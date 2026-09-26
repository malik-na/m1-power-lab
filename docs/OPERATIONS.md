# Operations guide

## Current qualification state

The application is ready for host-only development and replay demonstrations.
The real m1n1 adapter remains unavailable until target identity, transport,
result collection, and recovery pass the physical qualification gates.

## Local development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
export M1LAB_DATA_DIR="$HOME/.local/share/m1-power-lab"
.venv/bin/m1lab init
.venv/bin/m1lab replay-demo
.venv/bin/m1lab serve
```

The default Codex workspace is `$M1LAB_DATA_DIR/workspace`. The loopback mode
accepts only loopback clients and does not trust forwarded identity headers.

## ThinkPad service installation

The system unit uses this layout:

| Path | Purpose |
|---|---|
| `/opt/m1-power-lab/releases/<release>` | immutable application releases |
| `/opt/m1-power-lab/current` | active release symlink |
| `/var/lib/m1-power-lab` | database, artifacts, workspace, and Codex home |
| `/etc/m1-power-lab.env` | host configuration |
| `/usr/local/bin/codex` | explicit system-wide Codex executable |

Run the installer on the ThinkPad from a clean, committed checkout. It builds
the release from the Git commit (excluding untracked files), installs the
pinned requirements, creates the service account and private state paths,
preserves an existing environment file, installs the systemd unit, and selects
the release atomically. The service remains stopped so you can configure it
before first startup. Release directories are immutable and must have unique
IDs.

```bash
RELEASE_ID=$(git rev-parse --short HEAD)
sudo scripts/release.sh install "$RELEASE_ID"
```

The script refuses to switch while the service is active and refuses to
overwrite an existing release. Before an update, pause or stop the session,
resolve unknown work, make and verify a backup, then stop the service. Run the
installer from the new committed checkout using a new release ID. The previous
release and state remain available. Review the configuration and run
`m1lab diagnostics` against the selected release before starting the unit.

Install Codex through its supported system-wide installation method. Set its
absolute path and the executable's SHA-256 digest as `M1LAB_CODEX_SHA256` in
`/etc/m1-power-lab.env`, then verify that the service account
can execute it and access its own authentication state:

```bash
sudo -u m1lab env HOME=/var/lib/m1-power-lab \
  CODEX_HOME=/var/lib/m1-power-lab/codex /usr/local/bin/codex --version
```

Complete the Codex CLI login flow as the `m1lab` account before setting
`M1LAB_CODEX_RUNTIME=app-server`. The runtime child receives only its home and
XDG paths, PATH, locale, network bypass/TLS settings, and variables explicitly supplied
by the coordinator. The web CSRF secret and unrelated host variables are not
inherited. Explicit child environment overrides are limited to that same allowlist.
The app-server refuses to start if the configured executable is missing or its
SHA-256 differs from the configured pin. Calculate it with `sha256sum` after
installing the Codex CLI.

Edit `/etc/m1-power-lab.env`, generate the CSRF secret shown in the example,
and set the exact Tailscale login. Create the session with the same owner before
starting the service:

```bash
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab init \
  --owner owner@example.com --target-identity m1-target
sudo systemctl enable --now m1-power-lab
sudo systemctl --no-pager status m1-power-lab
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
```

On each service start, `m1lab serve` takes the coordinator lock and reconciles
the durable journal before opening the HTTP listener. Diagnostics report the
OS/platform, Python and Codex versions, configured paths, Codex executable pin
status, runtime configuration, and unqualified hardware gates. An executable
pin match does not qualify authentication or a live model turn. Check process
readiness and startup errors with:

```bash
sudo journalctl -u m1-power-lab --since today --no-pager
```

CLI and web Codex jobs take fresh AC, thermal, and data-disk readings before
admission and again immediately before runtime launch. Work is denied unless
AC is confirmed, a thermal reading is available and below 90 °C, and at least
5 GiB is free under the data root. An admission change after a durable job
record is created leaves a failed job record and releases its reservation; it
does not start Codex. These checks do not qualify sleep inhibition, lid
behavior, shutdown handling, or the correctness of the T480's sensors.

## Tailscale access

Keep the application on loopback and proxy private HTTPS with Tailscale Serve:

```bash
sudo tailscale serve --bg 127.0.0.1:8765
tailscale serve status
```

Set `M1LAB_TRUST_TAILSCALE_HEADERS=1` and `M1LAB_OWNER_LOGIN` to the session
owner. Restrict the tailnet policy to that owner and do not enable Funnel. Test
the four views, reconnect behavior, and approval handling from the iPhone before
installing the site on its Home Screen.

## Optional owner notifications

Push delivery is disabled until all three VAPID settings are configured. On
the ThinkPad, generate a stable key pair in the private service state directory
and print the public application-server key:

```bash
sudo install -d -o m1lab -g m1lab -m 0700 /var/lib/m1-power-lab/vapid
sudo -u m1lab sh -c 'umask 077 && cd /var/lib/m1-power-lab/vapid && \
  /opt/m1-power-lab/current/.venv/bin/vapid --gen && \
  chmod 0600 private_key.pem && chmod 0644 public_key.pem && \
  /opt/m1-power-lab/current/.venv/bin/vapid --applicationServerKey'
```

Set `M1LAB_VAPID_PUBLIC_KEY` to the printed key,
`M1LAB_VAPID_PRIVATE_KEY` to
`/var/lib/m1-power-lab/vapid/private_key.pem`, and
`M1LAB_VAPID_SUBJECT` to an owner contact such as `mailto:owner@example.com`
in `/etc/m1-power-lab.env`. Keep the private key readable only by the service
account and preserve the same pair across releases; rotating it invalidates
existing browser subscriptions. Restart the service after configuration.

The owner explicitly enables notifications from the interface and can revoke
them there. Alerts use generic text and fixed private-view paths. Push delivery
is best effort: denied permissions, offline phones, expired subscriptions, or
delivery delays never change coordinator state or its approval/recovery queue.
Actual Home Screen behavior and delivery limitations still need qualification
on the iPhone 12 mini.

## Operator recovery commands

The CLI can inspect evidence and repair explicitly uncertain durable state:

```bash
m1lab status
m1lab events
m1lab artifacts
m1lab artifact-read ARTIFACT_ID
m1lab jobs --state running
m1lab operation-reconcile OPERATION_ID no_effect \
  --evidence ARTIFACT_ID --note "target observation proves no dispatch effect"
m1lab usage-resolve 250000 --evidence "provider report plus admitted upper bound" \
  --owner-decision
```

`job-interrupt` sends the request to the process that owns the live runtime. In
Tailscale mode, use the private HTTPS origin so Tailscale supplies the owner
identity:

```bash
m1lab job-interrupt JOB_ID \
  --coordinator-url https://thinkpad-name.tailnet-name.ts.net
```

If a `thread/start`, `thread/resume`, or `turn/start` response is lost or
ambiguous, the job is recorded as `unknown`, its Codex process group is stopped,
and new Codex work is blocked until `usage-resolve` records a conservative
upper bound.

An accepted response proves the interruption request reached the runtime. The
terminal job event and final usage record determine whether it completed. If
the coordinator cannot confirm either, usage remains uncertain and new model
work stays closed.

A stopped host process does not prove a native target harness stopped. Observe
the target identity, boot epoch, and last operation before resuming.

## Backup and restore

Create a verified bundle before every update and keep it with the release that
created it:

```bash
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab \
  backup-bundle /var/lib/m1-power-lab/pre-update.zip
```

Artifact publication and new Codex or target work stop when less than 512 MiB
would remain for the SQLite journal and cleanup. A capture estimated at 1 MiB
or larger must leave 1 GiB free after its result evidence. The check runs at
job admission, operation authorization, immediately before dispatch, and again
while publishing an artifact. A backup or restore also stops if its temporary
files would consume the 512 MiB reserve. Backup creation fails when any
referenced artifact is unavailable or fails its size or SHA-256 check; it does
not create a partial bundle that silently omits that evidence.

Restore only with the coordinator stopped. The restore tool takes the
coordinator lock, checks that its manifest covers exactly the database's
artifact rows and publication links, verifies every artifact size and digest,
runs SQLite `quick_check`, and moves the prior database and artifact tree into
a timestamped `restore-previous-*` directory. Validation finishes before the
current data root is replaced.

```bash
sudo systemctl stop m1-power-lab
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/python \
  /opt/m1-power-lab/current/scripts/restore-backup.py \
  /var/lib/m1-power-lab/pre-update.zip /var/lib/m1-power-lab
sudo systemctl start m1-power-lab
```

## Update and rollback

Install an update into a new release directory using the same archive, venv,
and package installation steps as the first install. Do not modify an installed
release; keep the prior release directory as the known-good rollback target.
Inspect status and jobs as `m1lab`, pause or stop the session, and wait until no
job is admitted or running. Resolve any unknown job or operation first. Do not
transition releases during an active experiment. Create a verified backup,
then switch the symlink and restart:

```bash
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab status
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab jobs
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab control pause
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab backup-bundle \
  /var/lib/m1-power-lab/pre-update.zip
sudo systemctl stop m1-power-lab
sudo ln -s releases/NEW_RELEASE /opt/m1-power-lab/current.next
sudo mv -Tf /opt/m1-power-lab/current.next /opt/m1-power-lab/current
sudo systemctl start m1-power-lab
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab status
```

To roll back code, stop the service and atomically point `current` at the prior
release. If the new release changed durable data incompatibly, restore the
matching pre-update bundle after switching code and before starting the old
release.

```bash
sudo systemctl stop m1-power-lab
sudo scripts/release.sh switch OLD_RELEASE
sudo systemctl start m1-power-lab
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab status
```

## Uninstall

Create and verify a final bundle before removing the service. Keep the data
root if its evidence or Codex state is still needed.

```bash
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/m1lab backup-bundle \
  /var/lib/m1-power-lab/final-backup.zip
sudo systemctl disable --now m1-power-lab
sudo rm -f /etc/systemd/system/m1-power-lab.service /etc/m1-power-lab.env
sudo systemctl daemon-reload
sudo rm -rf /opt/m1-power-lab
sudo userdel m1lab
```

After securely retaining the verified backup, remove `/var/lib/m1-power-lab`
only if its evidence and Codex state are no longer required:

```bash
sudo rm -rf /var/lib/m1-power-lab
```

## Qualification boundary

`m1lab replay-demo` proves only the host workflow. It does not qualify USB,
serial, m1n1, target recovery, power sensors, native result collection, or a
power improvement. `m1lab diagnostics` keeps that distinction visible.
