# M1 Power Lab

M1 Power Lab is a ThinkPad-hosted research workbench for investigating power management on an Apple M1 target through m1n1. It keeps scientific evidence, approvals, budgets, Codex jobs and target operations in one durable local application.

The host application runs independently as a ThinkPad service. It supports bounded Codex analysis of retained evidence and a replay hardware adapter. A separate inspect-only helper can observe the connected m1n1 proxy; native experiment dispatch remains disabled until transport, capture and recovery are qualified.

Project design and planning documents are checked into [`docs/plan`](docs/plan):

- [Approved design](docs/plan/M1%20investigation%20tool%20-%20design.md)
- [Implementation plan](docs/plan/M1%20investigation%20tool%20-%20implementation%20plan.md)
- [Requirements and gap audit](docs/plan/M1%20investigation%20tool%20-%20requirements%20and%20gap%20audit.md)
- [Historical transport and recovery research](docs/plan/M1%20tool%20-%20transport%20and%20recovery%20evidence.md)
- [Historical measurement research](docs/plan/M1%20tool%20-%20measurement%20evidence.md)
- [Historical Codex runtime research](docs/plan/M1%20tool%20-%20Codex%20runtime%20evidence.md)

The implemented module and information flow is summarized in
`docs/ARCHITECTURE.md`.

## Current status

The host application now includes the durable coordinator, replay experiment
executor, bounded Codex app-server adapter, CLI, and responsive owner UI.  The
native experiment adapter remains unavailable until the ThinkPad-to-Mac
transport and recovery path are qualified on the actual machines. The latest
physical attempt reached Linux USB enumeration. Target-side trace snapshots show
the selected EP0 status wrapper returned after its command was accepted, but
show no subsequent EP0 event; the host timed out during configuration and
captured no native samples. See
[current status](docs/STATUS.md) for the installed release, verified
capabilities, and remaining qualification gates.

## Quick start on the ThinkPad

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
export M1LAB_DATA_DIR="$HOME/.local/share/m1-power-lab"
# The default workspace is $M1LAB_DATA_DIR/workspace.
.venv/bin/m1lab init
.venv/bin/m1lab replay-demo
.venv/bin/m1lab serve
```

Open `http://127.0.0.1:8765`. The replay demonstration exercises a read-only
observation and an exactly approved simulated boot, then publishes immutable
host-only scientific evidence for matching CLI and web readback. It does not
access a physical device or establish M1 behavior.

Useful recovery commands:

```bash
.venv/bin/m1lab status
.venv/bin/m1lab events
.venv/bin/m1lab artifacts
.venv/bin/m1lab science list
.venv/bin/m1lab science brief
.venv/bin/m1lab jobs
.venv/bin/m1lab control pause
.venv/bin/m1lab control stop
.venv/bin/m1lab reconcile
.venv/bin/m1lab export ./evidence.json
.venv/bin/m1lab backup ./m1lab.sqlite3.backup
.venv/bin/m1lab backup-bundle ./m1lab-backup.zip
```

When Codex is enabled, set `M1LAB_CODEX_EXECUTABLE` to the installed CLI and
`M1LAB_CODEX_SHA256` to its SHA-256 digest, then set
`M1LAB_CODEX_RUNTIME=app-server`. The CLI verifies that digest before every
app-server process start. The child process receives a small environment
containing its home/config paths, locale, executable path and TLS settings;
unrelated service secrets are not inherited.

See `docs/OPERATIONS.md` for Tailscale Serve and service deployment.
See `docs/SCIENCE.md` for the validated scientific record workflow.
See `docs/BUILDING.md` for isolated target builds and artifact provenance.
See `docs/STATUS.md` for the implemented and physically qualified boundary.

For the connected Mac's explicit native harness, run the read-only
[native preflight](docs/NATIVE-PREFLIGHT.md) before starting a helper. After a
capture, `m1lab --session SESSION native-summary --capture-artifact ARTIFACT`
checks retained raw evidence and lists sensor fields, missing readings and
reported cadence. Use `investigate --artifact-id ARTIFACT` to select that
capture explicitly for technical analysis. See the
[native harness guide](docs/NATIVE-HARNESS.md) for the attended launch workflow.
