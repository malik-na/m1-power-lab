> Historical research snapshot dated 2026-09-26. Implementation-state statements below describe the project at the time of research and are superseded by the current [qualification status](../STATUS.md). Source and product behavior may have changed; recheck version-sensitive details before qualification.

# M1 tool — transport and recovery evidence

Research date: 2026-09-26. Scope: Linux ThinkPad T480 host, MacBook Air M1 J313/T8103 target, host-prepared experiments, evidence return and recovery. Read-only documentation/source audit; no hardware operations, installation or tests were performed. The [design](M1%20investigation%20tool%20-%20design.md) and [implementation plan](M1%20investigation%20tool%20-%20implementation%20plan.md) remain planning documents. Source links to branches describe the inspected state, not pinned release guarantees.

## Conclusion

The host arrangement is supported for m1n1 development. Three capabilities need separate qualification: **USB proxy control, hypervisor guest control, and native Linux measurement with a working result channel**. The third cannot be inferred from the first two. Recovery also needs explicit levels: reconnect, reboot while target software responds, physical reset, and firmware recovery.

## What the sources establish

| Capability | Evidence and practical limit |
|---|---|
| Linux host and cross-compilation | Asahi documents a GNU/Linux host of any architecture and AArch64 GCC/Clang toolchains. The T480 fits this architecture; actual distro, resources, USB permissions and build success remain unverified. [Tethered boot](https://asahilinux.org/docs/sw/tethered-boot/) |
| Bare proxy | m1n1 exposes two ACM interfaces: one for proxy commands and one for the hypervisor virtual UART. A normal USB data cable is sufficient for this mode. Device enumeration numbers are examples, not durable target identities. [m1n1 user guide](https://asahilinux.org/docs/sw/m1n1-user-guide/) |
| Host-prepared Linux payload | The loader accepts a kernel, DTB and optional initramfs. This permits a self-contained host-built experiment image; it does not supply a userspace harness automatically. The loader's `--tty` opens a separately named serial device. [Loader source](https://github.com/AsahiLinux/m1n1/blob/main/proxyclient/tools/linux.py) |
| Linux under hypervisor | The documented helper packages the guest, chainloads a matching m1n1 build and provides guest console output on the secondary interface. Hypervisor commands include interrupt, resume and reboot. These depend on a functioning hypervisor/transport. [Tethered boot](https://asahilinux.org/docs/sw/tethered-boot/) |
| Native Linux handoff | m1n1 sets the next-stage kernel entry, then shuts down its USB I/O device before jumping. Its existing proxy and hypervisor virtual UART are therefore not an always-resident native-Linux channel. [Kernel handoff source](https://github.com/AsahiLinux/m1n1/blob/main/src/kboot.c), [main handoff source](https://github.com/AsahiLinux/m1n1/blob/main/src/main.c) |
| Physical native serial/reset | Asahi documents a 1.2 V UART and vendor USB-PD commands, using another M1 host or a dedicated interface. Central Scrutinizer is one documented interface with USB2 pass-through. An ordinary T480 USB connection alone is not evidence of these capabilities. [Serial debug](https://asahilinux.org/docs/hw/soc/serial-debug/) |

### Native results are a first-class feasibility gate

**Recommended design:** an approved, immutable native experiment image contains a small bounded harness: run ID, image hash, fixed workload/measurement schedule, finite runtime, bounded result buffer, completion manifest and a specified shutdown/reboot behavior. No pre-existing target shell, SSH service, desktop or resident agent is assumed. This is a proposed implementation, not an existing m1n1 feature.

Choose and demonstrate a native result transport before relying on native trials. A dedicated debug UART is documented. A Linux gadget serial channel is another candidate, but the generic kernel gadget API requires an appropriate device-controller driver and configuration; generic support is not proof that the pinned J313 kernel/DTB/cable combination works. Qualify enumeration, transfer, loss detection, observer effects and return to proxy. Do not silently substitute hypervisor measurements when native transport is missing. [Linux gadget serial documentation](https://docs.kernel.org/usb/gadget_serial.html)

A run whose native harness cannot report completion stays `outcome unknown`. RAM-only results can disappear on a crash. Storage export would require a declared destination and approval for its writes; do not quietly mount the user's internal filesystem to close this gap.

### Setup is distinct from runtime

If proxy mode is already configured, routine work can proceed from the Linux host. If it is not, Asahi's documented installation/enabling paths involve local macOS/Recovery authentication and boot-policy changes. Expert tethered-only installation is an alternative to the optional proxy break-in path. The tool cannot promise to bootstrap these prerequisites solely by talking to a nonexistent proxy. [Tethered boot](https://asahilinux.org/docs/sw/tethered-boot/)

macOS tracing is an optional later capability requiring its own prepared target environment. The hypervisor guide currently lists macOS 13.5 and 14.8.3 targets, recommends a separate macOS installation, and requires version-specific kernel extraction and boot-object configuration. Those local preparation steps are unavailable under the present runtime assumptions unless separately arranged. Its proxy ABI is explicitly unstable; host tools and chainloaded m1n1 must match. [macOS hypervisor guide](https://asahilinux.org/docs/sw/m1n1-hypervisor/)

Host readiness should also inspect the current source build requirements: m1n1's Makefile builds a Rust library in addition to AArch64 C/assembly. A plan mentioning only Python and a C cross-compiler is incomplete. This does not require writing the coordinator in Rust. [m1n1 Makefile](https://github.com/AsahiLinux/m1n1/blob/main/Makefile)

## Recovery levels and limits

| Level | Planning rule |
|---|---|
| USB reconnect | Reopen only the identified target and inspect its mode and state. Re-enumeration is not proof of an operation's success or rollback. |
| Responsive software reboot | Use only an approved procedure supported in the current mode; verify the next boot identity and epoch. |
| Hung target | Record whether an operator must hold the power button or a demonstrated independent USB-PD reset interface exists. Tailscale reaches the ThinkPad, not the Mac's physical controls. |
| Boot/firmware failure | Escalate to a distinct owner-guided recovery workflow. Never treat DFU restore as an automatic retry. |

Apple's supported DFU procedure requires **another Mac running macOS 14 or later**, a suitable USB-C data/charging cable and physical entry to DFU mode. Revive preserves data; restore erases it. This user has no second Mac, so that supported fallback is currently unavailable unless access is arranged. [Apple recovery procedure](https://support.apple.com/en-us/108900)

Linux `idevicerestore` is a real alternative to investigate: its project supports Linux, and its upstream history includes macOS DFU support work. That establishes an available implementation, not successful recovery on this T480/J313 combination. Firmware compatibility, dependencies, signing, exact revive/restore behavior and physical DFU entry need qualification. Keep it `documented candidate`, never `demonstrated`, until there is evidence; do not perform an erase merely to qualify it. [Project README](https://github.com/libimobiledevice/idevicerestore), [upstream history](https://cgit.sukimashita.com/idevicerestore.git/)

## Corrections and readiness gates for the plan

1. **M0 records separate capabilities:** current proxy boot path; matching tool/build source; native result-channel candidate; independent reset availability; manual recovery contact/access; firmware-recovery fallback. Unknown capabilities stay unknown.
2. **M4 qualifies round trips:** proxy → approved payload/hypervisor → result → reboot/re-identification; and separately proxy → native image → complete result → return to proxy. Every boot transition creates a new boot epoch; stale operations cannot cross it.
3. **Define the ephemeral harness explicitly:** bounded behavior, exact artifacts, result framing/checksums, workload, watchdog/timeout assumptions and storage policy. Do not make a permanent target agent an implicit prerequisite.
4. **Separate routine and unattended operation:** remote owner control is feasible; recovery from every hang is not proven. A session can safely stop for manual intervention without claiming the target recovered. Fully unattended recovery requires demonstrated physical-reset capability.
5. **Make native completion an M5 prerequisite:** the native channel and required display/workload must be demonstrated before power-benefit trials. Proxy/HV mechanism findings remain useful while this is pending, but cannot satisfy native power acceptance.
6. **Bind approval to available recovery:** describe the actual recovery level, exact setup and physical assistance required. Missing a second Mac does not make all proxy research impossible; it changes which procedures are eligible and what consequences the owner sees.

These are design recommendations inferred from the inspected interfaces and constraints. Actual performance, target compatibility, signal quality and recovery success remain live qualification work after implementation is authorized.
