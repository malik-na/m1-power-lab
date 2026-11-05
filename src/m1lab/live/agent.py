#!/usr/bin/env python3
"""m1power target agent.

Runs on the Apple-silicon Mac being measured (stdlib only, no host imports).
The host pushes this file over SSH and invokes it; experiments that would be
perturbed by network traffic run detached on the target and leave JSON results
in /var/lib/m1power for the host to collect.

Commands print one JSON document (or JSON lines for streaming samplers).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import shutil
import signal
import struct
import subprocess
import sys
import time
from pathlib import Path

AGENT_VERSION = 3
STATE_DIR = Path("/var/lib/m1power")
RUN_DIR = Path("/run/m1power")
JOURNAL = RUN_DIR / "journal.json"
LEDGER = STATE_DIR / "ledger.jsonl"
TUNE_SPEC = Path("/etc/m1power/tune.json")
DEBUGFS = Path("/sys/kernel/debug/m1power")
BATTERY = Path("/sys/class/power_supply/macsmc-battery")
AC = Path("/sys/class/power_supply/macsmc-ac")
# Each key read is an SMC mailbox round trip (an interrupt on the target), so
# the sampler watches only what the analysis uses.
WATCH_KEYS = ["PSTR", "PHPC", "zSPa", "zSPc", "zSLa"]
BATTERY_EVERY_S = 10.0


# --------------------------------------------------------------- utilities


def read(path, default=None):
    try:
        with open(path) as handle:
            return handle.read().strip()
    except OSError:
        return default


def read_int(path, default=None):
    value = read(path)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def write(path, value):
    with open(path, "w") as handle:
        handle.write(str(value))


def sh(*args, check=False, timeout=30, env=None):
    proc = subprocess.run(
        list(args), capture_output=True, text=True, timeout=timeout, check=False, env=env
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)}: {proc.stderr.strip() or proc.returncode}")
    return proc


def clocks():
    return time.clock_gettime(time.CLOCK_MONOTONIC), time.clock_gettime(time.CLOCK_BOOTTIME)


def sysfs_power_files(name):
    """Every /sys/devices/**/power/<name>, without following sysfs symlink loops."""
    found = []
    for directory, subdirs, files in os.walk("/sys/devices", followlinks=False):
        if directory.endswith("/power") and name in files:
            found.append(f"{directory}/{name}")
            subdirs[:] = []
    return found


def emit(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":"), sort_keys=True) + "\n")
    sys.stdout.flush()


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True))
    os.replace(tmp, path)


# --------------------------------------------------------------------- SMC


def decode_smc(type_code, hexval):
    if hexval in ("-", "") or hexval.startswith("E"):
        return None
    raw = bytes.fromhex(hexval)
    t = type_code.strip()
    try:
        if t == "flt":
            return struct.unpack("<f", raw)[0]
        if t.startswith("ui"):
            return int.from_bytes(raw, "little")
        if t.startswith("si"):
            return int.from_bytes(raw, "little", signed=True)
        if t == "flag":
            return raw[0]
        if t == "ioft":
            return int.from_bytes(raw, "little") / 65536.0
        if t.startswith("ch8"):
            return raw.rstrip(b"\0").decode("ascii", "replace")
    except (struct.error, ValueError):
        return None
    return hexval


def parse_smc_lines(text):
    values = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] in ("BOOT", "MONO"):
            values[parts[0]] = int(parts[1])
            continue
        if len(parts) < 5:
            continue
        # type codes like "flt " lose their trailing space when split
        key, type_code, hexval = parts[0], parts[1], parts[-1]
        values[key] = decode_smc(type_code, hexval)
    return values


class Smc:
    """SMC access through the m1power module, with an hwmon fallback.

    smc_watch keeps its key list per open file, so each Smc holds its own fd:
    the keys are written once, and every read rewinds that fd and reads it to
    EOF. Other readers (an ad-hoc `smc KEY`, a concurrent sampler) never
    disturb this instance's key list."""

    def __init__(self, keys=WATCH_KEYS):
        self.keys = list(keys)
        self.fd = None
        path = DEBUGFS / "smc_watch"
        if path.exists():
            fd = os.open(path, os.O_RDWR)
            try:
                os.write(fd, " ".join(self.keys).encode("ascii"))
            except BaseException:
                os.close(fd)
                raise
            self.fd = fd
        self.module = self.fd is not None
        self.hwmon = None
        for name in glob.glob("/sys/class/hwmon/hwmon*/name"):
            if read(name) == "macsmc_hwmon":
                self.hwmon = Path(name).parent

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:  # noqa: BLE001 - also runs from __del__ at exit
                pass
            self.fd = None

    def __del__(self):
        self.close()

    def _read_module(self):
        os.lseek(self.fd, 0, os.SEEK_SET)
        chunks = []
        while True:
            chunk = os.read(self.fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks).decode("ascii", "replace")

    def read(self):
        if self.module:
            try:
                return parse_smc_lines(self._read_module())
            except OSError:
                return {}
        out = {}
        if self.hwmon:
            for item in self.hwmon.glob("power*_label"):
                label = read(item)
                value = read_int(str(item).replace("_label", "_input"))
                if value is None:
                    continue
                if label == "Total System Power":
                    out["PSTR"] = value / 1e6
                elif label == "AC Input Power":
                    out["PDTR"] = value / 1e6
                elif label == "Heatpipe Power":
                    out["PHPC"] = value / 1e6
        return out


def smc_dump():
    text = read(DEBUGFS / "smc_keys")
    if text is None:
        raise SystemExit("m1power kernel module is not loaded")
    keys = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        keys[parts[0]] = {
            "type": parts[1],
            "size": int(parts[-3]),
            "flags": parts[-2],
            "value": decode_smc(parts[1], parts[-1]),
        }
    return keys


# ----------------------------------------------------------------- battery


def battery():
    info = {}
    for name in (
        "status",
        "capacity",
        "energy_now",
        "energy_full",
        "charge_now",
        "power_now",
        "current_now",
        "voltage_now",
        "charge_behaviour",
        "charge_control_end_threshold",
        "cycle_count",
    ):
        value = read(BATTERY / name)
        if value is None:
            continue
        try:
            info[name] = int(value)
        except ValueError:
            info[name] = value
    info["ac_online"] = read_int(AC / "online")
    return info


# --------------------------------------------------------------- CPU state


def _policy_number(path):
    match = re.search(r"(\d+)$", str(path))
    return int(match.group(1)) if match else 0


def policy_max_freq(policy):
    """Top frequency of a cpufreq policy, or None when nothing says.

    cpuinfo_max_freq returns EBUSY while every CPU of the policy is offline
    (e.g. during a pcores=off A/B), so fall back to the frequency tables."""
    value = read_int(f"{policy}/cpuinfo_max_freq")
    if value:
        return value
    freqs = [int(f) for f in (read(f"{policy}/scaling_available_frequencies") or "").split() if f.isdigit()]
    for line in (read(f"{policy}/stats/time_in_state") or "").splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            freqs.append(int(parts[0]))
    return max(freqs) if freqs else None


def cpu_policies():
    policies = {}
    for policy in sorted(glob.glob("/sys/devices/system/cpu/cpufreq/policy*"), key=_policy_number):
        cpus = [int(c) for c in (read(f"{policy}/related_cpus") or "").split()]
        policies[Path(policy).name] = {"cpus": cpus, "max": policy_max_freq(policy)}
    # Name the clusters: the lower-frequency policy holds the E-cores. If any
    # policy's top frequency is unreadable, never guess from it: fall back to
    # policy order (the lowest-numbered policy is the E-cluster on Apple SoCs).
    if all(info["max"] for info in policies.values()):
        ordered = sorted(policies.items(), key=lambda item: (item[1]["max"], _policy_number(item[0])))
    else:
        ordered = sorted(policies.items(), key=lambda item: _policy_number(item[0]))
    names = {}
    if ordered:
        names[ordered[0][0]] = "e"
    if len(ordered) > 1:
        names[ordered[-1][0]] = "p"
    return {names.get(k, k): v | {"policy": k, "max": v["max"] or 0} for k, v in policies.items()}


def idle_counters():
    """Per-CPU {state_name: [usage, time_us, s2idle_usage, s2idle_time_us]}.

    Keyed by the CPU number as a string, so a snapshot survives a JSON round
    trip unchanged (the sleep hook saves the pre-suspend snapshot to disk)."""
    result = {}
    for cpu in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpuidle"):
        index = int(re.search(r"cpu(\d+)", cpu).group(1))
        states = {}
        for state in sorted(glob.glob(f"{cpu}/state*")):
            name = read(f"{state}/name", Path(state).name)
            states[name] = [
                read_int(f"{state}/usage", 0),
                read_int(f"{state}/time", 0),
                read_int(f"{state}/s2idle/usage", 0),
                read_int(f"{state}/s2idle/time", 0),
            ]
        result[str(index)] = states
    return result


def freq_counters(policies):
    result = {}
    for cluster, info in policies.items():
        table = {}
        text = read(f"/sys/devices/system/cpu/cpufreq/{info['policy']}/stats/time_in_state", "")
        for line in text.splitlines():
            freq, ticks = line.split()
            table[int(freq)] = int(ticks)
        result[cluster] = table
    return result


def proc_stat():
    stats = {}
    for line in (read("/proc/stat", "") or "").splitlines():
        parts = line.split()
        if parts and parts[0] in ("ctxt", "intr"):
            stats[parts[0]] = int(parts[1])
    return stats


def interrupts():
    counts = {}
    for line in (read("/proc/interrupts", "") or "").splitlines()[1:]:
        parts = line.split()
        if not parts or not parts[0].endswith(":"):
            continue
        name = parts[0][:-1]
        numbers = []
        rest = []
        for item in parts[1:]:
            if item.isdigit() and not rest:
                numbers.append(int(item))
            else:
                rest.append(item)
        label = " ".join(rest[-2:]) if rest else name
        counts[f"{name} {label}".strip()] = sum(numbers)
    return counts


def processes():
    snapshot = {}
    for status in glob.glob("/proc/[0-9]*/status"):
        pid = status.split("/")[2]
        text = read(status)
        stat = read(f"/proc/{pid}/stat")
        if not text or not stat:
            continue
        fields = {}
        for line in text.splitlines():
            key, _, value = line.partition(":")
            if key in ("Name", "voluntary_ctxt_switches", "nonvoluntary_ctxt_switches"):
                fields[key] = value.strip()
        try:
            after = stat.rsplit(")", 1)[1].split()
            cpu_ticks = int(after[11]) + int(after[12])
        except (IndexError, ValueError):
            cpu_ticks = 0
        snapshot[pid] = (
            fields.get("Name", "?"),
            int(fields.get("voluntary_ctxt_switches", 0)) + int(fields.get("nonvoluntary_ctxt_switches", 0)),
            cpu_ticks,
        )
    return snapshot


def wakeup_sources():
    sources = {}
    text = read("/sys/kernel/debug/wakeup_sources", "") or ""
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                sources[parts[0]] = int(parts[2])
            except ValueError:
                continue
    return sources


def power_domains():
    """Parse pm_genpd_summary: domain lines are flush left, devices indented by 4."""
    text = read("/sys/kernel/debug/pm_genpd/pm_genpd_summary", "") or ""
    domains = {}
    current = None
    for line in text.splitlines():
        if not line.strip() or line.startswith(("domain", "---")) or line.lstrip().startswith("/device"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        parts = line.split()
        if indent == 0:
            current = parts[0]
            domains[current] = {"status": parts[1] if len(parts) > 1 else "?", "devices": []}
        elif indent == 4 and current:
            domains[current]["devices"].append([parts[0], parts[1] if len(parts) > 1 else "?"])
    return domains


# ------------------------------------------------------------------ sampler


class Sampler:
    def __init__(self, smc_keys=WATCH_KEYS):
        self.smc = Smc(smc_keys)
        self.policies = cpu_policies()
        self.cluster_of = {}
        for cluster, info in self.policies.items():
            for cpu in info["cpus"]:
                self.cluster_of[str(cpu)] = cluster
        self.prev = None
        self._battery = {}
        self._battery_at = -1e9

    def raw(self):
        mono, boot = clocks()
        if mono - self._battery_at >= BATTERY_EVERY_S:
            self._battery = battery()
            self._battery_at = mono
        return {
            "mono": mono,
            "boot": boot,
            "smc": self.smc.read(),
            "bat": self._battery,
            "idle": idle_counters(),
            "freq": freq_counters(self.policies),
            "stat": proc_stat(),
        }

    def derive(self, prev, cur):
        dt = cur["mono"] - prev["mono"]
        smc = cur["smc"]
        sample = {
            "t": round(cur["mono"], 3),
            "dt": round(dt, 3),
            "slept": round((cur["boot"] - cur["mono"]) - (prev["boot"] - prev["mono"]), 3),
        }
        for key, out in (("PSTR", "sys_w"), ("PDTR", "dcin_w"), ("PPBR", "rail_w"), ("PHPC", "soc_w"), ("PMVC", "mvc_w"), ("Pb0f", "bat_w")):
            if isinstance(smc.get(key), (int, float)):
                sample[out] = round(smc[key], 4)
        if isinstance(smc.get("zSLa"), int) and isinstance(prev["smc"].get("zSLa"), int):
            sample["load_acc_w"] = round((smc["zSLa"] - prev["smc"]["zSLa"]) / 1000.0 / max(dt, 1e-6), 4)
        if isinstance(smc.get("zSPa"), int) and isinstance(prev["smc"].get("zSPa"), int):
            sample["dcin_acc_w"] = round((smc["zSPa"] - prev["smc"]["zSPa"]) / 1000.0 / max(dt, 1e-6), 4)
        bat = cur["bat"]
        if "power_now" in bat:
            sign = -1 if bat.get("status") == "Discharging" else 1
            sample["bat_sysfs_w"] = round(sign * bat["power_now"] / 1e6, 4)
        if "energy_now" in bat:
            sample["bat_wh"] = round(bat["energy_now"] / 1e6, 4)
        if dt > 0:
            sample["ctxt_s"] = round((cur["stat"].get("ctxt", 0) - prev["stat"].get("ctxt", 0)) / dt, 1)
            sample["irq_s"] = round((cur["stat"].get("intr", 0) - prev["stat"].get("intr", 0)) / dt, 1)
            residency = {}
            for cpu, states in cur["idle"].items():
                before = prev["idle"].get(str(cpu), {})
                cluster = self.cluster_of.get(str(cpu), "?")
                bucket = residency.setdefault(cluster, {"n": 0})
                bucket["n"] += 1
                for name, values in states.items():
                    delta_us = values[1] - before.get(name, [0, 0])[1]
                    short = "wfi" if name.upper().startswith("WFI") else "deep"
                    bucket[short] = bucket.get(short, 0.0) + delta_us / 1e6 / dt
            sample["idle"] = {
                c: {k: round(v / b["n"], 4) for k, v in b.items() if k != "n"} for c, b in residency.items()
            }
            freqs = {}
            for cluster, table in cur["freq"].items():
                before = prev["freq"].get(cluster, {})
                deltas = {f: table[f] - before.get(f, 0) for f in table}
                total = sum(deltas.values())
                if total > 0:
                    freqs[cluster] = round(sum(f * d for f, d in deltas.items()) / total / 1000.0)
            sample["mhz"] = freqs
        return sample

    def tick(self):
        cur = self.raw()
        sample = None
        if self.prev is not None:
            sample = self.derive(self.prev, cur)
        self.prev = cur
        return sample


def top_deltas(before, after, seconds, limit=12):
    rows = []
    for key, value in after.items():
        delta = value - before.get(key, 0)
        if delta > 0:
            rows.append([key, round(delta / seconds, 2)])
    rows.sort(key=lambda row: -row[1])
    return rows[:limit]


def process_deltas(before, after, seconds, limit=15):
    rows = []
    hz = os.sysconf("SC_CLK_TCK")
    for pid, (name, switches, ticks) in after.items():
        prior = before.get(pid)
        if not prior or prior[0] != name:
            continue
        d_switch = switches - prior[1]
        d_cpu = (ticks - prior[2]) / hz
        if d_switch > 0 or d_cpu > 0:
            rows.append({"pid": int(pid), "comm": name, "wakeups_s": round(d_switch / seconds, 2), "cpu_pct": round(100 * d_cpu / seconds, 3)})
    rows.sort(key=lambda row: (-row["wakeups_s"], -row["cpu_pct"]))
    return rows[:limit]


def wifi_ap():
    """BSSID and SSID the Wi-Fi interface is associated with, e.g.
    "16:ec:e4:5e:d0:42 iPhone", or "none". A pair of A/B blocks that spans a
    change of access point (a router outage and a fallback hotspot, a roam)
    measures the network change, not the knob, and is set aside."""
    for path in glob.glob("/sys/class/net/*/phy80211"):
        iface = path.split("/")[4]
        out = sh("iw", "dev", iface, "link").stdout if shutil.which("iw") else ""
        bssid = re.search(r"Connected to ([0-9a-f:]{17})", out)
        ssid = re.search(r"SSID: (.*)", out)
        if bssid:
            return f"{bssid.group(1)} {ssid.group(1).strip() if ssid else ''}".strip()
        return "none"
    return "no-wifi"


def measure_window(sampler, seconds, interval=1.0, with_detail=True, stream=None):
    """Sample for `seconds`; return samples plus a window summary."""
    ap_start = wifi_ap()
    irq0 = interrupts() if with_detail else None
    procs0 = processes() if with_detail else None
    sampler.prev = None
    sampler.tick()
    start = time.monotonic()
    samples = []
    next_tick = start + interval
    while True:
        now = time.monotonic()
        if now >= start + seconds:
            break
        time.sleep(max(0.0, next_tick - now))
        next_tick += interval
        sample = sampler.tick()
        if sample is not None:
            samples.append(sample)
            if stream:
                stream(sample)
    elapsed = time.monotonic() - start
    summary = summarize(samples)
    summary["ap_start"], summary["ap_end"] = ap_start, wifi_ap()
    if with_detail:
        summary["top_irqs"] = top_deltas(irq0, interrupts(), elapsed)
        summary["top_wakers"] = process_deltas(procs0, processes(), elapsed)
    return samples, summary


def summarize(samples):
    summary = {"n": len(samples)}
    if not samples:
        return summary
    for key in ("sys_w", "load_acc_w", "dcin_w", "dcin_acc_w", "rail_w", "soc_w", "mvc_w", "bat_w", "bat_sysfs_w", "ctxt_s", "irq_s"):
        values = [s[key] for s in samples if key in s]
        if values:
            summary[key] = round(sum(values) / len(values), 4)
            if key == "sys_w" and len(values) > 1:
                mean = summary[key]
                summary["sys_w_sd"] = round((sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5, 4)
    idle = {}
    for sample in samples:
        for cluster, states in sample.get("idle", {}).items():
            acc = idle.setdefault(cluster, {})
            for name, value in states.items():
                acc[name] = acc.get(name, 0.0) + value
    summary["idle"] = {c: {k: round(v / len(samples), 4) for k, v in s.items()} for c, s in idle.items()}
    mhz = {}
    for sample in samples:
        for cluster, value in sample.get("mhz", {}).items():
            mhz.setdefault(cluster, []).append(value)
    summary["mhz"] = {c: round(sum(v) / len(v)) for c, v in mhz.items()}
    return summary


# -------------------------------------------------------------------- knobs


def gui_env():
    """Environment for talking to the logged-in user's Hyprland session."""
    for runtime in glob.glob("/run/user/*/hypr/*/.socket.sock"):
        parts = runtime.split("/")
        uid = int(parts[3])
        signature = parts[5]
        try:
            import pwd

            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            continue
        env = {
            "PATH": "/usr/local/bin:/usr/bin",
            "XDG_RUNTIME_DIR": f"/run/user/{uid}",
            "HYPRLAND_INSTANCE_SIGNATURE": signature,
        }
        return user, env
    return None, None


def hyprctl(*args):
    user, env = gui_env()
    if not user:
        raise RuntimeError("no Hyprland session")
    proc = sh("runuser", "-u", user, "--", "hyprctl", *args, env=env)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "hyprctl failed")
    return proc.stdout


class LabArrived(Exception):
    """The lab started using the Mac in the middle of an experiment."""


def check_lab(force, where):
    if force:
        return
    reason = lab_activity()
    if reason:
        raise LabArrived(f"{where}: {reason}")


class Knob:
    name = ""
    help = ""
    choices = None
    kills_network = False
    persistable = True

    def supported(self):
        return True

    def get(self):
        raise NotImplementedError

    def set(self, value):
        raise NotImplementedError

    def describe(self):
        info = {"name": self.name, "help": self.help, "choices": self.choices, "kills_network": self.kills_network, "persistable": self.persistable}
        try:
            info["supported"] = bool(self.supported())
            if info["supported"]:
                info["value"] = self.get()
        except Exception as error:  # noqa: BLE001 - report every knob
            info["supported"] = False
            info["error"] = str(error)
        return info


class SysfsKnob(Knob):
    def __init__(self, name, path, help, choices=None, bracketed=False, persistable=True):
        self.name, self.path, self.help, self.choices, self.bracketed = name, path, help, choices, bracketed
        self.persistable = persistable

    def supported(self):
        paths = glob.glob(self.path)
        return bool(paths) and all(os.access(p, os.W_OK) and os.stat(p).st_mode & 0o222 for p in paths)

    def get(self):
        value = read(glob.glob(self.path)[0])
        if self.bracketed:
            match = re.search(r"\[(\S+)\]", value or "")
            return match.group(1) if match else value
        return value

    def set(self, value):
        for path in glob.glob(self.path):
            write(path, value)


class ProfileKnob(Knob):
    name = "ppd"
    help = "power-profiles-daemon profile"
    choices = ["performance", "balanced", "power-saver"]

    def supported(self):
        return shutil.which("powerprofilesctl") is not None and sh("powerprofilesctl", "get").returncode == 0

    def get(self):
        return sh("powerprofilesctl", "get").stdout.strip()

    def set(self, value):
        sh("powerprofilesctl", "set", value, check=True)


class GovernorKnob(Knob):
    name = "governor"
    help = "cpufreq governor on every policy"
    choices = ["schedutil", "powersave", "conservative", "ondemand", "performance"]

    def get(self):
        values = {read(p) for p in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_governor")}
        return values.pop() if len(values) == 1 else "mixed"

    def set(self, value):
        for path in glob.glob("/sys/devices/system/cpu/cpufreq/policy*/scaling_governor"):
            write(path, value)


class ClusterMaxKnob(Knob):
    def __init__(self, cluster):
        self.cluster = cluster
        self.name = f"{cluster}core_max_khz"
        self.help = f"{cluster.upper()}-cluster frequency cap (kHz, or 'max')"

    def _policy(self):
        return cpu_policies().get(self.cluster, {}).get("policy")

    def supported(self):
        return self._policy() is not None

    def get(self):
        policy = self._policy()
        value = read_int(f"/sys/devices/system/cpu/cpufreq/{policy}/scaling_max_freq")
        top = read_int(f"/sys/devices/system/cpu/cpufreq/{policy}/cpuinfo_max_freq")
        return "max" if value == top else str(value)

    def set(self, value):
        policy = self._policy()
        if value == "max":
            value = read(f"/sys/devices/system/cpu/cpufreq/{policy}/cpuinfo_max_freq")
        write(f"/sys/devices/system/cpu/cpufreq/{policy}/scaling_max_freq", value)


class PCoresKnob(Knob):
    name = "pcores"
    help = "P-cluster CPUs online"
    choices = ["on", "off"]

    def _cpus(self):
        """The highest-capacity CPUs. cpu_capacity stays readable while a CPU
        is offline, unlike its cpufreq policy files (EBUSY once inactive)."""
        capacity = {}
        for path in glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpu_capacity"):
            value = read_int(path)
            if value is not None:
                capacity[int(re.search(r"cpu(\d+)/", path).group(1))] = value
        if len(set(capacity.values())) < 2:
            return cpu_policies().get("p", {}).get("cpus", [])
        top = max(capacity.values())
        return sorted(cpu for cpu, value in capacity.items() if value == top)

    def supported(self):
        return bool(self._cpus()) and all(Path(f"/sys/devices/system/cpu/cpu{c}/online").exists() for c in self._cpus())

    def get(self):
        online = [read(f"/sys/devices/system/cpu/cpu{c}/online") == "1" for c in self._cpus()]
        return "on" if all(online) else ("off" if not any(online) else "partial")

    def set(self, value):
        for cpu in self._cpus():
            write(f"/sys/devices/system/cpu/cpu{cpu}/online", "1" if value == "on" else "0")


class WifiPowerSaveKnob(Knob):
    name = "wifi_ps"
    help = "802.11 power save on the Wi-Fi interface"
    choices = ["on", "off"]

    def _iface(self):
        for path in glob.glob("/sys/class/net/*/phy80211"):
            return path.split("/")[4]
        return None

    def supported(self):
        return self._iface() is not None and shutil.which("iw") is not None

    def get(self):
        out = sh("iw", "dev", self._iface(), "get", "power_save").stdout
        return "on" if "on" in out.lower() else "off"

    def set(self, value):
        sh("iw", "dev", self._iface(), "set", "power_save", value, check=True)


class RfkillKnob(Knob):
    def __init__(self, kind, kills_network):
        self.kind = kind
        self.name = {"wlan": "wifi", "bluetooth": "bt"}[kind]
        self.help = f"{kind} radio (rfkill)"
        self.choices = ["on", "off"]
        self.kills_network = kills_network

    def supported(self):
        return any(read(f"{p}/type") == self.kind for p in glob.glob("/sys/class/rfkill/rfkill*"))

    def get(self):
        for path in glob.glob("/sys/class/rfkill/rfkill*"):
            if read(f"{path}/type") == self.kind:
                return "off" if read(f"{path}/soft") == "1" else "on"
        return "absent"

    def set(self, value):
        sh("rfkill", "block" if value == "off" else "unblock", self.kind, check=True)


class BacklightKnob(Knob):
    name = "backlight"
    help = "panel backlight level (raw units, or 'NN%')"

    def _path(self):
        paths = glob.glob("/sys/class/backlight/*")
        return paths[0] if paths else None

    def supported(self):
        return self._path() is not None

    def get(self):
        return read(f"{self._path()}/brightness")

    def set(self, value):
        path = self._path()
        if str(value).endswith("%"):
            value = round(read_int(f"{path}/max_brightness") * float(value[:-1]) / 100)
        write(f"{path}/brightness", value)


class DisplayKnob(Knob):
    name = "display"
    help = "Hyprland DPMS (panel and display pipeline on/off)"
    choices = ["on", "off"]
    persistable = False

    def supported(self):
        return gui_env()[0] is not None

    def get(self):
        monitors = json.loads(hyprctl("monitors", "all", "-j"))
        states = {bool(m.get("dpmsStatus", True)) for m in monitors if not m.get("disabled")}
        return "on" if states == {True} else ("off" if states == {False} else "mixed")

    def set(self, value):
        # Hyprland < 0.56 takes `dispatch dpms off`; 0.56+ evaluates dispatch
        # arguments as Lua and wants `hl.dsp.dpms("off")`.
        try:
            out = hyprctl("dispatch", "dpms", value)
        except RuntimeError as error:
            out = f"error: {error}"
        if out.strip().lower().startswith("error"):
            out = hyprctl("dispatch", f'hl.dsp.dpms("{value}")')
            if out.strip().lower().startswith("error"):
                raise RuntimeError(out.strip())


class HyprOptionKnob(Knob):
    def __init__(self, name, option, help):
        self.name, self.option, self.help = name, option, help
        self.choices = ["0", "1"]
        self.persistable = False

    def supported(self):
        if gui_env()[0] is None:
            return False
        return not hyprctl("getoption", self.option, "-j").startswith("no such option")

    def get(self):
        data = json.loads(hyprctl("getoption", self.option, "-j"))
        for key in ("bool", "int", "float", "str"):
            if key in data:
                value = data[key]
                return str(int(value)) if isinstance(value, bool) else str(value)
        return ""

    def set(self, value):
        hyprctl("keyword", self.option, str(value))


class RuntimePmKnob(Knob):
    name = "runtime_pm"
    help = "runtime PM 'auto' for every device that offers it ('baseline' restores)"
    choices = ["auto", "baseline"]
    # Under STATE_DIR so a persisted tune (runtime_pm=auto at every boot) can
    # still be reverted; tagged with the boot it was taken in.
    SAVE = STATE_DIR / "runtime_pm_baseline.json"

    def _controls(self):
        return sysfs_power_files("control")

    def _load(self):
        try:
            saved = json.loads(self.SAVE.read_text())
        except (OSError, ValueError):
            return None
        if isinstance(saved, dict) and isinstance(saved.get("controls"), dict):
            return saved
        return {"boot_id": None, "controls": saved if isinstance(saved, dict) else {}}

    def ensure_baseline(self):
        """Record the pre-tuning control values unless a usable record exists.

        A record from an earlier boot is replaced only while the devices are
        not already all on 'auto' (then the old record is the better guess)."""
        saved = self._load()
        if saved is not None and (saved.get("boot_id") == boot_id() or self.get() == "auto"):
            return
        atomic_json(self.SAVE, {"boot_id": boot_id(), "controls": {p: read(p) for p in self._controls()}})

    def get(self):
        values = [read(p) for p in self._controls()]
        on = sum(1 for v in values if v == "on")
        return "auto" if on == 0 else f"on:{on}"

    def set(self, value):
        if value == "auto":
            self.ensure_baseline()
            for path in self._controls():
                try:
                    write(path, "auto")
                except OSError:
                    pass
        else:
            saved = (self._load() or {}).get("controls", {})
            for path, old in saved.items():
                try:
                    write(path, old)
                except OSError:
                    pass


class ServiceKnob(Knob):
    def __init__(self, unit):
        self.unit = unit
        self.name = f"service:{unit}"
        self.help = f"systemd unit {unit} running"
        self.choices = ["on", "off"]
        self.persistable = False

    def supported(self):
        return sh("systemctl", "cat", self.unit).returncode == 0

    def get(self):
        return "on" if sh("systemctl", "is-active", self.unit).stdout.strip() == "active" else "off"

    def set(self, value):
        sh("systemctl", "start" if value == "on" else "stop", self.unit, check=True, timeout=60)


class FreezeKnob(Knob):
    """SIGSTOP/SIGCONT every process with a given name (cheap A/B of a daemon)."""

    def __init__(self, comm):
        self.comm = comm
        self.name = f"freeze:{comm}"
        self.help = f"processes named {comm} running or stopped"
        self.choices = ["running", "frozen"]
        self.persistable = False

    def _pids(self):
        pids = []
        for status in glob.glob("/proc/[0-9]*/comm"):
            if read(status) == self.comm:
                pids.append(int(status.split("/")[2]))
        return pids

    def supported(self):
        return bool(self._pids())

    def get(self):
        states = set()
        for pid in self._pids():
            stat = read(f"/proc/{pid}/stat", "")
            states.add(stat.rsplit(")", 1)[1].split()[0] if ")" in stat else "?")
        return "frozen" if states == {"T"} else "running"

    def set(self, value):
        for pid in self._pids():
            try:
                os.kill(pid, signal.SIGSTOP if value == "frozen" else signal.SIGCONT)
            except ProcessLookupError:
                pass


class UsbPortKnob(Knob):
    """Unbind an unused USB-C port's controller and PHY so its ATC power
    domains can switch off (the dwc3-apple controller has no runtime PM until
    a cable connects). Refuses a port with anything plugged in. Experimental:
    stock kernels oops unbinding dwc3-apple from a never-connected port
    (dwc3_apple_remove NULL dereference); see docs/STATUS.md."""

    choices = ["bound", "unbound"]
    persistable = False
    SAVE_DIR = RUN_DIR / "usbport"

    def __init__(self, device):
        self.device = device
        self.name = f"usbport:{device}"
        self.help = f"USB-C controller {device} and its PHY bound to their drivers"

    def _dev(self):
        return Path("/sys/bus/platform/devices") / self.device

    def _phys(self):
        """Platform devices behind the controller's phy supplier links."""
        phys = []
        for link in sorted(self._dev().glob("supplier:phy:phy-*")):
            name = link.name.split("supplier:phy:phy-", 1)[1].rsplit(".", 1)[0]
            if name not in phys:
                phys.append(name)
        return phys

    def _port(self):
        for link in self._dev().glob("consumer:typec:*"):
            return link.name.split("consumer:typec:", 1)[1]
        return None

    def supported(self):
        return self._dev().exists() and bool(self._phys() or (self.SAVE_DIR / f"{self.device}.json").exists())

    def get(self):
        return "bound" if (self._dev() / "driver").exists() else "unbound"

    def _saved(self):
        try:
            return json.loads((self.SAVE_DIR / f"{self.device}.json").read_text())
        except (OSError, ValueError):
            return None

    def set(self, value):
        if value == self.get():
            return
        if value == "unbound":
            port = self._port()
            if port and Path(f"/sys/class/typec/{port}-partner").exists():
                raise RuntimeError(f"{port} has something connected; refusing to unbind {self.device}")
            phys = self._phys()
            drivers = {self.device: Path(os.path.realpath(self._dev() / "driver")).name}
            for phy in phys:
                link = Path("/sys/bus/platform/devices") / phy / "driver"
                if link.exists():
                    drivers[phy] = Path(os.path.realpath(link)).name
            atomic_json(self.SAVE_DIR / f"{self.device}.json", {"drivers": drivers, "order": [self.device] + phys})
            for dev in [self.device] + phys:
                if dev in drivers:
                    write(f"/sys/bus/platform/drivers/{drivers[dev]}/unbind", dev)
        else:
            saved = self._saved()
            if not saved:
                raise RuntimeError(f"no record of the drivers {self.device} was unbound from")
            for dev in reversed(saved["order"]):
                driver = saved["drivers"].get(dev)
                if driver and not (Path("/sys/bus/platform/devices") / dev / "driver").exists():
                    write(f"/sys/bus/platform/drivers/{driver}/bind", dev)


def wifi_pci_device():
    """BDF of the PCIe Wi-Fi function (the device behind the phy80211 netdev)."""
    for path in glob.glob("/sys/class/net/*/phy80211"):
        dev = os.path.realpath(str(Path(path).parent / "device"))
        name = Path(dev).name
        if re.match(r"^[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]$", name):
            return name
    return None


class PcieLinkKnob(Knob):
    """One of a PCIe device's per-link ASPM switches (link/l1_1_aspm,
    l1_2_aspm, l1_1_pcipm, l1_2_pcipm, clkpm, l1_aspm). `wifi` names the
    Wi-Fi function, so `pcielink:wifi:l1_1_aspm`."""

    choices = ["0", "1"]
    persistable = True

    def __init__(self, device, attr):
        self.device, self.attr = device, attr
        self.name = f"pcielink:{device}:{attr}"
        self.help = f"PCIe link {attr} of {device}"

    def _path(self):
        bdf = wifi_pci_device() if self.device == "wifi" else self.device
        return Path(f"/sys/bus/pci/devices/{bdf}/link/{self.attr}") if bdf else None

    def supported(self):
        path = self._path()
        return bool(path and path.exists())

    def get(self):
        return read(self._path())

    def set(self, value):
        write(self._path(), value)


class L1ssTimingKnob(Knob):
    """T_POWER_ON in microseconds on both ends of the Wi-Fi link (L1 PM
    Substates Control 2). The spec allows changing it only while L1.2 is
    disabled, so the knob turns L1.2 off, writes both ends, and puts the
    link switches back. The Apple root port reports no T_POWER_ON of its own,
    so Linux programs the endpoint's 6 us."""

    name = "l1ss_tpoweron_us"
    help = "L1.2 exit time budget (T_POWER_ON, us) on the Wi-Fi link"
    choices = None
    persistable = True
    SCALES = ((0, 2), (1, 10), (2, 100))

    def _ends(self):
        bdf = wifi_pci_device()
        if not bdf:
            return None, None
        parent = Path(os.path.realpath(f"/sys/bus/pci/devices/{bdf}")).parent.name
        return bdf, parent

    def supported(self):
        dev, parent = self._ends()
        return bool(dev and parent and shutil.which("setpci") and Path(f"/sys/bus/pci/devices/{dev}/link").exists())

    @staticmethod
    def encode(us):
        """Smallest encodable T_POWER_ON >= us, as the Control 2 register value."""
        us = int(us)
        for scale, unit in L1ssTimingKnob.SCALES:
            value = -(-us // unit)
            if value <= 31:
                return (value << 3) | scale, value * unit
        raise ValueError(f"T_POWER_ON {us} us is beyond 3100 us")

    @staticmethod
    def decode(reg):
        scale, value = reg & 0x3, (reg >> 3) & 0x1F
        unit = dict(L1ssTimingKnob.SCALES).get(scale, 0)
        return value * unit

    def _ctl2(self, bdf):
        out = sh("setpci", "-s", bdf, "ECAP_L1PM+0x0c.l", check=True).stdout.strip()
        return int(out, 16)

    def get(self):
        dev, _ = self._ends()
        return str(self.decode(self._ctl2(dev)))

    def set(self, value):
        reg, _ = self.encode(value)
        dev, parent = self._ends()
        link = Path(f"/sys/bus/pci/devices/{dev}/link")
        saved = {attr: read(link / attr) for attr in ("l1_2_aspm", "l1_2_pcipm")}
        try:
            for attr in saved:
                if saved[attr] == "1":
                    write(link / attr, "0")
            for bdf in (parent, dev):  # upstream end first, as the ASPM core does
                current = self._ctl2(bdf)
                sh("setpci", "-s", bdf, f"ECAP_L1PM+0x0c.l={(current & ~0xFF) | reg:08x}", check=True)
        finally:
            for attr, old in saved.items():
                if old == "1":
                    write(link / attr, "1")


class LtrMaxLatencyKnob(Knob):
    """Max Snoop / No-Snoop Latency in the Wi-Fi function's LTR capability,
    in microseconds. They cap the latency tolerance the device may report;
    the root port enters ASPM L1.2 only when the reported tolerance exceeds
    LTR_L1.2_THRESHOLD. On x86 firmware programs them (often ~3 ms); on this
    Device Tree platform nothing does, so they read 0 and L1.2 is entered
    only now and then."""

    name = "ltr_max_us"
    help = "LTR max snoop/no-snoop latency (us) the Wi-Fi device may report"
    choices = None
    persistable = True
    # LTR latency encoding: value (bits 9:0) x 32^scale ns, scale 0..5
    UNITS_NS = (1, 32, 1024, 32768, 1048576, 33554432)

    @staticmethod
    def encode(us):
        ns = int(us) * 1000
        for scale, unit in enumerate(LtrMaxLatencyKnob.UNITS_NS):
            value = -(-ns // unit)
            if value <= 0x3FF:
                return (scale << 10) | value
        raise ValueError(f"{us} us is beyond the LTR range")

    @staticmethod
    def decode(reg):
        return (reg & 0x3FF) * LtrMaxLatencyKnob.UNITS_NS[min((reg >> 10) & 0x7, 5)] / 1000.0

    def supported(self):
        bdf = wifi_pci_device()
        return bool(bdf and shutil.which("setpci") and sh("setpci", "-s", bdf, "ECAP_LTR+0x4.w").returncode == 0)

    def get(self):
        bdf = wifi_pci_device()
        out = sh("setpci", "-s", bdf, "ECAP_LTR+0x4.w", "ECAP_LTR+0x6.w", check=True).stdout.split()
        snoop, nosnoop = (int(x, 16) for x in out)
        return f"{self.decode(snoop):g}" if snoop == nosnoop else f"{self.decode(snoop):g}/{self.decode(nosnoop):g}"

    def set(self, value):
        bdf = wifi_pci_device()
        text = str(value).split("/")[0]
        reg = int(text, 16) if text.lower().startswith("0x") else self.encode(float(text))
        sh("setpci", "-s", bdf, f"ECAP_LTR+0x4.w={reg:04x}", f"ECAP_LTR+0x6.w={reg:04x}", check=True)


class L1ssProfileKnob(Knob):
    """L1.2 timing on both ends of the Wi-Fi link: Linux's values (copied
    from the endpoint: CMRT 8 us, T_POWER_ON 6 us, threshold 20 us, because
    the Apple root port advertises 0) or Apple's (root-port CMRT 25 us,
    LTR_L1.2_THRESHOLD 85 x 1024 ns = 87 us, as macOS programs this link) with
    a T_POWER_ON of 50 or 100 us. Timing may only change while L1.2 is off,
    so the knob drops the ASPM policy to `default` (all substates off), writes
    the root port first, then the endpoint, and restores the policy."""

    name = "l1ss_profile"
    help = "L1.2 timing on the Wi-Fi link: linux, apple50 or apple100"
    choices = ["linux", "apple50", "apple100"]
    persistable = True
    SAVED = STATE_DIR / "l1ss-linux.json"
    # (root CTL1 value, root mask, endpoint CTL1 value, endpoint mask, CTL2)
    PROFILES = {
        "apple50": (0x40551900, 0xE3FFFF00, 0x40550000, 0xE3FF0000, 0x29),
        "apple100": (0x40801900, 0xE3FFFF00, 0x40800000, 0xE3FF0000, 0x0A),
    }

    def _ends(self):
        return L1ssTimingKnob()._ends()

    def supported(self):
        return L1ssTimingKnob().supported()

    def _read(self, bdf, reg):
        return int(sh("setpci", "-s", bdf, f"ECAP_L1PM+{reg}.l", check=True).stdout.strip(), 16)

    def get(self):
        dev, parent = self._ends()
        current = (self._read(parent, "8") & 0xE3FFFF00, self._read(dev, "8") & 0xE3FF0000, self._read(dev, "c") & 0xFF)
        for name, (rp, _, ep, _, ctl2) in self.PROFILES.items():
            if current == (rp, ep, ctl2):
                return name
        return "linux" if not self.SAVED.exists() or current == tuple(json.loads(self.SAVED.read_text())["key"]) else "custom"

    def set(self, value):
        dev, parent = self._ends()
        if not self.SAVED.exists():
            atomic_json(self.SAVED, {
                "rp_ctl1": self._read(parent, "8"), "ep_ctl1": self._read(dev, "8"),
                "rp_ctl2": self._read(parent, "c"), "ep_ctl2": self._read(dev, "c"),
                "key": [self._read(parent, "8") & 0xE3FFFF00, self._read(dev, "8") & 0xE3FF0000, self._read(dev, "c") & 0xFF],
            })
        policy_path = "/sys/module/pcie_aspm/parameters/policy"
        policy = re.search(r"\[(\S+)\]", read(policy_path)).group(1)
        try:
            if policy != "default":
                write(policy_path, "default")  # every L1SS enable off on both ends
            if value == "linux":
                saved = json.loads(self.SAVED.read_text())
                writes = [(parent, "8", saved["rp_ctl1"], 0xE3FFFF00), (dev, "8", saved["ep_ctl1"], 0xE3FF0000),
                          (parent, "c", saved["rp_ctl2"], 0xFF), (dev, "c", saved["ep_ctl2"], 0xFF)]
            else:
                rp, rp_mask, ep, ep_mask, ctl2 = self.PROFILES[value]
                writes = [(parent, "8", rp, rp_mask), (dev, "8", ep, ep_mask), (parent, "c", ctl2, 0xFF), (dev, "c", ctl2, 0xFF)]
            for bdf, reg, val, mask in writes:
                sh("setpci", "-s", bdf, f"ECAP_L1PM+{reg}.l={val & mask:08x}:{mask:08x}", check=True)
        finally:
            if policy != "default":
                write(policy_path, policy)


def knob_registry():
    knobs = [
        ProfileKnob(),
        GovernorKnob(),
        ClusterMaxKnob("e"),
        ClusterMaxKnob("p"),
        PCoresKnob(),
        SysfsKnob("idle_governor", "/sys/devices/system/cpu/cpuidle/current_governor", "cpuidle governor", ["menu", "teo", "ladder"]),
        SysfsKnob("wq_power_efficient", "/sys/module/workqueue/parameters/power_efficient", "power-efficient unbound workqueues", ["Y", "N"]),
        SysfsKnob("aspm", "/sys/module/pcie_aspm/parameters/policy", "PCIe ASPM policy", ["default", "performance", "powersave", "powersupersave"], bracketed=True),
        SysfsKnob("dirty_writeback", "/proc/sys/vm/dirty_writeback_centisecs", "page-cache writeback interval (centiseconds)"),
        SysfsKnob("timer_migration", "/proc/sys/kernel/timer_migration", "migrate timers to busy CPUs", ["0", "1"]),
        SysfsKnob("kbd_backlight", "/sys/class/leds/*kbd_backlight/brightness", "keyboard backlight level"),
        WifiPowerSaveKnob(),
        RfkillKnob("wlan", kills_network=True),
        RfkillKnob("bluetooth", kills_network=False),
        BacklightKnob(),
        DisplayKnob(),
        HyprOptionKnob("hypr_animations", "animations:enabled", "Hyprland animations"),
        L1ssTimingKnob(),
        L1ssProfileKnob(),
        LtrMaxLatencyKnob(),
        HyprOptionKnob("hypr_vfr", "misc:vfr", "Hyprland variable frame rate (render only on change)"),
        RuntimePmKnob(),
    ]
    return {k.name: k for k in knobs}


def get_knob(name):
    registry = knob_registry()
    if name in registry:
        return registry[name]
    if name.startswith("service:"):
        return ServiceKnob(name.split(":", 1)[1])
    if name.startswith("freeze:"):
        return FreezeKnob(name.split(":", 1)[1])
    if name.startswith("usbport:"):
        return UsbPortKnob(name.split(":", 1)[1])
    if name.startswith("pcielink:"):
        _, device, attr = name.split(":", 2)
        return PcieLinkKnob(device, attr)
    raise SystemExit(f"unknown knob {name!r}")


def journal_load():
    try:
        return json.loads(JOURNAL.read_text())
    except (OSError, ValueError):
        return {}


def journal_set(name, value):
    """Apply a knob, remembering its original value for `restore`."""
    knob = get_knob(name)
    journal = journal_load()
    if name not in journal:
        journal[name] = knob.get()
        atomic_json(JOURNAL, journal)
    knob.set(value)


def boot_id():
    return read("/proc/sys/kernel/random/boot_id")


def journal_save(journal):
    if journal:
        atomic_json(JOURNAL, journal)
    else:
        JOURNAL.unlink(missing_ok=True)


def tune_knobs():
    try:
        return json.loads(TUNE_SPEC.read_text()).get("knobs", {})
    except (OSError, ValueError, AttributeError):
        return {}


def restore_knobs(names):
    """Restore the named journaled knobs (newest first) and drop them from the
    journal; a knob that fails to restore keeps its journal entry."""
    journal = journal_load()
    restored, errors = {}, {}
    for name in reversed([n for n in journal if n in names]):
        try:
            get_knob(name).set(journal[name])
            restored[name] = journal[name]
        except Exception as error:  # noqa: BLE001 - keep restoring the rest
            errors[name] = str(error)
    journal = journal_load()
    for name in restored:
        journal.pop(name, None)
    journal_save(journal)
    if not journal and not errors:
        # Nothing left to protect: a failsafe still pending (from `knob`, or
        # one left armed by an earlier failed restore) would otherwise fire
        # later and revert knobs set after this point.
        disarm_all_failsafes()
    # The runtime PM baseline outlives a restore while a persisted tune still
    # holds runtime_pm, so `tune revert` can put the devices back later.
    if "runtime_pm" in restored and "runtime_pm" not in tune_knobs():
        RuntimePmKnob.SAVE.unlink(missing_ok=True)
    return {"restored": restored, "errors": errors}


def restore_all():
    return restore_knobs(set(journal_load()))


def arm_failsafe(seconds, tag):
    """A transient timer that restores every journaled knob if we die.

    The unit name is unique per call, so a leftover timer from an earlier job
    can never block arming this one; arming failures raise before any knob is
    touched."""
    unit = f"m1power-failsafe-{tag}-{os.getpid()}-{time.monotonic_ns()}"
    proc = sh("systemd-run", "--quiet", f"--on-active={int(seconds)}", f"--unit={unit}", "--collect",
              sys.executable, "-I", os.path.abspath(__file__), "restore")
    if proc is None or proc.returncode != 0:
        raise RuntimeError(f"cannot arm failsafe {unit}: {getattr(proc, 'stderr', '').strip()}")
    proc = sh("systemd-run", "--quiet", f"--on-active={int(seconds) + 5}", f"--unit={unit}-rfkill", "--collect",
              "rfkill", "unblock", "all")
    if proc is None or proc.returncode != 0:
        sh("systemctl", "stop", f"{unit}.timer")
        raise RuntimeError(f"cannot arm failsafe {unit}-rfkill: {getattr(proc, 'stderr', '').strip()}")
    return unit


def disarm_all_failsafes():
    sh("systemctl", "stop", "m1power-failsafe-*.timer")


def disarm_failsafe(unit):
    for name in (unit, f"{unit}-rfkill"):
        sh("systemctl", "stop", f"{name}.timer")


# -------------------------------------------------------------- experiments


def run_ab(args):
    refuse_during_lab("an A/B experiment", getattr(args, "force", False))
    knob = get_knob(args.knob)
    if not knob.supported():
        raise SystemExit(f"knob {args.knob} is not supported here")
    original = knob.get()
    a = args.a if args.a is not None else original
    b = args.b
    if a == b:
        raise SystemExit(f"A and B are both {a!r}")
    total = args.pairs * 2 * (args.settle + args.measure) + 120
    had_entry = args.knob in journal_load()
    unit = None
    touched = False
    rng = random.Random(args.seed)
    try:
        unit = arm_failsafe(total, "ab")
        sampler = Sampler()
        result = {
            "kind": "ab",
            "agent": AGENT_VERSION,
            "knob": args.knob,
            "a": a,
            "b": b,
            "original": original,
            "pairs": args.pairs,
            "settle_s": args.settle,
            "measure_s": args.measure,
            "started_wall": time.time(),
            "battery_start": battery(),
            "blocks": [],
            "context": context_snapshot(),
        }
        touched = True
        journal_set(args.knob, a)
        try:
            for index in range(args.pairs):
                order = [a, b] if rng.random() < 0.5 else [b, a]
                pair = {"index": index, "order": order}
                for value in order:
                    check_lab(getattr(args, "force", False), f"pair {index}")
                    journal_set(args.knob, value)
                    time.sleep(args.settle)
                    samples, summary = measure_window(sampler, args.measure, with_detail=args.detail)
                    pair["a" if value == a else "b"] = summary
                    if args.keep_samples:
                        pair[("a" if value == a else "b") + "_samples"] = samples
                result["blocks"].append(pair)
                if args.out:
                    atomic_json(args.out, result | {"status": "running"})
        except LabArrived as arrived:
            # Stop, put the knob back (finally) and keep the completed pairs.
            result["aborted"] = f"lab: {arrived}"
    finally:
        # Forget the knob and disarm the failsafe only once the knob is really
        # back: if restoring raises, its journal entry and the timers stay so
        # `restore` (or the failsafe) can still put it back.
        if touched:
            knob.set(original)
            if not had_entry:
                journal = journal_load()
                journal.pop(args.knob, None)
                journal_save(journal)
        if unit:
            disarm_failsafe(unit)
    result["status"] = "complete"  # terminal; "aborted" says why it ended early
    result["finished_wall"] = time.time()
    result["battery_end"] = battery()
    if args.out:
        atomic_json(args.out, result)
    return result


def context_snapshot():
    """What else could explain a power difference."""
    info = {
        "kernel": os.uname().release,
        "ac": read_int(AC / "online"),
        "battery_status": read(BATTERY / "status"),
        "backlight": read(glob.glob("/sys/class/backlight/*/brightness")[0]) if glob.glob("/sys/class/backlight/*") else None,
        "load": read("/proc/loadavg"),
    }
    try:
        info["display"] = DisplayKnob().get()
    except Exception:  # noqa: BLE001
        info["display"] = "unknown"
    return info


def run_record(args):
    sampler = Sampler()
    stream = emit if not args.out else None
    samples, summary = measure_window(sampler, args.duration, interval=args.interval, stream=stream)
    result = {
        "kind": "record",
        "agent": AGENT_VERSION,
        "label": args.label,
        "started_wall": time.time() - args.duration,
        "context": context_snapshot(),
        "summary": summary,
        "samples": samples,
        "domains_on": sorted(d for d, v in power_domains().items() if v["status"] == "on"),
    }
    if args.out:
        atomic_json(args.out, result)
    else:
        emit({"summary": summary})
    return result


# -------------------------------------------------------------- sleep tests


def domain_offs():
    """Per power domain: [status, power-off count] from genpd debugfs.

    genpd times are on the monotonic clock, which stops in s2idle, so a sleep
    is judged by transitions instead: a domain that was on before the suspend
    and logged no new power-off stayed powered all the way through it."""
    domains = {}
    status = {name: info["status"] for name, info in power_domains().items()}
    for directory in glob.glob("/sys/kernel/debug/pm_genpd/*/"):
        name = Path(directory).name
        usage = 0
        for line in (read(f"{directory}idle_states", "") or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 3 and parts[2].isdigit():
                usage += int(parts[2])
        domains[name] = [status.get(name, "?"), usage]
    return domains


def sleep_snapshot():
    mono, boot = clocks()
    sensors = parse_smc_lines(read(DEBUGFS / "smc_sensors", "") or "")
    return {
        "mono": mono,
        "boot": boot,
        "wall": time.time(),
        "smc": sensors,
        "bat": battery(),
        "idle": idle_counters(),
        "wake": wakeup_sources(),
        "irq": interrupts(),
        "domains": domain_offs(),
    }


def ledger_append(record):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")


def ledger_records(limit=None):
    try:
        lines = LEDGER.read_text().splitlines()
    except OSError:
        return []
    records = [json.loads(line) for line in lines if line.strip()]
    return records[-limit:] if limit else records


def sleep_summary(pre, post):
    """Derive sleep power and quality from hook snapshots around one suspend."""
    slept = (post["boot"] - post["mono"]) - (pre["boot"] - pre["mono"])
    wall = post["boot"] - pre["boot"]
    out = {"slept_s": round(slept, 3), "bracket_s": round(wall, 3), "start_wall": pre["wall"], "end_wall": post["wall"]}
    smc_pre, smc_post = pre.get("smc", {}), post.get("smc", {})
    if isinstance(smc_pre.get("zSPa"), int) and isinstance(smc_post.get("zSPa"), int) and wall > 0:
        out["dcin_j"] = round((smc_post["zSPa"] - smc_pre["zSPa"]) / 1000.0, 3)
        out["dcin_w"] = round(out["dcin_j"] / wall, 4)
        out["smc_samples"] = (smc_post.get("zSPc") or 0) - (smc_pre.get("zSPc") or 0)
    if isinstance(smc_pre.get("zSLa"), int) and isinstance(smc_post.get("zSLa"), int) and wall > 0:
        out["load_w"] = round((smc_post["zSLa"] - smc_pre["zSLa"]) / 1000.0 / wall, 4)
    bat_pre, bat_post = pre.get("bat", {}), post.get("bat", {})
    if "energy_now" in bat_pre and "energy_now" in bat_post:
        delta_wh = (bat_post["energy_now"] - bat_pre["energy_now"]) / 1e6
        out["battery_delta_wh"] = round(delta_wh, 4)
        if wall > 0:
            out["battery_w"] = round(-delta_wh * 3600 / wall, 4)
            if bat_pre.get("energy_full"):
                out["battery_pct_per_hour"] = round(-delta_wh / (bat_pre["energy_full"] / 1e6) * 100 * 3600 / wall, 3)
    if bat_pre.get("energy_full"):
        out["battery_full_wh"] = round(bat_pre["energy_full"] / 1e6, 3)
    out["on_ac"] = bool(bat_pre.get("ac_online"))
    out["battery_status"] = bat_pre.get("status")
    # Best single estimate of the average draw over the bracket. zSLa is the
    # SMC's system-load energy accumulator (mJ, 1 Hz, keeps counting in
    # s2idle): on battery it tracks the discharge exactly (1.105 W against
    # 1.116 W from the gauge), on the charger it equals DC-in. The battery
    # gauge only moves in coarse steps, so it is the last resort.
    if "load_w" in out:
        out["sleep_w"] = out["load_w"]
        out["sleep_w_source"] = "smc_load"
    elif out["on_ac"] and "dcin_w" in out:
        out["sleep_w"] = out["dcin_w"]
    elif "battery_w" in out:
        out["sleep_w"] = out["battery_w"]
    elif "dcin_w" in out:
        out["sleep_w"] = out["dcin_w"]
    # s2idle depth. The per-state s2idle *time* counters use sched_clock,
    # which the kernel stops for the frozen part of s2idle, so they read near
    # zero however long the sleep. Entry counts are reliable: a CPU that
    # entered its deepest (power-down) state during the sleep reached it, and
    # extra entries are interrupts that woke it and put it back.
    idle_pre = {str(cpu): states for cpu, states in pre.get("idle", {}).items()}
    entries = {}
    for cpu, states in post.get("idle", {}).items():
        before = idle_pre.get(str(cpu), {})
        deepest = list(states)[-1] if states else None
        if deepest is None:
            continue
        entries[str(cpu)] = states[deepest][2] - before.get(deepest, [0, 0, 0, 0])[2]
    if entries:
        out["s2idle_pd_entries"] = entries
        out["s2idle_cpus_pd"] = round(sum(1 for n in entries.values() if n > 0) / len(entries), 4)
    wake = []
    for name, count in post.get("wake", {}).items():
        delta = count - pre.get("wake", {}).get(name, 0)
        if delta > 0:
            wake.append([name, delta])
    out["wake_sources"] = sorted(wake, key=lambda row: -row[1])
    irqs = []
    for name, count in post.get("irq", {}).items():
        delta = count - pre.get("irq", {}).get(name, 0)
        if delta > 0:
            irqs.append([name, delta])
    out["irqs_during"] = sorted(irqs, key=lambda row: -row[1])[:12]
    stayed_on = []
    for name, (status, offs) in pre.get("domains", {}).items():
        after = post.get("domains", {}).get(name)
        if status == "on" and after and after[1] == offs:
            stayed_on.append(name)
    if pre.get("domains"):
        out["domains_stayed_on"] = sorted(stayed_on)
    return out


STANDBY_SPEC = Path("/etc/m1power/standby.json")
# In /run so every boot starts a fresh asleep-on-battery clock.
STANDBY_STATE = RUN_DIR / "standby-state.json"
SLEEP_TEST_MARK = RUN_DIR / "sleep-test-active"
SLEEP_KNOBS_SAVED = RUN_DIR / "sleep-knobs.json"
# Wakeup sources that mean a person touched the Mac (keyboard, lid, power
# button). Anything else (power-supply events, alarmtimer) can accompany a
# timer wake without making it a user wake.
USER_WAKE_SOURCES = re.compile(r"macsmc[-_]input|gpio[-_]keys|keyboard|kbd|(?<![a-z])lid(?![a-z])|power[-_]?button", re.I)


def is_user_wake_source(name):
    return bool(USER_WAKE_SOURCES.search(name))


def user_input_count(sources=None):
    """Total wakeup events counted by the user-input wakeup sources."""
    sources = wakeup_sources() if sources is None else sources
    return sum(count for name, count in sources.items() if is_user_wake_source(name))


def is_dark_wake(woken_by):
    """The m1power wake timer fired and no user-input source did."""
    woken_by = set(woken_by)
    return "m1power_waketimer" in woken_by and not any(is_user_wake_source(n) for n in woken_by)


def sleep_test_active():
    """True only while the sleep test that wrote the marker is still running."""
    try:
        pid = int(SLEEP_TEST_MARK.read_text().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    comm = read(f"/proc/{pid}/comm", "") or ""
    return comm.startswith("python")


def waketimer_armed():
    text = read(DEBUGFS / "waketimer", "") or ""
    return bool(re.search(r"^armed 1$", text, re.M))


def standby_spec():
    try:
        return json.loads(STANDBY_SPEC.read_text())
    except (OSError, ValueError):
        return None


def sleep_knobs_for(spec, test_running):
    """Sleep-only knobs for this suspend. Those in the persisted tune apply to
    every suspend, sleep tests included (they keep suspend working, e.g. PCIe
    link substates off for the Wi-Fi D3 handshake); the standby guard's apply
    only outside tests."""
    knobs = {}
    if TUNE_SPEC.exists():
        try:
            knobs.update(json.loads(TUNE_SPEC.read_text()).get("sleep_knobs", {}))
        except (OSError, ValueError):
            pass
    if spec and not test_running:
        knobs.update(spec.get("sleep_knobs", {}))
    return knobs


def apply_sleep_knobs(knobs):
    """Knobs that apply only while asleep; restored on resume."""
    saved = {}
    for name, value in (knobs or {}).items():
        try:
            knob = get_knob(name)
            if knob.supported():
                saved[name] = knob.get()
                if saved[name] != value:
                    if knob.kills_network:
                        radios = {}
                        try:
                            radios = json.loads(SLEEP_RADIOS.read_text())
                        except (OSError, ValueError):
                            pass
                        radios[name] = saved[name]
                        atomic_json(SLEEP_RADIOS, radios)
                    knob.set(value)
        except Exception:  # noqa: BLE001 - never block suspend
            continue
    if saved:
        atomic_json(SLEEP_KNOBS_SAVED, saved)


def restore_sleep_knobs():
    try:
        saved = json.loads(SLEEP_KNOBS_SAVED.read_text())
    except (OSError, ValueError):
        return
    for name, value in saved.items():
        try:
            get_knob(name).set(value)
        except Exception:  # noqa: BLE001
            continue
    SLEEP_KNOBS_SAVED.unlink(missing_ok=True)
    restore_sleep_radios()


def standby_decide(summary, spec):
    """After a timer-only wake: power off, or go straight back to sleep."""
    try:
        state = json.loads(STANDBY_STATE.read_text())
    except (OSError, ValueError):
        state = {}
    bat = battery()
    on_ac = bool(bat.get("ac_online"))
    now = time.time()
    if on_ac or summary.get("on_ac"):
        # Only continuous time asleep on battery counts toward poweroff_after_s.
        state["asleep_since_wall"] = now
    else:
        state.setdefault("asleep_since_wall", summary.get("start_wall"))
    state["dark_wakes"] = state.get("dark_wakes", 0) + 1
    asleep_for = now - (state["asleep_since_wall"] or now)
    action = "resleep"
    lab = lab_activity()
    critical = not on_ac and bat.get("capacity") is not None and bat["capacity"] <= spec.get("poweroff_below_pct", 10)
    if critical:
        # A clean poweroff beats a flat battery, for the owner and for any lab
        # job alike (a dead battery ends the job too, without a clean log).
        action = "poweroff"
    elif lab:
        # A dark wake may have let lab-agent pick up a job: never put the Mac
        # back to sleep under the lab.
        action = "stay"
    elif spec.get("max_dark_wakes") and state["dark_wakes"] >= int(spec["max_dark_wakes"]):
        # Testing aid: after N dark wakes, stay awake so the host can reach the Mac.
        action = "stay"
    elif not on_ac and spec.get("poweroff_after_s") and asleep_for >= spec["poweroff_after_s"]:
        action = "poweroff"
    state["last_action"] = action
    if action in ("poweroff", "stay"):
        STANDBY_STATE.unlink(missing_ok=True)
    else:
        atomic_json(STANDBY_STATE, state)
    inputs = user_input_count()
    if action == "stay":
        ledger_append({"kind": "standby", "action": action, "capacity": bat.get("capacity"), "on_ac": on_ac,
                       "asleep_for_s": round(asleep_for), "dark_wakes": state["dark_wakes"], "end_wall": now,
                       "reason": lab or "max_dark_wakes"})
        return action
    ledger_append({"kind": "standby", "action": action, "capacity": bat.get("capacity"), "on_ac": on_ac,
                   "asleep_for_s": round(asleep_for), "dark_wakes": state["dark_wakes"], "end_wall": now})
    # Never call systemctl synchronously from inside systemd-sleep. The
    # transient unit re-runs the agent, which re-checks for a user before acting.
    sh("systemd-run", "--quiet", "--collect", "--on-active=1",
       f"--unit=m1power-standby-{action}-{time.monotonic_ns()}",
       sys.executable, "-I", os.path.abspath(__file__), "standby-act", action, str(inputs),
       "--since-mono-us", str(time.clock_gettime_ns(time.CLOCK_MONOTONIC) // 1000))
    return action


def graphical_session_active_since(since_mono_us):
    """Name of a graphical seat0 session that logind says went non-idle after
    `since_mono_us` (CLOCK_MONOTONIC), or None. A session whose idle hint
    nobody maintains never changes, so it never counts."""
    if shutil.which("loginctl") is None:
        return None
    listing = sh("loginctl", "list-sessions", "--no-legend")
    if listing.returncode != 0:
        return None
    for line in listing.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        props = {}
        shown = sh("loginctl", "show-session", parts[0], "-p", "Seat", "-p", "Type", "-p", "Active",
                   "-p", "IdleHint", "-p", "IdleSinceHintMonotonic")
        for item in shown.stdout.splitlines():
            key, _, value = item.partition("=")
            props[key] = value.strip()
        if props.get("Seat") != "seat0" or props.get("Type") not in ("wayland", "x11", "mir"):
            continue
        if props.get("Active") != "yes" or props.get("IdleHint") != "no":
            continue
        try:
            changed = int(props.get("IdleSinceHintMonotonic") or 0)
        except ValueError:
            continue
        if changed and changed >= since_mono_us:
            return parts[0]
    return None


STANDBY_WATCH_S = 8.0
# struct input_event on 64-bit: timeval (2 x 8 bytes), u16 type, u16 code, s32 value
INPUT_EVENT = struct.Struct("qqHHi")
USER_EVENT_TYPES = {1: "key", 2: "pointer", 3: "touch", 5: "switch"}


def watch_user_input(seconds):
    """Watch every input device for `seconds`; return a description of the
    first key, pointer, touch or switch (lid) event, or None.

    Wakeup-source counters only move for hard wakeups during suspend, so the
    only reliable sign of a person at an awake Mac is its input devices."""
    import select

    fds = []
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fds.append((os.open(path, os.O_RDONLY | os.O_NONBLOCK), path))
        except OSError:
            continue
    try:
        deadline = time.monotonic() + seconds
        while fds:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            ready, _, _ = select.select([fd for fd, _ in fds], [], [], remaining)
            for fd in ready:
                try:
                    data = os.read(fd, INPUT_EVENT.size * 64)
                except OSError:
                    continue
                for offset in range(0, len(data) - INPUT_EVENT.size + 1, INPUT_EVENT.size):
                    _, _, etype, code, _ = INPUT_EVENT.unpack_from(data, offset)
                    if etype in USER_EVENT_TYPES:
                        name = dict((f, p) for f, p in fds).get(fd, "?")
                        return f"{USER_EVENT_TYPES[etype]} event (code {code}) on {name}"
        return None
    finally:
        for fd, _ in fds:
            os.close(fd)


def standby_act(action, input_count, since_mono_us=None, watch_s=STANDBY_WATCH_S):
    """Run from the transient unit standby_decide scheduled: suspend or power
    off, unless someone uses the Mac during a short watch window."""
    reason = watch_user_input(watch_s) if watch_s else None
    now_inputs = user_input_count()
    # The watch window also gives lab-agent time to reconnect and pick up work.
    lab = lab_activity() if action != "poweroff" else None
    if reason:
        reason = f"user input: {reason}"
    elif lab:
        reason = f"lab: {lab}"
    elif now_inputs != int(input_count):
        reason = f"user input since decision ({input_count} -> {now_inputs})"
    elif since_mono_us is not None:
        session = graphical_session_active_since(int(since_mono_us))
        if session:
            reason = f"session {session} became active"
    record = {"kind": "standby-act", "action": action, "end_wall": time.time()}
    if reason:
        # The user is back: forget the dark-wake run and cancel the wake timer.
        STANDBY_STATE.unlink(missing_ok=True)
        if (DEBUGFS / "waketimer").exists():
            try:
                write(DEBUGFS / "waketimer", "0")
            except OSError:
                pass
        record |= {"outcome": "aborted", "reason": reason}
        ledger_append(record)
        return record
    verb = "poweroff" if action == "poweroff" else "suspend"
    record["outcome"] = verb
    ledger_append(record)
    proc = sh("systemctl", verb, timeout=60)
    if proc.returncode != 0:
        record["error"] = proc.stderr.strip() or str(proc.returncode)
    return record


# --------------------------------------------------------- maclab coexistence
#
# The Mac may be enrolled in a maclab test lab (lab-agent.service). On a
# Lab-owned Mac, Maintainers can boot a test kernel or run a job at any time,
# and nothing in maclab stops the Mac suspending meanwhile. m1power therefore
# stays passive whenever the lab is, or may be, using the Mac.

MACLAB_DIR = Path("/var/lib/maclab")
LAB_AGENT_CGROUP = Path("/sys/fs/cgroup/system.slice/lab-agent.service/cgroup.procs")
# A child of lab-agent counts as work only once it has lived this long: an idle
# lab-agent runs `systemctl is-system-running` and friends on every check-in.
LAB_CHILD_MIN_AGE_S = 2.0


def lab_boot():
    """A maclab Lab boot (test kernel or job boot), from the kernel command line."""
    words = (read("/proc/cmdline", "") or "").split()
    return any(w == "maclab.lab_boot=1" or w.startswith("maclab.job=") for w in words)


def pm_test_mode():
    value = read("/sys/power/pm_test", "") or ""
    match = re.search(r"\[(\S+)\]", value)
    return match.group(1) if match else "none"


def boot_time():
    for line in (read("/proc/stat", "") or "").splitlines():
        if line.startswith("btime "):
            return int(line.split()[1])
    return 0


def process_age_s(pid):
    """Seconds since the process started, or None."""
    stat = read(f"/proc/{pid}/stat")
    uptime = read("/proc/uptime")
    if not stat or not uptime or ")" not in stat:
        return None
    try:
        start_ticks = int(stat.rsplit(")", 1)[1].split()[19])
        return float(uptime.split()[0]) - start_ticks / os.sysconf("SC_CLK_TCK")
    except (IndexError, ValueError):
        return None


def process_cmdline(pid):
    raw = read(f"/proc/{pid}/cmdline", "") or ""
    return raw.replace("\0", " ").strip()


def process_ppid(pid):
    stat = read(f"/proc/{pid}/stat")
    try:
        return int(stat.rsplit(")", 1)[1].split()[1])
    except (AttributeError, IndexError, ValueError):
        return None


def lab_agent_work(pids):
    """Name a lab-agent child doing real work, or None. Its idle helpers are
    the PrepareForSleep monitor (busctl monitor), the sleep delay lock
    (systemd-inhibit --mode=delay) and the placeholder that lock runs."""
    comms = {pid: read(f"/proc/{pid}/comm") for pid in pids}
    for pid, comm in comms.items():
        if not comm or comm == "lab-agent":
            continue
        cmdline = process_cmdline(pid)
        if comm == "systemd-inhibit":
            if "--mode=block" in cmdline:
                return f"lab-agent holds a sleep block inhibitor (pid {pid})"
            if "--mode=delay" in cmdline:
                continue
        if comm == "busctl" and " monitor" in f" {cmdline}":
            continue
        if comm == "sleep" and comms.get(str(process_ppid(pid))) == "systemd-inhibit":
            continue
        age = process_age_s(pid)
        if age is not None and age < LAB_CHILD_MIN_AGE_S:
            continue  # a routine check-in probe, not a command
        return f"lab-agent is running {comm} (pid {pid})"
    return None


def lab_activity():
    """Why the lab may be using the Mac right now, or None.

    Checks the Lab-boot markers, maclab's pm_test suspend cycles, job output
    directories created during this boot (an interrupted command leaves its
    directory behind, so older ones mean nothing; maclab's own busy check
    reads them the same way), and lab-agent children doing real work."""
    if lab_boot():
        return "maclab Lab boot"
    if pm_test_mode() != "none":
        return f"pm_test={pm_test_mode()} (maclab suspend-devices cycle)"
    booted = boot_time()
    for sub in ("out", "jobs"):
        try:
            entries = list((MACLAB_DIR / sub).iterdir())
        except OSError:
            entries = []
        for entry in entries:
            try:
                if entry.stat().st_mtime >= booted:
                    return f"maclab job files in {entry}"
            except OSError:
                continue
    try:
        pids = LAB_AGENT_CGROUP.read_text().split()
    except OSError:
        pids = []
    return lab_agent_work(pids)


def lab_status():
    """What `doctor` shows about maclab enrollment and activity."""
    status = {"enrolled": False}
    try:
        cfg = json.loads(Path("/etc/maclab/agent.json").read_text())
        status = {"enrolled": True, "name": cfg.get("name"), "server": cfg.get("server"),
                  "kind": (cfg.get("enrollment") or {}).get("kind")}
    except (OSError, ValueError):
        pass
    status["lab_boot"] = lab_boot()
    status["activity"] = lab_activity()
    return status


def refuse_during_lab(what, force=False):
    reason = lab_activity()
    if reason and not force:
        raise SystemExit(f"refusing {what}: {reason}. The lab may be using this Mac; pass --force to override.")


def run_hook(phase, operation):
    """systemd-sleep hook: bracket every suspend in the persistent ledger,
    apply sleep-only knobs, and run the standby guard."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    pre_file = RUN_DIR / "sleep-pre.json"
    spec = standby_spec()
    test_running = sleep_test_active()
    # On a Lab boot or during maclab's pm_test cycles, only observe: no sleep
    # knobs, no wake timer, no tuning and no standby decisions.
    lab_passive = lab_boot() or pm_test_mode() != "none"
    if phase == "pre":
        if not lab_passive:
            apply_sleep_knobs(sleep_knobs_for(spec, test_running))
        guard_armed = False
        if spec and not test_running and not lab_passive:
            if spec.get("check_every_s") and (DEBUGFS / "waketimer").exists() and not waketimer_armed():
                try:
                    write(DEBUGFS / "waketimer", str(int(spec["check_every_s"])))
                    guard_armed = True
                except OSError:
                    pass
        snap = sleep_snapshot()
        snap["operation"] = operation
        # Only a wake from a timer the guard itself armed is a dark wake; the
        # timer may also belong to a probe, a test or someone at a shell.
        snap["guard_armed"] = guard_armed
        atomic_json(pre_file, snap)
        return
    if phase != "post":
        return
    restore_sleep_knobs()
    try:
        pre = json.loads(pre_file.read_text())
    except (OSError, ValueError):
        pre = None
    summary = None
    if pre:
        post = sleep_snapshot()
        summary = sleep_summary(pre, post)
        summary["operation"] = operation
        summary["kind"] = "sleep"
        summary["tune"] = TUNE_SPEC.exists()
        summary["test"] = test_running
        summary["standby"] = bool(spec)
        summary["waketimer_fired"] = "m1power_waketimer" in dict(summary["wake_sources"])
        summary["lab_boot"] = lab_boot()
        summary["pm_test"] = pm_test_mode()
        ledger_append(summary)
        pre_file.unlink(missing_ok=True)
    if lab_passive:
        return
    # Runtime knobs such as Wi-Fi power save can reset across suspend.
    if TUNE_SPEC.exists():
        try:
            tune_run()
        except Exception:  # noqa: BLE001 - never block resume
            pass
    if not spec or test_running or summary is None:
        return
    woken_by = {name for name, _ in summary["wake_sources"]}
    if is_dark_wake(woken_by) and pre.get("guard_armed"):
        standby_decide(summary, spec)
    else:
        STANDBY_STATE.unlink(missing_ok=True)
        if (DEBUGFS / "waketimer").exists():
            try:
                write(DEBUGFS / "waketimer", "0")
            except OSError:
                pass


def run_sleep(args):
    """Arm the wake timer, suspend, wait for resume, return the ledger entry."""
    refuse_during_lab("a sleep test", getattr(args, "force", False))
    if not Path(HOOK_PATH).exists():
        raise SystemExit("sleep hook is not installed: run `m1power install` first")
    has_timer = (DEBUGFS / "waketimer").exists()
    if not has_timer and not args.manual_wake:
        raise SystemExit("wake timer unavailable; pass --manual-wake and wake the Mac yourself")
    before = len(ledger_records())
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    journal_before = set(journal_load())
    # The --set knobs (e.g. wifi=off) must come back even if this process dies.
    unit = arm_failsafe(args.seconds + 600, "sleep") if args.set else None
    SLEEP_TEST_MARK.write_text(str(os.getpid()))
    completed = False
    try:
        entry = _run_sleep(args, has_timer, before, journal_before)
        # A knob that failed to come back keeps the failsafe armed.
        completed = not entry.get("restore_errors")
        return entry
    finally:
        SLEEP_TEST_MARK.unlink(missing_ok=True)
        if unit:
            if not completed and args.restore:
                completed = not restore_knobs(set(journal_load()) - journal_before)["errors"]
            if completed:
                disarm_failsafe(unit)


def _run_sleep(args, has_timer, before, journal_before):
    for name, value in (args.set or []):
        journal_set(name, value)
    if args.settle:
        time.sleep(args.settle)
    try:
        check_lab(getattr(args, "force", False), "before suspend")
    except LabArrived as arrived:
        raise SystemExit(f"aborted, lab: {arrived}") from None
    if has_timer:
        write(DEBUGFS / "waketimer", str(args.seconds))
    mono0, boot0 = clocks()
    gap0 = boot0 - mono0
    proc = sh("systemctl", "suspend", timeout=60)
    if proc.returncode != 0:
        raise SystemExit(f"suspend refused: {proc.stderr.strip()}")
    deadline = time.monotonic() + args.seconds + 180
    while time.monotonic() < deadline:
        time.sleep(0.5)
        mono, boot = clocks()
        if (boot - mono) - gap0 > 1.0:
            break
    else:
        raise SystemExit("the Mac never suspended (inhibitor?)")
    for _ in range(40):
        if len(ledger_records()) > before:
            break
        time.sleep(0.25)
    time.sleep(args.post_settle)
    records = ledger_records()
    entry = records[-1] if len(records) > before else {"error": "no ledger entry"}
    entry["requested_s"] = args.seconds
    if args.set:
        entry["knobs"] = dict(args.set)
    if args.restore:
        # Only what this sleep set: context knobs from before it stay.
        restored = restore_knobs(set(journal_load()) - journal_before)
        if restored["errors"]:
            entry["restore_errors"] = restored["errors"]
    if args.out:
        atomic_json(args.out, entry)
    return entry


# ------------------------------------------------------------ suspend stress

SUSPEND_STATS = Path("/sys/power/suspend_stats")
WIFI_ERROR_PATTERNS = ("brcmf_pcie_pm_enter_D3", "Timeout on response", "timed out waiting for txstatus",
                       "failed to suspend", "Some devices failed to suspend", "brcmf_cfg80211_set_power_mgmt: error",
                       "query command", "Firmware has halted", "PCIe link", "AER")


def suspend_counts():
    return {name: read_int(SUSPEND_STATS / name, 0) for name in ("success", "fail", "failed_suspend")}


def kernel_lines_since(cursor):
    """Kernel log lines after a journal cursor, and the new cursor."""
    args = ["journalctl", "-k", "-o", "short-monotonic", "--no-pager", "--show-cursor"]
    args += [f"--after-cursor={cursor}"] if cursor else ["-n", "0"]
    proc = sh(*args, timeout=30)
    lines, new_cursor = [], cursor
    for line in proc.stdout.splitlines():
        if line.startswith("-- cursor: "):
            new_cursor = line[len("-- cursor: "):]
        elif line and not line.startswith("-- "):
            lines.append(line)
    return lines, new_cursor


def gateway():
    out = sh("ip", "route", "show", "default").stdout.split()
    return out[out.index("via") + 1] if "via" in out else None


def run_stress(args):
    """Suspend/resume cycles with Wi-Fi traffic in between; stops at the first
    failed suspend or Wi-Fi firmware error so a wedge is caught early."""
    refuse_during_lab("a suspend stress test", getattr(args, "force", False))
    if not (DEBUGFS / "waketimer").exists():
        raise SystemExit("the m1power wake timer is needed for unattended cycles")
    for name, value in (args.set or []):
        journal_set(name, value)
    result = {"kind": "stress", "agent": AGENT_VERSION, "cycles": [], "set": dict(args.set or []),
              "knobs": {n: get_knob(n).get() for n in ("aspm", "l1ss_tpoweron_us", "pcielink:wifi:l1_1_aspm",
                                                        "pcielink:wifi:l1_2_aspm", "pcielink:wifi:l1_1_pcipm",
                                                        "pcielink:wifi:l1_2_pcipm", "wifi_ps")
                        if get_knob(n).supported()},
              "started_wall": time.time(), "status": "running"}
    _, cursor = kernel_lines_since(None)
    gw = gateway()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    SLEEP_TEST_MARK.write_text(str(os.getpid()))
    try:
        for index in range(args.cycles):
            cycle = {"index": index, "ap_start": wifi_ap()}
            # awake with traffic
            ping = sh("ping", "-q", "-c", str(int(args.awake * 5)), "-i", "0.2", "-W", "1", gw, timeout=args.awake + 30) if gw else None
            cycle["ping_loss"] = (re.search(r"(\d+(?:\.\d+)?)% packet loss", ping.stdout).group(1) if ping and "packet loss" in ping.stdout else None)
            before = suspend_counts()
            mono0, boot0 = clocks()
            write(DEBUGFS / "waketimer", str(args.sleep))
            sh("systemctl", "suspend", timeout=60)
            outcome = "timeout"
            deadline = time.monotonic() + args.sleep + 120
            while time.monotonic() < deadline:
                time.sleep(0.5)
                now = suspend_counts()
                if now["fail"] > before["fail"]:
                    outcome = "failed"
                    break
                if now["success"] > before["success"]:
                    outcome = "ok"
                    break
            mono1, boot1 = clocks()
            cycle["outcome"] = outcome
            cycle["ap_end"] = wifi_ap()
            cycle["slept_s"] = round((boot1 - mono1) - (boot0 - mono0), 2)
            write(DEBUGFS / "waketimer", "0")
            time.sleep(args.settle)
            lines, cursor = kernel_lines_since(cursor)
            cycle["wifi_errors"] = [l for l in lines if any(p in l for p in WIFI_ERROR_PATTERNS)][:20]
            result["cycles"].append(cycle)
            if args.out:
                atomic_json(args.out, result)
            if outcome != "ok" or (cycle["wifi_errors"] and args.stop_on_error):
                result["stopped"] = f"cycle {index}: {outcome}" + (f", {len(cycle['wifi_errors'])} Wi-Fi errors" if cycle["wifi_errors"] else "")
                break
    finally:
        SLEEP_TEST_MARK.unlink(missing_ok=True)
        if args.restore:
            restore_knobs(set(dict(args.set or [])))
    ok = sum(1 for c in result["cycles"] if c["outcome"] == "ok")
    result["summary"] = {"cycles": len(result["cycles"]), "ok": ok,
                         "cycles_with_wifi_errors": sum(1 for c in result["cycles"] if c["wifi_errors"])}
    result["status"] = "complete"
    result["finished_wall"] = time.time()
    if args.out:
        atomic_json(args.out, result)
    return result


# ----------------------------------------------------------- maclab probe


def wdt_channels():
    """Watchdog channel registers from the module, as {channel: {reg: int}}."""
    channels = {}
    for line in (read(DEBUGFS / "wdt_regs", "") or "").splitlines():
        parts = line.split()
        if not parts or not parts[0].startswith("wd"):
            continue
        regs = {}
        for item in parts[1:]:
            key, _, value = item.partition("=")
            try:
                regs[key] = int(value, 16)
            except ValueError:
                continue
        channels[parts[0]] = regs
    return channels


def run_probe(args):
    """One self-contained measurement for a maclab job (or any boot): settle,
    idle capture with the display off, then one self-waking sleep. Writes a
    single JSON file. It is the lab's own work, so it does not defer to it."""
    plan = json.loads(Path(args.plan).read_text()) if args.plan else {}
    settle_s = float(plan.get("settle_s", 60))
    idle_s = float(plan.get("idle_s", 90))
    sleep_s = int(plan.get("sleep_s", 90))
    display = plan.get("display", "off")
    result = {
        "kind": "probe",
        "agent": AGENT_VERSION,
        "plan": plan,
        "job": os.environ.get("MACLAB_JOB"),
        "test": os.environ.get("MACLAB_TEST"),
        "kernel": os.uname().release,
        "model": (read("/proc/device-tree/model") or "").rstrip("\0"),
        "cmdline": read("/proc/cmdline"),
        "lab_boot": lab_boot(),
        "module": {"loaded": (DEBUGFS / "smc_keys").exists(), "waketimer": (DEBUGFS / "waketimer").exists()},
        "started_wall": time.time(),
        "status": "running",
    }

    def save():
        if args.out:
            atomic_json(args.out, result)

    save()
    uptime = float((read("/proc/uptime") or "0 0").split()[0])
    if uptime < settle_s:
        time.sleep(settle_s - uptime)
    result["uptime_at_start_s"] = float((read("/proc/uptime") or "0 0").split()[0])
    restore_display = None
    if display in ("on", "off"):
        try:
            knob = DisplayKnob()
            if knob.supported():
                restore_display = knob.get()
                knob.set(display)
                time.sleep(5)
        except Exception as error:  # noqa: BLE001 - measure anyway, say so
            result["display_error"] = str(error)
    try:
        result["context"] = context_snapshot()
        _, summary = measure_window(Sampler(), idle_s)
        result["idle"] = summary
        result["domains_on"] = sorted(d for d, v in power_domains().items() if v["status"] == "on")
        save()
        if sleep_s and result["module"]["waketimer"]:
            result["wdt_before"] = wdt_channels()
            RUN_DIR.mkdir(parents=True, exist_ok=True)
            SLEEP_TEST_MARK.write_text(str(os.getpid()))
            pre = sleep_snapshot()
            write(DEBUGFS / "waketimer", str(sleep_s))
            mono0, boot0 = clocks()
            proc = sh("systemctl", "suspend", timeout=60)
            if proc.returncode != 0:
                result["sleep"] = {"error": proc.stderr.strip() or "suspend refused"}
            else:
                deadline = time.monotonic() + sleep_s + 180
                resumed = False
                while time.monotonic() < deadline:
                    time.sleep(0.5)
                    mono, boot = clocks()
                    if (boot - mono) - (boot0 - mono0) > 1.0:
                        resumed = True
                        break
                time.sleep(3)
                post = sleep_snapshot()
                sleep = sleep_summary(pre, post)
                sleep["resumed"] = resumed
                sleep["requested_s"] = sleep_s
                result["sleep"] = sleep
                result["wdt_after"] = wdt_channels()
            SLEEP_TEST_MARK.unlink(missing_ok=True)
        elif sleep_s:
            result["sleep"] = {"skipped": "the m1power wake timer is not loaded on this boot"}
    finally:
        SLEEP_TEST_MARK.unlink(missing_ok=True)
        if restore_display not in (None, display):
            try:
                DisplayKnob().set(restore_display)
            except Exception:  # noqa: BLE001
                pass
    result["status"] = "complete"
    result["finished_wall"] = time.time()
    save()
    return result


# ------------------------------------------------------------- persistence

HOOK_PATH = "/usr/lib/systemd/system-sleep/m1power"
AGENT_HOME = Path("/usr/local/lib/m1power")
KMOD_SRC = Path("/usr/local/src/m1power")


def tune_run():
    if lab_boot():
        # Lab boots run a stock system, also for tune units written before
        # the unit gained its ConditionKernelCommandLine guard.
        return {"applied": {}, "errors": {}, "skipped": "maclab Lab boot"}
    spec = json.loads(TUNE_SPEC.read_text())
    applied, errors = {}, {}
    for name, value in spec.get("knobs", {}).items():
        try:
            knob = get_knob(name)
            if knob.kills_network:
                # Never cut the network at boot or resume (an older spec may hold one).
                errors[name] = "kills the network; not applied"
                continue
            if knob.supported() and knob.get() != value:
                knob.set(value)
            applied[name] = value
        except Exception as error:  # noqa: BLE001
            errors[name] = str(error)
    # A radio that is switched off only while asleep must be on whenever the
    # Mac is awake: this runs at boot and after every resume, so a resume hook
    # that never ran cannot leave the Mac offline.
    restored = restore_sleep_radios()
    applied.update(restored)
    return {"applied": applied, "errors": errors}


# Radios the pre-sleep hook switched off. Kept on disk (not /run) because
# systemd-rfkill saves every rfkill change and restores it at boot: if the Mac
# crashed or lost power while asleep, the next boot must turn them back on.
# A radio the user switched off themselves is never in this file.
SLEEP_RADIOS = STATE_DIR / "sleep-radios-off.json"


def restore_sleep_radios():
    try:
        radios = json.loads(SLEEP_RADIOS.read_text())
    except (OSError, ValueError):
        return {}
    restored = {}
    for name, value in radios.items():
        try:
            get_knob(name).set(value)
            restored[name] = value
        except Exception:  # noqa: BLE001 - try the rest; keep the marker
            continue
    if len(restored) == len(radios):
        SLEEP_RADIOS.unlink(missing_ok=True)
    return restored


def write_tune_unit():
    Path("/etc/systemd/system/m1power-tune.service").write_text(
        "[Unit]\nDescription=Apply the m1power idle tuning\nAfter=multi-user.target NetworkManager.service power-profiles-daemon.service\n"
        "# maclab Lab boots run a stock system so the lab's checks compare like with like.\n"
        "ConditionKernelCommandLine=!maclab.lab_boot=1\n\n"
        "[Service]\nType=oneshot\nExecStartPre=/usr/bin/sleep 5\n"
        f"ExecStart=/usr/bin/python3 -I {AGENT_HOME}/agent.py tune run\nRemainAfterExit=yes\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    )
    sh("systemctl", "daemon-reload")


def tune_apply(spec_json):
    spec = json.loads(spec_json)
    knobs = spec.get("knobs", {})
    for name in knobs:
        knob = get_knob(name)
        if not knob.persistable:
            raise SystemExit(f"knob {name} cannot be persisted")
        if knob.kills_network:
            raise SystemExit(f"knob {name} kills the network; it would be re-applied at every boot and resume")
        if not knob.supported():
            raise SystemExit(f"knob {name} is not supported here")
    sleep_knobs = spec.get("sleep_knobs", {})
    for name in sleep_knobs:
        knob = get_knob(name)
        if not knob.supported():
            raise SystemExit(f"sleep knob {name} is not supported here")
        if knob.kills_network and sleep_knobs[name] != "off":
            raise SystemExit(f"sleep knob {name}: a network radio may only be switched off for sleep")
    if "runtime_pm" in knobs:
        # `tune revert` needs the pre-tuning control values, even across reboots.
        RuntimePmKnob().ensure_baseline()
    previous = {}
    if TUNE_SPEC.exists():
        previous = json.loads(TUNE_SPEC.read_text()).get("baseline", {})
    baseline = dict(previous)
    for name in knobs:
        baseline.setdefault(name, get_knob(name).get())
    TUNE_SPEC.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(TUNE_SPEC, {"knobs": knobs, "sleep_knobs": sleep_knobs, "baseline": baseline,
                            "applied_wall": time.time(), "note": spec.get("note", "")})
    write_tune_unit()
    sh("systemctl", "enable", "m1power-tune.service")
    return tune_run() | {"baseline": baseline}


def tune_revert():
    if not TUNE_SPEC.exists():
        return {"reverted": {}, "note": "no tuning installed"}
    spec = json.loads(TUNE_SPEC.read_text())
    reverted, errors, warnings = {}, {}, {}
    for name, value in spec.get("baseline", {}).items():
        if name == "runtime_pm" and not RuntimePmKnob.SAVE.exists():
            warnings[name] = f"no baseline in {RuntimePmKnob.SAVE}; device runtime PM left as it is"
        try:
            get_knob(name).set(value)
            reverted[name] = value
        except Exception as error:  # noqa: BLE001
            errors[name] = str(error)
    if "runtime_pm" in reverted and "runtime_pm" not in journal_load():
        RuntimePmKnob.SAVE.unlink(missing_ok=True)
    if errors:
        # Keep what failed (and its baseline) installed so it can be retried.
        spec["knobs"] = {k: v for k, v in spec.get("knobs", {}).items() if k not in reverted}
        spec["baseline"] = {k: v for k, v in spec.get("baseline", {}).items() if k not in reverted}
        atomic_json(TUNE_SPEC, spec)
        return {"reverted": reverted, "errors": errors, "warnings": warnings, "remaining": spec["baseline"]}
    sh("systemctl", "disable", "m1power-tune.service")
    Path("/etc/systemd/system/m1power-tune.service").unlink(missing_ok=True)
    sh("systemctl", "daemon-reload")
    TUNE_SPEC.unlink()
    return {"reverted": reverted, "errors": errors} | ({"warnings": warnings} if warnings else {})


def kmod_ensure():
    """Build (if needed) and load the m1power module for the running kernel."""
    if (DEBUGFS / "smc_keys").exists():
        return {"loaded": True, "built": False}
    if lab_boot():
        # Lab test kernels ship no headers, and compiling during boot-health
        # and omarchy-m-test would show up as a regression in the lab's checks.
        return {"loaded": False, "skipped": "maclab Lab boot"}
    release = os.uname().release
    out_dir = AGENT_HOME / "kmod" / release
    ko = out_dir / "m1power.ko"
    built = False
    if not ko.exists() and not Path(f"/usr/lib/modules/{release}/build/Makefile").exists():
        return {"loaded": False, "skipped": f"no kernel headers for {release}"}
    lab = lab_activity()
    if not ko.exists() and lab:
        return {"loaded": False, "skipped": f"not compiling while the lab works ({lab}); the next boot builds it"}
    if not ko.exists():
        build_dir = Path(f"/var/tmp/m1power-build-{release}")
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.copytree(KMOD_SRC, build_dir)
        proc = sh("make", "-C", str(build_dir), timeout=600)
        if proc.returncode != 0:
            return {"loaded": False, "error": proc.stdout[-2000:] + proc.stderr[-2000:]}
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(build_dir / "m1power.ko", ko)
        shutil.rmtree(build_dir, ignore_errors=True)
        built = True
    proc = sh("insmod", str(ko))
    if proc.returncode != 0 and "File exists" not in proc.stderr:
        return {"loaded": False, "built": built, "error": proc.stderr.strip()}
    return {"loaded": True, "built": built}


# --------------------------------------------------------------------- info


def info():
    config = {}
    try:
        import gzip

        with gzip.open("/proc/config.gz", "rt") as handle:
            for line in handle:
                for key in ("CONFIG_HIBERNATION", "CONFIG_SUSPEND", "CONFIG_USB_DWC3_GADGET", "CONFIG_NO_HZ_IDLE", "CONFIG_NO_HZ_FULL", "CONFIG_HZ", "CONFIG_MODULE_SIG_FORCE"):
                    if line.startswith(key + "=") or line.startswith(f"# {key} is not set"):
                        config[key] = line.split("=", 1)[1].strip() if "=" in line else "n"
    except OSError:
        pass
    knobs = [get_knob(name).describe() for name in knob_registry()]
    return {
        "kind": "info",
        "agent": AGENT_VERSION,
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "model": (read("/proc/device-tree/model") or "").rstrip("\0"),
        "mem_sleep": read("/sys/power/mem_sleep"),
        "sleep_states": read("/sys/power/state"),
        "hibernation": Path("/sys/power/disk").exists(),
        "kernel_config": config,
        "module": {
            "loaded": (DEBUGFS / "smc_keys").exists(),
            "waketimer": (DEBUGFS / "waketimer").exists(),
        },
        "hook_installed": Path(HOOK_PATH).exists(),
        "maclab": lab_status(),
        "tune": json.loads(TUNE_SPEC.read_text()) if TUNE_SPEC.exists() else None,
        "battery": battery(),
        "smc_now": parse_smc_lines(read(DEBUGFS / "smc_sensors", "") or "") if (DEBUGFS / "smc_sensors").exists() else Smc().read(),
        "cpuidle": {"driver": read("/sys/devices/system/cpu/cpuidle/current_driver"), "governor": read("/sys/devices/system/cpu/cpuidle/current_governor")},
        "policies": cpu_policies(),
        "knobs": knobs,
        "journal": journal_load(),
        "domains_on": sorted(d for d, v in power_domains().items() if v["status"] == "on"),
        "wakeup_enabled": sorted(
            p.rsplit("/power/wakeup", 1)[0].split("/devices/", 1)[-1]
            for p in sysfs_power_files("wakeup")
            if read(p) == "enabled"
        ),
        "uptime_s": float((read("/proc/uptime") or "0 0").split()[0]),
    }


# --------------------------------------------------------------------- main


def main(argv=None):
    parser = argparse.ArgumentParser(prog="m1power-agent")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    sub.add_parser("info")
    sub.add_parser("domains")
    smc = sub.add_parser("smc")
    smc.add_argument("keys", nargs="*")
    rec = sub.add_parser("record")
    rec.add_argument("--duration", type=float, default=60)
    rec.add_argument("--interval", type=float, default=1.0)
    rec.add_argument("--label", default="")
    rec.add_argument("--out")
    knob = sub.add_parser("knob")
    knob.add_argument("name")
    knob.add_argument("value", nargs="?")
    sub.add_parser("knobs")
    sub.add_parser("restore")
    ab = sub.add_parser("ab")
    ab.add_argument("--knob", required=True)
    ab.add_argument("--a")
    ab.add_argument("--b", required=True)
    ab.add_argument("--pairs", type=int, default=4)
    ab.add_argument("--settle", type=float, default=15)
    ab.add_argument("--measure", type=float, default=45)
    ab.add_argument("--seed", type=int)
    ab.add_argument("--detail", action="store_true")
    ab.add_argument("--keep-samples", action="store_true")
    ab.add_argument("--out")
    ab.add_argument("--force", action="store_true", help="run even while the maclab lab may be using the Mac")
    batch = sub.add_parser("batch", help="run a list of jobs from a JSON file, sequentially")
    batch.add_argument("spec")
    batch.add_argument("--out", required=True)
    slp = sub.add_parser("sleep")
    slp.add_argument("--seconds", type=int, default=300)
    slp.add_argument("--manual-wake", action="store_true")
    slp.add_argument("--settle", type=float, default=5)
    slp.add_argument("--post-settle", type=float, default=3)
    slp.add_argument("--set", nargs=2, action="append", metavar=("KNOB", "VALUE"))
    slp.add_argument("--restore", action="store_true")
    slp.add_argument("--out")
    slp.add_argument("--force", action="store_true", help="run even while the maclab lab may be using the Mac")
    hook = sub.add_parser("hook")
    hook.add_argument("phase")
    hook.add_argument("operation", nargs="?", default="")
    ledger = sub.add_parser("ledger")
    ledger.add_argument("--last", type=int)
    tune = sub.add_parser("tune")
    tune.add_argument("action", choices=["run", "apply", "revert", "show", "refresh-unit"])
    tune.add_argument("--spec")
    sub.add_parser("kmod")
    sub.add_parser("lab")
    stress = sub.add_parser("stress", help="suspend/resume cycles with Wi-Fi traffic; stops at the first failure")
    stress.add_argument("--cycles", type=int, default=10)
    stress.add_argument("--awake", type=float, default=60)
    stress.add_argument("--sleep", type=int, default=60)
    stress.add_argument("--settle", type=float, default=8)
    stress.add_argument("--set", nargs=2, action="append", metavar=("KNOB", "VALUE"))
    stress.add_argument("--restore", action="store_true")
    stress.add_argument("--stop-on-error", action="store_true")
    stress.add_argument("--force", action="store_true")
    stress.add_argument("--out")
    probe = sub.add_parser("probe", help="one settle/idle/sleep measurement, e.g. inside a maclab job")
    probe.add_argument("--plan")
    probe.add_argument("--out")
    standby = sub.add_parser("standby")
    standby.add_argument("action", choices=["set", "show", "off"])
    standby.add_argument("--spec")
    act = sub.add_parser("standby-act", help="internal: run by the standby guard's transient unit")
    act.add_argument("action", choices=["resleep", "poweroff"])
    act.add_argument("input_count", type=int)
    act.add_argument("--since-mono-us", type=int)
    args = parser.parse_args(argv)

    if args.cmd == "version":
        emit({"agent": AGENT_VERSION})
    elif args.cmd == "info":
        emit(info())
    elif args.cmd == "domains":
        emit(power_domains())
    elif args.cmd == "smc":
        if args.keys:
            emit(Smc(args.keys).read())
        else:
            emit(smc_dump())
    elif args.cmd == "record":
        run_record(args)
    elif args.cmd == "knobs":
        emit({name: get_knob(name).describe() for name in knob_registry()})
    elif args.cmd == "knob":
        emit(set_knob_cmd(args.name, args.value))
    elif args.cmd == "restore":
        emit(restore_all())
    elif args.cmd == "ab":
        result = run_ab(args)
        emit({"status": result["status"], "out": args.out} if args.out else result)
    elif args.cmd == "batch":
        run_batch(args)
    elif args.cmd == "sleep":
        emit(run_sleep(args))
    elif args.cmd == "hook":
        run_hook(args.phase, args.operation)
    elif args.cmd == "ledger":
        for record in ledger_records(args.last):
            emit(record)
    elif args.cmd == "tune":
        if args.action == "run":
            emit(tune_run())
        elif args.action == "apply":
            emit(tune_apply(args.spec))
        elif args.action == "revert":
            emit(tune_revert())
        elif args.action == "refresh-unit":
            if TUNE_SPEC.exists():
                write_tune_unit()
                emit({"refreshed": True})
            else:
                emit({"refreshed": False})
        else:
            emit(json.loads(TUNE_SPEC.read_text()) if TUNE_SPEC.exists() else {})
    elif args.cmd == "lab":
        emit(lab_status())
    elif args.cmd == "stress":
        result = run_stress(args)
        emit({"status": result["status"], "out": args.out} if args.out else result)
    elif args.cmd == "probe":
        result = run_probe(args)
        emit({"status": result["status"], "out": args.out} if args.out else result)
    elif args.cmd == "kmod":
        # Runs early at every boot (m1power-kmod.service), with or without a
        # tune: the place to undo a radio left off by an interrupted sleep.
        restored = restore_sleep_radios()
        emit(kmod_ensure() | ({"radios_restored": restored} if restored else {}))
    elif args.cmd == "standby":
        if args.action == "set":
            spec = json.loads(args.spec)
            for name in spec.get("sleep_knobs", {}):
                get_knob(name)
            atomic_json(STANDBY_SPEC, spec)
            emit({"standby": spec})
        elif args.action == "off":
            STANDBY_SPEC.unlink(missing_ok=True)
            STANDBY_STATE.unlink(missing_ok=True)
            emit({"standby": None})
        else:
            emit({"standby": standby_spec(), "state": json.loads(STANDBY_STATE.read_text()) if STANDBY_STATE.exists() else None})
    elif args.cmd == "standby-act":
        emit(standby_act(args.action, args.input_count, args.since_mono_us))


KNOB_FAILSAFE_S = 300


def set_knob_cmd(name, value):
    """`knob NAME [VALUE]`: a change to a network-killing knob arms a failsafe
    that restores it after KNOB_FAILSAFE_S unless `restore` runs first."""
    knob = get_knob(name)
    extra = {}
    if value is not None:
        if knob.kills_network and knob.get() != value:
            arm_failsafe(KNOB_FAILSAFE_S, "knob")
            extra["failsafe_s"] = KNOB_FAILSAFE_S
        journal_set(name, value)
    return knob.describe() | extra


def run_batch(args):
    """Run several experiments back to back without host involvement."""
    jobs = json.loads(Path(args.spec).read_text())
    results = {"kind": "batch", "agent": AGENT_VERSION, "started_wall": time.time(), "jobs": [], "status": "running"}
    atomic_json(args.out, results)
    for job in jobs:
        kind = job.pop("kind")
        journal_before = set(journal_load())
        try:
            if kind == "ab":
                ns = argparse.Namespace(a=None, pairs=4, settle=15, measure=45, seed=None, detail=False, keep_samples=False, out=None)
                for key, value in job.items():
                    setattr(ns, key, value)
                res = run_ab(ns)
            elif kind == "record":
                ns = argparse.Namespace(duration=60, interval=1.0, label="", out=None)
                for key, value in job.items():
                    setattr(ns, key, value)
                res = run_record(ns)
                res.pop("samples", None)
            elif kind == "sleep":
                ns = argparse.Namespace(seconds=300, manual_wake=False, settle=5, post_settle=3, set=None, restore=True, out=None)
                for key, value in job.items():
                    setattr(ns, key, value)
                res = run_sleep(ns)
            elif kind == "set":
                # Context for the following jobs (an experiment arm); journaled,
                # so a later `restore` job or the failsafe puts it back.
                applied = {}
                for name, value in job.get("knobs", {}).items():
                    journal_set(name, value)
                    applied[name] = get_knob(name).get()
                res = {"applied": applied}
            elif kind == "restore":
                res = restore_all()
            elif kind == "stress":
                ns = argparse.Namespace(cycles=10, awake=60, sleep=60, settle=8, set=None, restore=True,
                                        stop_on_error=False, force=False, out=None)
                for key, value in job.items():
                    setattr(ns, key, value)
                res = run_stress(ns)
            else:
                res = {"error": f"unknown job kind {kind}"}
        except (Exception, SystemExit) as error:  # noqa: BLE001 - record and continue
            res = {"error": str(error), "job": job}
            # Undo only what this job changed; knobs the host set as context
            # for the whole batch (e.g. display=off) stay as they are.
            restored = restore_knobs(set(journal_load()) - journal_before)
            if restored["restored"] or restored["errors"]:
                res["restore"] = restored
        res["job_kind"] = kind
        results["jobs"].append(res)
        atomic_json(args.out, results)
        error = str(res.get("error", ""))
        lab_stop = res.get("aborted") or (error if ("aborted, lab" in error or "lab may be using" in error) else None)
        if lab_stop:
            # The lab has the Mac now: leave the remaining jobs undone.
            results["aborted"] = f"stopped after job {len(results['jobs'])}: {lab_stop}"
            break
    results["status"] = "complete"
    results["finished_wall"] = time.time()
    atomic_json(args.out, results)


if __name__ == "__main__":
    main()
