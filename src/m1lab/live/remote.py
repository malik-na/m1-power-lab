"""SSH transport from the Omarchy host to the measured Mac.

Everything the target runs is the single-file agent in ``agent.py``. Short
commands run synchronously; experiments run detached under ``systemd-run`` so
that the measurement is not perturbed by an open network stream, and the host
collects their JSON result afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import threading
import time
from typing import Any, Callable, Iterator

PACKAGE_DIR = Path(__file__).resolve().parent
AGENT_SOURCE = PACKAGE_DIR / "agent.py"
REPO_ROOT = PACKAGE_DIR.parents[2]
KMOD_DIR = REPO_ROOT / "target" / "kmod"

REMOTE_HOME = "/usr/local/lib/m1power"
REMOTE_AGENT = f"{REMOTE_HOME}/agent.py"
REMOTE_KMOD_SRC = "/usr/local/src/m1power"
REMOTE_RESULTS = "/var/lib/m1power/results"
HOOK_PATH = "/usr/lib/systemd/system-sleep/m1power"

HOOK_SCRIPT = f"""#!/bin/sh
# m1power: bracket every suspend in /var/lib/m1power/ledger.jsonl
[ -x /usr/bin/python3 ] && [ -f {REMOTE_AGENT} ] || exit 0
exec /usr/bin/python3 -I {REMOTE_AGENT} hook "$1" "$2" >/dev/null 2>&1 || true
"""

KMOD_UNIT = f"""[Unit]
Description=Build and load the m1power research module
After=local-fs.target
ConditionPathExists={REMOTE_KMOD_SRC}

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -I {REMOTE_AGENT} kmod
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
"""


class TargetError(RuntimeError):
    pass


class Unreachable(TargetError):
    pass


class NeedsReauth(TargetError):
    """Tailscale SSH in check mode wants the owner to re-authenticate."""


TAILSCALE_CHECK = "Tailscale SSH requires an additional check"


def _reauth_message(*chunks: bytes | str | None) -> str | None:
    text = "".join(c.decode(errors="replace") if isinstance(c, bytes) else (c or "") for c in chunks)
    if TAILSCALE_CHECK not in text:
        return None
    url = next((word for word in text.split() if word.startswith("https://login.tailscale.com/")), "")
    return f"Tailscale SSH needs you to re-authenticate before m1power can reach the target: open {url}".strip()


def default_target() -> str:
    env = os.environ.get("M1POWER_TARGET")
    if env:
        return env
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "m1-power-lab" / "target"
    if config.exists():
        return config.read_text().strip()
    return "root@naeems-m1-air"


def results_dir() -> Path:
    override = os.environ.get("M1POWER_RESULTS")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    path = base / "m1-power-lab" / "live"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agent_digest() -> str:
    return hashlib.sha256(AGENT_SOURCE.read_bytes()).hexdigest()[:16]


def verified_upload_script(path: str, digest: str) -> str:
    """Shell that writes stdin to ``path`` atomically, only if its sha256 matches.

    The data lands in a temp file in the same directory and is renamed into
    place, so an interrupted upload never leaves a truncated file at ``path``.
    """
    directory = shlex.quote(os.path.dirname(path))
    return (
        f"set -e; mkdir -p {directory}; tmp=$(mktemp {directory}/.agent.XXXXXX); trap 'rm -f \"$tmp\"' EXIT; "
        f"cat > \"$tmp\"; "
        f"if [ \"$(sha256sum \"$tmp\" | cut -c1-16)\" != {shlex.quote(digest)} ]; then echo 'agent upload corrupted (sha256 mismatch)' >&2; exit 1; fi; "
        f"chmod 644 \"$tmp\"; mv -f \"$tmp\" {shlex.quote(path)}; trap - EXIT"
    )


def collect_hint(job_id: str) -> str:
    return f"job {job_id} keeps running on the target; collect its result later with `m1power collect {job_id}`"


@dataclass
class Target:
    address: str

    def _ssh(self, command: str, *, input: bytes | None = None, timeout: float = 120) -> subprocess.CompletedProcess[bytes]:
        args = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=3",
            "-o", "StrictHostKeyChecking=accept-new",
            self.address,
            command,
        ]
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        chunks: dict[str, list[bytes]] = {"out": [], "err": []}

        def pump(stream, key):
            for block in iter(lambda: stream.read1(65536), b""):
                chunks[key].append(block)

        readers = [
            threading.Thread(target=pump, args=(process.stdout, "out"), daemon=True),
            threading.Thread(target=pump, args=(process.stderr, "err"), daemon=True),
        ]
        for reader in readers:
            reader.start()
        if input:
            try:
                process.stdin.write(input)
            except BrokenPipeError:
                pass
        process.stdin.close()
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            # Tailscale's check prompt arrives at once, then blocks until the
            # owner authenticates: report it instead of waiting out `timeout`.
            if time.monotonic() < deadline - timeout + 20:
                message = _reauth_message(b"".join(chunks["out"])[:600], b"".join(chunks["err"])[:600])
                if message:
                    process.kill()
                    raise NeedsReauth(message)
            if time.monotonic() > deadline:
                process.kill()
                raise Unreachable(f"{self.address}: timed out after {timeout:.0f}s")
            time.sleep(0.2)
        for reader in readers:
            reader.join(timeout=5)
        stdout, stderr = b"".join(chunks["out"]), b"".join(chunks["err"])
        proc = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        message = _reauth_message(stdout[:600], stderr[:600])
        if message:
            raise NeedsReauth(message)
        if proc.returncode == 255:
            raise Unreachable(f"{self.address}: {proc.stderr.decode(errors='replace').strip()}")
        return proc

    def run(self, command: str, *, input: bytes | None = None, timeout: float = 120, check: bool = True) -> str:
        proc = self._ssh(command, input=input, timeout=timeout)
        if check and proc.returncode != 0:
            raise TargetError(f"{command!r} failed ({proc.returncode}): {proc.stderr.decode(errors='replace').strip()}")
        return proc.stdout.decode(errors="replace")

    def reachable(self, timeout: float = 12) -> bool:
        try:
            self._ssh("true", timeout=timeout)
            return True
        except Unreachable:
            return False

    # ------------------------------------------------------------- agent

    def agent_path(self) -> str:
        """Make sure the current agent is on the target; return its path.

        A stale installed agent is replaced in place, so the sleep hook, the
        boot units and experiments always run the same version. Without an
        install the agent lives in /run. Every copy is checked by digest.
        """
        digest = agent_digest()
        fallback = f"/run/m1power/agent-{digest}.py"
        out = self.run(
            f"dg() {{ sha256sum \"$1\" 2>/dev/null | cut -c1-16; }}; "
            f"if [ -f {REMOTE_AGENT} ]; then if [ \"$(dg {REMOTE_AGENT})\" = {digest} ]; then echo {REMOTE_AGENT}; else echo stale; fi; "
            f"elif [ -f {fallback} ] && [ \"$(dg {fallback})\" = {digest} ]; then echo {fallback}; else echo missing; fi"
        ).strip()
        if out not in ("stale", "missing"):
            return out
        path = REMOTE_AGENT if out == "stale" else fallback
        self.run(f"bash -c {shlex.quote(verified_upload_script(path, digest))}", input=AGENT_SOURCE.read_bytes())
        return path

    def agent(self, *args: str, timeout: float = 120) -> Any:
        path = self.agent_path()
        out = self.run(f"cd /tmp && python3 -I {path} " + " ".join(shlex.quote(a) for a in args), timeout=timeout)
        lines = [line for line in out.splitlines() if line.strip()]
        if not lines:
            return None
        if len(lines) == 1:
            return json.loads(lines[0])
        return [json.loads(line) for line in lines]

    def stream(self, *args: str) -> Iterator[dict[str, Any]]:
        path = self.agent_path()
        command = f"cd /tmp && exec python3 -I -u {path} " + " ".join(shlex.quote(a) for a in args)
        proc = subprocess.Popen(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", self.address, command],
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                if line.strip():
                    yield json.loads(line)
        finally:
            proc.terminate()

    # ---------------------------------------------------------- detached

    def start_detached(self, job_id: str, *args: str) -> str:
        """Run an agent command under systemd-run; returns the result path."""
        path = self.agent_path()
        out_path = f"{REMOTE_RESULTS}/{job_id}.json"
        command = (
            f"mkdir -p {REMOTE_RESULTS} && rm -f {out_path} && "
            f"systemd-run --quiet --collect --unit=m1power-{job_id} --working-directory=/tmp "
            f"/usr/bin/python3 -I {path} " + " ".join(shlex.quote(a) for a in args) + f" --out {out_path}"
        )
        self.run(command)
        return out_path

    def wait_detached(
        self,
        job_id: str,
        out_path: str,
        *,
        expected_s: float,
        progress: Callable[[str], None] | None = None,
        poll_s: float = 20,
        grace_s: float = 900,
    ) -> dict[str, Any]:
        """Stay quiet for the expected duration, then poll for the result.

        Raises NeedsReauth (with the collect command) if Tailscale wants the
        owner to re-authenticate; the job itself keeps running on the target.
        """
        say = progress or (lambda message: None)
        deadline = time.monotonic() + expected_s
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            say(f"running on target, ~{remaining:.0f}s left (host stays off the network)")
            time.sleep(min(remaining, 60))
        give_up = time.monotonic() + grace_s
        last_error = ""
        while time.monotonic() < give_up:
            try:
                state = self.run(
                    f"echo \"state=$(systemctl is-active m1power-{job_id} 2>/dev/null)\"; cat {out_path} 2>/dev/null || true", timeout=40, check=False
                )
            except Unreachable as error:
                last_error = str(error)
                say("target not reachable yet (asleep or reconnecting)")
                time.sleep(poll_s)
                continue
            except NeedsReauth as error:
                raise NeedsReauth(f"{error}\n{collect_hint(job_id)}") from error
            status, _, body = state.partition("\n")
            # The state line is always present, even when is-active prints
            # nothing (bus not ready right after resume): treat that as unknown.
            status = status.removeprefix("state=")
            if not status.strip():
                say("job state unknown (systemd not answering yet)")
                time.sleep(poll_s)
                continue
            running = status.strip() in ("active", "activating")
            data = None
            if body.strip():
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = None
            if isinstance(data, dict) and data.get("status", "complete") == "complete" and not running:
                return data
            if not running:
                # The unit is gone but the file is missing, partial or
                # unreadable (reboot, crash, killed): waiting cannot help.
                try:
                    log = self.run(f"journalctl -u m1power-{job_id} --no-pager -n 30 -o cat", check=False, timeout=40)
                except NeedsReauth as error:
                    raise NeedsReauth(f"{error}\n{collect_hint(job_id)}") from error
                if not body.strip():
                    what = "ended without a result"
                elif isinstance(data, dict):
                    what = f"ended with an incomplete result (status {data.get('status')!r}, partial data left in {out_path})"
                else:
                    what = f"ended with an unreadable result in {out_path}"
                raise TargetError(f"job {job_id} {what} (unit {status.strip() or 'unknown'}):\n{log}")
            say("finishing on target")
            time.sleep(poll_s)
        raise TargetError(f"job {job_id} did not finish in time ({last_error}); {collect_hint(job_id)}")

    # ----------------------------------------------------------- install

    def install(self) -> dict[str, Any]:
        """Install agent, sleep hook, kernel module source and boot unit."""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            archive.add(AGENT_SOURCE, arcname="agent.py")
            for name in ("m1power.c", "Makefile"):
                archive.add(KMOD_DIR / name, arcname=f"kmod/{name}")
            for name, text in (("hook", HOOK_SCRIPT), ("unit", KMOD_UNIT)):
                data = text.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        script = f"""
set -e
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
tar -x -C "$tmp"
install -Dm644 "$tmp/agent.py" {REMOTE_AGENT}
rm -rf {REMOTE_KMOD_SRC}; install -d {REMOTE_KMOD_SRC}
install -m644 "$tmp/kmod/m1power.c" "$tmp/kmod/Makefile" {REMOTE_KMOD_SRC}/
install -Dm755 "$tmp/hook" {HOOK_PATH}
install -Dm644 "$tmp/unit" /etc/systemd/system/m1power-kmod.service
install -d /var/lib/m1power/results
# rebuild for the running kernel if the module source changed
new=$(sha256sum {REMOTE_KMOD_SRC}/m1power.c | cut -c1-16)
old=$(cat {REMOTE_HOME}/kmod/source.sha 2>/dev/null || true)
if [ "$new" != "$old" ]; then
  # the old module must go before the new source counts as installed
  if [ -d /sys/module/m1power ] && ! rmmod m1power; then
    # Drop the stale build so a reboot (m1power-kmod.service) compiles the new
    # source instead of reloading the old module.
    rm -rf {REMOTE_HOME}/kmod; mkdir -p {REMOTE_HOME}/kmod; echo "$new" > {REMOTE_HOME}/kmod/source.sha
    echo "m1power: the loaded m1power module is busy (a capture or job holds its files), so the changed module source cannot be loaded now; stop the job and rerun install, or reboot the target to build and load the new module" >&2
    exit 1
  fi
  rm -rf {REMOTE_HOME}/kmod; mkdir -p {REMOTE_HOME}/kmod; echo "$new" > {REMOTE_HOME}/kmod/source.sha
fi
systemctl daemon-reload
systemctl enable m1power-kmod.service >/dev/null 2>&1
cd /tmp && python3 -I {REMOTE_AGENT} kmod
"""
        out = self.run(f"bash -c {shlex.quote(script)}", input=buffer.getvalue(), timeout=900)
        return json.loads(out.strip().splitlines()[-1])

    def uninstall(self) -> str:
        script = f"""
python3 -I {REMOTE_AGENT} tune revert >/dev/null 2>&1 || true
python3 -I {REMOTE_AGENT} restore >/dev/null 2>&1 || true
systemctl disable --now m1power-kmod.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/m1power-kmod.service {HOOK_PATH}
rmmod m1power 2>/dev/null || true
rm -rf {REMOTE_HOME} {REMOTE_KMOD_SRC}
systemctl daemon-reload
echo "removed (the sleep ledger stays in /var/lib/m1power)"
"""
        return self.run(f"bash -c {shlex.quote(script)}")


def save_result(kind: str, data: dict[str, Any], label: str = "") -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%S")
    name = f"{stamp}-{kind}" + (f"-{label}" if label else "")
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
    path = results_dir() / f"{safe}.json"
    path.write_text(json.dumps(data, indent=1, sort_keys=True))
    return path


def new_job_id(kind: str) -> str:
    return f"{kind}-{time.strftime('%H%M%S')}-{os.getpid() % 10000}"
