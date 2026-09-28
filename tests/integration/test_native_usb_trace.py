"""Synthetic exact-format Asahi trace records; never access host tracefs."""

import importlib.util
import os
from pathlib import Path
import time

import pytest


SPEC = importlib.util.spec_from_file_location(
    "native_usb_trace_test", Path(__file__).resolve().parents[2] / "target/native_usb_trace.py")
assert SPEC and SPEC.loader
trace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trace)


def record(event, body):
    return f"     irq/47-dwc3-128 [002] d..2. 1.000001: {event}: {body}\n".encode()


SETUP = record("dwc3_ctrl_req", "0x0000000382280000: Set Configuration(Config = 1)")
OTHER_SETUP = record("dwc3_ctrl_req", "0x0000000382280000: Get String Descriptor(Index = 4, Length = 255)")
ACM0 = record("m1lab_acm_enter", "(acm_set_alt+0x0/0x198 [usb_f_acm]) intf=0")
ACM1 = record("m1lab_acm_enter", "(acm_set_alt+0x0/0x198 [usb_f_acm]) intf=1")
ACM_RETURN = record("m1lab_acm_return", "(set_config+0x1c0/0x2e0 [libcomposite] <- acm_set_alt [usb_f_acm]) ret=0")
SERIAL = record("m1lab_serial_enter", "(gserial_connect+0x0/0x18c [u_serial])")
SERIAL_RETURN = record("m1lab_serial_return", "(acm_set_alt+0x140/0x198 [usb_f_acm] <- gserial_connect [u_serial]) ret=0")
TRB_BODY = "0x0000000382280000: ep0in: trb 00000000ca123456 (E0:D0) buf 0000000080020000 size 0 ctrl 00000c23 sofn 00000000 (HLcs:SC:status2)"
STATUS_ARGS = "dwc=0xffff800080060000 dep=0xffff800080068000"
STATUS_ENTER = record("m1lab_status_enter", "(__dwc3_ep0_do_control_status+0x0/0xe8 [dwc3]) " + STATUS_ARGS)
STATUS_RETURN = record("m1lab_status_return", "(dwc3_ep0_interrupt+0x378/0xe90 [dwc3] <- __dwc3_ep0_do_control_status [dwc3]) " + STATUS_ARGS)
def io_event(event, offset, value, *, controller="0x0000000382280000", irq=False):
    data = record(event, f"{controller}: addr 00000000dead1234 offset {offset:04x} value {value:08x}")
    return data.replace(b"irq/47-dwc3-128 [002]", b"swapper/0-0 [000]") if irq else data


COUNT_READ = io_event("dwc3_readl", 0xc40c, 4, irq=True)
MASK = io_event("dwc3_writel", 0xc408, 0x80001000, irq=True)
ACK = io_event("dwc3_writel", 0xc40c, 4, irq=True)
UNMASK = io_event("dwc3_writel", 0xc408, 4096)
BATCH = COUNT_READ + MASK + ACK
STATUS_NRDY = record("dwc3_event", "0x0000000382280000: event (000020c2): ep0in: Transfer Not Ready [00000000] (Not Active) [Status Phase]")
PREPARE = BATCH + STATUS_NRDY + STATUS_ENTER + record("dwc3_prepare_trb", TRB_BODY)
COMMAND = record("dwc3_gadget_ep_cmd", "0x0000000382280000: ep0in: cmd 'Start Transfer' [406] params 00000000 80020000 00000000 --> status: Successful")
COMPLETE = record("dwc3_complete_trb", TRB_BODY.replace("ep0in", "ep0out"))
ACM_SUCCESS = ACM0 + ACM_RETURN + ACM1 + SERIAL + SERIAL_RETURN + ACM_RETURN


@pytest.fixture
def fake_kernel(tmp_path, monkeypatch):
    root = tmp_path / "tracing"
    root.mkdir()
    (root / "instances").mkdir()
    (root / "kprobe_events").write_text("p:unrelated/other some_function\n")
    (root / "kprobe_profile").write_text("".join(f"{name} 0 0\n" for name in trace.PROBES))
    instance = root / "instances/m1lab"
    real_mkdir = Path.mkdir

    def mkdir(path, *args, **kwargs):
        result = real_mkdir(path, *args, **kwargs)
        if path == instance and not kwargs.get("exist_ok"):
            files = {
                "tracing_on": "0\n", "current_tracer": "nop\n", "trace_clock": "local\n",
                "buffer_size_kb": "0\n", "trace_pipe": "", "events/enable": "0\n",
                "per_cpu/cpu0/stats": "entries: 0\noverrun: 0\ncommit overrun: 0\ndropped events: 0\n",
            }
            for name in trace.PROBES:
                files[f"events/{trace.GROUP}/{name}/enable"] = "0\n"
            for name in trace.DWC3_EVENTS:
                files[f"events/dwc3/{name}/enable"] = "0\n"
                files[f"events/dwc3/{name}/filter"] = ""
            for name, data in files.items():
                dest = instance / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(data)
        return result

    monkeypatch.setattr(Path, "mkdir", mkdir)
    monitor = trace.NativeUsbTrace(root)
    yield monitor
    monitor.close()


def armed(monitor, data=b""):
    monitor.start(time.monotonic() + 10)
    assert monitor.validity == 1
    (monitor.instance / "trace_pipe").write_bytes(data)
    return monitor


def test_prepare_uses_only_own_instance_named_probes_and_nonblocking_fd(fake_kernel):
    import fcntl
    monitor = armed(fake_kernel)
    definitions = (monitor.root / "kprobe_events").read_text()
    assert definitions.startswith("p:unrelated/other some_function\n")
    assert all(line in definitions for line in trace.PROBES.values())
    assert "$retval:s32" in definitions and "intf=$arg2:u32" in definitions
    assert fcntl.fcntl(monitor._fd, fcntl.F_GETFL) & os.O_NONBLOCK
    assert (monitor.instance / "buffer_size_kb").read_text() == "32\n"
    assert monitor.poll() == ("1000", "READY")
    assert monitor.close() is True
    assert monitor.close() is True
    definitions = (monitor.root / "kprobe_events").read_text()
    assert all(f"-:{trace.GROUP}/{name}\n" in definitions for name in trace.PROBES)
    assert "-:unrelated" not in definitions


@pytest.mark.parametrize(("data", "digits"), [
    (SETUP, "2000"),
    (SETUP + ACM0, "2100"),
    (SETUP + ACM0 + ACM_RETURN, "2200"),
    (SETUP + ACM0 + ACM_RETURN + ACM1 + SERIAL, "2110"),
    (SETUP + ACM_SUCCESS, "2320"),
    (SETUP + ACM_SUCCESS + PREPARE, "2321"),
    (SETUP + ACM_SUCCESS + PREPARE + COMMAND, "2322"),
    (SETUP + ACM_SUCCESS + PREPARE + COMMAND + COMPLETE, "2323"),
    (SETUP + ACM_SUCCESS + PREPARE + COMMAND.replace(b"Successful", b"Timed Out"), "2324"),
    (SETUP + ACM0 + ACM_RETURN + ACM1 + SERIAL
     + SERIAL_RETURN.replace(b"ret=0", b"ret=-110") + ACM_RETURN, "2330"),
    (SETUP + ACM0 + ACM_RETURN.replace(b"ret=0", b"ret=-22"), "2400"),
])
def test_exact_asahi_records_distinguish_configuration_progress(fake_kernel, data, digits):
    assert armed(fake_kernel, data).poll() == (digits, "CONFIG WINDOW")


def test_descriptor_status_before_and_after_configuration_cannot_claim_completion(fake_kernel):
    data = OTHER_SETUP + PREPARE + COMMAND + COMPLETE + SETUP + ACM0
    data += OTHER_SETUP + PREPARE + COMMAND + COMPLETE + SETUP + ACM_SUCCESS
    assert armed(fake_kernel, data).poll() == ("2100", "CONFIG WINDOW")


def test_different_controller_setup_does_not_end_configuration_window(fake_kernel):
    data = SETUP + OTHER_SETUP.replace(b"0x0000000382280000", b"0x0000000382380000") + ACM_SUCCESS
    assert armed(fake_kernel, data).poll() == ("2320", "CONFIG WINDOW")


def test_partial_reads_preserve_order_and_withhold_clean_code(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    data = SETUP + ACM_SUCCESS + PREPARE + COMMAND + COMPLETE
    chunks = iter((data[:47], None, data[47:len(SETUP) + 12], None,
                   data[len(SETUP) + 12:], None))
    original = trace.os.read
    def read(fd, count):
        if fd == monitor._fd:
            chunk = next(chunks)
            if chunk is None:
                raise BlockingIOError()
            return chunk
        return original(fd, count)
    monkeypatch.setattr(trace.os, "read", read)
    assert monitor.poll()[0] == "1000"
    assert monitor.poll()[0] == "1000"
    assert monitor.poll() == ("2323", "CONFIG WINDOW")


def test_eagain_is_ready_without_wait_or_error(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    original = trace.os.read
    def read(fd, count):
        if fd == monitor._fd:
            raise BlockingIOError()
        return original(fd, count)
    monkeypatch.setattr(trace.os, "read", read)
    assert monitor.poll() == ("1000", "READY")


@pytest.mark.parametrize("bad", [
    b"CPU:2 [LOST 3 EVENTS]\n", b"arbitrary private kernel detail\n",
    b"x" * (trace.LINE_BYTES + 1),
    SETUP + ACM_RETURN, SETUP + SERIAL_RETURN,
    SETUP + ACM0 + ACM0,
    SETUP + PREPARE + COMPLETE,
    SETUP + PREPARE + COMMAND + COMPLETE.replace(b"ca123456", b"ca000000"),
    SETUP + PREPARE.replace(b"00000000ca123456", b"(____ptrval____)"),
    SETUP + PREPARE + COMMAND.replace(b"params 00000000", b"params missing"),
    SETUP + PREPARE + COMMAND.replace(b"Successful", b"unrecognized value"),
])
def test_bad_or_missing_records_fail_closed_without_raw_output(fake_kernel, bad, capsys):
    code, label = armed(fake_kernel, bad).poll()
    assert code[0] == "3" and label == "INCOMPLETE"
    assert fake_kernel._fd is None
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("field", ["overrun", "commit overrun", "dropped events"])
def test_ring_loss_invalidates_even_apparent_complete_sequence(fake_kernel, field):
    monitor = armed(fake_kernel, SETUP + ACM_SUCCESS + PREPARE + COMMAND + COMPLETE)
    stats = monitor.instance / "per_cpu/cpu0/stats"
    stats.write_text(stats.read_text().replace(f"{field}: 0", f"{field}: 1"))
    assert monitor.poll()[0] == "3323"


def test_probe_misses_and_missing_profiles_invalidate(fake_kernel):
    monitor = armed(fake_kernel, SETUP)
    profile = monitor.root / "kprobe_profile"
    profile.write_text(profile.read_text().replace("m1lab_acm_return 0 0", "m1lab_acm_return 2 1"))
    assert monitor.poll()[0] == "3000"


def test_missing_probe_profile_cannot_report_clean_window(fake_kernel):
    monitor = armed(fake_kernel, SETUP + ACM_SUCCESS)
    (monitor.root / "kprobe_profile").write_text("m1lab_acm_enter 2 0\n")
    assert monitor.poll()[0] == "3320"


def test_total_byte_budget_and_per_poll_byte_bound(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    original = trace.os.read
    reads = []
    def read(fd, count):
        if fd == monitor._fd:
            reads.append(count)
            return b"#\n" * (count // 2)
        return original(fd, count)
    monkeypatch.setattr(trace.os, "read", read)
    for _ in range(trace.TOTAL_BYTES // trace.READ_BYTES):
        assert monitor.poll()[0] == "1000"
    assert monitor.poll()[0] == "3000"
    assert reads == [trace.READ_BYTES] * 9


def test_short_pipe_reads_do_not_claim_backlog_is_drained(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    chunks = iter([SETUP] + [b"#\n"] * (trace.MAX_READS - 1))
    original = trace.os.read
    calls = []
    def read(fd, count):
        if fd == monitor._fd:
            calls.append(count)
            return next(chunks)
        return original(fd, count)
    monkeypatch.setattr(trace.os, "read", read)
    assert monitor.poll() == ("1000", "READY")
    assert len(calls) == trace.MAX_READS


@pytest.mark.parametrize("conflict", ["probe", "instance", "deadline"])
def test_prepare_refuses_existing_state_and_expired_deadline(fake_kernel, conflict):
    monitor = fake_kernel
    if conflict == "probe":
        (monitor.root / "kprobe_events").write_text(trace.PROBES["m1lab_acm_enter"] + "\n")
    elif conflict == "instance":
        monitor.instance.mkdir()
    before = (monitor.root / "kprobe_events").read_text()
    monitor.start(time.monotonic() + (-1 if conflict == "deadline" else 10))
    assert monitor.poll() == ("0000", "UNAVAILABLE")
    assert (monitor.root / "kprobe_events").read_text() == before
    assert monitor.close() is True


def test_partial_setup_failure_cleans_only_registered_probes(fake_kernel, monkeypatch):
    original = trace._write
    def write(path, value, **kwargs):
        if path.name == "enable" and "m1lab_acm_return" in path.parts:
            raise PermissionError()
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    fake_kernel.start(time.monotonic() + 10)
    assert fake_kernel.poll() == ("0000", "UNAVAILABLE")
    definitions = (fake_kernel.root / "kprobe_events").read_text()
    assert "-:m1lab_usb/m1lab_acm_enter" in definitions
    assert "-:m1lab_usb/m1lab_acm_return" in definitions
    assert "m1lab_serial" not in definitions


@pytest.mark.parametrize("failure", ["write", "readback", "remove"])
def test_cleanup_failure_never_reports_capture_safe(fake_kernel, monkeypatch, failure):
    monitor = armed(fake_kernel)
    original = trace._write
    def write(path, value, **kwargs):
        if failure in ("write", "readback") and path == monitor.instance / "tracing_on":
            if failure == "write":
                raise PermissionError()
            return
        if failure == "remove" and value.startswith("-:"):
            raise PermissionError()
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    assert monitor.close() is False
    assert monitor.close() is False
    assert monitor.poll()[0] == "3000"


def test_cleanup_retries_failed_ownership_without_redeleting_successful_probes(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    original = trace._write
    blocked = [True]
    attempts = []
    def write(path, value, **kwargs):
        attempts.append((path.name, value))
        if blocked[0] and (path == monitor.instance / "tracing_on"
                           or value == "-:m1lab_usb/m1lab_acm_enter"):
            raise PermissionError()
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    assert monitor.close() is False
    assert monitor._owned and monitor._probes == ["m1lab_acm_enter"]
    blocked[0] = False
    attempts.clear()
    assert monitor.close() is False  # Failure remains visible to capture caller.
    assert ("tracing_on", "0") in attempts
    assert [value for _name, value in attempts if value.startswith("-:")] == ["-:m1lab_usb/m1lab_acm_enter"]
    assert monitor._probes == []


def test_no_truncation_or_creation_when_writing_trace_controls(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(trace.os, "open", lambda path, flags: calls.append((path, flags)) or 777)
    monkeypatch.setattr(trace.os, "write", lambda _fd, data: len(data))
    monkeypatch.setattr(trace.os, "close", lambda _fd: None)
    trace._write(tmp_path / "kprobe_events", "probe", append=True)
    assert calls[0][1] & os.O_APPEND
    assert not calls[0][1] & (os.O_TRUNC | os.O_CREAT)


def test_metadata_short_reads_cannot_hide_existing_owned_probe(fake_kernel, monkeypatch):
    monitor = fake_kernel
    text = "p:unrelated/other some_function\n" + trace.PROBES["m1lab_acm_enter"] + "\n"
    (monitor.root / "kprobe_events").write_text(text)
    original = trace.os.read
    monkeypatch.setattr(trace.os, "read", lambda fd, count: original(fd, min(count, 32)))
    monitor.start(time.monotonic() + 10)
    assert monitor.poll() == ("0000", "UNAVAILABLE")
    assert (monitor.root / "kprobe_events").read_text() == text


def controller_event(raw, text, *, endpoint="ep0in", address="0x0000000382280000"):
    # trace.h: %pa: event (%08x): ...; debug.h decodes the raw endpoint fields.
    return record("dwc3_event", f"{address}: event ({raw:08x}): {endpoint}: {text}")


IN_COMPLETE = controller_event(0x0000c042, "Transfer Complete (sIL) [Status Phase]")
OUT_COMPLETE = controller_event(0x00000040, "Transfer Complete (sil) [Setup Phase]", endpoint="ep0out")
IN_NRDY = controller_event(0x000020c2, "Transfer Not Ready [00000000] (Not Active) [Status Phase]")


def test_status_probe_uses_entry_saved_arguments_and_ep0_event_filter(fake_kernel):
    monitor = armed(fake_kernel)
    definitions = (monitor.root / "kprobe_events").read_text()
    assert "r16:m1lab_usb/m1lab_status_return dwc3:__dwc3_ep0_do_control_status dwc=$arg1:x64 dep=$arg2:x64" in definitions
    assert "dwc3:dwc3_ep0_start_trans" not in definitions  # Inlined on STATUS2 path.
    assert (monitor.instance / "events/dwc3/dwc3_event/filter").read_text() == trace.EVENT_FILTER + "\n"
    for name in ("dwc3_readl", "dwc3_writel"):
        assert (monitor.instance / f"events/dwc3/{name}/filter").read_text() == trace.IO_FILTER + "\n"
    # Only EP0 and the explicitly decoded, non-SOF device kinds survive.
    expression = trace.EVENT_FILTER.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    for event in range(4096):
        expected = not event & 61 or (event & 255 == 1 and (event >> 8) in (0,1,2,3,4,5,6,9,10,11))
        assert bool(eval(expression, {"__builtins__": {}}, {"event": event})) == bool(expected)


@pytest.mark.parametrize(("tail", "old", "new"), [
    (b"", "2321", "2100"),
    (COMMAND, "2322", "2100"),
    (COMMAND + STATUS_RETURN, "2322", "2200"),
    (STATUS_RETURN, "2321", "2300"),  # Already-started fast path, no accepted command.
    (COMMAND.replace(b"Successful", b"Timed Out") + STATUS_RETURN, "2324", "2300"),
    (COMMAND + STATUS_RETURN + IN_COMPLETE, "2322", "2214"),
    (COMMAND + STATUS_RETURN + IN_COMPLETE + COMPLETE, "2323", "2214"),
    (COMMAND + STATUS_RETURN + OUT_COMPLETE, "2322", "2222"),
    (COMMAND + STATUS_RETURN + IN_NRDY, "2322", "2230"),
])
def test_wrapper_return_and_event_page_separate_callback_progress(fake_kernel, tail, old, new):
    monitor = armed(fake_kernel, SETUP + ACM_SUCCESS + PREPARE + tail)
    assert monitor.poll() == (old, "CONFIG WINDOW")
    assert monitor.event_page() == (new, "CONFIG WINDOW")


def test_other_call_returns_cannot_complete_selected_status_call(fake_kernel):
    other_enter = STATUS_ENTER.replace(b"-128 [002]", b"-129 [003]").replace(b"80068000", b"80168000")
    other_return = STATUS_RETURN.replace(b"-128 [002]", b"-129 [003]").replace(b"80068000", b"80168000")
    monitor = armed(fake_kernel, SETUP + PREPARE + other_enter + COMMAND + other_return)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page()[0] == "2100"
    with (monitor.instance / "trace_pipe").open("ab") as stream:
        stream.write(STATUS_RETURN)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page()[0] == "2200"


@pytest.mark.parametrize("bad", [
    STATUS_RETURN,  # No corresponding entry.
    STATUS_ENTER + STATUS_ENTER,  # Nested same-context calls are ambiguous.
    PREPARE + COMMAND + STATUS_RETURN.replace(b"80068000", b"80168000"),
    PREPARE + COMMAND + STATUS_RETURN.replace(b"-128 [002]", b"-128 [003]"),
    PREPARE + COMMAND.replace(b"-128 [002]", b"-129 [003]"),
    record("dwc3_prepare_trb", TRB_BODY),  # Missing wrapper entry.
    STATUS_ENTER.replace(b"dep=0xffff800080068000", b"dep=0x0"),
    STATUS_ENTER.replace(b"-128 [002]", b"-missing [002]"),
    PREPARE + COMMAND + IN_COMPLETE.replace(b"0000c042", b"0000c040"),
    PREPARE + COMMAND + IN_COMPLETE.replace(b"(sIL)", b"(sil)"),
    PREPARE + COMMAND + IN_COMPLETE.replace(b"Status Phase", b"UNKNOWN"),
    PREPARE + COMMAND + IN_NRDY.replace(b"Not Active", b"Active"),
    PREPARE + COMMAND + IN_NRDY.replace(b"00000000]", b"00000001]"),
    PREPARE + COMMAND + IN_NRDY.replace(b"event (", b"event malformed ("),
])
def test_new_correlation_and_decoder_failures_share_invalidity(fake_kernel, bad, capsys):
    monitor = armed(fake_kernel, SETUP + bad)
    assert monitor.poll()[0][0] == "3"
    assert monitor.event_page()[0][0] == "3"
    assert monitor.event_page()[1] == "INCOMPLETE"
    assert monitor._fd is None
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize(("raw", "endpoint", "text", "digits"), [
    (0x10c0, "ep0out", "Transfer Not Ready [00000000] (Not Active) [Data Phase]", "2240"),
    (0xa0c2, "ep0in", "Transfer Not Ready [00000000] (Active) [Status Phase]", "2230"),
    (0x000601c2, "ep0in", "Endpoint Command Complete", "2250"),
    (0x0001c082, "ep0in", "Transfer In Progress [00000001] (sIM)", "2260"),
    (0x102, "ep0in", "FIFO", "2270"),
    (0x00011182, "ep0in", " Stream 1 Found", "2280"),
    (0x2182, "ep0in", " Stream Not Found", "2280"),
    (0x242, "ep0in", "UNKNOWN", "2290"),
    (0x42, "ep0in", "Transfer Complete (sil) [Unconnected]", "2211"),
    (0x42, "ep0in", "Transfer Complete (sil) [Data Phase]", "2213"),
])
def test_exact_event_raw_fields_and_text_decoding(fake_kernel, raw, endpoint, text, digits):
    data = SETUP + PREPARE + COMMAND + STATUS_RETURN + controller_event(raw, text, endpoint=endpoint)
    monitor = armed(fake_kernel, data)
    assert monitor.poll() == ("2002", "CONFIG WINDOW")
    assert monitor.event_page()[0] == digits


def test_first_completion_latches_and_next_setup_freezes_both_pages(fake_kernel):
    data = SETUP + PREPARE + COMMAND + STATUS_RETURN + IN_NRDY + OUT_COMPLETE + IN_COMPLETE
    data += OTHER_SETUP + IN_COMPLETE + COMPLETE
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page()[0] == "2222"  # Later good-state event cannot erase first completion.


def test_events_before_command_other_controller_and_after_window_do_not_advance(fake_kernel):
    data = SETUP + IN_COMPLETE + PREPARE + IN_NRDY + COMMAND
    data += IN_COMPLETE.replace(b"0x0000000382280000", b"0x0000000382380000").replace(b"-128 [002]", b"-129 [003]")
    data += OTHER_SETUP + STATUS_RETURN + IN_COMPLETE
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page()[0] == "2100"


def test_status_context_storage_is_bounded(fake_kernel):
    calls = b"".join(STATUS_ENTER.replace(b"-128 [002]", f"-{pid} [002]".encode())
                     for pid in range(100, 117))
    monitor = armed(fake_kernel, SETUP + calls)
    assert monitor.poll()[0] == "3000"
    assert len(monitor._status_calls) == 16


@pytest.mark.parametrize("probe", ["m1lab_status_enter", "m1lab_status_return"])
def test_new_probe_miss_invalidates_both_pages(fake_kernel, probe):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + IN_COMPLETE)
    profile = monitor.root / "kprobe_profile"
    profile.write_text(profile.read_text().replace(f"{probe} 0 0", f"{probe} 3 1"))
    assert monitor.poll()[0] == "3002"
    assert monitor.event_page() == ("3214", "INCOMPLETE")


def test_event_page_does_not_read_write_open_or_hide_existing_invalidity(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + IN_NRDY)
    monitor.poll()
    with monkeypatch.context() as patch:
        def forbidden(*_args, **_kwargs):
            pytest.fail("event_page must not perform I/O")
        for operation in ("open", "read", "write"):
            patch.setattr(trace.os, operation, forbidden)
        assert monitor.event_page() == ("2230", "CONFIG WINDOW")
        monitor.validity = 3
        assert monitor.event_page() == ("3230", "INCOMPLETE")


def test_new_probe_cleanup_failure_retains_ownership_and_forbids_capture(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel)
    original = trace._write
    def write(path, value, **kwargs):
        if value == "-:m1lab_usb/m1lab_status_return":
            raise OSError("injected removal failure")
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    assert monitor.close() is False
    assert monitor._probes == ["m1lab_status_return"]
    assert monitor.event_page() == ("3000", "INCOMPLETE")


def test_partial_status_return_cannot_claim_completed_call(fake_kernel):
    cut = len(STATUS_RETURN) - 7
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN[:cut])
    assert monitor.poll()[0] == "1002"
    assert monitor.event_page() == ("1100", "READY")
    with (monitor.instance / "trace_pipe").open("ab") as stream:
        stream.write(STATUS_RETURN[cut:] + IN_COMPLETE)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page() == ("2214", "CONFIG WINDOW")


@pytest.mark.parametrize("failure", ["status_probe", "event_filter"])
def test_new_instrumentation_setup_failure_stays_unavailable_and_cleans(fake_kernel, monkeypatch, failure):
    original = trace._write
    def write(path, value, **kwargs):
        if ((failure == "status_probe" and "m1lab_status_return" in path.parts)
                or (failure == "event_filter" and path.name == "filter" and "dwc3_event" in path.parts)):
            raise OSError("injected setup failure")
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    fake_kernel.start(time.monotonic() + 10)
    assert fake_kernel.poll() == ("0000", "UNAVAILABLE")
    assert fake_kernel.event_page() == ("0000", "UNAVAILABLE")
    assert fake_kernel._probes == [] and fake_kernel._fd is None
    assert fake_kernel.close() is True


def test_non_ascii_trace_pipe_disables_tracing_and_stays_incomplete(fake_kernel, monkeypatch):
    """Exercise real pipe reads and real cleanup, not a mocked decode exception."""
    import errno

    monitor = armed(fake_kernel)
    os.close(monitor._fd)
    read_fd, write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
    monitor._fd = read_fd
    # Model the aggregate enable value, which real tracefs computes for events.
    (monitor.instance / "events/enable").write_text("1\n")
    original_close = monitor.close
    close_results = []

    def close():
        result = original_close()
        close_results.append(result)
        return result

    monkeypatch.setattr(monitor, "close", close)
    try:
        assert issubclass(UnicodeDecodeError, ValueError)
        os.write(write_fd, SETUP)
        assert monitor.poll() == ("2000", "CONFIG WINDOW")
        assert (monitor.instance / "tracing_on").read_text() == "1\n"

        os.write(write_fd, b"non-ASCII kernel trace byte: \xff\n")
        assert monitor.poll() == ("3000", "INCOMPLETE")
        assert monitor.event_page() == ("3000", "INCOMPLETE")
        assert close_results == [True]
        assert (monitor.instance / "tracing_on").read_text() == "0\n"
        assert (monitor.instance / "events/enable").read_text() == "0\n"
        assert monitor._fd is None and monitor._probes == []
        with pytest.raises(OSError) as closed:
            os.fstat(read_fd)
        assert closed.value.errno == errno.EBADF

        assert monitor.poll() == ("3000", "INCOMPLETE")
        assert monitor.event_page() == ("3000", "INCOMPLETE")
        assert close_results == [True]  # No reopening/recovery on later polls.
    finally:
        os.close(write_fd)


@pytest.mark.parametrize(("tail", "digits"), [
    (b"", "2101"),
    (STATUS_RETURN, "2101"),
    (STATUS_RETURN + UNMASK, "2201"),
    (STATUS_RETURN + UNMASK + io_event("dwc3_readl", 0xc40c, 0, irq=True), "2211"),
    (STATUS_RETURN + UNMASK + COUNT_READ, "2221"),
    (STATUS_RETURN + UNMASK + io_event("dwc3_readl", 0xc408, 0), "2201"),
    (STATUS_RETURN + UNMASK + io_event("dwc3_writel", 0xc40c, 0x80000000), "2201"),
])
def test_cached_batch_rearm_and_fresh_count_observation(fake_kernel, tail, digits):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + tail)
    assert monitor.poll() == ("2002", "CONFIG WINDOW")
    assert monitor.rearm_page() == (digits, "CONFIG WINDOW")
    assert monitor.device_page() == ("2001", "CONFIG WINDOW")


@pytest.mark.parametrize("first", [0, 4])
def test_first_post_rearm_read_latches_and_never_means_current_register_value(fake_kernel, first):
    tail = STATUS_RETURN + UNMASK + io_event("dwc3_readl", 0xc40c, first, irq=True)
    tail += io_event("dwc3_readl", 0xc40c, 4 if first == 0 else 0, irq=True)
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + tail)
    assert monitor.poll()[0] == "2002"
    assert monitor.rearm_page()[0] == ("2211" if first == 0 else "2221")


def test_startup_other_controller_and_prior_batches_cannot_claim_selected_rearm(fake_kernel):
    startup = UNMASK + COUNT_READ + io_event("dwc3_writel", 0xc40c, 4, irq=True)
    prior_batch = BATCH + STATUS_NRDY + UNMASK
    other = (COUNT_READ + MASK + ACK + STATUS_NRDY + UNMASK).replace(
        b"0x0000000382280000", b"0x0000000382380000").replace(b"-128 [002]", b"-129 [003]")
    monitor = armed(fake_kernel, startup + prior_batch + SETUP + PREPARE + COMMAND + STATUS_RETURN + other)
    assert monitor.poll()[0] == "2002"
    assert monitor.rearm_page()[0] == "2101"


def test_setup_batch_and_status_batch_may_be_separate_and_irq_task_differs_from_thread(fake_kernel):
    # Acknowledgement happens in hardirq; event parsing/wrapper/unmask in threaded IRQ.
    data = BATCH + OUT_COMPLETE + SETUP + ACM_SUCCESS + UNMASK
    data += PREPARE + COMMAND + STATUS_RETURN + UNMASK + COUNT_READ
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "2322"
    assert monitor.rearm_page()[0] == "2221"


@pytest.mark.parametrize("bad", [
    STATUS_NRDY + STATUS_ENTER + record("dwc3_prepare_trb", TRB_BODY),  # Missing batch.
    COUNT_READ + MASK + STATUS_NRDY + STATUS_ENTER + record("dwc3_prepare_trb", TRB_BODY),  # Missing ack.
    PREPARE.replace(STATUS_NRDY, b""),  # No event processing in selected thread.
    PREPARE.replace(STATUS_NRDY, STATUS_NRDY.replace(b"-128 [002]", b"-129 [002]")),
    PREPARE.replace(ACK, ACK.replace(b"[000]", b"[001]")),
    PREPARE.replace(MASK, MASK.replace(b"swapper/0-0", b"swapper/0-1")),
    PREPARE.replace(COUNT_READ, b""),
    PREPARE.replace(ACK, ACK.replace(b"value 00000004", b"value 00000008")),
    PREPARE.replace(ACK, ACK + ACK),
    PREPARE.replace(MASK, MASK + MASK),
    PREPARE.replace(ACK, ACK + COUNT_READ),
    PREPARE + COMMAND + UNMASK,  # Must see selected helper return first.
    PREPARE + COMMAND + STATUS_RETURN + UNMASK.replace(b"[002]", b"[003]"),
    PREPARE + COMMAND + STATUS_RETURN + UNMASK.replace(b"-128 [002]", b"-129 [002]"),
    PREPARE + COMMAND + STATUS_RETURN + UNMASK.replace(b"value 00001000", b"value 00002000"),
    PREPARE.replace(COUNT_READ, COUNT_READ.replace(b"value 00000004", b"value 00002000")),
    MASK.replace(b"offset c408", b"offset c409"),
    COUNT_READ.replace(b"value 00000004", b"value nope"),
    COUNT_READ.replace(b"addr 00000000dead1234", b"addr (____ptrval____)"),
])
def test_missing_ambiguous_or_malformed_batch_evidence_fails_closed(fake_kernel, bad):
    monitor = armed(fake_kernel, SETUP + bad)
    assert monitor.poll()[0][0] == "3"
    assert monitor.rearm_page()[0][0] == monitor.device_page()[0][0] == "3"
    assert monitor._fd is None
    assert monitor.poll()[0][0] == "3"


def test_controller_batch_storage_is_bounded_before_first_configuration(fake_kernel):
    data = b"".join(io_event("dwc3_readl", 0xc40c, 4,
                             controller=f"0x{0x382280000 + index * 0x100000:016x}", irq=True)
                    for index in range(17))
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "3000"
    assert len(monitor._batches) == 16


def device_record(raw, text, controller="0x0000000382280000"):
    return record("dwc3_event", f"{controller}: event ({raw:08x}): {text}")


@pytest.mark.parametrize(("raw", "text", "digits", "window"), [
    (0x00040001, "Disconnect: [SS.Disabled]", "2014", 4),
    (0x000e0101, "Reset [Reset]", "2023", 3),
    (0x00000201, "Connection Done [U0]", "2031", 1),
    (0x00010301, "Link Change [U1]", "2041", 1),
    (0x000f0401, "WakeUp [Resume]", "2051", 1),
    (0x00000501, "UNKNOWN", "2061", 1),
    (0x00030601, "Suspend [U3]", "2071", 1),
    (0x00000901, "Erratic Error [U0]", "2101", 1),
    (0x00000a01, "Command Complete [U0]", "2111", 1),
    (0x000c0301, "Link Change [UNKNOWN link state]", "2041", 1),
    (0x00000b01, "Overflow [U0]", "3121", 1),
])
def test_known_device_events_and_independent_window_closure(fake_kernel, raw, text, digits, window):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + UNMASK + device_record(raw, text))
    monitor.poll()
    assert monitor.device_page()[0] == digits
    assert monitor.rearm_page()[0] == f"{digits[0]}20{window}"
    assert monitor.event_page()[0] == f"{digits[0]}200"  # Device event is not EP0 event.


@pytest.mark.parametrize(("raw", "text"), [
    (0x00000701, "Start-Of-Frame [U0]"),  # Filtered out: cannot silently accept it.
    (0x00000801, "UNKNOWN"),
    (0x00000c01, "UNKNOWN"),
    (0x00000003, "Disconnect: [U0]"),  # Wrong device subtype.
    (0x00001001, "Disconnect: [U0]"),  # Reserved raw field.
    (0x02000001, "Disconnect: [U0]"),
    (0x00000301, "Link Change [U3]"),  # Raw/text mismatch.
    (0x00000101, "Disconnect: [U0]"),
])
def test_unknown_filtered_or_inconsistent_device_records_fail_closed(fake_kernel, raw, text):
    monitor = armed(fake_kernel, SETUP + device_record(raw, text))
    assert monitor.poll()[0] == "3000"
    assert monitor.device_page()[0] == "3001"


@pytest.mark.parametrize(("close", "window"), [
    (OTHER_SETUP, 2),
    (device_record(0x101, "Reset [U0]"), 3),
    (device_record(1, "Disconnect: [U0]"), 4),
])
def test_first_window_closure_preserves_all_observations_and_ignores_later_progress(fake_kernel, close, window):
    first_device = device_record(0x301, "Link Change [U0]")
    data = SETUP + PREPARE + COMMAND + first_device + close
    data += STATUS_RETURN + UNMASK + COUNT_READ + IN_COMPLETE + COMPLETE + OTHER_SETUP
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "2002"
    assert monitor.event_page()[0] == "2100"
    assert monitor.rearm_page()[0] == f"210{window}"
    assert monitor.device_page()[0] == f"204{window}"  # First device remains separate from closure.


def test_device_events_before_window_or_from_other_controller_cannot_close_it(fake_kernel):
    reset = device_record(0x101, "Reset [U0]")
    wrong_controller = reset.replace(b"0x0000000382280000", b"0x0000000382380000").replace(b"-128 [002]", b"-129 [003]")
    monitor = armed(fake_kernel, reset + SETUP + PREPARE + COMMAND + wrong_controller + STATUS_RETURN + UNMASK)
    assert monitor.poll()[0] == "2002"
    assert monitor.rearm_page()[0] == "2201"
    assert monitor.device_page()[0] == "2001"


def test_new_pages_have_no_io_and_share_current_loss_validity(fake_kernel, monkeypatch):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + UNMASK + COUNT_READ)
    monitor.poll()
    with monkeypatch.context() as patch:
        def forbidden(*_args, **_kwargs):
            pytest.fail("numeric pages must not perform I/O")
        for operation in ("open", "read", "write"):
            patch.setattr(trace.os, operation, forbidden)
        assert monitor.rearm_page() == ("2221", "CONFIG WINDOW")
        assert monitor.device_page() == ("2001", "CONFIG WINDOW")
        monitor.validity = 3
        assert monitor.rearm_page() == ("3221", "INCOMPLETE")
        assert monitor.device_page() == ("3001", "INCOMPLETE")


@pytest.mark.parametrize("event", ["dwc3_readl", "dwc3_writel"])
def test_io_trace_setup_failure_stays_unavailable_and_cleans(fake_kernel, monkeypatch, event):
    original = trace._write
    def write(path, value, **kwargs):
        if event in path.parts and path.name == "filter":
            raise OSError("injected register trace filter failure")
        return original(path, value, **kwargs)
    monkeypatch.setattr(trace, "_write", write)
    fake_kernel.start(time.monotonic() + 10)
    assert fake_kernel.poll() == ("0000", "UNAVAILABLE")
    assert fake_kernel.rearm_page() == fake_kernel.device_page() == ("0000", "UNAVAILABLE")
    assert fake_kernel._probes == [] and fake_kernel._fd is None


def test_startup_count_ack_cannot_supply_stale_count_for_later_mask(fake_kernel):
    startup = COUNT_READ + io_event("dwc3_writel", 0xc40c, 4, irq=True)
    missing_fresh_read = PREPARE.replace(COUNT_READ, b"")
    monitor = armed(fake_kernel, startup + SETUP + missing_fresh_read + COMMAND + STATUS_RETURN + UNMASK)
    assert monitor.poll()[0] == "3000"
    assert monitor.rearm_page()[0] == "3001"


def test_partial_unmask_and_later_count_cannot_claim_progress_until_records_complete(fake_kernel):
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + UNMASK[:-3])
    assert monitor.poll()[0] == "1002"
    assert monitor.rearm_page()[0] == "1101"
    with (monitor.instance / "trace_pipe").open("ab") as stream:
        stream.write(UNMASK[-3:] + COUNT_READ[:-3])
    assert monitor.poll()[0] == "1002"
    assert monitor.rearm_page()[0] == "1201"
    with (monitor.instance / "trace_pipe").open("ab") as stream:
        stream.write(COUNT_READ[-3:])
    assert monitor.poll()[0] == "2002"
    assert monitor.rearm_page()[0] == "2221"


@pytest.mark.parametrize("witness", [
    device_record(0x301, "Link Change [U0]"),
    IN_COMPLETE,
    OUT_COMPLETE,
    controller_event(0x20c0, "Transfer Not Ready [00000000] (Not Active) [Status Phase]", endpoint="ep0out"),
    controller_event(0x10c2, "Transfer Not Ready [00000000] (Not Active) [Data Phase]"),
    controller_event(0xa0c2, "Transfer Not Ready [00000000] (Active) [Status Phase]"),
    STATUS_NRDY.replace(b"0x0000000382280000", b"0x0000000382380000"),
])
def test_only_explicit_in_status_nrdy_can_anchor_wrapper_entry(fake_kernel, witness):
    # Synthetic hardening cases: these are not claimed realizable on the exact
    # normal ACM path, whose status dispatch switches on exact NRDY status2.
    data = SETUP + PREPARE.replace(STATUS_NRDY, witness) + COMMAND + STATUS_RETURN + UNMASK
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "3000"
    assert monitor.rearm_page()[0] == "3001"


@pytest.mark.parametrize("intervening", [
    device_record(0x301, "Link Change [U0]"),
    STATUS_NRDY,
    STATUS_NRDY.replace(b"0x0000000382280000", b"0x0000000382380000"),
    record("dwc3_prepare_trb", TRB_BODY.replace("0x0000000382280000", "0x0000000382380000")),
])
def test_entry_witness_cannot_be_replaced_before_selected_prepare(fake_kernel, intervening):
    # Even another identical NRDY is a new event, not the entry-time witness.
    data = SETUP + PREPARE.replace(STATUS_ENTER, STATUS_ENTER + intervening) + COMMAND + STATUS_RETURN + UNMASK
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "3000"
    assert monitor.rearm_page()[0] == "3001"


def test_nrdy_observed_only_after_wrapper_entry_cannot_retroactively_bind_it(fake_kernel):
    data = SETUP + BATCH + STATUS_ENTER + STATUS_NRDY + record("dwc3_prepare_trb", TRB_BODY)
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "3000"
    assert monitor.rearm_page()[0] == "3001"


def test_foreign_controller_same_selected_thread_context_is_ambiguous(fake_kernel):
    foreign = device_record(0x301, "Link Change [U0]", controller="0x0000000382380000")
    monitor = armed(fake_kernel, SETUP + PREPARE + COMMAND + STATUS_RETURN + foreign + UNMASK)
    assert monitor.poll()[0] == "3002"
    assert monitor.rearm_page()[0] == "3101"


def test_status_nrdy_in_later_batch_may_run_on_another_cpu_than_setup_batch(fake_kernel):
    data = BATCH + OUT_COMPLETE + SETUP + ACM_SUCCESS + UNMASK
    # The IRQ thread can migrate between batches, but a batch's locked callback
    # and matched helper/unmask must remain in the same context.
    status_batch = PREPARE + COMMAND + STATUS_RETURN + UNMASK
    data += status_batch.replace(b"-128 [002]", b"-128 [003]") + COUNT_READ
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "2322"
    assert monitor.rearm_page()[0] == "2221"
    assert monitor.event_page()[0] == "2200"


def test_other_call_witness_does_not_replace_selected_controller_call_binding(fake_kernel):
    other_enter = STATUS_ENTER.replace(b"-128 [002]", b"-129 [003]").replace(b"80068000", b"80168000")
    other_return = STATUS_RETURN.replace(b"-128 [002]", b"-129 [003]").replace(b"80068000", b"80168000")
    monitor = armed(fake_kernel, SETUP + PREPARE + other_enter + COMMAND + other_return + STATUS_RETURN + UNMASK)
    assert monitor.poll()[0] == "2002"
    assert monitor.rearm_page()[0] == "2201"
    assert monitor._call_witnesses == {}



def test_one_nrdy_witness_cannot_be_reused_by_two_wrapper_calls(fake_kernel):
    data = SETUP + BATCH + STATUS_NRDY + STATUS_ENTER + STATUS_RETURN
    data += STATUS_ENTER + record("dwc3_prepare_trb", TRB_BODY) + COMMAND + STATUS_RETURN + UNMASK
    monitor = armed(fake_kernel, data)
    assert monitor.poll()[0] == "3000"
    assert monitor.rearm_page()[0] == "3001"
