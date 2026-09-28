# Operations guide

## Current qualification state

Release `1212afd` is installed and enabled on the ThinkPad. The coordinator,
private owner interface, and service-owned Codex jobs run independently of the
setup terminal. The sleep, idle, and lid-switch inhibitor is held while the
coordinator runs. A separately installed, explicitly started inspect-only
helper has completed five fixed read-only requests against the connected M1
proxy on USB topology `1-2` at `/dev/ttyACM1`. Native experiment dispatch
remains disabled; result collection, power measurement, and recovery have not
passed the physical qualification gates.

The previous installed session was stopped after resolving uncertain usage
with a conservative 300,000-token owner decision, not a provider measurement.
The new session `session_8b26578813be485da5afc3058473ea28` retains the failed
eighth-attempt evidence. Its first service-owned analysis used 27,986 reported
tokens; a resumed turn used 51,192 additional tokens, for a provider-reported
thread total of 79,178 with no usage uncertainty. During the resumed turn, 90
authenticated and anonymous HTTP probes returned the expected 200 or 403, with
the slowest at 3.438 seconds. This demonstrates independently available
bounded analysis; it does not qualify an autonomous native experiment loop.

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
IDs. If installation stops after a release is built, rerun the command with
the same ID and same source commit to resume the systemd setup and selection;
the installer verifies the release completion marker before continuing.

```bash
RELEASE_ID=$(git rev-parse --short HEAD)
sudo scripts/release.sh install "$RELEASE_ID"
```

The script refuses to switch while the service is active and refuses to
overwrite or resume a release built from a different commit. Before an update,
pause or stop the session, resolve unknown work, make and verify a backup, then
stop the service. Run the installer from the new committed checkout using a
new release ID. The previous release and state remain available. Review the
configuration and run
`m1lab diagnostics` against the selected release before starting the unit.
The installer takes the same coordinator lock as the service and reads the
journal read-only. For install and rollback it also checks that the journal
schema version is inside the selected release's supported range. It refuses to
install or switch while a session phase is active, job/operation effects or
usage are unresolved, a live budget reservation remains, or an active-time
segment is still open.

Source maintenance tooling also refuses an active hardware-helper unit and
holds its stable owner lock through the release operation. The helper's private
state directory is `/var/lib/m1-power-lab-helper`; its deny journal is retained
across source updates and rollbacks. These guards are installed in release
`1212afd`. The earlier usage hold was resolved before installation; maintenance
still requires the current session and jobs to satisfy the gates above.

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
Each Codex turn also receives restricted sandbox read access rooted at the
configured workspace. Workspace-write jobs can write only to declared paths
inside that workspace; path resolution rejects symlinks that escape it.
`CODEX_HOME` and unrelated host files are outside those roots. System-provided
compatibility paths remain available for the sandbox.
The systemd unit also gives the coordinator and its Codex child a private `/dev`,
so they cannot open host USB/serial devices. The separate inspect-only helper
has scoped device access; native dispatch is still unavailable. Do not remove
the coordinator's private-device boundary to enable hardware dispatch. systemd
stops the full service cgroup, including the Codex app-server, and escalates
after the 20-second shutdown window if graceful cleanup does not finish.

## Inspect-only hardware-helper unit

`systemd/m1-power-lab-helper.service` and
`config/m1-power-lab-helper.env.example` remain prepare-only repository
templates. The release installer does not install or enable the helper unit;
the installed unit was separately reviewed and installed. Its fixed observer
can inspect the proxy but cannot enable live experiment dispatch. The example
retains an invalid `UNSET` serial digest so it cannot start unconfigured.

The installed helper runs as `m1lab` with primary group `m1lab`, without a
supplementary `uucp` group. Its closed device policy admits only the reviewed
`/dev/ttyACM1` at USB topology `1-2`, with mode `0660` scoped to `m1lab`.
The coordinator retains `PrivateDevices=yes`. The configured tty, unit
`DeviceAllow`, topology and locally verified serial digest must agree. The
root-owned environment file has mode 0600; keep the serial-derived identifier
out of published evidence. The repository template still names the earlier
`/dev/ttyACM0` and `uucp` setup; do not treat it as the installed unit.

The installed helper unit has no boot enablement or start/restart dependency on
the coordinator. `After` orders explicit starts and `StopPropagatedFrom` propagates
stop requests. The helper's `--require-coordinator-service` mode independently
requires the fixed coordinator unit to be active, opens a kernel process handle
(`pidfd`) for its MainPID and rechecks its invocation identity. When that process
ends, the helper stops; a new coordinator process cannot inherit the old
helper. `Restart=no` prevents helper self-restart. This avoids `BindsTo` and
`PartOf`, which can propagate coordinator restart into reopening the target.

The installed scoped unit completed a bounded five-request physical inspection
and was followed by five fixed read-only requests after the resumed Codex job.
This verifies proxy observation under its selected device policy. Static
`systemd-analyze verify` validates unit syntax only. Native result transport,
qualified dispatch and target recovery still require separate physical proof.
Future unit changes need the same settled accounting, backup and exact review
gates; do not copy the repository template over the running lab setup.

Preserve the helper state as well as the coordinator backup before eventual
maintenance. The existing coordinator backup/export does not include the
separate helper directory. Never overwrite or delete `owner.lock.deny` when
restoring an older coordinator archive: it retains refusal of already attempted
dispatches, including uncertain ones. Restore/migration of the combined state
still requires qualification before production dispatch is enabled.

## Codex runtime configuration

The app-server refuses to start if the configured executable is missing or its
SHA-256 differs from the configured pin. Calculate it with `sha256sum` after
installing the Codex CLI.

The coordinator admits one primary Codex job and at most two concurrent
analysis, review, or owner-chat helper jobs. The default
`M1LAB_MAX_CONCURRENT_CODEX_JOBS=3`
can be lowered to `1` or `2` in the service environment. Every job, including
helpers, gets its own durable record, deadline, reservation, usage accounting,
and stop handling. Hidden runtime child jobs are not part of the accounting
model. The app-server uses `medium` reasoning effort by default and rejects
`ultra`, which the upstream [Codex protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/config_types.rs)
identifies as the route to proactive multi-agent behavior.

An owner can start an independent helper against the current evidence, or link
one to a completed primary job so its result and bounded parent artifacts are
included in the helper's manifest:

```bash
m1lab --session SESSION_ID investigate --kind analyze \
  --parent-job-id PRIMARY_JOB_ID \
  --estimated-tokens 50000 --estimated-minutes 10 --deadline-minutes 10 \
  "Independently examine the strongest counterevidence and identify a discriminating next step."
```

A primary job can have at most two linked analysis/review helpers over its
lifetime. Helpers cannot spawn further helpers; review helpers still need an exact
`--procedure-id`. All helper admission goes through the same coordinator and
session budgets as primary jobs.

Edit `/etc/m1-power-lab.env`, generate the CSRF secret shown in the example,
and set the exact Tailscale login. Create the session with the same owner before
starting the service:

```bash
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab init \
  --owner owner@example.com --target-identity m1-target
sudo systemctl enable --now m1-power-lab
sudo systemctl --no-pager status m1-power-lab
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
```

Service-account CLI commands do not inherit the systemd service environment.
Set `M1LAB_DATA_DIR=/var/lib/m1-power-lab` explicitly, as in these examples,
to use the deployed journal and selected session.

On each service start, `m1lab serve` takes the coordinator lock and reconciles
the durable journal before opening the HTTP listener. Startup refuses a journal
with missing migration history or a schema version outside this release's
supported range, before changing its journal mode or applying schema changes.
Diagnostics report OS/platform, Python and Codex versions, configured paths,
Codex executable pin status, runtime configuration, and unqualified hardware
gates. An executable pin match does not qualify authentication or a live model
turn. Check process
readiness and startup errors with:

```bash
sudo journalctl -u m1-power-lab --since today --no-pager
```

CLI and web Codex jobs take fresh AC, thermal, and data-disk readings before
admission and again immediately before runtime launch. Work is denied unless
AC is confirmed, a thermal reading is available and below 90 °C, and at least
5 GiB is free under the data root. An admission change after a durable job
record is created leaves a failed job record and releases its reservation; it
does not start Codex. These checks do not establish actual lid behavior,
shutdown handling, or the correctness of the T480's sensors. The separately
held sleep inhibitor only confirms the logind lock request.

While the app-server runtime is enabled, the coordinator repeats these host
checks every five seconds. A blocker or failed readiness sample pauses active
investigation phases, records `host.readiness_blocked`, and requests
interruption of live Codex jobs. A review or approval wait is preserved if
only a bounded job was running. After a safety pause, the owner must inspect
the cause and resume explicitly; recovery never auto-resumes paid work. On
service shutdown, the runtime is interrupted through its normal close path.

Sleep and lid inhibition is opt-in. Set `M1LAB_INHIBIT_SLEEP=1` in the
root-owned environment file to run the service under `systemd-inhibit` with
sleep, idle, and lid-switch handling locks. The locks exist only while the
service process is alive and are released automatically when it exits; no
logind settings are edited. Installation adds a Polkit rule granting only the
`m1lab` account the three logind inhibitor actions needed for this mode. If
logind denies the lock or the command is missing, the service fails to start
rather than claiming inhibition. A held lock does not qualify actual lid
behavior. The lock does not block explicit shutdown requests.

The overview and `m1lab diagnostics` report whether inhibition was not
requested, requested but unconfirmed, or held by the service wrapper. A held
lock confirms the logind request succeeded; it does not prove how this T480's
firmware or lid sensor behaves. If inhibition is explicitly requested but not
confirmed, Codex admission is closed even when `m1lab serve` is launched
outside the systemd wrapper.

The standalone `m1lab investigate` command also takes the coordinator lease and
reconciles the journal before starting a turn. It refuses to run while the
service or another coordinator owns the data directory; submit jobs through the
owner interface while the service is running.

For standalone evidence input, `--evidence` accepts only UTF-8 regular files up
to 1 MB and does not follow symlinks. Common credential forms and recognized
provider token formats, credential-named JSON fields (including short values
under token, authorization, and private-key names), email addresses, and
home-directory prefixes are scrubbed from evidence text and labels. Ordinary
usage fields such as `codex_tokens` are retained. Review selected material for
other personal data or unrelated private contents before starting the turn;
automated scrubbing cannot identify every such case.
Use repeatable `--artifact-id` to include exact published artifacts from the
selected session, including older captures outside the automatic context
window. The manifest retains bounded excerpts and artifact digests.

Approval cards show the recorded recovery steps, status and evidence references
alongside the reasons for their risk category. High declared failure severity
is high risk; a mutating procedure with no recovery steps or explicitly
unqualified recovery is also high risk. Other mutating procedures remain medium
risk. These are conservative categories from recorded fields, not recovery
probabilities or proof that recovery was demonstrated.

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

Budget reservations close admission for additional jobs but do not by themselves
interrupt the job that holds the reservation. Reaching the actual token or
active-time limit moves the session to `budget_exhausted` and interrupts live
Codex work. After granting tokens or extending/resetting time, explicitly resume
the session.

An accepted response proves the interruption request reached the runtime. The
terminal job event and final usage record determine whether it completed.
An interrupted job retains a usage hold even if earlier response counts exist:
those counts remain recorded, but cannot prove coverage of the interrupted
response. Reconcile the missing usage with evidence or an explicit owner
allowance decision before further model work or maintenance. If
the coordinator cannot confirm either, usage remains uncertain and new model
work stays closed.

A stopped host process does not prove a native target harness stopped. Observe
the target identity, boot epoch, and last operation before resuming.

## Backup and restore

Create a verified bundle before every update and keep it with the release that
created it:

```bash
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab \
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
runs SQLite `quick_check`, and checks the database schema against the manifest
and selected release before swapping data. New version-two bundles carry a
schema stamp; legacy version-one bundles without one are accepted only when the
bundled database's recorded schema is supported. It moves the prior database
and artifact tree into a timestamped
`restore-previous-*` directory. Validation finishes before the current data
root is replaced. Restored database and artifact files are mode
0600, and the artifact directory is mode 0700.

```bash
sudo systemctl stop m1-power-lab
sudo -u m1lab /opt/m1-power-lab/current/.venv/bin/python \
  /opt/m1-power-lab/current/scripts/restore-backup.py \
  /var/lib/m1-power-lab/pre-update.zip /var/lib/m1-power-lab
sudo systemctl start m1-power-lab
```

## Update and rollback

Install updates from a clean, committed checkout using the guarded installer.
Do not modify an installed release; keep the prior release directory as the
known-good rollback target. Inspect status and jobs as `m1lab`, pause or stop
the session, reconcile uncertain job usage with an evidence-backed
`usage-resolve` bound, and reconcile any unknown-effect operation with
`operation-reconcile`. Historical `unknown` job records remain intact after
usage resolution and do not prevent maintenance. Admitted or running jobs,
uncertain usage, active reservations, and open active-time segments still
block maintenance. Stop the service, run
the maintenance check, create a verified backup, then install and start the
new release:

```bash
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab status
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab jobs
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab control pause
sudo systemctl stop m1-power-lab
sudo scripts/release.sh check
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab backup-bundle \
  /var/lib/m1-power-lab/pre-update.zip
RELEASE_ID=$(git rev-parse --short HEAD)
sudo scripts/release.sh install "$RELEASE_ID"
sudo systemctl start m1-power-lab
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab status
```

To roll back code, stop the service and atomically point `current` at the prior
release. If the new release changed durable data incompatibly, restore the
matching pre-update bundle after switching code and before starting the old
release.

```bash
sudo systemctl stop m1-power-lab
sudo /opt/m1-power-lab/current/scripts/release.sh switch OLD_RELEASE
sudo systemctl start m1-power-lab
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab diagnostics
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab status
```

## Uninstall

Pause the session and wait for Codex jobs to settle, reconcile uncertain usage,
and resolve unknown-effect operations. Historical unknown job outcomes may
remain after usage resolution. Create and verify a final bundle before removing
the service.
Keep the data root if its evidence or Codex state is still needed.

If this installation uses the dedicated Tailscale HTTPS listener shown above,
check `tailscale serve status` and remove that proxy before removing the
application:

```bash
sudo tailscale serve --https=443 off
```

This disables the HTTPS listener on port 443. If it also serves other
applications, preserve their routes and remove only the lab proxy through
the Tailscale configuration instead.

```bash
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab status
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab jobs
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab control pause
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab jobs
sudo systemctl stop m1-power-lab
sudo /opt/m1-power-lab/current/scripts/release.sh check
sudo -u m1lab env M1LAB_DATA_DIR=/var/lib/m1-power-lab \
  /opt/m1-power-lab/current/.venv/bin/m1lab backup-bundle \
  /var/lib/m1-power-lab/final-backup.zip
sudo systemctl disable m1-power-lab
sudo rm -f /etc/systemd/system/m1-power-lab.service \
  /etc/polkit-1/rules.d/50-m1-power-lab-inhibit.rules \
  /etc/m1-power-lab.env
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
