# Handoff: continuing from macOS on the M3 Max (2026-11-09)

Work so far ran from Omarchy Linux on the M3 Max. This note is what a new session on the M3 Max's
macOS needs. Private material (notes, register dumps, Claude memory) is not in git; it is in
`m1-handoff/` on the M3 Max's EFI partition (see "Private bundle" below).

## Where things are

| What | Where |
|---|---|
| This repo (lab tools, evidence) | github.com/malik-na/m1-power-lab, branch `omarchy-live-power` |
| Linux S2R kernel | github.com/malik-na/linux-aurora, branch `m1power/s2r-pmp` (b6b2ea1d1, global sleep) |
| m1n1 with the S2R wake note | not on GitHub: git bundle `m1n1-omarchy-wake.bundle` in the private bundle (branch `m1power/omarchy-wake`, 7fe06e9) |
| Linux S2R evidence, runs 1–11 | `docs/evidence/2026-11-07-linux-s2r/README.md` |
| M1 reboot over USB-C from Linux | `tools/m1-reboot/` (tuxvdmtool + ported tipd debugfs) |

## State

- **Linux S2R on the M1 Air:** enters real S2R, the PMU alarm fires, the boot CPU never restarts; the
  watchdog resets ~181 s after the commit. Run 11 (XNU core order) also did not wake. Paused: the
  peer session's budget is spent, so no run 12 or other sleep test without the user's direct go.
  Untested leads: `ps_atc0_common` (0x23b700420) and `ps_gfx` (0x23b7003f8) targets at the commit.
- **Serial console:** with a USB4 cable on the M3 Max's "USB-C Left Back" and the M1's back-left port,
  tuxvdmtool puts both ends in serial mode (every command 0x00, target ACK 0x05ac8052), but no byte
  crosses in either direction (each side's uart0 tx counts rise, rx stays 0). Likely the M3 Max's SBU
  route does not land on the uart Linux exposes (0x391200000). **First thing to try on macOS:**
  `macvdmtool serial` (or `reboot serial`) on the M3 Max, which is the supported host path; if bytes
  arrive there, the cable and the M1 are fine and the gap is Linux-host-side on t6031.
- **M1 Air:** Omarchy, stock kernel, original stage-2 m1n1 restored, lab status READY. Its Wi-Fi
  sometimes sticks after resets (associated, no traffic); a reboot fixes it, `power_save off` no longer
  does.

## Standing rules (from the user)

- Kernelcache and Apple binaries are never committed or shared; SEQUENCE.md, the register drafts and
  the recfg dumps stay private.
- No changes to the M1's network config or default behaviour (idle, lock, brightness) to stabilise tests.
- Never handle the user's passwords or tokens.
- Commit and push as you go. Git identity Naeem Malik <malik2015naeem@gmail.com>.
- Use the camera facing the M1 to watch it instead of guessing.

## Private bundle

On Linux it is at `/boot/efi/m1-handoff/`. On macOS: `diskutil list` → find the 500 MB EFI partition
labelled "EFI - OMARC" (disk0s4 on this Mac) → `sudo diskutil mount disk0s4` → `/Volumes/EFI - OMARC/m1-handoff/`.
Copy it into the repo checkout's `var/` (gitignored) and the Claude memory folder, then delete it from
the EFI partition. Contents: `memory/` (Claude memory files), `var-notes/`, `var-recfg/`,
`var-s2r-static/`, `var-night/`, `m1n1-omarchy-wake.bundle`, `m1n1.bin` (wake-note stage 2),
`tuxvdmtool-hold.patch`.
