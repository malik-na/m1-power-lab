> Historical research snapshot dated 2026-09-26. Implementation-state statements below describe the project at the time of research and are superseded by the current [qualification status](../STATUS.md). Source and product behavior may have changed; recheck version-sensitive details before qualification.

# M1 tool — measurement and scientific workflow evidence

Research date: 2026-09-26. Scope: gaps in the current [design](M1%20investigation%20tool%20-%20design.md) and [implementation plan](M1%20investigation%20tool%20-%20implementation%20plan.md). This is research and proposed design detail, not a record of experiments. Implementation remains on hold. No target operation, test or model evaluation was run.

## 1. Findings that change the plan

**The sensor name does not establish its measurement boundary or independence.** Linux defines units and distinctions between charge, energy, percentage capacity, instantaneous readings and hardware averages; drivers may omit unsupported properties. Inventory actual fields, sign conventions, update cadence and driver implementation before selecting an outcome. [Linux power-supply class](https://kernel.org/doc/html/next/power/power_supply_class.html)

The current upstream `macsmc-power.c` reads battery `POWER_NOW` from SMC key `B0AP`, but derives `ENERGY_NOW` from remaining charge and a fixed nominal voltage. Its AC `INPUT_POWER_LIMIT` is a limit, not a measured draw. Charging-control capabilities depend on available firmware keys. Consequently, battery energy estimates, voltage/current products and battery power require provenance; displaying several of them does not establish independent instruments. These are facts about the inspected source, not a claim that this target runs it. Pin the actual kernel commit during readiness. [Upstream driver source](https://raw.githubusercontent.com/torvalds/linux/master/drivers/power/supply/macsmc-power.c)

**CPU-idle statistics are mechanism evidence.** Kernel documentation says software idle time can overstate physical residency and an idle state's `power` attribute should not be relied on for meaningful power estimates. Fewer wakeups or a larger idle-time counter therefore cannot certify the requested whole-device reduction. [CPU idle documentation](https://www.kernel.org/doc/html/latest/admin-guide/pm/cpuidle.html)

**The baseline must include current upstream work.** Asahi's current M1 table lists battery information upstream in 7.1 but cpuidle in `linux-asahi`. Its August 2026 report describes ongoing PSCI/UEFI work and explains why the downstream driver still exists. Baseline against the appropriate working Asahi stack, with the actual driver/configuration captured, rather than claiming a discovery from an obsolete or missing-feature kernel. This does not authorize adopting experimental upstream patches. [M1 support table](https://asahilinux.org/docs/platform/feature-support/m1/), [Asahi August report](https://asahilinux.org/2026/08/progress-report-7-2/)

**Native confirmation needs its own control/result path.** The m1n1 documentation distinguishes direct Linux boot from hypervisor execution; direct native boot cannot be treated as a perpetually available proxy shell. Freeze a host-prepared measurement image and deterministic collector, its return/result channel and recovery procedure. Heavy tracing belongs in mechanism discovery; final power trials use native Linux with a characterized low-overhead collector. [Linux bring-up documentation](https://asahilinux.org/docs/sw/linux-bringup/), [m1n1 user guide](https://asahilinux.org/docs/sw/m1n1-user-guide/)

## 2. Recommended measurement contract

Create a versioned **measurement protocol** referenced by every experiment and result. Its required fields are:

- The estimand: whole-device average power for the specified native Linux screen-on idle fixture; improvement `100 × (1 − mean_changed / mean_baseline)`. A SoC rail result is a separate outcome.
- Exact kernel/configuration, firmware, boot artifacts, root filesystem, collector and analysis hashes. Record whether any component under investigation also produces the measured telemetry.
- Static screen content, brightness setting, refresh mode, lid state, keyboard lighting, radios/link state, peripherals, services and idle workload. Freeze the actual desktop fixture; a minimal framebuffer environment only supports a claim about that environment.
- Energy boundary and power arrangement: battery discharge, DC input, or wall input; all sources/sinks; battery state-of-charge band; charging state; temperature/stability range; USB role and attachment.
- Warm-up and stabilization rule with a maximum wait; sample cadence; capture duration; averaging/integration rule; clock domains and alignment; predefined data-quality exclusions.
- Trial order, reset/boot requirements, block definition, number of independent trials, uncertainty analysis, confirmation data boundary and stop rules.
- Regressions to measure and the measurement resolution needed to assess them; artifact/version bound to the claim.

For each valid run, calculate average power as energy over elapsed measurement time, or the time-weighted integral of valid instantaneous power samples divided by elapsed time. Never silently treat irregular samples as equally spaced; never turn a missing reading into zero. Preserve dropouts, raw timestamps and rejected runs, with reasons determined by protocol rather than treatment outcome.

### Power arrangements and observer effects

Prefer a verified battery-discharge arrangement for battery-life claims. A connected USB cable may supply energy and change controller behavior, so battery discharge alone may omit part of the load. Confirm every energy path; if separation cannot be established, scope the result to the tethered arrangement or pause its promotion to a general battery-life claim. Inhibiting charging is not proof that the battery supplies the whole machine.

An external USB-C meter measures input at its insertion point. Battery charging/discharging and conversion losses still matter; a wall meter includes charger losses. Changing power arrangements changes the quantity measured. Characterize meter resolution, accuracy and sampling at the actual idle level before purchase/use is proposed. Merely adding an external instrument does not fix a mismatched energy boundary.

Pilot collector-off versus collector-on conditions and restrained versus heavy tracing where feasible. Include any polling, display workload and USB dependency in the fixture. Readiness must produce an uncertainty/observer-effect budget showing that the method can resolve the claimed reduction; extra repeats do not remove systematic sensor bias. If a candidate changes telemetry computation, an unaffected measurement path becomes necessary for confirmation.

These are proposed controls inferred from measurement boundaries, not verified properties of the user's setup.

## 3. Exploration, confirmation and statistical stopping

Use two explicit stages. Exploration may adapt hypotheses, capture lengths and candidate patches. Confirmation freezes the candidate, primary outcome, analysis and trial count before new data are collected. Keep exploration results out of the confirmatory estimate. If confirmation leads to patch or analysis changes, create a new exploratory revision and new confirmation data; keep every attempt visible.

**Default trial design:** matched baseline/changed trials, randomized AB/BA order within blocks, with reset/warm-up between treatments. Block on practical nuisance factors such as measurement session and state-of-charge band. Include a return-to-baseline/revert check to reveal persistent state and drift. An A/B/A sequence alone can be useful diagnostically but repeated unrandomized order can confound time with treatment. Record any technical restriction on order. This follows the role of blocking and randomization described by NIST. [Randomized block designs](https://www.itl.nist.gov/div898/handbook/pri/section3/pri332.htm)

Use whole independently restarted trial/block results as replicate units. Hundreds of adjacent sensor polls are not hundreds of independent experiments. Inspect run trends and autocorrelation in the pilot; aggregate correlated samples and use a documented block/paired analysis. If between-block dependence persists, collect across suitably separated sessions or use a justified dependence-aware method. [NIST autocorrelation](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35c.htm)

Do not invent a universal “five runs” rule. Choose the fixed confirmation sample size from pilot variability, required precision, the practical decision threshold and available resources. If the required precision cannot fit the budget, request a concrete extension or report an inconclusive result. NIST explicitly makes sample size conditional on variability and the desired error/decision risks. [Sample-size planning](https://www.itl.nist.gov/div898/handbook/prc/section2/prc222.htm)

**Recommended claim rule:** estimate the percentage reduction with a predeclared 95% interval at the trial/block level, including material measurement uncertainty. Declare the “at least 10%” target established only when its lower bound is at least 10%, new confirmation data agree, and regression criteria pass. A 12% point estimate with a 2–22% interval demonstrates possible improvement but does not establish the 10% target. This lower-bound rule is a proposed explicit interpretation of the goal, not a rule already supplied by the user.

Use a reviewed implementation of the chosen paired/block interval method; preserve pairing and account for uncertainty in the baseline denominator. Default to a fixed confirmation batch and one final decision analysis. Monitor collection for safety and predefined quality failures, but do not stop early merely because a favorable interval appears. Multiple candidate confirmation attempts require a documented multiplicity policy before any family-wide statistical claim; the complete candidate/attempt history must remain visible.

**Independence has separate meanings:** fresh confirmation trials can independently reproduce a result using the same characterized sensor. They do not independently validate that sensor. Corroboration from an unaffected sensor/method is a separate claim; a second model review is neither kind of physical confirmation.

## 4. Outcomes and regressions

Use distinct result states:

| Result | Meaning |
|---|---|
| Validated improvement | Frozen candidate meets the power target under its stated fixture, uncertainty rule and regression contract |
| Below target | Adequate data put the improvement below 10%; this can coexist with a smaller real benefit |
| Bounded negative finding | A named mechanism or candidate fails its predeclared predictions within stated conditions/resolution |
| Inconclusive | Precision, conflicting results, invalid assumptions or missing observations prevent a decision |
| Invalid experiment | Prerequisites or capture/protocol validity failed; its artifacts remain evidence about the failure |
| Stopped/blocked | Resource, permission or physical prerequisites ended work; this is not a scientific negative result |

A confidence interval crossing zero does not prove equivalence. Similarly, an inconclusive branch does not prove that M1 power management has no remaining improvements.

Regression confirmation should cover CPU throughput, short idle-to-work latency, relevant interactive/display latency, functional errors and affected device paths. Add suspend/resume when the candidate can affect it. Freeze representative workloads and timing definitions before confirmation. A reproducible degradation blocks adoption even if power passes. If the measurement cannot assess an affected behavior, mark that regression dimension unverified; do not report “no regression” from a noisy nonsignificant comparison. Set practical resolution targets during pilot and disclose the bounds of the resulting claim. Changing the user's no-repeatable-regression requirement into an allowed slowdown would require an explicit scope change.

## 5. Efficient research decisions without confidence scores

Maintain a small active frontier of mechanisms with source evidence, counterevidence, predictions and unresolved assumptions; archive rather than repeatedly reprompt on inactive branches. Each selected experiment states which observed outcomes would alter the next engineering action and which outcome would be uninformative.

Choose an eligible experiment by a short comparison of decision relevance, discriminating power, total cost, recovery burden and reuse of existing setup/data. Give a concrete reason for rejecting the cheaper alternative. Numerical probability or utility scores are unnecessary unless their inputs have defensible meanings.

Recommended operational defaults:

1. Inspect existing source/captures before a new hardware run.
2. Investigate one bounded question at a time; parallelize independent reading/analysis only.
3. After two consecutive experiments that fail to discriminate the same hypotheses, require a brief redesign checkpoint before more of the same procedure. This triggers reconsideration rather than automatic abandonment.
4. Stop a branch when its discriminating predictions are contradicted under adequate conditions; switch to another eligible branch or record the bounded conclusion.
5. When no affordable eligible experiment can change a consequential decision, checkpoint with the missing prerequisite and the next useful experiment. Budget exhaustion alone produces a resource-limited conclusion.
6. After every decisive result, update evidence and the frontier once. Do not re-plan per trace sample or conduct ceremonial model-to-model debates.

## 6. Live unknowns and milestone changes

No live hardware facts were established in this research. Required readiness evidence remains: exact target kernel/firmware, native boot/result/return mechanism, usable sensors and cadence, real charging/USB energy paths, stable desktop fixture, environmental variability, recovery, and whether independent instrumentation is necessary/available.

Move the measurement-feasibility proof ahead of substantial autonomous-loop work. A thin end-to-end host-controlled capture should establish that the proposed execution arrangement can actually measure the goal. Full measurement characterization precedes autonomous candidate selection; frozen confirmation precedes adopting a patch. The three-hour default is a session allowance, not a promise that pilot, discovery and independent confirmation will fit one session.

The main design should name the measurement protocol and analysis result as first-class versioned records. The implementation plan should require explicit positive, below-target, negative, inconclusive and invalid outcomes, plus an example where good-looking telemetry cannot establish the required power result. These are future acceptance criteria, not tests run here.
