# Delivery checkpoint — September 28, 2026

This checkpoint compares the implemented work with the original implementation
plan. It does not redefine first-release acceptance or turn diagnostics into
scientific evidence. Twelve native physical attempts have produced zero samples;
the proposed thirteenth attempt has not been dispatched at this checkpoint.

| Original milestone | Observed delivery state |
|---|---|
| M0 readiness | Host, target/proxy identity, pinned build inputs and several operational facts recorded. Native log/result transport, measurement fixture and independent reset remain unqualified. |
| M1 minimal controls/runtime | Coordinator, journal, immutable artifacts, CLI, review/approval gates, accounting and bounded Codex runtime implemented. Installed service has completed two analysis turns. Remaining runtime/operational qualification is listed in STATUS.md. |
| M2 transport and measurement feasibility | Blocked. m1n1 replies work and a RAM-only Linux image boots, but Linux USB SET_CONFIGURATION times out with -110. No native result stream or sample has been acquired. Sensor/energy-boundary qualification and unattended recovery are not demonstrated. |
| M3 scientific automation | Host logic and replay/synthetic cases implemented. No live evidence-to-experiment-to-result scientific cycle is qualified. |
| M4 phone and availability | Private HTTPS and service operation demonstrated. The owner reports that the actual iPhone loads overview, evidence and conversation, and reconnects after browser reopening. Full controls, push and disruptive host availability cases remain incomplete. |
| M5 real investigation | Not started; depends on M2. |
| M6 confirmation/release | Not achieved. The original release requires a real multi-cycle investigation and supported conclusion as well as operational acceptance. |

## Blocker and technical progress

The last physical run narrowed the Linux USB failure: ACM interface setup and
serial connection returned zero; the selected EP0 status helper returned after
command acceptance. No subsequent EP0 event was observed in its retained first
configuration-window snapshots. The host still could not configure the device.
This removes some candidate failure locations but establishes no driver fix.
The original unknown operation and the evidence-based failed reconciliation are
both retained. A fresh matching proxy connection is not independent proof of a
reboot or reliable recovery from every hang.

The next proposed diagnostic observes existing event-buffer mask/count accesses
and the end of the first configuration window. Its initial source passed 562
host tests and 53 packaged artifact checks. Exact procedure review requested
stronger observable attribution between the event batch and selected status
call, so it was not dispatched. Explicit status-NRDY witness hardening has now
passed 578 host tests, including 197 relevant integration tests. A new image
and exact procedure review remain necessary before physical use. These are
checks of a proposed diagnostic, not progress on power measurements.

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

Keep remaining work at M2: resolve the specific review finding, state which
observable outcomes change the next action, and permit no automatic repeat.
If the native result path remains unavailable, record the missing capability
and evaluate a supported independent debug interface. Do not expand the UI or
claim a full release to meet the calendar deadline.

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
