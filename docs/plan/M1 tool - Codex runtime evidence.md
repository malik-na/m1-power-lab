> Historical research snapshot dated 2026-09-26. Implementation-state statements below describe the project at the time of research and are superseded by the current [qualification status](../STATUS.md). Source and product behavior may have changed; recheck version-sensitive details before qualification.

# M1 tool — Codex runtime evidence

Research date: 2026-09-26. Scope: current local runtime observations and official OpenAI documentation relevant to the ThinkPad-hosted investigation tool. Design evidence only. No installation, authenticated request, model call, implementation, tests or hardware operation was performed. Credentials were not read.

## Recommendation

Use one **app-server-backed Codex adapter** owned by the coordinator. Prefer the supported Python SDK where its pinned version exposes the required protocol; use a small raw-RPC implementation inside that same adapter for missing stable operations. Do not run competing SDK and app-server orchestration loops. Keep the application journal, owner permissions and budget ledger authoritative.

The required phone interface is an application interface. It must not expose a general Codex control socket or terminal. The investigator, coder and reviewer receive different job scopes. They may use the same selected model, but the reviewer should begin with a fresh evidence packet and examine the exact procedure independently; separate invocation does not establish statistical independence or correctness.

## 1. What is installed here

Read-only observations from the current machine:

| Command/inspection | Result |
|---|---|
| `command -v codex` | `the user-local Codex executable` |
| `codex --version` | `codex-cli 0.155.1` |
| `codex app-server --help` | App-server command, local transports, schema-generation commands and remote Code Mode host option are present; CLI labels app-server experimental |
| `codex exec --help` | JSONL output, output schema, resume/fork/review, explicit sandbox, ephemeral and configuration-isolation options are present |
| Python module discovery for `openai_codex` | Not present in the current system Python import path |
| `python -m pip show openai-codex` | This system Python has no `pip` module |

This does not establish what exists in every virtual environment or what will be installed on the ThinkPad. CLI help is evidence of an interface, not evidence that account access, protocol compatibility or isolation works. The CLI emitted a read-only PATH-alias warning; version/help completed successfully.

## 2. SDK and protocol facts

The official Python package is `openai-codex`, requires Python 3.10 or newer, and is documented as stable. It controls local app-server over JSON-RPC and published builds include a pinned runtime. The documented defaults therefore differ from an arbitrary system CLI override. The SDK guide recommends the SDK for automation and app-server for custom-client concerns. [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)

App-server documents thread start/resume/fork/read; turn start/steer/interrupt; streamed item and terminal events; structured output; authentication/account methods; thread token-usage updates; and rate-limit reporting. Cancellation completion must be observed. Stable and experimental protocol surfaces are distinguished; generated schemas are runtime-version-specific. `thread/shellCommand` and experimental `process/*` execute outside the Codex sandbox. Restricted read roots are available, but the legacy read-only/workspace-write read-access default is broad. Dynamic tools and remote execution features require particular capability/version handling. [App-server](https://learn.chatgpt.com/docs/app-server)

Design implications:

- Pin SDK, runtime, protocol schema and model configuration as one qualified release. Do not silently pick up the user's globally upgraded CLI.
- Persist application job ID, runtime identity, thread ID, turn ID, instruction/configuration versions and evidence revision before execution. Resume by recorded identity, never “latest conversation.”
- Persist application events before forwarding them to the phone. Reconnection reloads authoritative application state; runtime conversation history is supplementary.
- A terminal model response is a proposed result. Validate schema, artifact references and policy before accepting it. A valid JSON shape does not establish scientific validity.
- Treat phone steering as an application command with a revision and acknowledgment. Deliver it to the next checkpoint, or deliberately steer the identified active turn; it never changes an approved in-flight procedure.
- On cancellation, stop admission first, request interruption, await a terminal state, and reconcile remaining tool processes separately. A lost runtime connection is not proof of job termination.

## 3. Isolation: a concrete design with a qualification requirement

Codex's Linux sandbox uses `bwrap` and `seccomp`. Official security guidance warns that a container with credentials exposed inside it does not by itself prevent credential exfiltration. [Agent approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security)

Permission profiles are beta. Legacy sandbox settings can override them. Command domain rules require an active proxy; they do not constrain model traffic, MCP, apps, browser or other separate surfaces. Restricted filesystem roots and default blocking of private/local proxy destinations are documented, subject to Linux enforcement support. [Permissions](https://learn.chatgpt.com/docs/permissions)

Configuration includes a default-shell toggle, a separate unified-exec flag, and controls for apps, multi-agent behavior and Code Mode. The shell toggle alone is not documented as disabling every file or execution tool. [Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

MCP supports explicit tool allowlists, per-tool controls and required servers whose startup failure can prevent operation. The MCP server's process and transport need their own isolation. [MCP documentation](https://learn.chatgpt.com/docs/extend/mcp)

**Proposed arrangement, not a verified property of this machine:**

1. The coordinator/hardware process owns execution policy, journal mutation and the target transport. The owner interface is a separate authenticated entry point. Neither is in an experiment workspace.
2. A dedicated runtime account and outer mount/PID/network isolation separate Codex from the owner's home, target devices, coordinator implementation, operator socket, Tailscale socket and host loopback services. Give the runtime a private control connection to its adapter, not arbitrary host-network access.
3. The trusted Codex harness needs authentication. Keep its auth store outside model-readable roots and outside application-managed build/analysis workers. Give native model tools an inner restricted-read sandbox, minimal environment, job-specific writable directory and no permission escalation. Default workspace-write alone is insufficient.
4. Application-owned build/analysis tools execute as a separate credential-free worker identity with no host devices, control sockets or owner network routes. A narrow broker accepts job-scoped evidence/proposal operations; it has no owner-approval or hardware-dispatch operation available to the model.
5. Disable unrelated apps, browser/computer-use, inherited plugins/hooks, autonomous child agents and other capabilities. Public technical research uses approved retrieval surfaces. Native tools are admitted only after the actual exposed catalog and execution routes are qualified.
6. If an exposed native tool cannot satisfy the boundary, disable it and route that function through an application-managed tool. If the pinned runtime cannot make this arrangement enforceable, that runtime cannot qualify for live operation. Do not solve it by granting full access or replacing the boundary with prompt instructions.

A separate UID protects against other accounts; it does **not** separate a credential-bearing harness from a same-UID child. A network namespace protects against the host network only if bridges/proxies and inherited descriptors cannot bypass it. Screening output is useful, but cannot make an already-readable credential inaccessible.

**Future qualification evidence must cover:** every exposed built-in and application tool; direct and symlink reads; `/proc`, environment and inherited descriptors; writes to runtime configuration/control code; Unix/abstract sockets; IPv4/IPv6 loopback and private addresses; device access; escalation requests; additional tool discovery; and subprocess survival after interruption. Use synthetic secrets/canaries for these checks. No real credentials belong in test fixtures or the research journal.

The combination of outer OS isolation, inner restrictions and separate tool workers is a feasible design direction. Documentation alone does not prove that the selected runtime enforces every required boundary. Qualify it before attaching hardware, and repeat qualification after runtime or policy upgrades.

## 4. Jobs, review and continuation

The non-interactive interface provides JSONL events and final usage fields, schema-constrained output, saved authentication reuse and session-ID resume. It is a useful diagnostic/fallback implementation route, but the tool should not grow a second public execution path around it. [Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)

Codex Goals persist within threads and continue at idle boundaries. They are not a global application state machine. [Goals documentation](https://developers.openai.com/cookbook/examples/codex/using_goals_in_codex)

For this tool, the coordinator should schedule bounded jobs and hold the continuing research objective. Keep runtime auto-continuation and uncontrolled child spawning off initially. Admit helper/reviewer work explicitly, with application job records, deadline and usage accounting. This prevents nested schedulers from continuing after the application has paused. Job prompts contain a stopping condition, expected artifact schema, allowed inputs and the next decision they support.

Fresh review should receive the proposed procedure, exact artifacts, relevant evidence, recovery prerequisites and possible failure consequences. The author may correct defects; a revised procedure needs a new review. Unresolved substantive disagreement remains visible to the owner. No reviewer grants hardware permission.

## 5. Token, time and service limits

The inspected documentation establishes usage reporting, but this audit did not establish a strict aggregate application token ceiling that aborts an in-flight model request with zero overshoot. No `max_tokens`/`max_output_tokens` application cap was found in the inspected Codex configuration reference. Absence from that search is not proof that no related runtime capability exists; it is a qualification question.

Required application policy:

- Retain **3 active hours or 100 million Codex tokens, whichever first**, as the user's default allowance. This is permission to use resources, not a prediction of available account quota or required work.
- Count actual input plus output once per completed usage interval. Preserve cache/reasoning details as subcategories after verifying the pinned runtime's counter semantics. Do not blindly sum cumulative thread snapshots or add subcategories twice.
- Account for investigator, coding, reviewer, helper and owner-chat calls attributable to the session. At exhaustion, controls/status/approvals still work without paid model generation; further model conversation requires a grant.
- Reserve estimated allowance before dispatch, limit concurrent jobs and monitor usage. Stop new work at the threshold and interrupt in-flight reasoning. Record any overrun, missing terminal usage and the accounting uncertainty; never record unknown as zero.
- Check cumulative-vs-incremental fields, compaction, retries, child jobs, fork history and interrupted turns during runtime qualification. A local tokenizer estimate is not the billing authority.
- A time reset changes the remaining active-time allowance without resetting lifetime consumption. While draining in-flight work, time remains active. Once settled, deliberate pause/approval/service-wait states do not burn the active allowance.

ChatGPT and API-key access have different billing and administrative policies; API keys are the documented default for generic automation. Headless device-code login is available subject to account settings. Preserve the user's requested supported local Codex-account path, but verify that account and unattended refresh on the ThinkPad instead of assuming entitlement. [Authentication](https://learn.chatgpt.com/docs/auth)

Included usage depends on plan/model/workload and may be constrained before the local allowance is exhausted. Credits, tokens and API expenditure are different quantities; API-key work is usage-billed. [Pricing and usage](https://learn.chatgpt.com/docs/pricing)

The application must distinguish local-budget exhaustion, service quota/rate limiting, temporary network failure, expired login and model unavailability. Bounded retry/backoff handles transient faults; authentication or quota problems enter an explicit wait state. Raising the tool's allowance does not buy credits or reset service limits. Never change auth mode, buy capacity or switch provider implicitly.

## 6. Future provider seam

Codex supports configurable providers and provider-specific transport/authentication. This is not a guarantee that every provider supplies equivalent reasoning, tools or lifecycle behavior. [Advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced)

Keep a small application interface for start/resume/cancel, streamed lifecycle, usage and validated artifacts. Before a second provider is enabled, qualify its accounting, context, cancellation, isolation and data policy, and require an explicit allowance policy. Preserve native provider metadata. Do not silently reuse Codex token balances or treat OpenAI account credits as portable.

## 7. Changes required in the plan

1. Specify one app-server-backed runtime adapter, a pinned capability contract and a single coordinator scheduler.
2. Add runtime isolation qualification before live-target work; leave credential separation unproven until the actual tools and OS boundary pass it.
3. Add explicit job/event/usage reconciliation and cancellation of surviving processes.
4. Keep Codex runtime approvals separate from exact hardware-procedure approvals; exclude unrestricted execution endpoints from application routing.
5. Specify chat usage, service-wait states, overshoot and missing-usage semantics. Do not promise a zero-overshoot token stop.
6. Add account login/refresh and available quota to readiness, without making an API-key migration or paid call part of this design revision.

These are planning corrections. Implementation remains on hold.
