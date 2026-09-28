# Native Linux capture source

`native_capture.py` is a standalone, read-only target-side collector included
in the [J313 candidate image](../docs/NATIVE-HARNESS.md). It consumes an immutable
`m1lab.native-launch.v1` manifest and emits the existing
`m1lab.native-result.v1` length-prefixed, checksummed identity/data/end frames
to stdout. The host owns and configures that descriptor; this program does not
open USB, serial, or network devices.

The identity frame repeats target identity and the prelaunch boot-epoch value.
Native startup also reads Linux's boot UUID and kernel release and hashes the
exact packaged image configuration before sampling. Its optional
`observed_linux` identity object is a Linux self-report; the new Linux boot UUID
is distinct from the prelaunch proxy epoch. The host checks the observed
configuration digest against the launch and retains the bounded fields.
`identity_verified` remains false until an independent live adapter verifies
the physical source. Legacy frames without this object retain their original
bytes/checksums. New images require an updated host decoder; old strict
decoders reject the additional object.

The launch `parameters` object must contain only `sample_count` and
`sample_period_ms`. The program limits the run to one hour, the protocol frame
limit, the launch output limit, and the launch deadline. Its monotonic deadline
bounds sampling and result-channel writes. Reaching a sample or output bound
emits a `partial` terminal frame when the channel still accepts output; a
stalled or incomplete frame remains unknown to the host. A stuck kernel driver
read cannot be interrupted by this process, so the host timeout and target
recovery path still require qualification.

Launch preparation reserves at least one second beyond the requested sampling
duration for startup. This is a minimum scheduling margin, not a promise that
an unqualified physical launch will finish in that time; the collector still
refuses a launch whose remaining deadline cannot contain the requested work.
The terminal-frame reserve fits within the final sample interval so increasing
the sample count does not systematically omit the last samples.

`output_limit_bytes` bounds decoded sample payload bytes. Base64, JSON, and
length prefixes add channel bytes; frame size and count have separate bounds,
and offline import caps the whole saved stream at 32 MiB. These are protocol
limits, not a measured channel-throughput or observer-effect qualification.

Each data frame contains one newline-terminated
`m1lab.raw-sysfs-sample.v1` JSON record. It samples a fixed allowlist under
`/sys/class/power_supply` and `/sys/class/thermal`, plus the device-tree model.
Values are retained as raw strings with UTC and monotonic timestamps. The
collector does not convert units, select an energy boundary, compute watts,
classify sensor independence, or claim whole-device power. Missing properties
are omitted; no absent value becomes zero. A complete capture means only that
the requested raw samples were framed and emitted.

An owner-reviewed build recipe must place Python 3 and this source in the
target image, hash the exact collector source, and bind the launch manifest to
that image. `m1lab native-launch` prepares the manifest as a session artifact;
`m1lab native-import` preserves a returned byte stream and publishes a
credential-screened view of recognized collector records. Raw binary frames
are not inserted into Codex context. Offline import deliberately marks target
identity, physical source, and capture timing as unverified,
even when frame checksums and sequence are valid. Neither command dispatches a
target operation. The candidate recipe and image are available, but the
result transport and return path remain unqualified. Do not use its
output as power evidence until the sensor provenance, observer effect,
physical channel, and recovery gates are qualified on the actual setup.

Host integration tests run this collector in a separate Python process with
synthetic sysfs snapshots, transport its real framed output through a pipe,
and import it into isolated coordinator artifact storage. Offline import can
accept an expired saved launch while live decoding retains its deadline gate.
These tests establish software behavior only; they do not run on the Mac.

The host's descriptor receiver can also consume the collector's stdout as it
flows, preserving partial wire bytes on channel failure and applying the same
sample screening before publishing a capture. This is a host acquisition
primitive for future qualified channel wiring. Its receive deadline bounds
host waiting; it cannot stop a stuck target or demonstrate recovery.
The owner CLI exposes it as `native-receive`, consuming the channel owner's
stdin pipe and publishing raw and screened artifacts for the selected launch.


Native startup also exposes an experimental USB **configuration string**
(`iConfiguration`), precreated and nonempty before binding the gadget. Its fixed
ASCII format is `M1Lab diag:v1:<stage>:<state>`, or
`M1Lab diag:v1:fail:<stage>:<type>:<state>` on failure. Only the six stages from
`acm_bind` through `capture_done`, recognized UDC states, and allowlisted
exception types are emitted; arbitrary error text is excluded. The static
product and serial strings remain unchanged.

Updates are best effort. While waiting for the launch line, a one-second select
slice refreshes the diagnostic without resetting the original 150-second boot
deadline; the separate image watchdog is unchanged. Configfs or UDC-state I/O
failure cannot establish a stage transition or stop a capture on its own.
A descriptor may be unavailable after an EP0 timeout, stale, or torn during a
concurrent read. These strings are neither physical identity nor samples and
must never be treated as capture success or hardware qualification.


For a fixed camera view that cuts off the lower screen, the same diagnostics
also redraw rows 1–14 of `/dev/tty0`. Four large digits encode **SS E U**: a
two-digit stage, one error digit, and one USB state digit. Each digit uses a
3-by-5 bitmap expanded to 9 columns by 10 rows of the existing console font.
The current stage is drawn with cached/unknown USB state before any diagnostic
sysfs access, then refreshed when a new state is available. A label below the
digits names the values; no exception messages or other arbitrary data appear.

| SS | Stage | SS | Stage |
| --- | --- | --- | --- |
| 00 | Python entry | 07 | Waiting for UDC |
| 01 | Load phy_apple_atc | 08 | Bind ACM gadget |
| 02 | Load tps6598x | 09 | Waiting for ttyGS0 |
| 03 | Load dwc3_apple | 10 | Waiting for launch |
| 04 | Load libcomposite | 11 | Launch received |
| 05 | Load usb_f_acm | 12 | Capture |
| 06 | Mount configfs | 13 | Capture emission finished |

**E:** 0 none, 1 TimeoutError, 2 ValueError, 3 OSError, 4 ImportError,
5 RuntimeError, 6 AssertionError, 7 TypeError, 8 other exception.
**U:** 0 unknown, 1 not attached, 2 attached, 3 powered, 4 reconnecting,
5 unauthenticated, 6 default, 7 address, 8 configured, 9 suspended.
For example, **10 1 7** means timeout while waiting for a launch, with the last
reported UDC state `address`. These are self-reported diagnostics, not proof of
samples, physical source, or successful recovery.

Each redraw is one nonblocking write to a verified character device 4:0, with
cursor/attribute save and restore. It does not clear the screen, suppress kernel
logs, change the scroll region, or write to USB or the result stream. A redraw
may be incomplete or overwritten by concurrent console messages. It refreshes
on existing stage/wait callbacks and adds no retry, timer, or watchdog extension;
the 150-second native deadline, 180-second image watchdog and failure hold
remain unchanged.


The diagnostic candidate includes `native_usb_trace.py`. After the
fixed USB modules load and before gadget binding, startup mounts tracefs and
attempts one private trace instance. Fixed entry/return probes observe
`usb_f_acm:acm_set_alt`, `u_serial:gserial_connect` and
`dwc3:__dwc3_ep0_do_control_status`; existing DWC3 events observe the first
SET_CONFIGURATION(1) request and its EP0 status handling.
It changes no kernel image, USB descriptor, role, transfer payload or recovery
limit. Tracing perturbs timing and this image remains a diagnostic candidate.

The upper display rotates every two seconds through **V A G P** (`M1LAB USB
TRACE`), **V R E S** (`M1LAB USB EVENT`) and the existing **SS E U** stage page.
The trace page uses:

| Digit | Meaning |
| --- | --- |
| V | 0 unavailable; 1 ready/no fully consumed configuration observation; 2 configuration observed with current loss checks clean; 3 incomplete/lost |
| A | 0 no ACM entry; 1 call outstanding; 2 one interface returned zero; 3 both interfaces returned zero; 4 nonzero return |
| G | 0 no serial entry; 1 outstanding; 2 returned zero; 3 nonzero return |
| P | 0 no status evidence; 1 STATUS2 TRB prepared; 2 start command succeeded; 3 controller status completion observed; 4 start command failed |

V2 is a provisional observation, not proof of host acknowledgement. The next
SETUP freezes the first configuration window so later descriptor reads cannot
appear as its progress. The observer uses a 32 KiB per-CPU ring (at most 32 CPUs),
at most 16 nonblocking reads totaling 64 KiB per poll, a 512 KiB total read cap,
and 1,024-byte lines. Missing controls, unexpected relevant data, lost events,
probe misses and exceeded bounds are unavailable or incomplete, never success.
Only numeric summaries and fixed labels reach the screen; raw addresses do not.

The event page keeps the same validity digit and separates return from the
STATUS2 helper from raw EP0 event delivery. The exact packaged kernel inlines
the transfer-start body inside `__dwc3_ep0_do_control_status`; probing the
standalone `dwc3_ep0_start_trans` would miss this path. The command-accepted
tracepoint occurs before resource-index readback and PHY-bit restoration, so
P2 alone does not establish that the helper returned.

| Digit | Meaning |
| --- | --- |
| R | 0 no selected STATUS2 call; 1 outstanding; 2 matched return after accepted command; 3 matched return without accepted command |
| E | 0 no post-command EP0 event; 1 IN complete; 2 OUT complete; 3 IN not-ready; 4 OUT not-ready; 5 endpoint-command complete; 6 in-progress; 7 FIFO; 8 stream; 9 other |
| S | 0 actual EP0 state unavailable; 1 unconnected; 2 setup; 3 data; 4 status |

The first post-command event is retained, then replaced once by the first
completion event. Only completion records contain the actual EP0 state;
not-ready request phases are not substituted for that state. Entry-saved
arguments associate the selected status-helper call and return. Ambiguous,
missing or malformed correlation remains incomplete. The raw event filter
admits physical endpoints 0 and 1 only, and the existing byte/read limits apply
to the enlarged event set.

Startup retains its 150-second deadline and 180-second image watchdog. Optional
trace read errors cannot abort launch waiting. Once a launch arrives, capture is
refused unless diagnostic tracing shutdown is confirmed. Cleanup is retried on
exit and cannot mask the original failure. The eleventh physical attempt
confirmed readable VAGP snapshots of 2322 and then launch timeout, with no
native samples. The additional helper-return/event page remains physically
unverified until a separately reviewed bounded run. Even a completed EP0 callback does not qualify
physical identity, sample provenance, power measurement or unattended recovery.
