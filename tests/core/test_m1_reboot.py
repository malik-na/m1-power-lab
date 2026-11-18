"""tools/m1-reboot/m1-reboot.sh finds the M1's port from its partner and refuses unsafe states.

On 2026-11-17 the script swapped the M3's USB-C driver under a live USB4 link and the M3's
Thunderbolt driver crashed at the M1's next login (docs/proposals/m1-safe-restart.md). The script
must now never load, unload or rebind a driver, must pick the M1's port from readings (PD identity
or Thunderbolt XDomain), refuse when none or several match, refuse without the tipd debugfs
command file, refuse unless the caller holds the M1, and run tuxvdmtool with --no-recover.
Runs against a fake sysfs and a stub tuxvdmtool in a copy of the script's tree.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _port(sys: Path, n: int, dev: str, label: str | None, id_header: str | None, cio: str | None):
    spmi = sys / "bus/spmi/devices" / dev
    (spmi / "of_node/connector").mkdir(parents=True)
    if label is not None:
        (spmi / "of_node/connector/label").write_bytes(label.encode() + b"\0")
    port = sys / f"class/typec/port{n}"
    port.mkdir(parents=True)
    (port / "device").symlink_to(spmi)
    if cio:
        (port / f"supplier:platform:{cio}").touch()
    if id_header is not None:
        (sys / f"class/typec/port{n}-partner/identity").mkdir(parents=True)
        (sys / f"class/typec/port{n}-partner/identity/id_header").write_text(id_header + "\n")
    (sys / "kernel/debug/usb/tipd" / dev).mkdir(parents=True)


def _xdomain(sys: Path, cio: str, name: str = "0-1"):
    d = sys / f"devices/platform/soc/{cio}/701f00000.nhi/domain0/0-0/{name}"
    d.mkdir(parents=True)
    (d / "uevent").write_text("DEVTYPE=thunderbolt_xdomain\n")
    (d / "vendor_name").write_text("Linux\n")
    (d / "device_name").write_text("m1-air-omarchy\n")
    (sys / "bus/thunderbolt/devices").mkdir(parents=True, exist_ok=True)
    (sys / "bus/thunderbolt/devices" / name).symlink_to(d)


def _setup(tmp_path: Path, *, apple_id=True, xdomain=False, command=True, second=False):
    root = tmp_path / "lab"
    (root / "tools/m1-reboot").mkdir(parents=True)
    (root / "tools/tb").mkdir(parents=True)
    (root / "var").mkdir()
    shutil.copy(REPO / "tools/m1-reboot/m1-reboot.sh", root / "tools/m1-reboot/")
    shutil.copy(REPO / "tools/tb/m1-claim", root / "tools/tb/")
    sys = tmp_path / "sys"
    _port(sys, 0, "1-06", None, "0x00000000", None)  # MagSafe: partner, no USB-C label
    _port(sys, 1, "2-08", "USB-C Right", None, "f01ac0000.cio")
    _port(sys, 2, "1-0c", "USB-C Left Back", "0xd50005ac" if apple_id else "0x00000000", "701ac0000.cio")
    _port(sys, 3, "1-0a", "USB-C Left Front",
          ("0xd50005ac" if second else None), "b01ac0000.cio")
    if xdomain:
        _xdomain(sys, "701ac0000.cio")
    if command:
        (sys / "kernel/debug/usb/tipd/1-0c/command").touch()
    calls = tmp_path / "tux-calls"
    tux = tmp_path / "tuxvdmtool"
    tux.write_text(
        "#!/bin/bash\n"
        'if [ "$1" = --help ]; then echo "        --no-recover    never rebind"; exit 0; fi\n'
        f'printf "%s\\n" "$*" >> {calls}\n'
    )
    tux.chmod(0o755)
    return root, sys, tux, calls


def _run(root: Path, sys: Path, tux: Path, *args: str, **env: str):
    e = {k: v for k, v in os.environ.items() if k not in ("M1_CLAIM", "M1_PORT")}
    e.update(M1R_SYS=str(sys), M1R_SUDO="", TUXVDMTOOL=str(tux), M1R_LOG=str(root / "var/log"))
    e.update(env)
    return subprocess.run(["bash", str(root / "tools/m1-reboot/m1-reboot.sh"), *args],
                          capture_output=True, text=True, env=e, timeout=30)


def _claim(root: Path, who: str):
    subprocess.run([str(root / "tools/tb/m1-claim"), "take", who, "test"], check=True,
                   capture_output=True)


def test_never_touches_modules_or_bindings():
    text = (REPO / "tools/m1-reboot/m1-reboot.sh").read_text()
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    for word in ("rmmod", "insmod", "modprobe", "/unbind", "/bind", "depmod"):
        assert word not in code, word
    assert "--no-recover" in code


def test_port_from_pd_identity(tmp_path):
    root, sys, tux, _ = _setup(tmp_path)
    r = _run(root, sys, tux, "which")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1-0c USB-C Left Back"


def test_port_from_thunderbolt_xdomain_when_identity_is_empty(tmp_path):
    root, sys, tux, _ = _setup(tmp_path, apple_id=False, xdomain=True)
    r = _run(root, sys, tux, "which")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1-0c USB-C Left Back"
    assert "m1-air-omarchy" in r.stderr


def test_refuses_when_nothing_identifies_the_m1(tmp_path):
    root, sys, tux, _ = _setup(tmp_path, apple_id=False)
    r = _run(root, sys, tux, "which")
    assert r.returncode == 1
    assert "REFUSED" in r.stderr and "M1_PORT" in r.stderr


def test_m1_port_names_it_when_nothing_identifies_the_m1(tmp_path):
    root, sys, tux, _ = _setup(tmp_path, apple_id=False)
    r = _run(root, sys, tux, "which", M1_PORT="1-0c")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "1-0c USB-C Left Back"


def test_m1_port_without_a_partner_or_against_the_readings_is_refused(tmp_path):
    root, sys, tux, _ = _setup(tmp_path)
    assert _run(root, sys, tux, "which", M1_PORT="2-08").returncode == 1  # no partner
    assert _run(root, sys, tux, "which", M1_PORT="1-06").returncode == 1  # MagSafe
    _port(sys, 4, "1-0d", "USB-C Spare", "0x00000000", None)
    r = _run(root, sys, tux, "which", M1_PORT="1-0d")
    assert r.returncode == 1 and "point at: 1-0c" in r.stderr


def test_refuses_when_several_ports_look_like_the_m1(tmp_path):
    root, sys, tux, _ = _setup(tmp_path, second=True)
    r = _run(root, sys, tux, "which")
    assert r.returncode == 1 and "several" in r.stderr


def test_refuses_without_the_command_file(tmp_path):
    root, sys, tux, calls = _setup(tmp_path, command=False)
    _claim(root, "me")
    r = _run(root, sys, tux, "reboot", M1_CLAIM="me")
    assert r.returncode == 1
    assert "command is missing" in r.stderr and "does not swap modules" in r.stderr
    assert not calls.exists()


def test_refuses_unless_the_caller_holds_the_m1(tmp_path):
    root, sys, tux, calls = _setup(tmp_path)
    r = _run(root, sys, tux, "reboot")
    assert r.returncode == 1 and "M1_CLAIM is not set" in r.stderr
    r = _run(root, sys, tux, "reboot", M1_CLAIM="me")  # free is not held
    assert r.returncode == 1 and "not claimed by 'me'" in r.stderr
    _claim(root, "other")
    r = _run(root, sys, tux, "reboot", M1_CLAIM="me")
    assert r.returncode == 1 and "held by" in r.stderr
    assert not calls.exists()


def test_refuses_a_tuxvdmtool_without_no_recover(tmp_path):
    root, sys, tux, calls = _setup(tmp_path)
    tux.write_text(f'#!/bin/bash\n[ "$1" = --help ] && exit 0\necho "$*" >> {calls}\n')
    _claim(root, "me")
    r = _run(root, sys, tux, "reboot", M1_CLAIM="me")
    assert r.returncode == 1 and "--no-recover" in r.stderr
    assert not calls.exists()


def test_sends_with_no_recover_on_the_m1s_port_and_logs(tmp_path):
    root, sys, tux, calls = _setup(tmp_path)
    _claim(root, "me")
    r = _run(root, sys, tux, "reboot serial", M1_CLAIM="me")
    assert r.returncode == 0, r.stderr
    assert calls.read_text().splitlines() == ["--no-recover -c USB-C Left Back reboot serial"]
    log = (root / "var/log").read_text()
    for step in ("claim: held by me", "M1 on 1-0c", "command interface present", "tuxvdmtool exit 0"):
        assert step in log, step


def test_unknown_command_is_refused(tmp_path):
    root, sys, tux, calls = _setup(tmp_path)
    _claim(root, "me")
    r = _run(root, sys, tux, "reset-controller", M1_CLAIM="me")
    assert r.returncode == 1 and not calls.exists()
