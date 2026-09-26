# M1 Power Lab

M1 Power Lab is a ThinkPad-hosted research workbench for investigating power management on an Apple M1 target through m1n1. It keeps scientific evidence, approvals, budgets, Codex jobs and target operations in one durable local application.

The first implementation uses a replay hardware adapter. Real m1n1 access stays disabled until the host/target transport, result channel and recovery path are qualified on the actual machines.

Authoritative design documents currently live in `/home/naeem/Notes`:

- `M1 investigation tool - design.md`
- `M1 investigation tool - implementation plan.md`
- `M1 investigation tool - requirements and gap audit.md`

The implemented module and information flow is summarized in
`docs/ARCHITECTURE.md`.

## Current status

The host application now includes the durable coordinator, replay experiment
executor, bounded Codex app-server adapter, CLI, and responsive owner UI.  The
real m1n1 adapter remains deliberately unavailable until the ThinkPad-to-Mac
transport and recovery path are qualified on the actual machines.

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

Open `http://127.0.0.1:8765`. The replay demonstration exercises observation,
review, authorization, typed dispatch, immutable evidence, and interpretation
without accessing a physical device.

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
`M1LAB_CODEX_RUNTIME=app-server`. The child process receives a small environment
containing its home/config paths, locale, executable path and TLS settings;
unrelated service secrets are not inherited.

See `docs/OPERATIONS.md` for Tailscale Serve and service deployment.
See `docs/SCIENCE.md` for the validated scientific record workflow.
See `docs/STATUS.md` for the implemented and physically qualified boundary.
