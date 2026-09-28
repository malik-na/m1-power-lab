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
PREPARE = STATUS_ENTER + record("dwc3_prepare_trb", TRB_BODY)
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
    assert (monitor.instance / "events/dwc3/dwc3_event/filter").read_text() == "!(event & 61)\n"
    # Bit0=device; physical endpoint is bits1..5: exactly EP0 OUT and IN survive.
    assert [value for value in range(64) if not value & 61] == [0, 2]


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
    data += IN_COMPLETE.replace(b"0x0000000382280000", b"0x0000000382380000")
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
