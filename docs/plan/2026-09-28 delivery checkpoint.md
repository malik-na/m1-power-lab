# Delivery checkpoint — September 28, 2026

This checkpoint compares the implemented work with the original implementation
plan. It does not redefine first-release acceptance or turn diagnostics into
scientific evidence. Thirteen bounded native physical attempts have produced
zero samples; the thirteenth has now been reconciled as failed.

| Original milestone | Observed delivery state |
|---|---|
| M0 readiness | Host, target/proxy identity, pinned build inputs and several operational facts recorded. Native log/result transport, measurement fixture and independent reset remain unqualified. The current image is a console diagnostic, not a qualified desktop fixture. |
| M1 minimal controls/runtime | Coordinator, journal, immutable artifacts, CLI, review/approval gates, accounting and bounded Codex runtime implemented. Installed service has completed two analysis turns. Remaining runtime/operational qualification is listed in STATUS.md. |
| M2 transport and measurement feasibility | Blocked. m1n1 replies work and a RAM-only Linux image boots, but Linux USB SET_CONFIGURATION times out with -110. No native result stream or sample has been acquired. Sensor/energy-boundary qualification and unattended recovery are not demonstrated. |
| M3 scientific automation | Host logic and replay/synthetic cases implemented. No live evidence-to-experiment-to-result scientific cycle is qualified. |
| M4 phone and availability | Private HTTPS and service operation demonstrated. The owner reports that the actual iPhone loads overview, evidence and conversation, and reconnects after browser reopening. Full controls, push and disruptive host availability cases remain incomplete. |
| M5 real investigation | Not started; depends on M2. |
| M6 confirmation/release | Not achieved. The original release requires a real multi-cycle investigation and supported conclusion as well as operational acceptance. |

## Blocker and technical progress

The thirteenth physical run used source `a9a9d03` and verified candidate
`build_a66761403b56471391bc625ecf14ab74`. The package passed 53 artifact
checks, all 584 host tests passed, and exact procedure review
`review_2125d19824ac44d8af824d2af553863c` accepted it. Host native USB
`1d6b:0104` appeared at 18:30:37 UTC, but `SET_CONFIGURATION` timed out
(`-110`) at 18:30:42 UTC. Independent raw-frame audit decoded `VAGP2322`,
`VRES2200`, `VMCW2201` and `VDDW2001`. The selected status command and wrapper
return occurred, the expected event-buffer unmask was observed, and the first
configuration window opened. No later event-count read or selected EP0/device
event was observed in the retained trace. The target-side `V2` indication is
provisional; it does not establish wire-level completion or a driver fix.
There was no native tty, payload or power sample.

Operation `operation_21b7785dafd342859c56c7448d23f2e4` initially returned
unknown and was reconciled as failed while preserving that original result.
The same checked proxy identity returned on a new connection at 18:33:05 UTC;
that does not independently attest a reboot or reliable recovery from every
hang. The camera was stopped; its no-audio recording remains private. Five
technical artifacts and the attempt summary were imported into the installed
session. The service and
inspect-only helper are restored active, and local authenticated HTTP returned
200, anonymous HTTP 403 and private HTTPS 200. See the
[attempt evidence](../evidence/2026-09-28-native-thirteenth-attempt.json) and
[service handoff](../evidence/2026-09-28-thirteenth-service-handoff.json).

The measurement preflight also leaves M0/M2 open: the current image is a
console diagnostic without a desktop screen-on fixture, and ordinary USB
tethering may affect battery draw. It cannot qualify the specified 10% screen-on
desktop idle condition. This is a fixture and energy-boundary gap as well as a
missing native result channel.

## Divergences and correction

More UI and research-loop implementation was completed before M2 than the
original feasibility-first sequence called for. Some parallel host development
was allowed, but it did not resolve the critical delivery dependency. Repeated
USB instrumentation and exact reviews have become a significant debugging
detour. Test counts, commits and accepted reviews must not be presented as
readiness to start native power investigations.

The camera is a user-authorized, bounded, private diagnostic fallback after the
native USB observation channel failed. It is not a permanent result channel or
power instrument. m1n1's hypervisor console is supported, but reserves the
connected USB port and changes execution/power behavior; it cannot silently
replace the native fixture. A RAM log surviving the firmware return has not
been established.

The owner's later instruction to proceed independently without repeated
permission prompts is recorded as delegated setup authority for exact bounded
procedures. Records explicitly say the owner did not manually read each digest.
That instruction does not waive source review, artifact checks, missing physical
evidence or scientific acceptance.

Keep remaining work at M2. The review finding was resolved before the
thirteenth run, but that run still supplied no native result path or power
sample. Stop repeating this trace without a new discriminating hypothesis.
Exact static source review found no verified fix. A supported independent
debug UART or USB protocol analyzer would supply the missing physical
event-progress evidence. Do not expand the UI or claim a full release to meet
the calendar deadline.

## Owner-only information and checks

The owner reports having only the ordinary USB cable; no Asahi-compatible
USB-PD/debug UART interface is available. This is an inventory finding, not a
purchase instruction. A supported physical debug UART is an independent
native-console option; a generic USB serial dongle is not automatically suitable.

The owner reports that the private lab URL loads overview, evidence and
conversation on the actual iPhone, and that closing then reopening the browser
returns to current lab state. This is owner-reported acceptance evidence; it
does not replace the remaining approval, push or fault-injection cases.

See [implementation plan](M1%20investigation%20tool%20-%20implementation%20plan.md),
[current status](../STATUS.md), and [native channel explanation](../NATIVE-HARNESS.md).
