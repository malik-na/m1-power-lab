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
DWC3_EVENTS = ("dwc3_ctrl_req", "dwc3_prepare_trb", "dwc3_complete_trb", "dwc3_gadget_ep_cmd",
               "dwc3_event", "dwc3_readl", "dwc3_writel")
# EP0 OUT/IN, or device kinds 0..6/9..11. Excludes SOF and unknown kinds.
# tracefs '&' is a predicate, not a value usable by a following comparison.
EVENT_FILTER = ("!(event & 61) || ((event & 1) && !(event & 254) && "
                "((!(event & 2048) && (!(event & 1024) || !(event & 512) || !(event & 256))) || "
                "((event & 2048) && !(event & 1024) && (event & 768))))")
IO_FILTER = "offset == 0xc408 || offset == 0xc40c"
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
_IO = re.compile(r"addr ([0-9a-f]{8,16}) offset (c408|c40c) value ([0-9a-f]{8})$")


class _Batch:
    """One controller's unique count/mask/cache-ack sequence; bounded by caller."""

    def __init__(self, count: int, context: tuple[int, int]):
        self.count, self.irq_context = count, context
        self.masked = self.acked = False
        self.processor: tuple[int, int] | None = None
        self.status_ready: tuple[tuple[int, int], object] | None = None
        self.status_claimed = False



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
        self._call_witnesses: dict[tuple[int, int], tuple[_Batch, object]] = {}
        self._selected_call: tuple[tuple[int, int], tuple[str, str]] | None = None
        self.returned = self.event = self.state = 0
        self.rearm = self.count = self.window = self.device_event = 0
        self._batches: dict[str, _Batch] = {}
        self._selected_batch: _Batch | None = None

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
                    put(event / "filter", EVENT_FILTER)
                elif name in ("dwc3_readl", "dwc3_writel"):
                    put(event / "filter", IO_FILTER)
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
        def context() -> tuple[int, int]:
            found = _CONTEXT.search(line[:match.start()])
            if not found:
                raise ValueError("missing trace context")
            return tuple(map(int, found.groups()))

        if event.startswith("dwc3_"):
            device = _DEVICE.fullmatch(body)
            if not device:
                raise ValueError("invalid controller record")
            address, body = device.groups()
            if self._device is not None and address != self._device:
                if not self._frozen and event in ("dwc3_event", "dwc3_prepare_trb"):
                    batch = self._batches.get(self._device)
                    if batch is not None and batch.processor == context():
                        # A different controller in the same active processing
                        # context cannot supply this controller's status witness.
                        batch.status_ready = None
                        if batch is self._selected_batch:
                            raise ValueError("foreign controller inside selected batch context")
                return
            if self._frozen:
                return
            if event in ("dwc3_readl", "dwc3_writel"):
                self._register_event(address, event, body, context())
                return
            if event == "dwc3_ctrl_req":
                if self._device is not None:
                    self._frozen, self.window = True, 2
                elif body == "Set Configuration(Config = 1)":
                    self._device, self.window = address, 1
                    self._batches = {address: self._batches[address]} if address in self._batches else {}
                return
            if event == "dwc3_event":
                batch = self._batches.get(address)
                if batch is not None and batch.acked:
                    key = context()
                    if batch.processor not in (None, key):
                        raise ValueError("ambiguous batch processing context")
                    batch.processor = key
                    batch.status_ready = None  # Only the current event can anchor a call.
        if self._device is None or self._frozen:
            return

        if event.startswith("m1lab_status_"):
            args = _STATUS_ARGS.search(body)
            if not args or any(int(value, 16) == 0 for value in args.groups()):
                raise ValueError("invalid status arguments")
            key, pointers = context(), args.groups()
            if event == "m1lab_status_enter":
                if key in self._status_calls or len(self._status_calls) >= 16:
                    raise ValueError("ambiguous status nesting")
                self._status_calls[key] = pointers
                batch = self._batches.get(self._device)
                if batch is not None and batch.status_ready is not None and batch.status_ready[0] == key:
                    if batch.status_claimed:
                        raise ValueError("status NRDY witness reused by another call")
                    batch.status_claimed = True
                    self._call_witnesses[key] = (batch, batch.status_ready[1])
            else:
                self._call_witnesses.pop(key, None)
                if self._status_calls.pop(key, None) != pointers:
                    raise ValueError("unmatched status return")
                if self._selected_call == (key, pointers):
                    self.returned = 2 if self.ep0 in (2, 3) else 3
        elif event == "dwc3_event":
            status_ready = self._controller_event(body)
            batch = self._batches.get(self._device)
            if status_ready and batch is not None and batch.acked:
                batch.status_ready = (context(), object())
                batch.status_claimed = False
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
                batch = self._batches.get(self._device)
                if (batch is None or not batch.acked or batch.processor != key
                        or batch.status_ready is None or batch.status_ready[0] != key
                        or self._call_witnesses.get(key) != (batch, batch.status_ready[1])):
                    raise ValueError("status without its entry-time EP0 IN status NRDY witness")
                # Exact ep0.c emits this prepare from start_control_status(dep)
                # inside the keyed wrapper. trace.h derives physical identity
                # from dep->dwc, binding the saved arguments through this call;
                # no equality between raw pointers and physical addresses is assumed.
                self._selected_batch, self.rearm = batch, 1
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

    def _register_event(self, address: str, event: str, body: str, key: tuple[int, int]) -> None:
        # trace.h prints the same physical base as dwc3_event. The hashed virtual
        # addr is syntax only: it is never used to establish controller identity.
        record = _IO.fullmatch(body)
        if not record:
            raise ValueError("invalid register trace")
        _, offset, value_text = record.groups()
        value = int(value_text, 16)
        batch = self._batches.get(address)
        if event == "dwc3_readl":
            if offset != "c40c":
                return
            amount = value & 0xfffc
            if self.rearm == 2 and not self.count:
                self.count = 2 if amount else 1  # First *observed* later read.
            if batch is not None and batch.masked:
                raise ValueError("count read before cached batch closed")
            if amount:
                if address not in self._batches and len(self._batches) >= 16:
                    raise ValueError("too many controller batches")
                self._batches[address] = _Batch(amount, key)
            else:
                self._batches.pop(address, None)
        elif offset == "c408":
            if value == 0x80001000:
                if batch is None or batch.masked or batch.irq_context != key or batch.count > 4096:
                    raise ValueError("mask without a unique bounded count read")
                batch.masked = True
            elif value == 4096:
                if batch is self._selected_batch and batch is not None:
                    if not batch.acked or key != batch.processor or self.returned not in (2, 3):
                        raise ValueError("unmask outside returned selected batch")
                    self.rearm = 2
                self._batches.pop(address, None)
            elif self._device is not None:
                raise ValueError("unexpected event buffer size write")
            else:
                self._batches.pop(address, None)  # Startup/cleanup is not a batch.
        elif value == 0x80000000:
            if batch is not None:
                raise ValueError("EHB write inside pending count sequence")
            return  # Optional EHB write after clear is not a count observation.
        elif batch is not None and batch.masked:
            if batch.acked or batch.irq_context != key or value != batch.count:
                raise ValueError("unmatched cached count acknowledgement")
            batch.acked = True
        else:
            self._batches.pop(address, None)  # Startup stale-event ack consumes its read.
            if self._device is not None and value:
                raise ValueError("count acknowledgement without masked batch")

    def _device_event(self, raw: int, text: str) -> None:
        kind = (raw >> 8) & 15
        names = {0: "Disconnect:", 1: "Reset", 2: "Connection Done", 3: "Link Change",
                 4: "WakeUp", 6: "Suspend", 9: "Erratic Error", 10: "Command Complete", 11: "Overflow"}
        links = ("U0", "U1", "U2", "U3", "SS.Disabled", "RX.Detect", "SS.Inactive",
                 "Polling", "Recovery", "Hot Reset", "Compliance", "Loopback",
                 "UNKNOWN link state", "UNKNOWN link state", "Reset", "Resume")
        if raw & 0xfe00f0fe or kind not in (*names, 5):
            raise ValueError("unknown device event")
        expected = "UNKNOWN" if kind == 5 else f"{names[kind]} [{links[(raw >> 16) & 15]}]"
        if text != expected:
            raise ValueError("inconsistent device event text")
        if not self.device_event:
            self.device_event = kind + 1
        if kind in (0, 1):
            self._frozen, self.window = True, 4 if kind == 0 else 3
        if kind == 11:
            raise ValueError("controller event buffer overflow")

    def _controller_event(self, body: str) -> bool:
        device = re.fullmatch(r"event \(([0-9a-f]{8})\): (.*)", body)
        if device and int(device[1], 16) & 1:
            self._device_event(int(device[1], 16), device[2])
            return False
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
        # xfernotready switches on the *entire* status: only exact value2
        # reaches status dispatch; Active/Status (10) cannot anchor this call.
        return raw & 0xffff == 0x20c2

    def event_page(self) -> tuple[str, str]:
        """No I/O: V, status-wrapper return, first event/completion, actual state.

        R: 0 absent, 1 outstanding, 2 returned after accepted command, 3 otherwise.
        E: 0 absent; 1/2 IN/OUT complete; 3/4 IN/OUT NRDY; 5 command complete;
        6 in progress; 7 FIFO; 8 stream; 9 other. S: 0 unavailable; 1 unconnected;
        2 setup; 3 data; 4 status. Actual state is printed only for completions.
        """
        return f"{self.validity}{self.returned}{self.event}{self.state}", LABELS[self.validity]

    def rearm_page(self) -> tuple[str, str]:
        """No I/O: VMCW. M0 absent,1 selected masked batch,2 matching clear after
        wrapper return. C0 no later count read,1 first later read zero,2 nonzero.
        W0 no config,1 open,2 next SETUP,3 reset,4 disconnect. No new MMIO I/O.
        """
        return f"{self.validity}{self.rearm}{self.count}{self.window}", LABELS[self.validity]

    def device_page(self) -> tuple[str, str]:
        """No I/O: VDDW. DD00 absent, otherwise first device kind+1:01 disconnect,
        02 reset,03 connect,04 link,05 wake,06 hibernation,07 suspend,10 erratic,
        11 command complete,12 overflow. W has the same meaning as rearm_page.
        """
        return f"{self.validity}{self.device_event:02d}{self.window}", LABELS[self.validity]

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
