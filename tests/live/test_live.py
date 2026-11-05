from __future__ import annotations

import json
import struct

import pytest

from m1lab.live import agent, analysis, cli, remote


def flt(value: float) -> str:
    return struct.pack("<f", value).hex()


def test_decode_smc_types() -> None:
    assert agent.decode_smc("flt", flt(1.5)) == pytest.approx(1.5)
    assert agent.decode_smc("ui32", "de1e0000") == 0x1EDE
    assert agent.decode_smc("si16", "ffff") == -1
    assert agent.decode_smc("ioft", "0000010000000000") == pytest.approx(1.0)
    assert agent.decode_smc("ch8*", "41424300") == "ABC"
    assert agent.decode_smc("flt", "-") is None
    assert agent.decode_smc("flt", "E-5") is None


def test_parse_smc_lines_handles_padded_type_codes() -> None:
    text = "\n".join(
        [
            "BOOT 200",
            "MONO 100",
            f"PSTR flt  4 85 {flt(1.25)}",
            "zSPa ui64 8 84 ae9c2a0200000000",
            "WKTP ui8  1 d0 -",
        ]
    )
    values = agent.parse_smc_lines(text)
    assert values["BOOT"] == 200 and values["MONO"] == 100
    assert values["PSTR"] == pytest.approx(1.25)
    assert values["zSPa"] == 0x022A9CAE
    assert values["WKTP"] is None


def snapshot(boot: float, mono: float, zspa: int, s2idle_us: int, wake: int, energy: int) -> dict:
    return {
        "boot": boot,
        "mono": mono,
        "wall": boot,
        "smc": {"zSPa": zspa, "zSPc": int(boot), "zSLa": zspa},
        "bat": {"energy_now": energy, "energy_full": 36_000_000, "ac_online": 0, "status": "Discharging"},
        "idle": {0: {"WFI": [0, 0, 0, 0], "CPU PD": [0, 0, 1 if s2idle_us else 0, s2idle_us]}},
        "wake": {"m1power_waketimer": wake, "macsmc-ac": 3},
        "irq": {"125 m1power-waketimer": wake},
    }


def test_sleep_summary_uses_boottime_gap_and_dcin_accumulator() -> None:
    pre = snapshot(boot=1000.0, mono=900.0, zspa=1_000_000, s2idle_us=0, wake=0, energy=30_000_000)
    post = snapshot(boot=1102.0, mono=902.0, zspa=1_051_000, s2idle_us=90_000_000, wake=1, energy=29_990_000)
    summary = agent.sleep_summary(pre, post)
    assert summary["slept_s"] == pytest.approx(100.0)
    assert summary["bracket_s"] == pytest.approx(102.0)
    assert summary["dcin_j"] == pytest.approx(51.0)
    assert summary["dcin_w"] == pytest.approx(0.5)
    assert summary["s2idle_cpus_pd"] == pytest.approx(1.0)
    assert summary["s2idle_pd_entries"] == {"0": 1}
    assert summary["battery_delta_wh"] == pytest.approx(-0.01)
    assert summary["battery_w"] == pytest.approx(0.01 * 3600 / 102, rel=1e-3)
    assert summary["wake_sources"] == [["m1power_waketimer", 1]]
    assert not summary["on_ac"]


def test_power_domains_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    text = """domain                          status          children        performance
    /device                         runtime status                  managed by
------------------------------------------------------------------------------
disp0_cpu0                      on                              0
    231304000.iommu                 active                      0           SW
dispext_fe                      on                              0
                                                dispext_cpu0
isp_set12                       off-0                           0
    genpd:13:22a000000.isp          suspended                   0           SW
"""
    monkeypatch.setattr(agent, "read", lambda path, default=None: text)
    domains = agent.power_domains()
    assert domains["disp0_cpu0"] == {"status": "on", "devices": [["231304000.iommu", "active"]]}
    assert domains["dispext_fe"]["devices"] == []
    assert domains["isp_set12"]["status"] == "off-0"


def test_summarize_averages_and_idle() -> None:
    samples = [
        {"sys_w": 1.0, "idle": {"e": {"deep": 0.8, "wfi": 0.1}}, "mhz": {"e": 600}},
        {"sys_w": 2.0, "idle": {"e": {"deep": 0.6, "wfi": 0.3}}, "mhz": {"e": 1000}},
    ]
    summary = agent.summarize(samples)
    assert summary["sys_w"] == pytest.approx(1.5)
    assert summary["idle"]["e"]["deep"] == pytest.approx(0.7)
    assert summary["mhz"]["e"] == 800


def ab_result(pairs: list[tuple[float, float]]) -> dict:
    return {
        "knob": "wifi_ps",
        "a": "off",
        "b": "on",
        "blocks": [{"a": {"sys_w": a, "irq_s": 400.0}, "b": {"sys_w": b, "irq_s": 300.0}} for a, b in pairs],
    }


def test_analyze_ab_detects_saving() -> None:
    analyzed = analysis.analyze_ab(ab_result([(1.30, 1.10), (1.28, 1.09), (1.31, 1.12), (1.29, 1.10)]))
    effect = analyzed["effects"]["sys_w"]
    assert effect["delta"] == pytest.approx(-0.1925, abs=1e-4)
    assert effect["significant"]
    assert analyzed["verdict"].startswith("saves 192 mW")
    assert analyzed["ten_percent_rule"] == "threshold_supported"


def test_analyze_ab_reports_no_effect_when_interval_spans_zero() -> None:
    analyzed = analysis.analyze_ab(ab_result([(1.30, 1.32), (1.28, 1.25), (1.31, 1.33)]))
    assert analyzed["verdict"].startswith("no detectable effect")
    assert not analyzed["effects"]["sys_w"]["significant"]


def test_summarize_sleeps_weights_by_duration() -> None:
    entries = [
        {"slept_s": 100, "dcin_w": 1.0, "s2idle_cpus_pd": 0.9},
        {"slept_s": 300, "dcin_w": 0.5, "s2idle_cpus_pd": 0.95},
        {"slept_s": 5, "dcin_w": 9.0},
    ]
    summary = analysis.summarize_sleeps(entries)
    assert summary["count"] == 2
    assert summary["dcin_w_weighted"] == pytest.approx(0.625)


def test_presets_only_name_known_knobs() -> None:
    known = set(agent.knob_registry())
    for jobs in cli.PRESETS.values():
        for job in jobs:
            name = job["knob"]
            assert name in known or name.split(":", 1)[0] in ("service", "freeze"), name


def test_restore_puts_back_journaled_values(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "JOURNAL", tmp_path / "journal.json")
    values = {"x": "old"}

    class Fake(agent.Knob):
        name = "x"

        def get(self) -> str:
            return values["x"]

        def set(self, value: str) -> None:
            values["x"] = value

    monkeypatch.setattr(agent, "get_knob", lambda name: Fake())
    agent.journal_set("x", "new")
    agent.journal_set("x", "newer")
    assert json.loads((tmp_path / "journal.json").read_text()) == {"x": "old"}
    assert values["x"] == "newer"
    assert agent.restore_all() == {"restored": {"x": "old"}, "errors": {}}
    assert values["x"] == "old"
    assert not (tmp_path / "journal.json").exists()


def test_hook_script_targets_installed_agent() -> None:
    assert remote.REMOTE_AGENT in remote.HOOK_SCRIPT
    assert remote.HOOK_SCRIPT.startswith("#!/bin/sh")


def test_save_result_names(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = remote.save_result("record", {"k": 1}, "a b/c")
    assert path.parent == tmp_path / "m1-power-lab" / "live"
    assert "a_b_c" in path.name
    assert json.loads(path.read_text()) == {"k": 1}


def test_cli_parser_accepts_core_commands() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["sweep", "--preset", "idle", "--pairs", "2"]).pairs == 2
    assert parser.parse_args(["sleep", "--seconds", "600", "--set", "wifi=off"]).set == ["wifi=off"]
    assert parser.parse_args(["tune", "apply", "wifi_ps=on"]).settings == ["wifi_ps=on"]


@pytest.mark.parametrize(
    ("capacity", "on_ac", "asleep_for", "expected"),
    [(8, 0, 60, "poweroff"), (8, 1, 60, "resleep"), (60, 0, 60, "resleep"), (60, 0, 90_000, "poweroff")],
)
def test_standby_decision(monkeypatch: pytest.MonkeyPatch, tmp_path, capacity, on_ac, asleep_for, expected) -> None:
    monkeypatch.setattr(agent, "STANDBY_STATE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(agent, "battery", lambda: {"capacity": capacity, "ac_online": on_ac})
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    monkeypatch.setattr(agent, "wakeup_sources", lambda: {"macsmc-input": 7, "m1power_waketimer": 3})
    now = 1_000_000.0
    monkeypatch.setattr(agent.time, "time", lambda: now)
    action = agent.standby_decide({"start_wall": now - asleep_for}, {"poweroff_below_pct": 10, "poweroff_after_s": 86_400})
    assert action == expected
    # The transient unit re-runs the agent, which re-checks for a user first.
    act = list(commands[-1])
    assert act[act.index("standby-act") + 1 : act.index("standby-act") + 3] == [expected, "7"]
    assert agent.ledger_records()[-1]["action"] == expected


def test_sleep_ab_pairs_in_run_order() -> None:
    entries = [
        {"slept_s": 300, "dcin_w": 0.70},
        {"slept_s": 300, "dcin_w": 0.50, "knobs": {"wifi": "off"}},
        {"slept_s": 300, "dcin_w": 0.52, "knobs": {"wifi": "off"}},
        {"slept_s": 300, "dcin_w": 0.71},
        {"slept_s": 300, "dcin_w": 0.69},
        {"slept_s": 300, "dcin_w": 0.49, "knobs": {"wifi": "off"}},
    ]
    effect = analysis.analyze_sleep_ab(entries, "wifi")
    assert effect["pairs"] == 3
    assert effect["delta"] == pytest.approx(-0.1967, abs=1e-3)
    assert effect["verdict"].startswith("saves")


# ------------------------------------------------- host-side review fixes


class FakeTarget(remote.Target):
    """A Target whose shell is a function of the command string."""

    def __init__(self, respond, agent_replies=None) -> None:
        super().__init__("root@fake")
        self.respond = respond
        self.agent_replies = agent_replies or {}
        self.commands: list[str] = []
        self.agent_calls: list[tuple] = []

    def run(self, command, *, input=None, timeout=120, check=True):  # noqa: A002 - mirrors Target.run
        self.commands.append(command)
        return self.respond(command)

    def agent(self, *args, timeout=120):
        self.agent_calls.append(args)
        return self.agent_replies[args[0]]


def test_parse_duration_requires_unit_and_positive_value() -> None:
    assert cli.parse_duration("2h") == 7200
    assert cli.parse_duration("90m") == 5400
    assert cli.parse_duration("600s") == 600
    for bad in ("2", "", "0m", "-1h", "abch", "h"):
        with pytest.raises(cli.UsageError):
            cli.parse_duration(bad)


def test_standby_set_rejects_short_interval_and_zero_poweroff_after() -> None:
    target = FakeTarget(lambda command: pytest.fail("target must not be contacted"))
    parser = cli.build_parser()
    for argv in (["standby", "set", "--check-every", "2m"], ["standby", "set", "--poweroff-after", "0h"]):
        with pytest.raises(cli.UsageError):
            cli.cmd_standby(target, parser.parse_args(argv))
    assert not target.agent_calls


def test_wait_detached_fails_fast_when_unit_died_with_partial_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remote.time, "sleep", lambda s: pytest.fail("must not wait out the grace period"))

    def respond(command: str) -> str:
        if command.startswith("journalctl"):
            return "Started m1power-batch-1.\nkernel: rebooting\n"
        return "inactive\n" + json.dumps({"status": "running", "jobs": [{"job_kind": "ab"}]})

    target = FakeTarget(respond)
    with pytest.raises(remote.TargetError) as caught:
        target.wait_detached("batch-1", "/x/batch-1.json", expected_s=0)
    message = str(caught.value)
    assert "incomplete" in message and "kernel: rebooting" in message

    target = FakeTarget(lambda c: "journal tail" if c.startswith("journalctl") else "failed\n{not json")
    with pytest.raises(remote.TargetError, match="unreadable"):
        target.wait_detached("batch-2", "/x/batch-2.json", expected_s=0)


def test_wait_detached_returns_complete_result_and_reauth_names_collect(monkeypatch: pytest.MonkeyPatch) -> None:
    done = {"status": "complete", "jobs": []}
    target = FakeTarget(lambda command: "inactive\n" + json.dumps(done))
    assert target.wait_detached("batch-3", "/x.json", expected_s=0) == done

    def reauth(command: str) -> str:
        raise remote.NeedsReauth("Tailscale SSH needs you to re-authenticate")

    with pytest.raises(remote.NeedsReauth, match=r"m1power collect batch-4"):
        FakeTarget(reauth).wait_detached("batch-4", "/x.json", expected_s=0)


def test_sleep_power_uses_battery_when_unplugged() -> None:
    battery = {"slept_s": 3600, "on_ac": False, "dcin_w": 0.0, "battery_w": 0.4}
    ac = {"slept_s": 3600, "on_ac": True, "dcin_w": 0.9, "battery_w": 0.0}
    assert analysis.sleep_watts(battery) == pytest.approx(0.4)
    assert analysis.sleep_watts(ac) == pytest.approx(0.9)
    assert analysis.sleep_watts({"sleep_w": 0.3, "dcin_w": 1.0, "on_ac": True}) == pytest.approx(0.3)
    summary = analysis.summarize_sleeps([battery, ac])
    assert summary["sleep_w_weighted"] == pytest.approx(0.65)
    assert summary["dcin_w_weighted"] == pytest.approx(0.45)
    assert summary["battery_count"] == 1 and summary["battery_w_weighted"] == pytest.approx(0.4)


def test_cli_standby_days_line_names_its_basis(capsys: pytest.CaptureFixture[str]) -> None:
    cli.print_sleeps([{"slept_s": 3600, "on_ac": False, "sleep_w": 0.5, "dcin_w": 0.0, "battery_w": 0.5}])
    text = capsys.readouterr().out
    assert "0.500 W average" in text and "on-battery" in text and "inf" not in text
    cli.print_sleeps([{"slept_s": 3600, "on_ac": True, "sleep_w": 0.8, "dcin_w": 0.8}])
    assert "DC-in figure" in capsys.readouterr().out


def test_sleep_ab_never_pairs_ac_with_battery() -> None:
    entries = [
        {"slept_s": 300, "on_ac": True, "dcin_w": 0.9},
        {"slept_s": 300, "on_ac": False, "dcin_w": 0.0, "battery_w": 0.4, "knobs": {"wifi": "off"}},
        {"slept_s": 300, "on_ac": False, "dcin_w": 0.0, "battery_w": 0.5},
    ]
    effect = analysis.analyze_sleep_ab(entries, "wifi")
    assert effect["pairs"] == 1
    assert effect["mean_a"] == pytest.approx(0.5) and effect["mean_b"] == pytest.approx(0.4)


def test_verdict_survives_zero_baseline() -> None:
    effect = analysis.paired_effect([0.0, 0.0, 0.0], [0.5, 0.6, 0.55], "sleep_w")
    assert effect.percent is None
    assert analysis.verdict(effect).startswith("costs")


def test_paired_effect_keeps_interval_past_t_table() -> None:
    a = [1.0 + 0.01 * (i % 3) for i in range(40)]
    b = [x - 0.1 for x in a]
    b[0] += 0.001
    effect = analysis.paired_effect(a, b, "sys_w")
    assert effect.ci_low is not None and effect.ci_high < 0
    assert analysis.verdict(effect).startswith("saves")


def write_batch(directory, jobs) -> None:
    (directory / "20260101T000000-batch.json").write_text(json.dumps({"kind": "batch", "status": "complete", "jobs": jobs}))


def test_report_renders_ab_jobs_without_sys_w(tmp_path) -> None:
    from m1lab.live import report

    write_batch(tmp_path, [{"job_kind": "ab", "knob": "x", "a": "0", "b": "1", "blocks": [{"a": {"irq_s": 1.0}, "b": {"irq_s": 2.0}}]}])
    assert "<title>M1 Power Report</title>" in report.render_report(tmp_path, [])


def test_render_report_writes_nothing_and_write_report_does(tmp_path) -> None:
    from m1lab.live import report

    write_batch(tmp_path, [])
    before = sorted(p.name for p in tmp_path.iterdir())
    html = report.render_report(tmp_path, [])
    assert html.startswith("<!doctype html>")
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    path = report.write_report(tmp_path, [], tmp_path / "out.html")
    assert path.read_text() == report.render_report(tmp_path, [])


def test_standby_records_are_not_sleeps(tmp_path) -> None:
    from m1lab.live import report

    ledger = [
        {"kind": "sleep", "slept_s": 600, "end_wall": 1_700_000_000, "on_ac": True, "dcin_w": 0.75, "wake_sources": [["m1power_waketimer", 1]]},
        {"kind": "standby", "action": "resleep", "end_wall": 1_700_000_100, "capacity": 80},
    ]
    html = report.render_report(tmp_path, ledger)
    assert html.count(" min</td>") == 1
    assert "resleep" not in html
    assert analysis.summarize_sleeps(ledger)["count"] == 1
    assert analysis.analyze_sleep_ab(ledger, "wifi") is None


def test_knob_refuses_network_killer_without_force(capsys: pytest.CaptureFixture[str]) -> None:
    knobs = {"wifi": {"kills_network": True, "persistable": True, "value": "on", "supported": True}}
    target = FakeTarget(lambda c: "", {"knobs": knobs, "knob": {"name": "wifi", "value": "off", "failsafe_s": 300}})
    parser = cli.build_parser()
    with pytest.raises(cli.UsageError, match="--force"):
        cli.cmd_knob(target, parser.parse_args(["knob", "wifi", "off"]))
    assert [c[0] for c in target.agent_calls] == ["knobs"]
    cli.cmd_knob(target, parser.parse_args(["knob", "wifi", "off", "--force"]))
    assert target.agent_calls[-1] == ("knob", "wifi", "off")
    assert "300 s" in capsys.readouterr().out
    with pytest.raises(cli.UsageError, match="cut the network"):
        cli.cmd_tune(target, parser.parse_args(["tune", "apply", "wifi=off"]))
    assert not any(c[:2] == ("tune", "apply") for c in target.agent_calls)


def test_verified_upload_is_atomic_and_checks_digest(tmp_path) -> None:
    import hashlib
    import subprocess

    data = b"print('agent')\n"
    digest = hashlib.sha256(data).hexdigest()[:16]
    path = tmp_path / "sub" / "agent.py"
    ok = subprocess.run(["bash", "-c", remote.verified_upload_script(str(path), digest)], input=data, capture_output=True)
    assert ok.returncode == 0 and path.read_bytes() == data
    bad = subprocess.run(["bash", "-c", remote.verified_upload_script(str(path), "0" * 16)], input=b"truncat", capture_output=True)
    assert bad.returncode != 0 and path.read_bytes() == data
    assert sorted(p.name for p in path.parent.iterdir()) == ["agent.py"]


# ---------------------------------------------------------------- agent fixes


class _FakeKnob(agent.Knob):
    """In-memory knob for agent tests; `fail_on` makes set(value) raise."""

    def __init__(self, name: str, store: dict, kills_network: bool = False, persistable: bool = True, fail_on=None) -> None:
        self.name, self.store, self.kills_network, self.persistable, self.fail_on = name, store, kills_network, persistable, fail_on

    def get(self) -> str:
        return self.store[self.name]

    def set(self, value: str) -> None:
        if value == self.fail_on:
            raise RuntimeError(f"cannot set {self.name}={value}")
        self.store[self.name] = value


def _use_journal(monkeypatch: pytest.MonkeyPatch, tmp_path, knobs: dict) -> None:
    monkeypatch.setattr(agent, "JOURNAL", tmp_path / "journal.json")
    monkeypatch.setattr(agent, "TUNE_SPEC", tmp_path / "tune.json")
    monkeypatch.setattr(agent.RuntimePmKnob, "SAVE", tmp_path / "runtime_pm_baseline.json")
    monkeypatch.setattr(agent, "get_knob", lambda name: knobs[name])


def test_idle_counters_survive_json_round_trip_in_sleep_summary() -> None:
    def snap(boot: float, mono: float, entries: int) -> dict:
        return {"boot": boot, "mono": mono, "wall": boot, "bat": {},
                "idle": {"0": {"WFI": [0, 0, 0, 0], "CPU PD": [0, 0, entries, 0]},
                         "4": {"WFI": [0, 0, 0, 0], "CPU PD": [0, 0, 7, 0]}}}

    # CPU 0 entered power-down 3 more times during this sleep; CPU 4 never did.
    pre = json.loads(json.dumps(snap(1000.0, 900.0, 40)))
    post = snap(1060.0, 900.0, 43)
    summary = agent.sleep_summary(pre, post)
    assert summary["s2idle_pd_entries"] == {"0": 3, "4": 0}
    assert summary["s2idle_cpus_pd"] == pytest.approx(0.5)
    legacy_pre = snap(1000.0, 900.0, 40) | {"idle": {0: {"WFI": [0, 0, 0, 0], "CPU PD": [0, 0, 40, 0]},
                                                     4: {"WFI": [0, 0, 0, 0], "CPU PD": [0, 0, 7, 0]}}}
    assert agent.sleep_summary(legacy_pre, post)["s2idle_pd_entries"] == {"0": 3, "4": 0}


def test_idle_counters_and_sampler_use_string_cpu_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_glob(pattern: str) -> list[str]:
        if pattern.endswith("cpuidle"):
            return ["/sys/devices/system/cpu/cpu3/cpuidle"]
        if pattern.endswith("state*"):
            return ["/sys/devices/system/cpu/cpu3/cpuidle/state0"]
        return []

    monkeypatch.setattr(agent.glob, "glob", fake_glob)
    monkeypatch.setattr(agent, "read", lambda path, default=None: "WFI" if path.endswith("name") else default)
    monkeypatch.setattr(agent, "read_int", lambda path, default=None: 5)
    counters = agent.idle_counters()
    assert list(counters) == ["3"]
    assert json.loads(json.dumps(counters)) == counters


def test_sleep_w_prefers_smc_load_accumulator_then_dcin_then_battery() -> None:
    pre = snapshot(boot=1000.0, mono=900.0, zspa=1_000_000, s2idle_us=0, wake=0, energy=30_000_000)
    post = snapshot(boot=1100.0, mono=902.0, zspa=1_050_000, s2idle_us=0, wake=1, energy=29_990_000)
    pre["smc"]["zSLa"], post["smc"]["zSLa"] = 2_000_000, 2_036_000  # 36 J over 100 s
    with_load = agent.sleep_summary(pre, post)
    assert with_load["sleep_w"] == with_load["load_w"] == pytest.approx(0.36)
    assert with_load["sleep_w_source"] == "smc_load"

    def without_load(snap: dict) -> dict:
        return snap | {"smc": {k: v for k, v in snap["smc"].items() if k != "zSLa"}}

    on_battery = agent.sleep_summary(without_load(pre), without_load(post))
    assert on_battery["sleep_w"] == on_battery["battery_w"]
    on_ac = agent.sleep_summary(without_load(pre) | {"bat": pre["bat"] | {"ac_online": 1}}, without_load(post))
    assert on_ac["sleep_w"] == on_ac["dcin_w"] == pytest.approx(0.5)
    no_battery = agent.sleep_summary(without_load(pre) | {"bat": {"ac_online": 0}}, without_load(post) | {"bat": {}})
    assert no_battery["sleep_w"] == no_battery["dcin_w"]


def test_standby_state_lives_in_run_dir() -> None:
    assert agent.STANDBY_STATE.parent == agent.RUN_DIR


def test_standby_counts_only_continuous_battery_time(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(agent, "STANDBY_STATE", state_file)
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: None)
    monkeypatch.setattr(agent, "wakeup_sources", lambda: {})
    power = {"capacity": 80, "ac_online": 1}
    monkeypatch.setattr(agent, "battery", lambda: dict(power))
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(agent.time, "time", lambda: clock["now"])
    spec = {"poweroff_below_pct": 10, "poweroff_after_s": 86_400}
    # Three days asleep on the charger...
    assert agent.standby_decide({"start_wall": clock["now"] - 3 * 86_400, "on_ac": True}, spec) == "resleep"
    assert json.loads(state_file.read_text())["asleep_since_wall"] == clock["now"]
    # ...then unplugged: two hours on battery is not 24 h asleep on battery.
    power["ac_online"] = 0
    clock["now"] += 7200
    assert agent.standby_decide({"start_wall": clock["now"] - 7200, "on_ac": False}, spec) == "resleep"
    # A poweroff decision clears the state so the next standby run starts fresh.
    power["capacity"] = 5
    clock["now"] += 7200
    assert agent.standby_decide({"start_wall": clock["now"] - 7200, "on_ac": False}, spec) == "poweroff"
    assert not state_file.exists()


def test_dark_wake_ignores_power_supply_but_not_user_input() -> None:
    assert agent.is_dark_wake({"m1power_waketimer"})
    assert agent.is_dark_wake({"m1power_waketimer", "macsmc-battery", "macsmc-ac", "alarmtimer"})
    assert not agent.is_dark_wake({"m1power_waketimer", "macsmc-input"})
    assert not agent.is_dark_wake({"m1power_waketimer", "macsmc-input.3.auto"})
    assert not agent.is_dark_wake({"macsmc-battery"})


def test_standby_act_rechecks_input_before_acting(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    state_file = tmp_path / "state.json"
    monkeypatch.setattr(agent, "STANDBY_STATE", state_file)
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(agent, "DEBUGFS", tmp_path / "debugfs")
    monkeypatch.setattr(agent, "graphical_session_active_since", lambda since: None)
    commands = []

    class Done:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args) or Done())
    sources = {"macsmc-input": 4}
    monkeypatch.setattr(agent, "wakeup_sources", lambda: dict(sources))
    state_file.write_text("{}")
    sources["macsmc-input"] = 5  # someone pressed a key after the decision
    record = agent.standby_act("poweroff", 4, 0, watch_s=0)
    assert record["outcome"] == "aborted" and not commands and not state_file.exists()
    assert agent.standby_act("resleep", 5, 0, watch_s=0)["outcome"] == "suspend"
    assert commands[-1] == ("systemctl", "suspend")
    assert [r["outcome"] for r in agent.ledger_records()] == ["aborted", "suspend"]


def test_sleep_test_marker_needs_a_live_python_pid(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import os
    import subprocess
    import sys

    mark = tmp_path / "sleep-test-active"
    monkeypatch.setattr(agent, "SLEEP_TEST_MARK", mark)
    assert not agent.sleep_test_active()
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    mark.write_text(str(dead.pid))
    assert not agent.sleep_test_active()
    mark.write_text(str(os.getpid()))
    assert agent.sleep_test_active() == agent.read(f"/proc/{os.getpid()}/comm", "").startswith("python")


def _ab_args(**overrides):
    import argparse

    base = dict(knob="x", a=None, b="new", pairs=1, settle=0, measure=0, seed=1, detail=False, keep_samples=False, out=None)
    return argparse.Namespace(**(base | overrides))


def _stub_ab_io(monkeypatch: pytest.MonkeyPatch, calls: list) -> None:
    monkeypatch.setattr(agent, "arm_failsafe", lambda seconds, tag: calls.append(("arm", tag)) or "unit-1")
    monkeypatch.setattr(agent, "disarm_failsafe", lambda unit: calls.append(("disarm", unit)))
    monkeypatch.setattr(agent, "Sampler", lambda: None)
    monkeypatch.setattr(agent, "measure_window", lambda *a, **kw: ([], {"n": 0}))
    monkeypatch.setattr(agent, "context_snapshot", lambda: {})
    monkeypatch.setattr(agent, "battery", lambda: {})
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)


def test_run_ab_keeps_journal_and_failsafe_when_restore_fails(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"x": "old"}
    _use_journal(monkeypatch, tmp_path, {"x": _FakeKnob("x", store, fail_on="old")})
    calls: list = []
    _stub_ab_io(monkeypatch, calls)
    with pytest.raises(RuntimeError):
        agent.run_ab(_ab_args())
    assert agent.journal_load() == {"x": "old"}
    assert ("disarm", "unit-1") not in calls


def test_run_ab_success_disarms_and_keeps_prior_journal_entry(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"x": "ctx"}
    _use_journal(monkeypatch, tmp_path, {"x": _FakeKnob("x", store)})
    (tmp_path / "journal.json").write_text(json.dumps({"x": "true-original"}))
    calls: list = []
    _stub_ab_io(monkeypatch, calls)
    assert agent.run_ab(_ab_args())["status"] == "complete"
    assert store["x"] == "ctx"
    assert agent.journal_load() == {"x": "true-original"}
    assert calls == [("arm", "ab"), ("disarm", "unit-1")]


def test_run_ab_does_not_touch_knob_when_failsafe_cannot_arm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"x": "old"}
    _use_journal(monkeypatch, tmp_path, {"x": _FakeKnob("x", store, fail_on="new")})
    calls: list = []
    _stub_ab_io(monkeypatch, calls)

    def refuse(seconds, tag):
        raise RuntimeError("systemd-run failed")

    monkeypatch.setattr(agent, "arm_failsafe", refuse)
    with pytest.raises(RuntimeError, match="systemd-run"):
        agent.run_ab(_ab_args())
    assert store["x"] == "old" and agent.journal_load() == {}


def test_arm_failsafe_uses_unique_units_and_checks_systemd_run(monkeypatch: pytest.MonkeyPatch) -> None:
    class Proc:
        def __init__(self, code: int) -> None:
            self.returncode, self.stderr = code, "unit exists"

    calls = []
    code = {"value": 0}
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: calls.append(args) or Proc(code["value"] if args[0] == "systemd-run" else 0))
    first, second = agent.arm_failsafe(10, "ab"), agent.arm_failsafe(10, "ab")
    assert first != second
    code["value"] = 1
    with pytest.raises(RuntimeError, match="failsafe"):
        agent.arm_failsafe(10, "ab")


def test_run_batch_restores_only_the_failed_jobs_knobs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import argparse

    store = {"display": "on", "x": "old"}
    _use_journal(monkeypatch, tmp_path, {"display": _FakeKnob("display", store), "x": _FakeKnob("x", store)})
    agent.journal_set("display", "off")  # context for the whole batch

    def failing_ab(ns):
        agent.journal_set("x", "new")
        raise RuntimeError("iw failed")

    monkeypatch.setattr(agent, "run_ab", failing_ab)
    spec = tmp_path / "jobs.json"
    spec.write_text(json.dumps([{"kind": "ab", "knob": "x", "b": "new"}]))
    out = tmp_path / "out.json"
    agent.run_batch(argparse.Namespace(spec=str(spec), out=str(out)))
    assert store == {"display": "off", "x": "old"}
    assert agent.journal_load() == {"display": "on"}
    job = json.loads(out.read_text())["jobs"][0]
    assert job["error"] == "iw failed" and job["restore"]["restored"] == {"x": "old"}


def test_tune_apply_refuses_network_killers_and_unpersistable(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"wifi": "on", "display": "on"}
    knobs = {"wifi": _FakeKnob("wifi", store, kills_network=True), "display": _FakeKnob("display", store, persistable=False)}
    _use_journal(monkeypatch, tmp_path, knobs)
    with pytest.raises(SystemExit, match="kills the network"):
        agent.tune_apply(json.dumps({"knobs": {"wifi": "off"}}))
    with pytest.raises(SystemExit, match="cannot be persisted"):
        agent.tune_apply(json.dumps({"knobs": {"display": "off"}}))
    assert not (tmp_path / "tune.json").exists() and store == {"wifi": "on", "display": "on"}


def test_tune_run_skips_network_killers_from_old_specs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"wifi": "on"}
    _use_journal(monkeypatch, tmp_path, {"wifi": _FakeKnob("wifi", store, kills_network=True)})
    (tmp_path / "tune.json").write_text(json.dumps({"knobs": {"wifi": "off"}}))
    result = agent.tune_run()
    assert store["wifi"] == "on" and "wifi" in result["errors"]


def test_knob_command_arms_failsafe_for_network_killers(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"wifi": "on", "bt": "on"}
    _use_journal(monkeypatch, tmp_path, {"wifi": _FakeKnob("wifi", store, kills_network=True), "bt": _FakeKnob("bt", store)})
    armed = []
    monkeypatch.setattr(agent, "arm_failsafe", lambda seconds, tag: armed.append(seconds) or "unit")
    out = agent.set_knob_cmd("wifi", "off")
    assert out["failsafe_s"] == 300 and armed == [300] and store["wifi"] == "off"
    assert "failsafe_s" not in agent.set_knob_cmd("wifi", "off")  # already off: nothing changes
    assert "failsafe_s" not in agent.set_knob_cmd("bt", "off")
    assert armed == [300]


def test_tune_revert_keeps_failed_knobs_installed(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"governor": "powersave", "aspm": "powersupersave"}
    knobs = {"governor": _FakeKnob("governor", store, fail_on="mixed"), "aspm": _FakeKnob("aspm", store)}
    _use_journal(monkeypatch, tmp_path, knobs)
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    spec = {"knobs": {"governor": "powersave", "aspm": "powersupersave"}, "baseline": {"governor": "mixed", "aspm": "default"}}
    (tmp_path / "tune.json").write_text(json.dumps(spec))
    result = agent.tune_revert()
    assert result["reverted"] == {"aspm": "default"} and "governor" in result["errors"]
    kept = json.loads((tmp_path / "tune.json").read_text())
    assert kept["knobs"] == {"governor": "powersave"} and kept["baseline"] == {"governor": "mixed"}
    assert not any("disable" in args for args in commands)


def test_restore_keeps_runtime_pm_baseline_unless_runtime_pm_restored(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"x": "old", "runtime_pm": "on:3"}
    _use_journal(monkeypatch, tmp_path, {"x": _FakeKnob("x", store), "runtime_pm": _FakeKnob("runtime_pm", store)})
    save = tmp_path / "runtime_pm_baseline.json"
    save.write_text("{}")
    agent.journal_set("x", "new")
    agent.restore_all()
    assert save.exists()
    agent.journal_set("runtime_pm", "auto")
    (tmp_path / "tune.json").write_text(json.dumps({"knobs": {"runtime_pm": "auto"}}))
    agent.restore_all()
    assert save.exists()  # a persisted tune still needs it for `tune revert`
    (tmp_path / "tune.json").unlink()
    agent.journal_set("runtime_pm", "auto")
    agent.restore_all()
    assert not save.exists()
    assert agent.RuntimePmKnob.SAVE.parent == tmp_path


def test_runtime_pm_baseline_default_is_persistent() -> None:
    assert agent.RuntimePmKnob.SAVE.parent == agent.STATE_DIR


def test_cpu_policies_never_swap_names_on_unreadable_max(monkeypatch: pytest.MonkeyPatch) -> None:
    root = "/sys/devices/system/cpu/cpufreq"
    files = {f"{root}/policy0/related_cpus": "0 1 2 3", f"{root}/policy4/related_cpus": "4 5 6 7"}

    def fake_read(path, default=None):
        return files.get(str(path), default)

    monkeypatch.setattr(agent.glob, "glob", lambda pattern: [f"{root}/policy4", f"{root}/policy0"])
    monkeypatch.setattr(agent, "read", fake_read)
    # P policy inactive: cpuinfo_max_freq is EBUSY, only the frequency table answers.
    files[f"{root}/policy0/cpuinfo_max_freq"] = "2064000"
    files[f"{root}/policy4/scaling_available_frequencies"] = "600000 3204000"
    policies = agent.cpu_policies()
    assert policies["p"]["policy"] == "policy4" and policies["e"]["policy"] == "policy0"
    # Nothing readable for the P policy: fall back to policy order.
    del files[f"{root}/policy4/scaling_available_frequencies"]
    policies = agent.cpu_policies()
    assert policies["p"]["cpus"] == [4, 5, 6, 7] and policies["e"]["cpus"] == [0, 1, 2, 3]


def test_smc_keeps_its_own_fd_and_rewinds(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "DEBUGFS", tmp_path)
    watch = tmp_path / "smc_watch"
    watch.write_text("")
    smc = agent.Smc(["PSTR", "PHPC"])
    assert watch.read_text() == "PSTR PHPC"
    watch.write_text(f"BOOT 5\nMONO 4\nPSTR flt  4 85 {flt(2.0)}\n")
    assert smc.read()["PSTR"] == pytest.approx(2.0)
    assert smc.read()["BOOT"] == 5  # every read starts again at offset 0
    smc.close()


def test_watch_user_input_sees_key_events_and_ignores_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    import os as _os

    read_end, write_end = _os.pipe()
    monkeypatch.setattr(agent.glob, "glob", lambda pattern: ["/dev/input/event-test"])
    monkeypatch.setattr(agent.os, "open", lambda path, flags: _os.dup(read_end))
    sync = agent.INPUT_EVENT.pack(0, 0, 0, 0, 0)  # EV_SYN: not a person
    _os.write(write_end, sync)
    assert agent.watch_user_input(0.2) is None
    _os.write(write_end, agent.INPUT_EVENT.pack(0, 0, 1, 30, 1))  # EV_KEY KEY_A down
    assert "key event (code 30)" in agent.watch_user_input(1.0)
    _os.close(read_end)
    _os.close(write_end)


def test_full_restore_disarms_leftover_failsafes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "JOURNAL", tmp_path / "journal.json")
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    values = {"x": "b"}

    class Fake(agent.Knob):
        name = "x"

        def get(self):
            return values["x"]

        def set(self, value):
            values["x"] = value

    monkeypatch.setattr(agent, "get_knob", lambda name: Fake())
    (tmp_path / "journal.json").write_text('{"x": "a"}')
    agent.restore_all()
    assert values["x"] == "a"
    assert ("systemctl", "stop", "m1power-failsafe-*.timer") in commands


def test_tune_sleep_knobs_apply_to_every_suspend_and_standby_only_outside_tests(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    spec_file = tmp_path / "tune.json"
    monkeypatch.setattr(agent, "TUNE_SPEC", spec_file)
    spec_file.write_text(json.dumps({"knobs": {"aspm": "powersupersave"}, "sleep_knobs": {"aspm": "default"}}))
    standby = {"sleep_knobs": {"bt": "off"}}
    assert agent.sleep_knobs_for(standby, test_running=True) == {"aspm": "default"}
    assert agent.sleep_knobs_for(standby, test_running=False) == {"aspm": "default", "bt": "off"}
    assert agent.sleep_knobs_for(None, test_running=False) == {"aspm": "default"}


def test_sleep_radio_off_is_restored_by_resume_or_next_boot(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "SLEEP_RADIOS", tmp_path / "radios.json")
    monkeypatch.setattr(agent, "SLEEP_KNOBS_SAVED", tmp_path / "saved.json")
    radio = {"wifi": "on"}

    class Wifi(agent.Knob):
        name = "wifi"
        kills_network = True

        def get(self):
            return radio["wifi"]

        def set(self, value):
            radio["wifi"] = value

    monkeypatch.setattr(agent, "get_knob", lambda name: Wifi())
    agent.apply_sleep_knobs({"wifi": "off"})
    assert radio["wifi"] == "off" and (tmp_path / "radios.json").exists()
    # The resume hook never ran (crash or power loss while asleep): boot restores it.
    (tmp_path / "saved.json").unlink()
    assert agent.restore_sleep_radios() == {"wifi": "on"}
    assert radio["wifi"] == "on" and not (tmp_path / "radios.json").exists()
    # A radio the user turned off themselves is left alone.
    radio["wifi"] = "off"
    assert agent.restore_sleep_radios() == {}
    assert radio["wifi"] == "off"


def test_battery_standby_uses_load_accumulator_not_gauge() -> None:
    entries = [
        {"kind": "sleep", "slept_s": 600, "on_ac": False, "sleep_w": 0.615, "battery_w": 0.476, "dcin_w": 0.0},
        {"kind": "sleep", "slept_s": 600, "on_ac": False, "sleep_w": 0.605, "battery_w": 0.70, "dcin_w": 0.0},
    ]
    summary = analysis.summarize_sleeps(entries)
    assert summary["battery_w_weighted"] == pytest.approx(0.61)


def test_standby_stays_awake_after_max_dark_wakes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "STANDBY_STATE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(agent, "battery", lambda: {"capacity": 80, "ac_online": 0})
    monkeypatch.setattr(agent, "wakeup_sources", lambda: {})
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    spec = {"poweroff_below_pct": 10, "max_dark_wakes": 1}
    assert agent.standby_decide({"start_wall": 0}, spec) == "stay"
    assert commands == [] and not (tmp_path / "state.json").exists()


IDLE_LAB_AGENT = (
    # pid, ppid, comm, cmdline, age in seconds
    ("861", "1", "lab-agent", "/usr/local/bin/lab-agent run", 9000),
    ("891", "861", "busctl", "busctl monitor --match type=signal,member=PrepareForSleep", 9000),
    ("5236", "861", "systemd-inhibit", "systemd-inhibit --what=sleep --who=lab-agent --mode=delay sleep infinity", 9000),
    ("5237", "5236", "sleep", "sleep infinity", 9000),
)


def _fake_lab(monkeypatch: pytest.MonkeyPatch, tmp_path, *, cmdline="root=/dev/x quiet", pm_test="[none] core devices",
              procs=IDLE_LAB_AGENT, job_files=False, stale_job_files=False) -> None:
    uptime = 10000.0
    hz = agent.os.sysconf("SC_CLK_TCK")
    files = {"/proc/cmdline": cmdline, "/sys/power/pm_test": pm_test, "/proc/uptime": f"{uptime} 1.0",
             "/proc/stat": "cpu 1 2 3\nbtime 1700000000\n"}
    for pid, ppid, comm, line, age in procs:
        start_ticks = int((uptime - age) * hz)
        fields = ["S", ppid] + ["0"] * 17 + [str(start_ticks)]
        files[f"/proc/{pid}/comm"] = comm
        files[f"/proc/{pid}/cmdline"] = line.replace(" ", "\0")
        files[f"/proc/{pid}/stat"] = f"{pid} ({comm}) " + " ".join(fields)
    real_read = agent.read
    monkeypatch.setattr(agent, "read", lambda path, default=None: files.get(str(path), real_read(path, default)))
    cgroup = tmp_path / "cgroup.procs"
    cgroup.write_text("\n".join(p[0] for p in procs))
    monkeypatch.setattr(agent, "LAB_AGENT_CGROUP", cgroup)
    maclab = tmp_path / "maclab"
    (maclab / "out").mkdir(parents=True)
    (maclab / "jobs").mkdir()
    if job_files:
        (maclab / "out" / "c123").mkdir()
        agent.os.utime(maclab / "out" / "c123", (1_800_000_000, 1_800_000_000))  # after btime
    if stale_job_files:
        (maclab / "out" / "c-old").mkdir()
        agent.os.utime(maclab / "out" / "c-old", (1_600_000_000, 1_600_000_000))  # before btime
    monkeypatch.setattr(agent, "MACLAB_DIR", maclab)


def test_lab_activity_idle_lab_agent_is_not_activity(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _fake_lab(monkeypatch, tmp_path)
    assert agent.lab_activity() is None
    assert not agent.lab_boot()


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"cmdline": "root=/dev/x maclab.lab_boot=1 maclab.job=j1105"}, "Lab boot"),
        ({"pm_test": "none core processors platform [devices] freezer"}, "pm_test=devices"),
        ({"job_files": True}, "job files"),
        ({"procs": IDLE_LAB_AGENT + (("999", "861", "bash", "bash /var/lib/maclab/test.sh", 30),)}, "lab-agent is running bash"),
        ({"procs": IDLE_LAB_AGENT + (("998", "861", "systemd-inhibit", "systemd-inhibit --what=sleep --who=lab-agent --mode=block sleep infinity", 30),)}, "block inhibitor"),
    ],
)
def test_lab_activity_detects_lab_work(monkeypatch: pytest.MonkeyPatch, tmp_path, kwargs, expected) -> None:
    _fake_lab(monkeypatch, tmp_path, **kwargs)
    assert expected in agent.lab_activity()


def test_experiments_refuse_during_lab_work_unless_forced(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _fake_lab(monkeypatch, tmp_path, procs=IDLE_LAB_AGENT + (("999", "861", "bash", "bash -c true", 30),))
    with pytest.raises(SystemExit, match="lab may be using"):
        agent.refuse_during_lab("an A/B experiment")
    agent.refuse_during_lab("an A/B experiment", force=True)


def test_standby_stays_awake_when_the_lab_is_working(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "STANDBY_STATE", tmp_path / "state.json")
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    battery = {"capacity": 50, "ac_online": 0}
    monkeypatch.setattr(agent, "battery", lambda: dict(battery))
    monkeypatch.setattr(agent, "wakeup_sources", lambda: {})
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    monkeypatch.setattr(agent, "lab_activity", lambda: "lab-agent is running bash (pid 999)")
    # The lab is working: never put the Mac back to sleep under it...
    assert agent.standby_decide({"start_wall": 0}, {"poweroff_below_pct": 10}) == "stay"
    assert commands == []
    assert agent.ledger_records()[-1]["reason"].startswith("lab-agent is running")
    # ...but a critical battery still powers off cleanly rather than going flat.
    battery["capacity"] = 5
    assert agent.standby_decide({"start_wall": 0}, {"poweroff_below_pct": 10}) == "poweroff"


def test_pm_test_cycles_are_not_counted_as_sleeps() -> None:
    entries = [
        {"kind": "sleep", "slept_s": 600, "sleep_w": 0.6, "pm_test": "none"},
        {"kind": "sleep", "slept_s": 600, "sleep_w": 9.9, "pm_test": "devices"},
    ]
    assert analysis.summarize_sleeps(entries)["sleep_w_weighted"] == pytest.approx(0.6)


def test_kmod_skips_lab_boots(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "DEBUGFS", tmp_path / "debugfs")
    monkeypatch.setattr(agent, "lab_boot", lambda: True)
    assert agent.kmod_ensure() == {"loaded": False, "skipped": "maclab Lab boot"}


def test_lab_activity_ignores_stale_job_dirs_and_short_probes(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    probe = ("997", "861", "systemctl", "systemctl is-system-running", 0.05)
    _fake_lab(monkeypatch, tmp_path, stale_job_files=True, procs=IDLE_LAB_AGENT + (probe,))
    assert agent.lab_activity() is None


def test_tune_run_is_a_no_op_on_lab_boots(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "lab_boot", lambda: True)
    assert agent.tune_run()["skipped"] == "maclab Lab boot"


def test_hook_is_passive_during_pm_test_cycles(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "RUN_DIR", tmp_path)
    monkeypatch.setattr(agent, "pm_test_mode", lambda: "devices")
    monkeypatch.setattr(agent, "standby_spec", lambda: {"check_every_s": 300, "sleep_knobs": {"bt": "off"}})
    applied = []
    monkeypatch.setattr(agent, "apply_sleep_knobs", lambda knobs: applied.append(knobs))
    monkeypatch.setattr(agent, "sleep_snapshot", lambda: {"boot": 1.0, "mono": 1.0, "wall": 1.0})
    armed = []
    monkeypatch.setattr(agent, "write", lambda path, value: armed.append((str(path), value)))
    agent.run_hook("pre", "suspend")
    assert applied == [] and not any("waketimer" in p for p, _ in armed)


def test_ab_stops_when_the_lab_arrives_and_restores_the_knob(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import argparse as _argparse

    monkeypatch.setattr(agent, "JOURNAL", tmp_path / "journal.json")
    values = {"x": "a"}

    class Fake(agent.Knob):
        name = "x"

        def get(self):
            return values["x"]

        def set(self, value):
            values["x"] = value

    monkeypatch.setattr(agent, "get_knob", lambda name: Fake())
    monkeypatch.setattr(agent, "arm_failsafe", lambda seconds, tag: "unit")
    monkeypatch.setattr(agent, "disarm_failsafe", lambda unit: None)
    monkeypatch.setattr(agent, "Sampler", lambda: object())
    monkeypatch.setattr(agent, "battery", lambda: {})
    monkeypatch.setattr(agent, "context_snapshot", lambda: {})
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    calls = {"n": 0}

    def measure(sampler, seconds, with_detail=True):
        return [], {"sys_w": 1.0}

    monkeypatch.setattr(agent, "measure_window", measure)

    def activity():
        calls["n"] += 1
        return None if calls["n"] <= 3 else "lab-agent is running bash (pid 9)"

    monkeypatch.setattr(agent, "lab_activity", activity)
    ns = _argparse.Namespace(knob="x", a=None, b="b", pairs=4, settle=0, measure=0, seed=1, detail=False,
                             keep_samples=False, out=None, force=False)
    result = agent.run_ab(ns)
    assert result["aborted"].startswith("lab:")
    assert len(result["blocks"]) == 1 and values["x"] == "a"


def test_guard_ignores_timer_wakes_it_did_not_arm(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "RUN_DIR", tmp_path)
    monkeypatch.setattr(agent, "LEDGER", tmp_path / "ledger.jsonl")
    monkeypatch.setattr(agent, "STATE_DIR", tmp_path)
    monkeypatch.setattr(agent, "SLEEP_TEST_MARK", tmp_path / "no-test")
    monkeypatch.setattr(agent, "TUNE_SPEC", tmp_path / "no-tune.json")
    monkeypatch.setattr(agent, "standby_spec", lambda: {"check_every_s": 7200})
    monkeypatch.setattr(agent, "waketimer_armed", lambda: True)  # someone else (a probe) armed it
    monkeypatch.setattr(agent, "apply_sleep_knobs", lambda knobs: None)
    monkeypatch.setattr(agent, "restore_sleep_knobs", lambda: None)
    monkeypatch.setattr(agent, "sleep_snapshot", lambda: {"boot": 100.0, "mono": 50.0, "wall": 100.0})
    monkeypatch.setattr(agent, "sleep_summary", lambda pre, post: {"wake_sources": [["m1power_waketimer", 1]], "start_wall": 0})
    decided = []
    monkeypatch.setattr(agent, "standby_decide", lambda summary, spec: decided.append(summary))
    agent.run_hook("pre", "suspend")
    agent.run_hook("post", "suspend")
    assert decided == []


@pytest.mark.parametrize(("us", "reg", "actual"), [(6, 0x18, 6), (7, 0x20, 8), (70, 0x39, 70), (200, 0xA1, 200), (400, 0x22, 400), (65, 0x39, 70)])
def test_l1ss_tpoweron_encoding(us, reg, actual) -> None:
    # The finest scale that fits is used, rounding up (65 us -> 7 x 10 us).
    assert agent.L1ssTimingKnob.encode(us) == (reg, actual)
    assert agent.L1ssTimingKnob.decode(reg) == actual


def test_pcielink_knob_name_parsing() -> None:
    knob = agent.get_knob("pcielink:wifi:l1_1_aspm")
    assert isinstance(knob, agent.PcieLinkKnob)
    assert (knob.device, knob.attr) == ("wifi", "l1_1_aspm")


@pytest.mark.parametrize(("us", "reg"), [(0, 0x0000), (1, 0x03E8), (3145, 0x0C60), (100, 0x0862)])
def test_ltr_latency_encoding(us, reg) -> None:
    assert agent.LtrMaxLatencyKnob.encode(us) == reg
    assert agent.LtrMaxLatencyKnob.decode(reg) >= us


def test_pairs_spanning_a_network_switch_are_set_aside() -> None:
    home, hotspot = "aa:aa:aa:aa:aa:aa Home", "bb:bb:bb:bb:bb:bb iPhone"

    def block(a, b, ap_a=(home, home), ap_b=(home, home)):
        return {"a": {"sys_w": a, "ap_start": ap_a[0], "ap_end": ap_a[1]},
                "b": {"sys_w": b, "ap_start": ap_b[0], "ap_end": ap_b[1]}}

    result = {"knob": "x", "a": "0", "b": "1", "blocks": [
        block(1.12, 1.12), block(1.12, 1.12), block(1.12, 0.83, ap_b=(home, hotspot)), block(1.11, 1.12)]}
    analyzed = analysis.analyze_ab(result)
    assert analyzed["pairs"] == 3 and analyzed["excluded_pairs"] == 1
    assert "set aside" in analyzed["verdict"]


def test_pcielink_knob_restores_by_clearing_not_writing_zero(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "JOURNAL", tmp_path / "journal.json")
    writes = []
    values = {"attr": "0", "policy": "[default] performance powersave powersupersave"}
    knob = agent.PcieLinkKnob("wifi", "l1_2_aspm")
    monkeypatch.setattr(knob, "_path", lambda: "ATTR")
    monkeypatch.setattr(agent, "get_knob", lambda name: knob)
    monkeypatch.setattr(agent, "read", lambda path, default=None: values["attr"] if path == "ATTR" else values["policy"])
    monkeypatch.setattr(agent, "write", lambda path, value: writes.append((str(path), str(value))))
    agent.journal_set("pcielink:wifi:l1_2_aspm", "1")
    assert json.loads((tmp_path / "journal.json").read_text()) == {"pcielink:wifi:l1_2_aspm": "clear"}
    agent.restore_all()
    assert ("ATTR", "1") in writes and ("ATTR", "0") not in writes
    assert writes[-1] == ("/sys/module/pcie_aspm/parameters/policy", "default")


def test_wakeup_knob_matches_devices_by_path(monkeypatch: pytest.MonkeyPatch) -> None:
    paths = ["/sys/devices/platform/x/0-0038/power_supply/tps6598x-source-psy-0-0038/power/wakeup",
             "/sys/devices/platform/x/0-003f/power_supply/tps6598x-source-psy-0-003f/power/wakeup",
             "/sys/devices/platform/soc/23e400000.smc/macsmc-input/power/wakeup"]
    state = dict.fromkeys(paths, "enabled")
    monkeypatch.setattr(agent, "sysfs_power_files", lambda name: paths)
    monkeypatch.setattr(agent, "read", lambda path, default=None: state[path])
    monkeypatch.setattr(agent, "write", lambda path, value: state.__setitem__(path, value))
    knob = agent.get_knob("wakeup:tps6598x")
    assert knob.get() == "enabled"
    knob.set("disabled")
    assert [state[p] for p in paths] == ["disabled", "disabled", "enabled"]


def test_sleep_knobs_save_the_restore_value(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent, "SLEEP_KNOBS_SAVED", tmp_path / "saved.json")
    monkeypatch.setattr(agent, "SLEEP_RADIOS", tmp_path / "radios.json")
    knob = agent.PcieLinkKnob("wifi", "l1_2_aspm")
    sets = []
    monkeypatch.setattr(knob, "get", lambda: "1")
    monkeypatch.setattr(knob, "set", lambda value: sets.append(value))
    monkeypatch.setattr(agent, "get_knob", lambda name: knob)
    agent.apply_sleep_knobs({"pcielink:wifi:l1_2_aspm": "0"})
    assert json.loads((tmp_path / "saved.json").read_text()) == {"pcielink:wifi:l1_2_aspm": "clear"}
    agent.restore_sleep_knobs()
    assert sets == ["0", "clear"]


def test_wifi_power_save_persists_through_networkmanager(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    conf_d = tmp_path / "conf.d"
    conf_d.mkdir()
    (conf_d / "omarchy-wifi-powersave.conf").write_text("[connection]\nwifi.powersave = 2\n")
    dropin = conf_d / "zz-m1power-wifi-powersave.conf"
    monkeypatch.setattr(agent.WifiPowerSaveKnob, "NM_DROPIN", dropin)
    commands = []
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: commands.append(args))
    knob = agent.WifiPowerSaveKnob()
    assert knob.persist("on") == f"wrote {dropin}"
    assert "wifi.powersave = 3" in dropin.read_text()
    # NetworkManager reads conf.d in name order and the later file wins.
    assert sorted(p.name for p in conf_d.iterdir())[-1] == dropin.name
    assert commands == [("nmcli", "general", "reload", "conf")]
    assert knob.persist("on") is None and len(commands) == 1  # unchanged: no rewrite, no reload
    assert knob.unpersist() == f"removed {dropin}" and not dropin.exists()
    assert knob.unpersist() is None


def test_wifi_power_save_persist_is_a_no_op_without_networkmanager(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(agent.WifiPowerSaveKnob, "NM_DROPIN", tmp_path / "absent" / "x.conf")
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: pytest.fail("no NetworkManager: nothing to reload"))
    assert agent.WifiPowerSaveKnob().persist("on") is None


class _PersistingKnob(_FakeKnob):
    def __init__(self, name: str, store: dict, log: list) -> None:
        super().__init__(name, store)
        self.log = log

    def persist(self, value):
        self.log.append(("persist", self.name, value))
        return "noted"

    def unpersist(self):
        self.log.append(("unpersist", self.name))


def test_tune_run_persists_and_revert_unpersists(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store, log = {"wifi_ps": "off", "aspm": "default"}, []
    knobs = {"wifi_ps": _PersistingKnob("wifi_ps", store, log), "aspm": _PersistingKnob("aspm", store, log)}
    _use_journal(monkeypatch, tmp_path, knobs)
    monkeypatch.setattr(agent, "sh", lambda *args, **kw: None)
    monkeypatch.setattr(agent, "write_tune_unit", lambda: None)
    monkeypatch.setattr(agent, "lab_boot", lambda: False)
    monkeypatch.setattr(agent, "restore_sleep_radios", lambda: {})
    result = agent.tune_apply(json.dumps({"knobs": {"wifi_ps": "on"}}))
    assert store["wifi_ps"] == "on" and result["persisted"] == {"wifi_ps": "noted"}
    assert ("persist", "wifi_ps", "on") in log
    # A new spec without wifi_ps undoes its persistence.
    agent.tune_apply(json.dumps({"knobs": {"aspm": "powersupersave"}}))
    assert ("unpersist", "wifi_ps") in log
    log.clear()
    agent.tune_revert()
    assert log == [("unpersist", "aspm")]


def test_tune_drift_reports_lapsed_knobs(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    store = {"wifi_ps": "off", "aspm": "powersupersave"}
    _use_journal(monkeypatch, tmp_path, {"wifi_ps": _FakeKnob("wifi_ps", store), "aspm": _FakeKnob("aspm", store)})
    monkeypatch.setattr(agent, "lab_boot", lambda: False)
    assert agent.tune_drift() == {}
    (tmp_path / "tune.json").write_text(json.dumps({"knobs": {"wifi_ps": "on", "aspm": "powersupersave"}}))
    assert agent.tune_drift() == {"wifi_ps": {"want": "on", "now": "off"}}


def test_ltr_knob_matches_hex_and_microsecond_spellings(monkeypatch: pytest.MonkeyPatch) -> None:
    knob = agent.LtrMaxLatencyKnob()
    monkeypatch.setattr(knob, "get", lambda: f"{agent.LtrMaxLatencyKnob.decode(0x1008):g}")
    assert knob.matches("0x1008") and knob.matches(knob.get()) and not knob.matches("0x1009")


def test_wifi_ps_timeout_reads_the_firmware_iovar(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_sh(*args, **kw):
        calls.append(args)
        return agent.argparse.Namespace(stdout="vendor response: 14 00 02 00 d0 07 00 00 73 6c 65 65 70 5f 72 65 \nvendor response: 00 00\n", returncode=0)

    monkeypatch.setattr(agent, "sh", fake_sh)
    monkeypatch.setattr(agent.WifiPowerSaveKnob, "_iface", lambda self: "wlan0")
    assert agent.WifiPsTimeoutKnob().get() == "2000"
    args = calls[0]
    assert args[:5] == ("iw", "dev", "wlan0", "vendor", "recv")
    payload = bytes(int(x, 16) for x in args[7:])
    assert payload[:4] == (262).to_bytes(4, "little") and payload[20:] == b"pm2_sleep_ret\0\0\0"
    with pytest.raises(ValueError):
        agent.WifiPsTimeoutKnob().set("0")


def test_display_knob_survives_a_toggling_dpms_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    state = {"dpms": True}
    calls = []

    def fake_hyprctl(*args):
        calls.append(args)
        if args[:2] == ("monitors", "all"):
            return json.dumps([{"dpmsStatus": state["dpms"], "disabled": False}])
        if args == ("dispatch", "dpms", "off") or args == ("dispatch", "dpms", "on"):
            state["dpms"] = not state["dpms"]  # Hyprland 0.56: old form toggles
            return "ok"
        if args[0] == "dispatch" and args[1].startswith("hl.dsp.dpms("):
            state["dpms"] = '"on"' in args[1]
            return "ok"
        raise AssertionError(args)

    monkeypatch.setattr(agent, "hyprctl", fake_hyprctl)
    monkeypatch.setattr(agent.time, "sleep", lambda s: None)
    knob = agent.DisplayKnob()
    for value in ["off", "off", "on", "on", "off"]:
        knob.set(value)
        assert knob.get() == value


def test_brcmf_dcmd_builds_iovar_get_and_set(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_sh(*args, **kw):
        calls.append(args)
        return agent.argparse.Namespace(stdout="vendor response: 10 00 02 00 03 00 00 00 \n", returncode=0)

    monkeypatch.setattr(agent, "sh", fake_sh)
    monkeypatch.setattr(agent.WifiPowerSaveKnob, "_iface", lambda self: "wlan0")
    knob = agent.WifiFirmwareIntKnob("wifi_bcn_li_dtim", "", iovar="bcn_li_dtim")
    assert knob.get() == "3"
    payload = bytes(int(x, 16) for x in calls[0][7:])
    assert payload[:20] == bytes.fromhex("06010000" "10000000" "14000000" "00000000" "00000000")
    assert payload[20:32] == b"bcn_li_dtim\0"
    knob.set("3")
    payload = bytes(int(x, 16) for x in calls[1][7:])
    assert calls[1][4] == "send"
    # matches the hand-checked WLC_SET_VAR string for bcn_li_dtim=3
    assert payload.hex() == "07010000" "10000000" "14000000" "01000000" "00000000" + b"bcn_li_dtim\0".hex() + "03000000"
    pm = agent.WifiFirmwareIntKnob("wifi_pm", "", ioctl=(85, 86))
    pm.set("1")
    assert bytes(int(x, 16) for x in calls[2][7:]).hex() == "56000000" "04000000" "14000000" "01000000" "00000000" "01000000"
