# Suspend-to-RAM entry

One deep-sleep attempt: the lab boots a test kernel once, the run script waits at its gate, enters "mem", and the M1 comes back (so far always through a reboot about 20 s later, before the 60 s alarm). The proof is the script's verdict, the acceptance postmortem, the power chip's scratch bytes and the outside timeline. It never counts as a wake unless the boot id stays the same.

## Sub-features

- `s2r-coldstart` makes the power chip's start byte 0x0201 read 04 (a power-button start).
- `s2r-submit` boots a test kernel with a run script through the lab.
- `s2r-gate` passes the script's charger/ports/battery gate.
- `s2r-postmortem` classifies the ending from the chip's clock and the restart record.
- `s2r-record` decodes the scratch bytes the driver left (stage, record, gates or watch).

## How to get to it (user POV)

- `lab run naeems-m1-air-r25 --kernel <kernel.tar.zst | full sha256> --cmdline "<S2R args>" --test boot-health --script <run script> --script-timeout 20m --no-wait`, or `lab retry <job>`.
- The kernels: `var/kernels/run26/kernel-run26.tar.zst` (linux-aurora `m1power/s2r-rs1-135`, run 22 + `sep_target`, enters on the 13.5 firmware) and the lab-stored `05754414583e96fd...` (run 25's labsep14). Scripts: `var/run22-src/run26-watch.sh`, `var/run25-src/run25*.sh` (private).

## Driving it with lab + m1tb/m1ts

Preconditions:

- Doctor: `drivable`, `M1 pmu0201 04`, `lab ... READY`. If 0x0201 is 01, shut the M1 down (`systemd-run --on-active=2s systemctl poweroff` on it) and ask Naeem to press the power button, then re-read it.
- Cable OUT unless Naeem accepted the M3 Max reset risk for this run; with the cable in, `m3-blackbox` runs.
- Battery discharging at the gate: with the M1's charger out and the cable out it already is; with the cable in and the M3 Max sourcing, set `charge_behaviour` to `force-discharge` during the gate wait (gate variant `run25-cablefd.sh` style).
- `tools/tb/m1-observe <label> &` started first.

- **Submit.** Run the `lab run` above. It prints `job <id> queued`. `lab job <id>` shows `booted <kernel>` and the script running.
- **Watch the gate.** Run `tools/tb/m1tb 'grep -E "GATE|ENTRY|NO ENTRY" $(ls -t /var/lib/m1power-s2r/run2*-2*.txt | head -1)'` (or `ssh m1ts ...`). `GATE PASSED` then `ENTRY: acceptance.sh cycle 60 now`; a `NO ENTRY` line names its reason.
- **Return.** Wait for SSH; read `uname -r`, `cat /proc/sys/kernel/random/boot_id`, uptime.
- **Postmortem.** Run `ssh m1ts 'S2R_PARAMS_FILE=/var/lib/m1power-s2r/run1/params.sh /var/lib/m1power-s2r/run1/acceptance.sh postmortem'` once (it closes the cycle). `RAW: this boot started N s after the recorded entry`, `ENDING ...`, verdicts A1-A6.
- **Record.** Run `tools/tb/m1-collect <label>` (`M1TB_VIA=m1ts` on Wi-Fi). Decode 0x9f0a (stage), 0x9f10-17 (record), 0x9f1a and 0x9f1c-1e with the driver's own legend (`s2r_seq.rs`); 0x0201 04 -> 01 means the chip's sequence got past its first step.
- **Outside.** In the observer log: Wi-Fi down / up, cable host disconnected / found, and the M1's type-C detach (cable in), which marks the SoC reset to within tens of ms.

## Gotchas

- Since the 2026-11-14 macOS 13.5 reinstall the enclave gates itself ~1.4 s after its driver's last exchange and its hwrng survey always fails (EIO): run 22-era scripts refuse unless their enclave checks use the target nibble and accept the survey line (`run26-watch.sh` does).
- With the cable in, the type-C power roles are renegotiated at every M1 boot, including the lab's reboot into the test kernel: a doctor reading taken before the submit (M1 sourcing, ac 0) does not hold at the gate (run 27: M3 Max sourcing, M1 charging, gate timed out). Use the discharging-only gate (`run27b.sh`) and set `force-discharge` once the gate waits, then read back `Discharging`.
- A stale type-C partner can stay on port0 after the cable is removed (no PD, no power): the strict gate never passes; it clears on the next boot.
- `lab run` puts tests in the order given: listing `omarchy-m-test` before the script makes the lab run it first (GPU and display load before the entry).
- The old after-script labelled `gate_record` bytes as wake sources; with `gate_record=1`, 0x9f1a / 0x9f1c-1e are wait-condition indices into `SEQ0_GATES`.
- A `NO ENTRY` leaves 0x0201 at 04 (no new cold start needed); a real entry makes it 01.
- The run script lives in the lab's artifact store and reaches the M1 only during the job (`/var/lib/maclab/jobs/<job>/test-<name>.sh`); copy it while the gate waits if you need it.
