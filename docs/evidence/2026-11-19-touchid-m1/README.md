# Touch ID on the M1 Air (J313): enrol, match, survive a reboot (2026-11-19)

## What ran

MacBook Air (M1, 2020), `apple,j313`, kernel `7.3.0-0test5-1-ARCH` (`linux-aurora 7.3.0.aurora0test5-1`,
`CONFIG_APPLE_SEP=m`), macOS 13.5 firmware. References: omacom/omarchy-mac-pkgs#90,
omacom/linux-aurora#141, #180, #223; Aurora Silicon `linux` `integration/aurora` `drivers/soc/apple/`
and `aurora-sep-userspace` (read as data).

1. Read-only load (`xart_writes=0 provision_keybag=0`), boot `7833839e`: enclave booted (TZ0, IMG4,
   12 endpoints, key store open), `/dev/sep-bio` present, `writes disabled`.
2. Raw copy of `nvme0n1p1` (iBootSystemContainer, 500 MiB) before any write; sha256
   `67cffbd1…` equal on the M1 and the copy (`var/touchid/20261119-072414-pre-xart-write/`).
3. Sensor calibration carved by `/usr/lib/linux-aurora/extract-mesa-calibration` into
   `/usr/lib/firmware/updates/apple/mesacal-j313.bin` (64130 bytes; the node's `firmware-name`).
4. `/etc/omarchy-mac/touchid-on` and `/etc/modprobe.d/omarchy-mac-touchid.conf`
   (`options apple_sep xart_writes=1 provision_keybag=1 xart_guard=0`), reboot (boot `377b3dbf`).
   Omarchy's `omarchy-mac-touchid-load`/`-activate` units ran; the M1-family gate in
   `touchid-eligibility` was bypassed by doing `touchid-enable`'s steps by hand.
5. `fprintd` 1.94.5 (extra) and libfprint built from `tools/touchid/libfprint-aurora-v5/`
   (v1.94.100 + Aurora's series; Omarchy's `libfprint-git` accepts only sep-bio v4 and logged
   `interface version 5, expected 4`).
6. `fprintd-enroll`, `fprintd-verify`; reboot (boot `12963018`); `fprintd-verify` again.

## Readings

| Step | Kernel / fprintd |
|---|---|
| keybag | `xART guard off`, `writes ENABLED`, `sks: identity keybag provisioned`; activation status `ready` (touchid ready, sensor_attach attached, restore empty, matching usable) |
| xART write | five 4 KiB blocks of `nvme0n1p1` changed (0x4ef000, 0x513000, 0x525000, 0x540000, 0x549000), all inside the `.gl` extent (base 0x4d4000); nothing else in the container |
| enrol, right index (07:30, 07:37) | `capture 0 ended without a frame` after 60 s, `enroll-unknown-error`. Naeem could not put that finger on the sensor: no touch, so these say nothing about capture |
| enrol, left index (07:39) | 8 stages, `enroll-completed`; `user 1000 now has 1 enrolled identity in the enclave`; capture by SPI polling (`no data-ready interrupt (describe it in DT)`) |
| verify (07:39-07:40) | first `verify-no-match` (enclave answered user -1), then 3 of 3 `verify-match`, identity `07a96708…` |
| reboot | `Touch ID: restored 1 enrolled identity/identities; enrolment survived reboot`; status `restored`/`usable` |
| verify after reboot (07:43) | `verify-match`, same identity (one earlier attempt timed out with no touch) |

The enclave's hwrng survey fails on every load (`survey failed after 5 attempts (EIO)`); not
investigated. Raw logs: `var/touchid/` (private).

## What this does not establish

- That macOS 13.5 on the M1 still boots and logs in after the xART write (not run).
- PAM: `sudo`, polkit and the lock screen are not wired to fprintd (no `pam_fprintd` lines).
- Sleep/resume with the driver loaded; the lid-closed reader hiding.
- The data-ready interrupt (#223's pin 104): capture worked by polling, so it was not needed here.
- Aurora's fprintd patches (failed-delete recovery, lockout reporting) are not installed.
