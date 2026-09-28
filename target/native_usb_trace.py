"""Bounded, RAM-only diagnostic for the first native SET_CONFIGURATION.

Exact text formats: Asahi Linux asahi-7.1.13-3. This observes controller
software, not host acknowledgement or scientific capture validity. Tracing
perturbs timing; even a complete status callback does not qualify a capture.
The caller mounts tracefs, prepares after module loading/before UDC binding,
polls from its existing wait loop, and closes before capture and on exit.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import time


TRACEFS = Path("/sys/kernel/tracing")
GROUP = "m1lab_usb"
PROBES = {
    "m1lab_acm_enter": "p:m1lab_usb/m1lab_acm_enter usb_f_acm:acm_set_alt intf=$arg2:u32",
    "m1lab_acm_return": "r16:m1lab_usb/m1lab_acm_return usb_f_acm:acm_set_alt ret=$retval:s32",
    "m1lab_serial_enter": "p:m1lab_usb/m1lab_serial_enter u_serial:gserial_connect",
    "m1lab_serial_return": "r16:m1lab_usb/m1lab_serial_return u_serial:gserial_connect ret=$retval:s32",
    # The packaged kernel inlines start_trans into this void status wrapper.
    # Exact-tag kretprobes save $argN at entry (FETCH_OP_EDATA), not at return.
    "m1lab_status_enter": "p:m1lab_usb/m1lab_status_enter dwc3:__dwc3_ep0_do_control_status dwc=$arg1:x64 dep=$arg2:x64",
    "m1lab_status_return": "r16:m1lab_usb/m1lab_status_return dwc3:__dwc3_ep0_do_control_status dwc=$arg1:x64 dep=$arg2:x64",
}
DWC3_EVENTS = ("dwc3_ctrl_req", "dwc3_prepare_trb", "dwc3_complete_trb", "dwc3_gadget_ep_cmd", "dwc3_event")
READ_BYTES = 64 * 1024
MAX_READS = 16
TOTAL_BYTES = 512 * 1024
LINE_BYTES = 1024
MAX_CPUS = 32
_EVENT = re.compile(r": (m1lab_(?:acm|serial|status)_(?:enter|return)|dwc3_[a-z_]+): (.*)$")
_DEVICE = re.compile(r"(0x[0-9a-fA-F]{1,16}): (.*)$")
_TRB = re.compile(r"(ep0in|ep0out): trb ([0-9a-fA-F]+) .*:status2\)$")
_CONTEXT = re.compile(r"-([0-9]+)\s+\[([0-9]+)\]\s+(?:\S+\s+)?[0-9]+\.[0-9]+$")
_STATUS_ARGS = re.compile(r"\bdwc=(0x[0-9a-f]{1,16}) dep=(0x[0-9a-f]{1,16})$")
LABELS = ("UNAVAILABLE", "READY", "CONFIG WINDOW", "INCOMPLETE")


def _write(path: Path, value: str, *, append: bool = False) -> None:
    # Never O_TRUNC global kprobe_events: that would delete unrelated probes.
    flags = os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(path, flags | (os.O_APPEND if append else 0))
    try:
        data = (value + "\n").encode("ascii")
        if os.write(fd, data) != len(data):
            raise OSError("short diagnostic write")
    finally:
        os.close(fd)


def _read(path: Path, limit: int) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        data = b""
        for _ in range(MAX_READS):
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                return data.decode("ascii")
            data += chunk
            if len(data) > limit:
                break
        raise ValueError("diagnostic read limit")
    finally:
        os.close(fd)


class NativeUsbTrace:
    """poll returns (VAGP digits, fixed label); no trace text is displayed.

    V: 0 unavailable, 1 armed/no configuration or pending records, 2 observed with current loss
    checks clean, 3 incomplete/lost. V2 is a live, provisional observation.
    A: 0 absent, 1 outstanding call, 2 one interface returned zero,
    3 both interfaces returned zero, 4 nonzero return.
    G: 0 absent, 1 entered, 2 returned zero, 3 nonzero return.
    P: 0 absent, 1 status2 prepared, 2 start command successful,
    3 controller status completion observed, 4 start command failed.
    Only the first configuration request is retained; the next SETUP closes
    its window, so subsequent descriptor reads cannot produce false progress.
    """

    def __init__(self, tracefs: Path = TRACEFS):
        self.root = tracefs
        self.instance = tracefs / "instances/m1lab"
        self.validity = 0
        self.acm = self.serial = self.ep0 = 0
        self._attempted = self._owned = self._frozen = False
        self._probes: list[str] = []
        self._stats: list[Path] = []
        self._fd: int | None = None
        self._partial = b""
        self._bytes = 0
        self._device: str | None = None
        self._acm_pending: int | None = None
        self._acm_done: set[int] = set()
        self._trb: str | None = None
        self._closed_ok = True
        self._status_calls: dict[tuple[int, int], tuple[str, str]] = {}
        self._selected_call: tuple[tuple[int, int], tuple[str, str]] | None = None
        self.returned = self.event = self.state = 0

    def prepare(self, deadline: float) -> None:
        """Best effort, one attempt; caller supplies the original boot deadline."""
        if self._attempted:
            return
        self._attempted = True
        try:
            def put(path: Path, text: str, *, append: bool = False) -> None:
                if time.monotonic() >= deadline:
                    raise TimeoutError("diagnostic preparation deadline")
                _write(path, text, append=append)

            if time.monotonic() >= deadline:
                return
            existing = _read(self.root / "kprobe_events", 65536)
            if GROUP + "/" in existing or any(name in existing for name in PROBES):
                return
            self.instance.mkdir()  # Refuse an existing instance; never take it over.
            self._owned = True
            put(self.instance / "tracing_on", "0")
            put(self.instance / "current_tracer", "nop")
            put(self.instance / "trace_clock", "global")
            put(self.instance / "buffer_size_kb", "32")
            with os.scandir(self.instance / "per_cpu") as entries:
                for entry in entries:
                    if re.fullmatch(r"cpu[0-9]+", entry.name):
                        self._stats.append(Path(entry.path) / "stats")
                        if len(self._stats) > MAX_CPUS:
                            raise ValueError("too many trace CPUs")
            if not self._stats:
                raise ValueError("missing trace CPU stats")
            for name, definition in PROBES.items():
                put(self.root / "kprobe_events", definition, append=True)
                self._probes.append(name)
                put(self.instance / "events" / GROUP / name / "enable", "1")
            for name in DWC3_EVENTS:
                event = self.instance / "events/dwc3" / name
                if name == "dwc3_event":
                    # Reject device bit0 and EP-number bits2..5; allow EP0 OUT/IN.
                    put(event / "filter", "!(event & 61)")
                elif name != "dwc3_ctrl_req":
                    put(event / "filter", 'name == "ep0in" || name == "ep0out"')
                put(event / "enable", "1")
            self._check_loss()
            self._fd = os.open(self.instance / "trace_pipe", os.O_RDONLY | os.O_NONBLOCK
                               | os.O_CLOEXEC | os.O_NOFOLLOW)
            put(self.instance / "tracing_on", "1")
            self.validity = 1
        except (OSError, ValueError):
            self.close()

    start = prepare

    def _check_loss(self) -> None:
        profiles = {}
        for line in _read(self.root / "kprobe_profile", 16384).splitlines():
            fields = line.split()
            if fields and fields[0] in PROBES:
                if len(fields) != 3 or fields[0] in profiles:
                    raise ValueError("invalid probe profile")
                profiles[fields[0]] = int(fields[2])
        if set(profiles) != set(PROBES) or any(profiles.values()):
            raise ValueError("missing or missed probe")
        for path in self._stats:
            fields = dict(line.split(":", 1) for line in _read(path, 2048).splitlines() if ":" in line)
            if any(int(fields.get(key, "-1")) != 0
                   for key in ("overrun", "commit overrun", "dropped events")):
                raise ValueError("trace ring loss")

    def _line(self, line: str) -> None:
        if "LOST" in line or "EVENTS DROPPED" in line:
            raise ValueError("lost trace events")
        match = _EVENT.search(line)
        if not match:
            if line and not line.startswith("#"):
                raise ValueError("unknown trace record")
            return
        event, body = match.groups()
        if event.startswith("dwc3_"):
            device = _DEVICE.fullmatch(body)
            if not device:
                raise ValueError("invalid controller record")
            address, body = device.groups()
            if self._device is not None and address != self._device:
                return
            if event == "dwc3_ctrl_req":
                if self._device is not None:
                    self._frozen = True
                elif body == "Set Configuration(Config = 1)":
                    self._device = address
                return
        if self._device is None or self._frozen:
            return
        def context() -> tuple[int, int]:
            found = _CONTEXT.search(line[:match.start()])
            if not found:
                raise ValueError("missing trace context")
            return tuple(map(int, found.groups()))

        if event.startswith("m1lab_status_"):
            args = _STATUS_ARGS.search(body)
            if not args or any(int(value, 16) == 0 for value in args.groups()):
                raise ValueError("invalid status arguments")
            key, pointers = context(), args.groups()
            if event == "m1lab_status_enter":
                if key in self._status_calls or len(self._status_calls) >= 16:
                    raise ValueError("ambiguous status nesting")
                self._status_calls[key] = pointers
            else:
                if self._status_calls.pop(key, None) != pointers:
                    raise ValueError("unmatched status return")
                if self._selected_call == (key, pointers):
                    self.returned = 2 if self.ep0 in (2, 3) else 3
        elif event == "dwc3_event":
            self._controller_event(body)
        elif event == "m1lab_acm_enter":
            intf = re.search(r"\bintf=([01])$", body)
            if not intf or self._acm_pending is not None:
                raise ValueError("invalid ACM entry")
            self._acm_pending = int(intf[1])
            if self.acm != 4:
                self.acm = 1
        elif event in ("m1lab_acm_return", "m1lab_serial_return"):
            ret = re.search(r"\bret=(-?[0-9]+)$", body)
            if not ret:
                raise ValueError("invalid return")
            if event == "m1lab_acm_return":
                if self._acm_pending is None or self._acm_pending in self._acm_done:
                    raise ValueError("unmatched ACM return")
                self._acm_done.add(self._acm_pending)
                self._acm_pending = None
                self.acm = 4 if int(ret[1]) or self.acm == 4 else len(self._acm_done) + 1
            else:
                if self.serial != 1:
                    raise ValueError("unmatched serial return")
                self.serial = 3 if int(ret[1]) else 2
        elif event == "m1lab_serial_enter":
            if self.serial:
                raise ValueError("duplicate serial entry")
            self.serial = 1
        elif event in ("dwc3_prepare_trb", "dwc3_complete_trb"):
            trb = _TRB.fullmatch(body)
            if not trb:
                if body.endswith(":status2)"):
                    raise ValueError("unrecognized status record")
                return  # setup/data/status3 TRBs are not this two-stage request.
            endpoint, pointer = trb.groups()
            if event == "dwc3_prepare_trb":
                if endpoint != "ep0in" or self.ep0:
                    raise ValueError("unexpected status preparation")
                key = context()
                if key not in self._status_calls:
                    raise ValueError("status preparation without call")
                self._selected_call = (key, self._status_calls[key])
                self.returned = 1
                self._trb = pointer
                self.ep0 = 1
            else:
                # ep0_complete_status traces eps[0], even for the IN status.
                if pointer != self._trb or self.ep0 != 2:
                    raise ValueError("unmatched status completion")
                self.ep0 = 3
        elif event == "dwc3_gadget_ep_cmd" and self.ep0 == 1:
            command = re.fullmatch(r"ep0in: cmd 'Start Transfer' \[[0-9a-fA-F]+\] params "
                                   r"[0-9a-fA-F]+ [0-9a-fA-F]+ [0-9a-fA-F]+ --> status: (.+)", body)
            if not command and body.startswith("ep0in: cmd 'Start Transfer'"):
                raise ValueError("unrecognized status command")
            if command:
                key = context()
                if self._selected_call != (key, self._status_calls.get(key)):
                    raise ValueError("status command outside selected call")
                status = command[1]
                if status not in ("Successful", "Timed Out", "No Resource", "Bus Expiry", "UNKNOWN"):
                    raise ValueError("unknown command status")
                self.ep0 = 2 if status == "Successful" else 4

    def _controller_event(self, body: str) -> None:
        record = re.fullmatch(r"event \(([0-9a-f]{8})\): (ep0in|ep0out): (.*)", body)
        if not record:
            raise ValueError("invalid endpoint event")
        raw_text, endpoint, text = record.groups()
        raw = int(raw_text, 16)
        if raw & 61 or endpoint != ("ep0in" if raw & 2 else "ep0out"):
            raise ValueError("inconsistent endpoint event")
        kind, status, parameter = (raw >> 6) & 15, (raw >> 12) & 15, raw >> 16
        flags = ("S" if status & 2 else "s") + ("I" if status & 4 else "i")
        state = 0
        if kind == 1:
            complete = re.fullmatch(r"Transfer Complete \(([sS][iI][lL])\) \[(.+)\]", text)
            states = ("Unconnected", "Setup Phase", "Data Phase", "Status Phase")
            if not complete or complete[1] != flags + ("L" if status & 8 else "l") or complete[2] not in states:
                raise ValueError("invalid completion state")
            code, state = (1 if raw & 2 else 2), states.index(complete[2]) + 1
            expected = text
        elif kind == 3:
            code = 3 if raw & 2 else 4
            expected = f"Transfer Not Ready [{parameter:08x}] ({'Active' if status & 8 else 'Not Active'})"
            expected += {1: " [Data Phase]", 2: " [Status Phase]"}.get(status & 3, "")
        elif kind == 2:
            code = 6
            expected = f"Transfer In Progress [{parameter:08x}] ({flags}{'M' if status & 8 else 'm'})"
        else:
            code = {7: 5, 4: 7, 6: 8}.get(kind, 9)
            expected = {7: "Endpoint Command Complete", 4: "FIFO", 6:
                        f" Stream {parameter} Found" if status == 1 else " Stream Not Found"}.get(kind, "UNKNOWN")
        if text != expected:
            raise ValueError("inconsistent event text")
        # The first completion supersedes the first other event, then is latched.
        # NRDY's printed phase is from status bits, NOT the actual dwc->ep0state.
        if self.ep0 in (2, 3) and (self.event == 0 or (code in (1, 2) and self.event not in (1, 2))):
            self.event, self.state = code, state

    def event_page(self) -> tuple[str, str]:
        """No I/O: V, status-wrapper return, first event/completion, actual state.

        R: 0 absent, 1 outstanding, 2 returned after accepted command, 3 otherwise.
        E: 0 absent; 1/2 IN/OUT complete; 3/4 IN/OUT NRDY; 5 command complete;
        6 in progress; 7 FIFO; 8 stream; 9 other. S: 0 unavailable; 1 unconnected;
        2 setup; 3 data; 4 status. Actual state is printed only for completions.
        """
        return f"{self.validity}{self.returned}{self.event}{self.state}", LABELS[self.validity]

    def poll(self) -> tuple[str, str]:
        """At most 16 nonblocking reads/64KiB and bounded loss checks per call."""
        if self._fd is not None and self.validity in (1, 2):
            try:
                data = b""
                drained = False
                for _ in range(MAX_READS):
                    try:
                        chunk = os.read(self._fd, READ_BYTES - len(data))
                    except BlockingIOError:
                        drained = True
                        break
                    if not chunk:
                        drained = True
                        break
                    data += chunk
                    if len(data) == READ_BYTES:
                        break
                self._bytes += len(data)
                if self._bytes > TOTAL_BYTES:
                    raise ValueError("trace byte budget")
                lines = (self._partial + data).split(b"\n")
                self._partial = lines.pop()
                if len(self._partial) > LINE_BYTES:
                    raise ValueError("trace line budget")
                for line in lines:
                    if len(line) > LINE_BYTES:
                        raise ValueError("trace line budget")
                    self._line(line.decode("ascii"))
                self._check_loss()
                # A short trace_pipe read does not prove the queue was drained.
                self.validity = 2 if self._device and not self._partial and drained else 1
            except (OSError, ValueError):
                self.validity = 3
                self.close()
        return f"{self.validity}{self.acm}{self.serial}{self.ep0}", LABELS[self.validity]

    def close(self) -> bool:
        """Confirm tracing is off; false conservatively forbids subsequent capture."""
        ok = True
        if self._owned:
            for path in (self.instance / "tracing_on", self.instance / "events/enable"):
                try:
                    _write(path, "0")
                    if _read(path, 32).strip() != "0":
                        raise ValueError("tracing disable unconfirmed")
                except (OSError, ValueError):
                    ok = False
                    if self.validity:
                        self.validity = 3
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                ok = False
                if self.validity:
                    self.validity = 3
            self._fd = None
        remaining = []
        for name in reversed(self._probes):
            try:
                _write(self.root / "kprobe_events", f"-:{GROUP}/{name}", append=True)
            except OSError:
                remaining.append(name)
                ok = False
                if self.validity:
                    self.validity = 3
        self._probes = list(reversed(remaining))
        if self._owned:
            try:
                self.instance.rmdir()
            except OSError:
                pass
            else:
                self._owned = False
        self._closed_ok = self._closed_ok and ok
        return self._closed_ok
