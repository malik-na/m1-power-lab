# Boot chain: how the M1 boots, and which loader it runs

iBoot -> stage-1 m1n1 -> stage-2 `boot.bin` (lab build "mb2" + SIO alias) -> u-boot -> Limine -> kernel.
2026-11-20. The stage 2 is the lab's mb2, not the `aura` package's m1n1; a package rebuild would replace it.

## The chain

| Stage | What, where | Source |
|---|---|---|
| iBoot | Apple firmware 13.5 (iBoot-8422.141.2); locks the boot CPU's RVBAR to the stage it loads. | [docs/LAB-INVENTORY.md 74-79; m1n1-mb2-breadcrumb `src/s2r.h` comment] |
| Stage 1 | m1n1, banner `v1.6.1` at EL2 (later called `v1.6.1-dirty`); not changeable from Linux. | [LAB-INVENTORY.md 74; evidence 2026-11-17, Observation round 4 table; evidence 2026-11-06-aurora-silicon-survey.md 441] |
| Stage 2 | `/boot/efi/m1n1/boot.bin`, sha256 `0a1e47f3...`, Nov 16. | [evidence 2026-11-17, breadcrumb section, provenance table] |
| u-boot | Inside `boot.bin` after `0x400000`. | [`tools/m1n1/install-breadcrumb.sh` header] |
| Limine | `/boot/efi/limine.conf`; test kernels go in its `# m1tb:` block. | [`tools/tb/m1-bootonce`] |
| Kernel | Omarchy's UKI (command line baked in), or a boot-once test kernel `/boot/efi/s2r/<tag>/`. | [evidence 2026-11-05-power-lever-review.md 260; `tools/tb/m1-bootonce`] |

## Established: what `boot.bin` 0a1e47f3 is

- First 4 MiB = m1n1 "mb2" (sha256 `24a8d4dc...`), then the device trees, then u-boot. [evidence 2026-11-17, breadcrumb section; install-breadcrumb.sh header]
- mb2 = Ante042/m1n1 `15a9a68` + a t8103 watchdog mark (local commit `07fae2d`); source `src-mb2-07fae2d.tar.gz` (sha256 `33455cc8...`) on the M1 in `/var/tmp/p2/mb1-in/`. [loader commit `d5b416c` message]
- Rebuilt on the M3 byte for byte: `var/bootloader/rebuild/boot-sio.bin` = `0a1e47f3`; log `build-mb2-on-m3.log`. [evidence 2026-11-17, breadcrumb section]
- Work clone: `~/Work/m1n1-mb2-breadcrumb` (mb2 import `d5b416c`, breadcrumb `4599569`, review `91d54c2`, branch `m1power/wake-breadcrumb`). [`git log` there]
- `0a1e47f3` = mb2 `boot.bin` (`26844aaf`) + one alias `/aliases/sio = "/soc/sio@236400000"` in the j313 tree, made by `tools/m1n1/dt-alias.py`. [evidence 2026-11-16-sio-alias]
- The kernels carry no device tree: every boot uses the j313 tree inside `boot.bin`. [evidence 2026-11-16-sio-alias, Cause]
- `/usr/lib/asahi-boot/m1n1.bin` (`cea13d62...`, package `aura` 1.0.0b13.r20261113-3) is **not** the installed loader. [var/bootloader/m1/m1-sums-and-pkg.txt; evidence 2026-11-17, breadcrumb section]
- mb2 publishes `/chosen/asahi,s2r-mailbox` and has the S2R reset path (see `wake-path.md`). [`src/s2r.c` 180-207]

## Backups and restore scripts

| On the ESP `/boot/efi/m1n1/` | Puts back | Source |
|---|---|---|
| `boot.bin.pre-sio-26844aaf` + `restore-pre-sio.sh` | mb2 without the SIO alias | [var/bootloader/m1/restore-pre-sio.sh; m1-sums-and-pkg.txt] |
| `boot.bin.pre-breadcrumb-0a1e47f3` + `restore-pre-breadcrumb.sh` | `0a1e47f3` over a breadcrumb build | [`tools/m1n1/install-breadcrumb.sh` header] |
| `boot.bin.orig-abcafc95` + `restore-second-stage.sh` (2026-11-12) | the packaged stage 2 of before mb2 | [var/bootloader/m1/restore-second-stage.sh] |

- Each script takes no arguments, runs from macOS or Linux with sudo, touches only `boot.bin*` in its folder, checks hashes. [the scripts' headers]
- Lab copies of older ESP files: `var/bootloader/m1/esp-history/` (`boot.bin.old`, `orig-abcafc95`, `pre-mb2-7273cba7`, `boot-pretrio.bin`, `s2r-m1n1-bd6a43d.bin`). [directory listing]
- Whether `boot.bin.orig-abcafc95` is still on the ESP: not read (the 2026-11-20 hash list names only `boot.bin` and `pre-sio`). [m1-sums-and-pkg.txt]

## The breadcrumb build

- `var/bootloader/boot.bin.breadcrumb` sha256 `396dd5df...`: `0a1e47f3` with only the first 4 MiB replaced by loader `91d54c2`, built `RELEASE=1 CHAINLOADING=1 ESP_STAGE2=1`; log `var/bootloader/build-breadcrumb.log`. [install-breadcrumb.sh header]
- Install: `M1_CLAIM=<who> tools/m1n1/install-breadcrumb.sh` (checks `0a1e47f3`, keeps it, writes the restore script, renames over `boot.bin`, re-reads the hash; no reboot). [header]
- Read: `tools/m1n1/read-breadcrumb.sh [--commit <time>]`, read-only through nvmem. [header]
- Ran once 2026-11-20, then restored to `0a1e47f3` (orchestrator's account). [evidence 2026-11-17, breadcrumb section, "M1 left"]

## Decided

- A change to what the M1 boots by default (its loader, its default entry) is asked of Naeem first, with a pick. [docs/agents/probe-lane.md, Rules]
- Every loader change keeps the old file and a restore script beside it. [handoff-2026-11-19, Next step]

## Warning: a package upgrade

- `update-m1n1` rebuilds `boot.bin` from `/usr/lib/asahi-boot/m1n1.bin` (aura) + DTBs + u-boot; it keeps only `boot.bin.old`. Run by hand or by a package hook, it replaces mb2 and drops the SIO alias. [var/bootloader/m1/update-m1n1; evidence 2026-11-05-power-lever-review.md 210-219]
- Whether a hook runs it on upgrade: not read. Open: read `/usr/share/libalpm/hooks/` on the M1.

## Recovery if a loader does not boot

1. From macOS (hold power, pick macOS): run the matching `restore-*.sh` under `/boot/efi/m1n1/` with sudo; restart, hold power, choose Omarchy. [restore-second-stage.sh message]
2. If nothing starts: DFU; the M1 is recoverable from DFU. [AGENTS.md, last rule; `tools/m1-reboot/m1-reboot.sh` `dfu`]

## Read more

- `docs/evidence/2026-11-17-deepsleep-clean-runs/README.md`, "Which loader the M1 runs"
- `docs/evidence/2026-11-16-sio-alias/README.md`
- `tools/m1n1/install-breadcrumb.sh`, `tools/m1n1/read-breadcrumb.sh` (headers)
- `var/bootloader/m1/` (private provenance: sums, restore scripts, `update-m1n1`)
- `wake-path.md`
