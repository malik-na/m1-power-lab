# M1 investigation tool — implementation plan

Revision: 2026-09-26, reconsidered from the hardware and scientific requirements and simplified for a personal lab. **Implementation is active in `the project checkout`; real hardware remains disabled until M2 qualification.** Follow the [design](M1%20investigation%20tool%20-%20design.md). The [requirements and gap audit](M1%20investigation%20tool%20-%20requirements%20and%20gap%20audit.md) maps each requirement to design decisions and future proof.

## Delivery strategy

Build a complete Codex-led workbench on the ThinkPad. Jev has no implementation or evaluation milestone. Qualify the hardest assumptions early: actual host/runtime isolation, native result transport, recovery and a power measurement capable of answering the question.

The sequence is **readiness → minimal controls/runtime qualification → supervised hardware and measurement proof → scientific automation and remote UI → real investigation → confirmation and release**. The full phone UI and autonomous research loop must not precede evidence that the target arrangement can produce useful measurements.

The checkout may implement and exercise host-only/replay behavior. Model calls and hardware operations remain gated. Live acceptance evidence below is future work on the actual ThinkPad/Mac.

## M0 — Readiness and qualification plan

**Entry:** implementation hold lifted; actual ThinkPad access. Host-only readiness may proceed while physical prerequisites are arranged.

Deliver:

- A versioned host/target inventory: Linux distribution, resources/storage, physical target identity, cable/port mapping, USB permissions, current boot/proxy arrangement and physical attendance.
- A source/dependency baseline: current working Asahi kernel and relevant upstream status, m1n1 commit, AArch64 toolchain and required Rust/Python/build dependencies. No experimental upstream patch is installed just because it exists.
- A pinned Codex SDK/runtime/model and capability checklist: authentication, thread/job lifecycle, structured results, interruption, counters, quota reporting and permission controls.
- A credential placement and worker-isolation design for the actual host. Enumerate every enabled model/tool/network route; disable inherited hooks/plugins and uncontrolled child scheduling.
- A target capability/recovery matrix: proxy, hypervisor, native channel candidates, software reboot, physical/independent reset, firmware recovery, and what needs owner presence.
- A measurement fixture proposal: native desktop/display workload, power boundary, available sensors, USB/charging arrangement, and whether extra equipment may be needed.
- A readiness list for owner-only Tailscale access and the actual iPhone's Home Screen/push support.

**Exit:** each prerequisite is observed, documented-only, missing or unqualified; no historical Mac preflight is presented as current ThinkPad proof. Setup actions needing local Recovery authentication or boot-policy changes have exact owner instructions and separate approval. Missing hardware blocks only dependent live work.

## M1 — Minimal coordinator, journal, CLI and runtime qualification

**Entry:** host readiness. No target device is exposed to a model process.

Deliver a narrow working slice:

1. Core record schemas and migrations; stable identities/revisions, target boot epochs, staged immutable artifacts, SQLite transitions and disk reserve.
2. Session/job/operation state, durable command inbox and events, sole coordinator lease, intent/outcome records and restart reconciliation.
3. CLI status/evidence/start/steer/pause/resume/stop plus exact approve/deny/revoke commands. Owner and worker channels have different authority.
4. Budget ledgers/reservations, deduplicated usage, active-time segments, extension/reset epochs and non-AI controls after exhaustion.
5. Typed procedure/eligibility checks, repeat/expiry scope and artifact-bound approval. Replay/synthetic transports are explicitly labeled.
6. Minimal exact-artifact procedure review: structural checks, a separate reviewer job, blocking-finding resolution and approval invalidation on relevant revision changes. This path exists before any live procedure.
7. One app-server-backed Codex adapter through the pinned SDK or stable RPC behind the same interface. Start with one job; add resume, interruption, schema validation and usage reconciliation.
8. Bounded Codex/build subprocesses with no sudo or direct target-device access, scoped workspaces and installed control code outside their writable paths. Operator actions cannot be routed through model tools.

**Runtime qualification:** inventory the enabled tools, confirm workers cannot open target devices or modify installed control code, and check interruption/process cleanup. Keep credentials out of worker workspaces and evidence. Add stronger isolation only when a concrete route violates these personal-lab controls.

**Accounting qualification:** establish cumulative versus incremental counters, fork/resume history, compaction, retries and interrupted-turn reporting. A missing hard token cap is recorded as a limitation; application admission/reservation/interruption still apply. Login refresh and service quota handling are qualified without assuming the 100-million-token allowance is available account capacity.

**Failure containment qualification:** every admitted job has a coordinator lease, deadline and supervisor-enforced process-group/cgroup cleanup. Coordinator loss cannot leave paid work running indefinitely. Unknown usage blocks further model work until reconciled or bounded by evidence; an owner allowance decision may preserve uncertainty but cannot erase it.

**Exit evidence:** a scoped Codex job can read permitted evidence, produce a validated artifact, be interrupted/reconciled and resume from records. Synthetic offline traces demonstrate stale/revoked approval refusal, duplicate command handling, unknown effects, resource exhaustion and history-preserving resets. Isolation holds for the enabled tool catalog. This milestone does not establish hardware safety or scientific validity.

## M2 — Supervised transport and measurement feasibility

**Entry:** M1 controls and isolation; actual host/target connection; approved setup and exact live procedures; required physical attendance.

Deliver:

- A qualified proxy connection identified independently of changing tty enumeration numbers, with matching m1n1 versions and a boot-epoch record.
- A live hardware adapter behind the coordinator: exclusive ownership of target interfaces, typed operations, dispatch rechecks, bounded capture/timeouts and reconciliation of unknown effects. No live operation bypasses this adapter.
- The M1 exact-artifact review path applied to every new live procedure; blocking findings are resolved before dispatch and relevant revision changes invalidate approval.
- A bounded observation using understood memory/register effects, with complete artifact capture through the real coordinator.
- An isolated, reproducible host build of the known-good payload/kernel/DTB/initramfs needed for subsequent modes.
- A deterministic, finite native experiment harness and a **demonstrated native result channel**. Prefer an available supported channel; qualify gadget serial on the actual kernel if attempted, or document the need for a debug interface. Neither capability is inferred from generic USB support.
- Separate mode transitions: proxy → payload/HV → result/return where needed; proxy → native experiment → complete result → return/re-identification. Record unavailable interruption during native windows.
- Qualified recovery per mode: reconnect, responsive reboot and physical/independent reset as available. Use safe demonstrations; no destructive firmware restore merely to claim readiness.
- A pilot native screen-on idle fixture: real sensor provenance/cadence, power paths, stability, collector overhead, missing-sample behavior and preliminary uncertainty.

**Exit evidence:** transport and measurement qualification are recorded separately. Transport qualifies when the adapter completes required mode round trips and recovery evidence. Measurement qualifies only when a complete native run returns attributable results and the pilot shows a plausible way to resolve the required power effect with stated uncertainty. Identifying a missing instrument leaves measurement qualification pending and blocks native confirmation. Keep a known-good image and recovery instructions.

**If qualification fails:** retain the failure evidence and state the missing capability/equipment with a bounded next attempt. Host development and eligible mechanism research may continue, but native confirmation and release claims remain blocked. Do not use hypervisor power, model confidence or a minimal mock fixture to declare this milestone complete.

## M3 — Scientific investigation and artifact pipeline

**Entry:** M1; M2 evidence before enabling autonomous live selection. Offline development can run against labeled captured/replayed evidence.

Deliver:

- Scoped jobs for investigation, artifact implementation, analysis, review and conclusion, with schemas and evidence manifests.
- Durable active hypotheses, predictions, strongest counterevidence, alternative experiments and compact current briefs. Restart/compaction must preserve failures and unresolved questions.
- One primary investigator with bounded helpers; all jobs use the same scheduler/accounting path. No nested autonomous scheduler.
- Candidate selection based on decision relevance, discrimination, total cost and recoverability. Require a redesign after repeated uninformative experiments.
- Isolated worktrees/build manifests, reproducible artifact hashes, screened evidence views and a proposal-promotion path. New target capabilities cannot arrive as arbitrary privileged host scripts.
- Structural checks and separate initial procedure review, resolution of blocking findings, exact owner approval and scoped repeat execution.
- Measurement protocol records, data-quality checks, time-weighted calculations, exploration/confirmation separation, analysis provenance and scientific outcome categories.
- Local research reports containing claims, supporting/contradicting evidence, reproducible procedures, known limits and the next useful decision.

**Exit evidence:** recorded cycles demonstrate evidence changing the leading explanation, a cheaper discriminating experiment being selected, a contradicted hypothesis being closed, and invalid/inconclusive results remaining distinct from a negative finding. The workflow handles a job restart without erasing prior evidence or expanding authority. Synthetic demonstrations qualify logic only; M5 supplies live scientific evidence.

## M4 — iPhone, Tailscale and host availability

**Entry:** M1 command/event contracts; Codex conversation uses M3 job scopes. Can proceed alongside M2/M3 once interfaces stabilize. Required before unattended remote sessions.

Deliver:

- CLI parity and four responsive iPhone views: overview, experiment/evidence, approvals/recovery and conversation.
- All owner controls: start, steer, approve/deny/revoke, pause/resume/stop, token increment, custom time extension/reset, evidence inspection/export and budgeted chat.
- Private Tailscale HTTPS with owner restriction, trusted ingress, origin/CSRF protection, request IDs/revisions and worker-network exclusion. No public endpoint or general terminal.
- SSE cursor/replay, snapshot recovery, command acknowledgments and visible live/stale/offline state. Never cache an actionable approval for offline automatic submission.
- Home Screen installation and generic permission-based push for approval, recovery, budgets and completion. Denial/delay must leave the authoritative queue intact.
- AC-powered lab mode, sleep inhibition, observed lid behavior, host power/thermal state and defined AC-loss/shutdown response.

**Exit evidence:** the actual iPhone 12 mini can complete the owner workflow through Tailscale. Browser closure does not terminate the host; reconnect shows current state. Duplicate taps/stale cards cannot dispatch extra operations. Notification delivery works when enrolled, with documented limitations. Worker processes cannot spoof a local owner request. Lab-mode exit restores prior sleep behavior.

## M5 — Complete a real bounded investigation

**Entry:** M2 measurement/recovery qualification and M3 scientific workflow; M4 before remote unattended operation. Available local/account budgets and required owner attendance/approvals.

Deliver:

1. A pilot-supported measurement protocol and declared native fixture, including regression sensitivity and uncertainty limits.
2. A broad initial source/baseline comparison of reporting, device activity, wakeups and CPU-idle behavior; then one bounded question selected from actual evidence.
3. Multiple live observe → hypothesis → experiment → result cycles, with predictions and costs recorded beforehand.
4. Capture reuse and narrow analysis without losing counterevidence, failed runs or configuration provenance.
5. A report that distinguishes validated mechanisms, contradicted mechanisms, unresolved questions and the exact scope of any conclusion.
6. A minimal candidate patch and its frozen confirmation proposal when justified; otherwise a defensible bounded negative conclusion supported by adequate experiments.

**Exit evidence:** at least one real investigation reaches either a defensible bounded negative/below-target conclusion or a candidate entering frozen confirmation with all selection history recorded. An inconclusive confirmation returns to this research stage or an explicit resource/prerequisite wait; it cannot be promoted to a completed positive result. Additional sessions/grants may be needed; no promised breakthrough or arbitrary session count.

## M6 — Confirmation, reliability and first release

**Entry:** M5. Candidate confirmation applies only when a candidate exists; operational acceptance always applies.

For a candidate:

- Freeze the build, native fixture, primary outcome, trial order/count, exclusions, analysis, uncertainty and regression checks before fresh confirmation data.
- Use randomized matched baseline/changed blocks plus revert checks, accounting for dependence and measurement uncertainty.
- Apply the design default: the 95% lower uncertainty bound establishes at least 10% improvement, and no repeatable performance/responsiveness regression is found within the predeclared sensitive checks.
- Use an unaffected measurement path for telemetry-changing patches. Treat insufficient precision as inconclusive; never promote an exploratory or cherry-picked result.
- Preserve all failed candidates. Report the exact scope of a successful result. Persistent deployment remains a separate approval.
- Apply the predeclared candidate-selection/multiplicity policy before promoting one successful candidate among repeated attempts. A point estimate below the frozen uncertainty rule, or an inconclusive confirmation, returns to research and does not complete the investigation.

For the workbench:

- Exercise the operational scenarios below through public module interfaces, with replay/fault injection where physical disruption is inappropriate.
- Demonstrate consistent backup/restore, artifact integrity, disk quota response and schema/update rollback under supported conditions.
- Package pinned installation/update procedures, operator quickstart, recovery guide and local diagnostics usable without the model/UI.
- Record the actual host/target/runtime/tool/policy versions qualified for release. A relevant update invalidates dependent qualification until rechecked.

**First-release acceptance:** all owner controls work on the actual phone; access/isolation/approvals/budgets hold; target uncertainty and recovery are reported honestly across supported failures; one real multi-cycle investigation has completed with reproducible evidence and a supported bounded conclusion. A validated patch is a possible research result, not a guaranteed release prerequisite. A bounded negative or below-target result qualifies; an inconclusive confirmation, unexplained failure or offline-only demonstration does not.

## Operational acceptance scenarios

These are future checks, not tests executed during planning.

| ID | Scenario | Required evidence |
|---|---|---|
| A01 | Wrong target, unknown mode, changed boot epoch or unmet prerequisite | Dispatch rejected with exact reason |
| A02 | Source/payload/procedure changes after approval; approval revoked/expired | Old authorization cannot dispatch new work |
| A03 | Duplicate phone command, concurrent jobs, second coordinator | One authoritative command/target owner; no duplicate dispatch |
| A04 | Crash before intent, after intent, after USB effect, before outcome commit | Correct no-effect/unknown-effect distinction; no blind replay |
| A05 | Artifact publication interrupted or journal refers to missing data | Partial/orphan/missing state detected; no invented complete evidence |
| A06 | Proxy/HV success followed by native channel loss | Native outcome stays unknown; no inference from the other mode |
| A07 | Target hang, USB loss, wrong device reconnect or unavailable recovery | Only qualified bounded recovery; physical assistance clearly requested |
| A08 | Runtime stream timeout, interrupted job, surviving child process | Existing handles reconciled; no accidental duplicate paid job |
| A09 | Cumulative usage, retries, resume/fork/compaction, missing usage | No double counting or zeroing of unknown consumption |
| A10 | Time/token limit during work; account quota/login failure | New work stops; cleanup only; overrun/service wait recorded |
| A11 | Token addition, time extension/reset or host clock change | New allowance epoch; lifetime history and correct active time preserved |
| A12 | Forbidden credential/device/socket/private-network access through each tool | OS/tool controls deny access using synthetic canaries |
| A13 | Forged owner identity, CSRF, stale card or offline approval | No unauthorized command; current revision/authentication required |
| A14 | Phone closes, Tailscale drops, push denied/delayed | Host remains authoritative; reconnect/pending queue accurate |
| A15 | AC loss, lid close, shutdown request, thermal fault | Qualified admission/cleanup behavior; no promise beyond tested conditions |
| A16 | Low disk, database/backup interruption, schema update failure | Reserve maintained, captures paused, consistent restore/rollback |
| A17 | Correlated/derived sensors, missing readings, drift or telemetry-changing patch | Invalid independence/power claim rejected; provenance retained |
| A18 | Favorable point estimate below uncertainty threshold or unverified regression | No validated-improvement/deployment recommendation |
| A19 | Repeated uninformative experiments or contradicting evidence | Redesign/branch update rather than automatic repetition |
| A20 | Model-generated approval, injected source instruction or control-code patch | Proposal cannot grant authority or modify running policy |

## Implementation shape and working order

Organize the checkout around the five modules in the design, plus installation/operations documentation and future acceptance fixtures. Keep schemas and command/event contracts versioned. Build small vertical slices through those interfaces; do not begin with a general workflow engine or a large dashboard.

Use Python, the qualified local Codex adapter, SQLite/artifacts, FastAPI/server-rendered HTML with a small TypeScript client, SSE and a shared CLI command interface. Add native code for payload needs or measured bottlenecks. Pin versions in M0 and record later changes.

Suggested dependency order:

- M0 → M1 → M2 is the critical feasibility path.
- M3 offline work and M4 interface work can proceed after M1 contracts stabilize.
- M3 live autonomy requires M2; remote unattended work also requires M4.
- M5 requires the live scientific path; M6 completes release evidence.
- Failed physical qualification must remain visible while independent host work progresses.

## Historical records and project maintenance

Preserve earlier research and the old Jev controller as historical artifacts; neither becomes the new runtime or live prerequisite evidence. Import only with original dates and explicit historical status. Preserve this design/plan and the three supporting evidence notes in the eventual project checkout.

Installation/update actions are reviewed against actual host permissions and existing configuration. Keep workers unable to install their own control changes. Back up before settled-state migrations; never update mid-experiment. No calendar estimate is credible until M0/M2 expose the physical and measurement constraints.
