# M1 investigation tool — requirements and gap audit

Revision: 2026-09-26. This audit records how the current design and implementation plan cover settled requirements. It is a planning verification artifact, not evidence that implementation or hardware qualification has occurred.

| Requirement | Current location | Proof still required |
|---|---|---|
| ThinkPad T480 is sole host; M1 Mac is USB/m1n1 target | Design §§1–3; plan M0/M2 | Actual host inventory, cable/proxy and target identity |
| No target desktop, SSH, package manager or resident agent assumed | Design §3 | Image/harness and result-channel qualification |
| Codex investigates; coordinator enforces | Design §§4–6; plan M1/M3 | Scoped jobs, rejected unauthorized proposals and live cycles |
| Jev entirely omitted | Design §1; plan delivery/history | No Jev runtime, key, configuration or dependency in checkout |
| Future provider option without first-release framework | Design §§1,6,14 | Adapter qualification only if later requested |
| Authority separation and worker isolation | Design §5–6; plan M1/M2 | OS/tool canary evidence and adapter dispatch records |
| Exact review and owner approval | Design §8; plan M1/M2/M3 | Revision-bound review/approval and stale-card rejection |
| Risk, recovery and physical attendance | Design §§8–9; plan M0/M2/A07 | Setup-specific recovery demonstrations and cards |
| Unknown USB effects never replayed | Design §§7,10; plan A04/A06/A07 | Fault-injection/replay and live reconciliation |
| Native transport not inferred from proxy/hypervisor | Design §3; plan M2/A06 | Demonstrated native channel and return/re-identification |
| Measurement can resolve whole-device idle power | Design §12; plan M2/M5/M6 | Sensor/provenance pilot, observer-effect and uncertainty evidence |
| ≥10% improvement with fresh confirmation and no regressions | Design §§1,12; plan M6/A18 | Frozen protocol, interval lower bound, fresh blocks and regressions |
| Exploration/confirmation and repeated-candidate selection controlled | Design §12; plan M3/M6 | Frozen confirmation and declared multiplicity policy |
| Scientific outcomes remain distinct | Design §12; plan M3/M5/M6 | Result records and release decision |
| 3 active hours or 100M Codex tokens; extensions/resets preserve history | Design §11; plan M1/M4/A09–A11 | Usage reconciliation and allowance epochs |
| Unknown usage cannot become false zero | Design §11; plan M1/A09–A10 | Crash/restart ledger evidence or explicit uncertainty decision |
| Runtime cannot continue paid work indefinitely after coordinator loss | Design §§10–11; plan M1/A08 | Supervisor lease/deadline/process cleanup evidence |
| iPhone 12 mini, Tailscale-only, push and stale/offline handling | Design §13; plan M4/A13–A15 | Actual-phone workflow and reconnect/notification evidence |
| Evidence policy excludes credentials, personal data and unrelated private contents | Design §§5–6; plan M1/A12 | Synthetic canaries, release manifests and local review |
| Durable journal, quota, backup and restore | Design §7; plan M1/M6/A05/A16 | Crash/backup/restore/quota evidence |
| Host-only implementation authorized; live hardware remains gated | Design/plan headers | M2 qualification and exact approvals before target access |

## Unresolved by design

The audit intentionally does not claim actual proxy access, native result transport, sensor quality, recovery, iPhone push support, Codex account entitlement or runtime isolation. These remain M0–M2 qualification gates. A documented interface, source note or model proposal cannot satisfy them.

No calendar estimate is assigned until physical and measurement prerequisites are observed. Host-only application development is authorized. Boot-policy changes, live hardware operations, model spending and target deployment remain gated by the design.
