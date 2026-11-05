"""m1power: measure and reduce idle and sleep power on an Apple-silicon Mac.

Runs on the Omarchy host (any Linux machine with SSH to the target). The target
is an Apple-silicon Mac running Asahi/Omarchy Linux; see docs/LIVE.md.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time
from typing import Any

from m1lab.live import analysis, report
from m1lab.live.remote import REMOTE_RESULTS, Target, TargetError, collect_hint, default_target, new_job_id, results_dir, save_result

PRESETS: dict[str, list[dict[str, Any]]] = {
    # Each entry is an A/B job: B is compared against the knob's current value.
    "idle": [
        {"knob": "ppd", "b": "power-saver"},
        {"knob": "ppd", "b": "balanced"},
        {"knob": "wifi_ps", "b": "on"},
        {"knob": "bt", "b": "off"},
        {"knob": "wq_power_efficient", "b": "Y"},
        {"knob": "aspm", "b": "powersupersave"},
        {"knob": "runtime_pm", "b": "auto"},
        {"knob": "idle_governor", "b": "teo"},
        {"knob": "freeze:superwhisper", "b": "frozen"},
        {"knob": "freeze:quickshell", "b": "frozen"},
    ],
    "radios": [
        {"knob": "wifi", "b": "off"},
        {"knob": "bt", "b": "off"},
        {"knob": "wifi_ps", "b": "on"},
    ],
    "display": [
        {"knob": "display", "b": "off"},
        {"knob": "backlight", "b": "0"},
        {"knob": "hypr_animations", "b": "0"},
    ],
}


MANUAL_WAKE_GRACE_S = 24 * 3600
FAILSAFE_S = 300  # the agent's automatic restore for network-killing knobs
MIN_CHECK_EVERY_S = 300


class UsageError(Exception):
    """A request m1power refuses before touching the target."""


def out(text: str = "") -> None:
    print(text, flush=True)


def progress(message: str) -> None:
    sys.stderr.write(f"\r\033[2K  {message}")
    sys.stderr.flush()


def end_progress() -> None:
    sys.stderr.write("\r\033[2K")
    sys.stderr.flush()


def fmt_w(value: Any) -> str:
    return f"{value:6.3f}" if isinstance(value, (int, float)) else "     -"


# ----------------------------------------------------------------- commands


def cmd_doctor(target: Target, args: argparse.Namespace) -> None:
    info = target.agent("info")
    out(f"target      {target.address}  ({info['model']}, {info['hostname']})")
    out(f"kernel      {info['kernel']}  agent v{info['agent']}")
    smc = info.get("smc_now", {})
    out(f"power now   system {fmt_w(smc.get('PSTR'))} W   DC-in {fmt_w(smc.get('PDTR'))} W   SoC {fmt_w(smc.get('PHPC'))} W")
    bat = info.get("battery", {})
    out(f"battery     {bat.get('capacity')}% {bat.get('status')}  AC={bat.get('ac_online')}  behaviour {bat.get('charge_behaviour')}  cycles {bat.get('cycle_count')}")
    out(f"sleep       mem_sleep={info['mem_sleep']}  hibernation={'yes' if info['hibernation'] else 'NO (kernel lacks CONFIG_HIBERNATION)'}")
    module = info.get("module", {})
    checks = [
        ("m1power module (full SMC sensor access)", module.get("loaded")),
        ("s2idle wake timer (unattended sleep tests)", module.get("waketimer")),
        ("sleep ledger hook (records every suspend)", info.get("hook_installed")),
        ("persistent tuning", bool(info.get("tune"))),
    ]
    for label, ok in checks:
        out(f"  [{'x' if ok else ' '}] {label}")
    if not all(ok for _, ok in checks[:3]):
        out("  run `m1power install` to set up the module, wake timer and ledger")
    if info.get("journal"):
        out(f"  ! knobs changed and not restored: {info['journal']} (run `m1power restore`)")
    out(f"cpuidle     {info['cpuidle']['driver']} / {info['cpuidle']['governor']}")
    out(f"domains on  {len(info['domains_on'])}: {' '.join(info['domains_on'])}")
    out("knobs:")
    for knob in info["knobs"]:
        state = knob.get("value") if knob.get("supported") else "unsupported"
        out(f"  {knob['name']:20} {str(state):14} {knob['help']}")
    if args.json:
        out(json.dumps(info, indent=1))


def cmd_install(target: Target, args: argparse.Namespace) -> None:
    out(f"installing on {target.address} ...")
    result = target.install()
    out(json.dumps(result))
    if not result.get("loaded"):
        out("module did not load; SMC access falls back to hwmon and sleep tests need --manual-wake")


def cmd_uninstall(target: Target, args: argparse.Namespace) -> None:
    out(target.uninstall().strip())


def cmd_watch(target: Target, args: argparse.Namespace) -> None:
    out("   time   sys W  DC-in W  SoC W   E idle(deep)  P idle(deep)   E MHz  P MHz   irq/s  ctxt/s")
    start = time.monotonic()
    try:
        for row in target.stream("record", "--duration", str(args.duration), "--interval", str(args.interval)):
            if "summary" in row:
                summary = row["summary"]
                out(f"mean over {summary['n']} samples: system {fmt_w(summary.get('sys_w'))} W, DC-in {fmt_w(summary.get('dcin_acc_w'))} W")
                break
            idle = row.get("idle", {})
            mhz = row.get("mhz", {})
            e, p = idle.get("e", {}), idle.get("p", {})
            out(
                f"{time.monotonic() - start:7.1f} {fmt_w(row.get('sys_w'))} {fmt_w(row.get('dcin_acc_w'))}  {fmt_w(row.get('soc_w'))}"
                f"   {100 * (e.get('wfi', 0) + e.get('deep', 0)):5.1f}({100 * e.get('deep', 0):4.1f})"
                f"  {100 * (p.get('wfi', 0) + p.get('deep', 0)):5.1f}({100 * p.get('deep', 0):4.1f})"
                f"   {mhz.get('e', 0):5}  {mhz.get('p', 0):5}  {row.get('irq_s', 0):6.0f}  {row.get('ctxt_s', 0):6.0f}"
            )
    except KeyboardInterrupt:
        pass


def cmd_record(target: Target, args: argparse.Namespace) -> None:
    job = new_job_id("record")
    path = target.start_detached(job, "record", "--duration", str(args.duration), "--label", args.label)
    out(f"started {job} on target (if the wait is interrupted: `m1power collect {job}`)")
    result = wait_job(target, job, path, expected_s=args.duration + 3)
    saved = save_result("record", result, args.label)
    print_record(result)
    out(f"saved {saved}")


def print_record(result: dict[str, Any]) -> None:
    s = result["summary"]
    ctx = result.get("context", {})
    out(f"context: display={ctx.get('display')} backlight={ctx.get('backlight')} AC={ctx.get('ac')} battery={ctx.get('battery_status')} load={ctx.get('load')}")
    out(f"system {fmt_w(s.get('sys_w'))} W (sd {s.get('sys_w_sd', 0):.3f})   DC-in {fmt_w(s.get('dcin_acc_w'))} W   SoC {fmt_w(s.get('soc_w'))} W   irq/s {s.get('irq_s')}   ctxt/s {s.get('ctxt_s')}")
    for cluster, states in s.get("idle", {}).items():
        out(f"  {cluster}-cluster: deep idle {100 * states.get('deep', 0):.1f}%  wfi {100 * states.get('wfi', 0):.1f}%  avg {s.get('mhz', {}).get(cluster)} MHz")
    if s.get("top_wakers"):
        out("top wakers (context switches/s, CPU%):")
        for row in s["top_wakers"][:10]:
            out(f"  {row['wakeups_s']:8.2f}/s  {row['cpu_pct']:6.2f}%  {row['comm']} [{row['pid']}]")
    if s.get("top_irqs"):
        out("top interrupts (/s):")
        for name, rate in s["top_irqs"][:8]:
            out(f"  {rate:8.2f}  {name}")


def cmd_knobs(target: Target, args: argparse.Namespace) -> None:
    knobs = target.agent("knobs")
    for name, knob in knobs.items():
        state = knob.get("value") if knob.get("supported") else "unsupported"
        choices = "/".join(knob.get("choices") or [])
        out(f"{name:20} {str(state):14} {choices:32} {knob['help']}")


def cmd_knob(target: Target, args: argparse.Namespace) -> None:
    extra = [args.value] if args.value is not None else []
    if args.value is not None:
        knob = target.agent("knobs").get(args.name) or {}
        if knob.get("kills_network") and str(knob.get("value")) != args.value:
            if not args.force:
                raise UsageError(
                    f"{args.name}={args.value} can cut the network this command arrives on, leaving the target unreachable; "
                    f"rerun with --force to set it anyway (the agent then restores it after {FAILSAFE_S} s), "
                    f"or measure it with `m1power ab` / `sweep`, which arm a failsafe"
                )
            out(f"{args.name} can cut the network: the agent arms a {FAILSAFE_S} s failsafe that restores it")
    result = target.agent("knob", args.name, *extra)
    out(json.dumps(result))
    if isinstance(result, dict) and result.get("failsafe_s"):
        out(f"failsafe armed: {args.name} is restored after {result['failsafe_s']} s")


def cmd_restore(target: Target, args: argparse.Namespace) -> None:
    out(json.dumps(target.agent("restore")))


def ab_job(knob: str, b: str, args: argparse.Namespace, a: str | None = None) -> dict[str, Any]:
    job: dict[str, Any] = {
        "kind": "ab",
        "knob": knob,
        "b": b,
        "pairs": args.pairs,
        "settle": args.settle,
        "measure": args.measure,
        "detail": True,
    }
    if a is not None:
        job["a"] = a
    return job


def wait_job(target: Target, job_id: str, out_path: str, *, expected_s: float, grace_s: float = 900) -> dict[str, Any]:
    try:
        return target.wait_detached(job_id, out_path, expected_s=expected_s, progress=progress, grace_s=grace_s)
    except KeyboardInterrupt:
        end_progress()
        out(f"stopped waiting; {collect_hint(job_id)}")
        raise
    finally:
        end_progress()


def run_batch(
    target: Target,
    jobs: list[dict[str, Any]],
    *,
    label: str,
    expected_s: float,
    job_id: str | None = None,
    grace_s: float = 900,
) -> dict[str, Any]:
    job_id = job_id or new_job_id("batch")
    out_path = start_batch(target, jobs, job_id=job_id, expected_s=expected_s)
    return finish_batch(target, job_id, out_path, label=label, expected_s=expected_s, grace_s=grace_s)


def start_batch(target: Target, jobs: list[dict[str, Any]], *, job_id: str, expected_s: float) -> str:
    spec_path = f"{REMOTE_RESULTS}/{job_id}-spec.json"
    target.run(f"mkdir -p {REMOTE_RESULTS} && cat > {spec_path}", input=json.dumps(jobs).encode())
    out_path = target.start_detached(job_id, "batch", spec_path)
    out(f"started {job_id} on target: {len(jobs)} job(s), about {expected_s / 60:.0f} min")
    out(f"  if the wait is interrupted, fetch the result later with `m1power collect {job_id}`")
    return out_path


def finish_batch(target: Target, job_id: str, out_path: str, *, label: str, expected_s: float, grace_s: float = 900) -> dict[str, Any]:
    result = wait_job(target, job_id, out_path, expected_s=expected_s, grace_s=grace_s)
    saved = save_result("batch", result, label)
    out(f"saved {saved}")
    return result


def cmd_collect(target: Target, args: argparse.Namespace) -> None:
    """Reattach to a detached job, then save and print it like the original command."""
    job_id = args.job_id
    out_path = f"{REMOTE_RESULTS}/{job_id}.json"
    result = wait_job(target, job_id, out_path, expected_s=0, grace_s=args.grace)
    kind = result.get("kind") or job_id.split("-", 1)[0]
    if kind == "record":
        saved = save_result("record", result, result.get("label") or job_id)
        print_record(result)
    else:
        saved = save_result(kind, result, job_id)
        jobs = result.get("jobs", [])
        ab = [j for j in jobs if j.get("job_kind") == "ab"]
        sleeps = [j for j in jobs if j.get("job_kind") == "sleep"]
        if ab:
            print_ab_table(ab)
        if sleeps:
            print_sleeps(sleeps)
        if not ab and not sleeps:
            out(f"{len(jobs)} job(s), status {result.get('status')}")
    out(f"saved {saved}")


def ab_seconds(args: argparse.Namespace) -> float:
    return args.pairs * 2 * (args.settle + args.measure) + 10


def cmd_ab(target: Target, args: argparse.Namespace) -> None:
    result = run_batch(target, [ab_job(args.knob, args.b, args, args.a)], label=f"ab-{args.knob}", expected_s=ab_seconds(args))
    print_ab_table(result["jobs"])


def cmd_sweep(target: Target, args: argparse.Namespace) -> None:
    entries = list(PRESETS[args.preset])
    for extra in args.include or []:
        knob, _, value = extra.partition("=")
        entries.append({"knob": knob, "b": value})
    if args.only:
        entries = [e for e in entries if e["knob"] in args.only]
    knobs = target.agent("knobs")
    jobs = []
    for entry in entries:
        name = entry["knob"]
        if name in knobs and not knobs[name].get("supported"):
            out(f"skip {name}: unsupported")
            continue
        if name in knobs and knobs[name].get("value") == entry["b"]:
            out(f"skip {name}: already {entry['b']}")
            continue
        jobs.append(ab_job(name, entry["b"], args))
    job_id = new_job_id("batch")
    if args.display:
        jobs.insert(0, {"kind": "record", "duration": 1, "label": "display-context"})
        target.agent("knob", "display", args.display)
    expected = len(jobs) * ab_seconds(args)
    try:
        out_path = start_batch(target, jobs, job_id=job_id, expected_s=expected)
    except BaseException:
        if args.display:
            target.agent("restore")
        raise
    try:
        result = finish_batch(target, job_id, out_path, label=f"sweep-{args.preset}", expected_s=expected)
    except (KeyboardInterrupt, TargetError):
        # The batch may still be running: restoring now would change the
        # display (and any knob under test) in the middle of a measurement.
        if args.display:
            out(f"display left {args.display}: after the batch ends run `m1power collect {job_id}`, then `m1power restore`")
        raise
    if args.display:
        target.agent("restore")
    print_ab_table([j for j in result["jobs"] if j.get("job_kind") == "ab"])


def print_ab_table(jobs: list[dict[str, Any]]) -> None:
    rows = []
    for job in jobs:
        if "error" in job:
            out(f"  error: {job['error']}")
            continue
        analyzed = analysis.analyze_ab(job)
        sys_effect = analyzed["effects"].get("sys_w", {})
        rows.append((sys_effect.get("delta", 0.0), analyzed, job))
    rows.sort(key=lambda row: row[0])
    out()
    out(f"{'knob':24} {'A -> B':28} {'A W':>7} {'B W':>7}  verdict")
    for _, analyzed, job in rows:
        effect = analyzed["effects"].get("sys_w", {})
        change = f"{job['a']} -> {job['b']}"
        out(f"{analyzed['knob']:24} {change[:28]:28} {effect.get('mean_a', 0):7.3f} {effect.get('mean_b', 0):7.3f}  {analyzed.get('verdict', '')}")
        irq = analyzed["effects"].get("irq_s")
        if irq and irq.get("significant"):
            out(f"{'':24} {'':28} {'':7} {'':7}  interrupts {irq['mean_a']:.0f}/s -> {irq['mean_b']:.0f}/s")


def cmd_sleep(target: Target, args: argparse.Namespace) -> None:
    jobs = []
    for _ in range(args.repeat):
        job: dict[str, Any] = {"kind": "sleep", "seconds": args.seconds, "restore": True}
        if args.set:
            job["set"] = [list(pair.split("=", 1)) for pair in args.set]
        if args.manual_wake:
            job["manual_wake"] = True
        jobs.append(job)
    expected = args.repeat * (args.seconds + 25)
    grace = 900
    if args.manual_wake:
        grace = MANUAL_WAKE_GRACE_S
        out(f"wake the Mac yourself when you want each sleep to end; the host waits up to {grace // 3600} h for the result")
    result = run_batch(target, jobs, label="sleep", expected_s=expected, grace_s=grace)
    print_sleeps([j for j in result["jobs"]])


def cmd_sleep_ab(target: Target, args: argparse.Namespace) -> None:
    import random

    jobs = []
    for _ in range(args.pairs):
        pair = [None, f"{args.knob}={args.value}"]
        random.shuffle(pair)
        for setting in pair:
            job: dict[str, Any] = {"kind": "sleep", "seconds": args.seconds, "restore": True}
            if setting:
                job["set"] = [setting.split("=", 1)]
            jobs.append(job)
    result = run_batch(target, jobs, label=f"sleep-ab-{args.knob}", expected_s=len(jobs) * (args.seconds + 25))
    entries = result["jobs"]
    print_sleeps(entries)
    effect = analysis.analyze_sleep_ab(entries, args.knob)
    if effect:
        out(f"\n{args.knob}={args.value} while asleep: {effect['verdict']}")


def print_sleeps(entries: list[dict[str, Any]]) -> None:
    entries = [e for e in entries if analysis.is_sleep(e) or "error" in e]
    out(f"{'ended':19} {'slept':>7} {'sleep W':>8} {'DC-in W':>8} {'bat W':>7} {'%/h':>6} {'CPUs PD':>7} woke by")
    for e in entries:
        if "error" in e:
            out(f"  error: {e['error']}")
            continue
        ended = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.get("end_wall", 0)))
        wake = ", ".join(f"{name}" for name, _ in e.get("wake_sources", [])[:3]) or "?"
        bat = e.get("battery_w")
        pct = e.get("battery_pct_per_hour")
        out(
            f"{ended:19} {e.get('slept_s', 0):7.0f} {fmt_w(analysis.sleep_watts(e))}  {fmt_w(e.get('dcin_w'))}  {fmt_w(bat) if not e.get('on_ac') else '  (AC)'} "
            f"{pct if pct is not None and not e.get('on_ac') else '':>6} {100 * e.get('s2idle_cpus_pd', 0):6.0f}%  {wake}"
        )
    summary = analysis.summarize_sleeps(entries)
    if summary.get("count"):
        out(f"\n{summary['count']} sleeps, {summary['slept_hours']} h: {summary['sleep_w_weighted']:.3f} W average draw while asleep")
        if summary.get("battery_count"):
            watts = summary["battery_w_weighted"]
            basis = f"from {summary['battery_count']} on-battery sleep(s)"
        else:
            watts = summary.get("dcin_w_weighted", summary["sleep_w_weighted"])
            basis = "a DC-in figure: includes charger loss; unplug the cable for a battery measurement"
        capacities = [e["battery_full_wh"] for e in entries if e.get("battery_full_wh")]
        if capacities:
            capacity, which = capacities[-1], "this Mac's battery at its current full charge"
        else:
            capacity, which = 49.9, "a new M1 Air battery (design capacity; this one may hold less)"
        out(f"  {capacity:.1f} Wh, {which}: ~{analysis.days_of_standby(watts, capacity):.1f} days of standby ({basis})")


def cmd_ledger(target: Target, args: argparse.Namespace) -> None:
    records = target.agent("ledger", *(["--last", str(args.last)] if args.last else []))
    if isinstance(records, dict):
        records = [records]
    print_sleeps(records or [])


def cmd_tune(target: Target, args: argparse.Namespace) -> None:
    if args.action == "show":
        out(json.dumps(target.agent("tune", "show"), indent=1))
    elif args.action == "revert":
        out(json.dumps(target.agent("tune", "revert"), indent=1))
    else:
        knobs = dict(pair.split("=", 1) for pair in args.settings)
        described = target.agent("knobs")
        for name in knobs:
            info = described.get(name) or {}
            if info.get("kills_network"):
                raise UsageError(f"refusing to persist {name}: it can cut the network, and re-applied at every boot and resume it would strand the target offline")
            if info and info.get("persistable") is False:
                raise UsageError(f"refusing to persist {name}: it is not persistable")
        sleep_knobs = dict(pair.split("=", 1) for pair in args.sleep or [])
        for name, value in sleep_knobs.items():
            if (described.get(name) or {}).get("kills_network") and value != "off":
                raise UsageError(f"refusing sleep knob {name}={value}: a network radio may only be switched off for sleep")
        spec = json.dumps({"knobs": knobs, "sleep_knobs": sleep_knobs, "note": args.note})
        out(json.dumps(target.agent("tune", "apply", "--spec", spec), indent=1))


def parse_duration(text: str) -> int:
    """Parse ``90m``/``2h``/``1d``/``600s``. A unit is required: a bare number is ambiguous."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    text = (text or "").strip().lower()
    if not text or text[-1] not in units:
        raise UsageError(f"duration {text!r} needs a unit: s, m, h or d (for example 90m or 2h)")
    try:
        value = float(text[:-1])
    except ValueError:
        raise UsageError(f"duration {text!r} is not a number with a unit") from None
    if not math.isfinite(value) or value * units[text[-1]] > 10 * 365 * 86400:
        raise UsageError(f"duration {text!r} is not a finite, reasonable length")
    seconds = int(value * units[text[-1]])
    if not value > 0 or seconds <= 0:
        raise UsageError(f"duration {text!r} must be positive")
    return seconds


def cmd_standby(target: Target, args: argparse.Namespace) -> None:
    if args.action == "show":
        out(json.dumps(target.agent("standby", "show"), indent=1))
        return
    if args.action == "off":
        out(json.dumps(target.agent("standby", "off")))
        return
    check_every_s = parse_duration(args.check_every)
    if check_every_s < MIN_CHECK_EVERY_S:
        raise UsageError(f"--check-every must be at least {MIN_CHECK_EVERY_S // 60} min: shorter dark-wake intervals loop suspend and resume")
    spec = {
        "check_every_s": check_every_s,
        "poweroff_below_pct": args.poweroff_below,
        "poweroff_after_s": parse_duration(args.poweroff_after) if args.poweroff_after is not None else None,
        "sleep_knobs": dict(pair.split("=", 1) for pair in args.sleep_knob or []),
        "max_dark_wakes": args.max_dark_wakes,
    }
    out(json.dumps(target.agent("standby", "set", "--spec", json.dumps(spec)), indent=1))


def cmd_domains(target: Target, args: argparse.Namespace) -> None:
    domains = target.agent("domains")
    for name, info in sorted(domains.items(), key=lambda kv: (kv[1]["status"] != "on", kv[0])):
        if args.all or info["status"] == "on":
            devices = " ".join(f"{d}({s})" for d, s in info["devices"])
            out(f"{name:20} {info['status']:8} {devices}")


def cmd_smc(target: Target, args: argparse.Namespace) -> None:
    data = target.agent("smc", *args.keys, timeout=300)
    if args.keys:
        for key, value in data.items():
            out(f"{key:6} {value}")
        return
    for key, info in sorted(data.items()):
        if args.grep and not key.startswith(tuple(args.grep)):
            continue
        out(f"{key:6} {info['type']:5} {info['flags']} {info['value']}")


def cmd_report(target: Target | None, args: argparse.Namespace) -> None:
    ledger = []
    if target and not args.offline:
        try:
            records = target.agent("ledger")
            ledger = records if isinstance(records, list) else ([records] if records else [])
        except TargetError as error:
            out(f"(ledger unavailable: {error})")
    path = report.write_report(results_dir(), ledger, Path(args.out) if args.out else None)
    out(f"wrote {path}")


# --------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="m1power", description=__doc__)
    parser.add_argument("--target", default=None, help="ssh destination of the measured Mac (env M1POWER_TARGET)")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="inventory the target and what is set up")
    doctor.add_argument("--json", action="store_true")
    sub.add_parser("install", help="install agent, kernel module, wake timer and sleep ledger on the target")
    sub.add_parser("uninstall", help="remove everything install added (keeps the ledger)")

    watch = sub.add_parser("watch", help="live power, idle residency, frequency and interrupt rates")
    watch.add_argument("--duration", type=float, default=3600)
    watch.add_argument("--interval", type=float, default=1.0)

    record = sub.add_parser("record", help="detached capture with top wakers and interrupts")
    record.add_argument("--duration", type=float, default=120)
    record.add_argument("--label", default="")

    sub.add_parser("knobs", help="list tunables and their current values")
    knob = sub.add_parser("knob", help="read or set one knob (recorded for `restore`)")
    knob.add_argument("name")
    knob.add_argument("value", nargs="?")
    knob.add_argument("--force", action="store_true", help=f"set a knob that can cut the network (restored after {FAILSAFE_S} s)")
    sub.add_parser("restore", help="put every knob changed by m1power back")
    collect = sub.add_parser("collect", help="reattach to a detached job (after Ctrl-C, re-auth or a timeout) and save its result")
    collect.add_argument("job_id")
    collect.add_argument("--grace", type=float, default=900, help="seconds to keep polling for the result")

    def timing(p: argparse.ArgumentParser, pairs: int, settle: float, measure: float) -> None:
        p.add_argument("--pairs", type=int, default=pairs)
        p.add_argument("--settle", type=float, default=settle)
        p.add_argument("--measure", type=float, default=measure)

    ab = sub.add_parser("ab", help="randomized paired A/B test of one knob")
    ab.add_argument("knob")
    ab.add_argument("b", help="value to compare against the current one")
    ab.add_argument("--a", help="baseline value (default: current)")
    timing(ab, 4, 15, 45)

    sweep = sub.add_parser("sweep", help="A/B every knob in a preset and rank the savings")
    sweep.add_argument("--preset", choices=sorted(PRESETS), default="idle")
    sweep.add_argument("--include", action="append", help="extra KNOB=VALUE, e.g. service:lab-agent=off")
    sweep.add_argument("--only", nargs="*")
    sweep.add_argument("--display", choices=["on", "off"], help="hold the display in this state for the sweep")
    timing(sweep, 3, 10, 30)

    sleep = sub.add_parser("sleep", help="unattended suspend test using the wake timer")
    sleep.add_argument("--seconds", type=int, default=300)
    sleep.add_argument("--repeat", type=int, default=1)
    sleep.add_argument("--set", action="append", help="KNOB=VALUE to apply during the sleep")
    sleep.add_argument("--manual-wake", action="store_true")

    sleep_ab = sub.add_parser("sleep-ab", help="paired sleeps with and without a knob change")
    sleep_ab.add_argument("knob")
    sleep_ab.add_argument("value")
    sleep_ab.add_argument("--pairs", type=int, default=3)
    sleep_ab.add_argument("--seconds", type=int, default=300)

    ledger = sub.add_parser("ledger", help="every suspend recorded on the target")
    ledger.add_argument("--last", type=int)

    tune = sub.add_parser("tune", help="persist knob settings on the target (re-applied at boot and resume)")
    tune.add_argument("action", choices=["apply", "revert", "show"])
    tune.add_argument("settings", nargs="*", help="KNOB=VALUE")
    tune.add_argument("--note", default="")
    tune.add_argument("--sleep", action="append", metavar="KNOB=VALUE",
                      help="value applied just before every suspend and undone on resume (e.g. aspm=default)")

    standby = sub.add_parser("standby", help="standby guard: periodic dark wakes that power off on low battery")
    standby.add_argument("action", choices=["set", "show", "off"])
    standby.add_argument("--check-every", default="2h", help="dark-wake interval, e.g. 90m or 2h")
    standby.add_argument("--poweroff-below", type=int, default=10, help="battery percent that triggers poweroff")
    standby.add_argument("--poweroff-after", help="power off after this long asleep on battery, e.g. 24h")
    standby.add_argument("--sleep-knob", action="append", help="KNOB=VALUE applied only while asleep")
    standby.add_argument("--max-dark-wakes", type=int, help="testing aid: stay awake after this many dark wakes")

    domains = sub.add_parser("domains", help="SoC power domains (PMGR) and their devices")
    domains.add_argument("--all", action="store_true")

    smc = sub.add_parser("smc", help="read SMC keys (all keys when none given)")
    smc.add_argument("keys", nargs="*")
    smc.add_argument("--grep", nargs="*", help="key prefixes to show from the full dump")

    rep = sub.add_parser("report", help="write an HTML report of every saved result and the sleep ledger")
    rep.add_argument("--out")
    rep.add_argument("--offline", action="store_true")
    return parser


COMMANDS = {
    "doctor": cmd_doctor,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
    "watch": cmd_watch,
    "record": cmd_record,
    "knobs": cmd_knobs,
    "knob": cmd_knob,
    "restore": cmd_restore,
    "collect": cmd_collect,
    "ab": cmd_ab,
    "sweep": cmd_sweep,
    "sleep": cmd_sleep,
    "sleep-ab": cmd_sleep_ab,
    "ledger": cmd_ledger,
    "tune": cmd_tune,
    "standby": cmd_standby,
    "domains": cmd_domains,
    "smc": cmd_smc,
    "report": cmd_report,
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    target = Target(args.target or default_target())
    try:
        COMMANDS[args.command](target, args)
    except (TargetError, UsageError) as error:
        end_progress()
        sys.exit(f"m1power: {error}")
    except KeyboardInterrupt:
        end_progress()
        sys.exit(130)


if __name__ == "__main__":
    main()
