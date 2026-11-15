# M1 MacBook Air (J313, t8103): hardware map

Everything here was read from the running M1 (Omarchy, stock kernel 7.3.0-0test5) over the
Thunderbolt cable on 2026-11-16, with tools/regmap/ (collect-inventory.sh, dt-map.py, hwdb.py).
The full database is `var/hwdb/m1-hw.db` (SQLite, gitignored: it holds register values, which
stay private); this page is the readable summary. No serial numbers or MAC addresses here.

## How to use the database

```bash
sqlite3 var/hwdb/m1-hw.db '.tables'
# every memory-mapped block, its driver and power domain
sqlite3 var/hwdb/m1-hw.db "SELECT printf('%#x',start), printf('%#x',size), node, driver, power_domains FROM block ORDER BY start"
# power domains that are on, awake
sqlite3 var/hwdb/m1-hw.db "SELECT name, actual, auto FROM power_domain WHERE snapshot=1 AND actual='f'"
# any sysfs attribute of any device (2514 rows per snapshot)
sqlite3 var/hwdb/m1-hw.db "SELECT object, name, value FROM attr WHERE subsystem='power_supply'"
# register reads joined to the block they fall in
sqlite3 var/hwdb/m1-hw.db "SELECT * FROM reg_map"
# reads that took the machine down (never repeat these)
sqlite3 var/hwdb/m1-hw.db "SELECT printf('%#x',addr), width, note FROM read_fault"
```

Tables: `snapshot` (one per collection: time, kernel, boot id, state), `block` (340 memory-mapped
ranges from the live device tree, absolute addresses), `platform_device` (245, with driver and
runtime-PM state), `power_domain` (146 PMGR domains: target/actual state, auto-gating),
`smc_key` (1445 SMC keys with values), `attr` (every sysfs attribute collected), `reg_read`,
`read_fault`, `note`. To add a snapshot: `tools/tb/m1tb 'bash -s' < tools/regmap/collect-inventory.sh
> inv.tar`, unpack, `tools/regmap/hwdb.py var/hwdb/m1-hw.db inventory <dir> "<state>"`.

## The machine

| | |
|---|---|
| SoC | Apple M1, t8103: 4 E cores (Icestorm, 600-2064 MHz, cpu0-3) + 4 P cores (Firestorm, up to 3204 MHz, cpu4-7), `apple-cpufreq` |
| CPU idle | two states: WFI (clock-gated, 1 us) and "CPU PD" (core/cluster powered down, 10 us), `cpuidle-apple` |
| Memory map | 340 MMIO ranges in the device tree, 327 enabled; 245 platform devices, 236 with a driver bound |
| Power domains | 146 (PMGR `apple-pmgr-pwrstate`); awake: 52 fully on, 77 off, 34 under hardware auto-gating |
| Firmware-run coprocessors (RTKit) | SMC, AOP (always-on: audio, ambient light), DCP x2 (internal / external display), ANS (NVMe), ISP (camera), GPU firmware, PMP (not started by Linux), SEP |

## Devices

| Device | Hardware | Linux driver | State / notes |
|---|---|---|---|
| USB-C ports (2, left side) | two Type-C ports, PD controllers CD321x on i2c-0 (0x38, 0x3f); Apple ATC PHYs; USB4/Thunderbolt via ACIO | `tps6598x`, `phy-apple-atc`, `dwc3-apple`, `thunderbolt-apple-acio`/`-nhi` | port0 (back) carries the Thunderbolt link to the M3 Max; port1 free. PD revision 2.0. With the M1 on battery the M3 Max sources it at **5 V / 3 A only (15 W)** |
| Internal display | 13.3" 2560x1600 eDP panel, backlight `apple-panel-bl` (max 394) | `apple-dcp` (DCP coprocessor at 0x231c00000), `apple-drm` | connected, enabled. Two DP connectors exist (DP-1, DP-2) through the display crossbar: disconnected |
| External display path | second DCP at 0x271c00000 (`dispext`) | `apple-dcp` | **its coprocessor domain `dispext_cpu0` is partly on (4) with nothing connected**: a candidate for idle power |
| Battery | bq20z451 gauge via the SMC; design 4382 mAh / 49.95 Wh | `macsmc-power` | **full charge 3267 mAh = 74.6 % of design, 767 cycles**, health "Good"; supports `charge_behaviour` auto / inhibit-charge / force-discharge and start/end thresholds (both 100 now) |
| Charger input | via the SMC (`macsmc-ac`) | `macsmc-power` | reports input current/power limits and voltage |
| Keyboard | Apple SPI keyboard on spi2 | `spi-hid-apple-of` (input0) | LEDs: caps lock, num lock etc. |
| Keyboard backlight | PWM LED `kbd_backlight` (0-255) | `apple-pwm`, `leds_pwm` | its PWM block sits in power domain fpwm1 |
| Trackpad | Apple SPI trackpad, same SPI HID device | `spi-hid-apple-of` (input1) | |
| Lid / power button | SMC events | `macsmc-input` (input2) | |
| Speakers | 2 x TI TAS5770L amplifiers (i2c-1 0x31, i2c-2 0x34) on the MCA I2S block | `tas2770`, `apple-mca`, `snd-soc-macaudio` | card 1 "MacBook Air J313" |
| Headphone jack | Cirrus CS42L83 codec (i2c-2 0x48) | `cs42l83` (input3 jack detect) | |
| Microphones | through the AOP ("High-Power Audio Interface") | `snd_soc_apple_aop` | card 0 |
| Ambient light sensor | through the AOP | `iio_aop_als` | |
| Camera | FaceTime HD, ISP coprocessor at 0x22a000000 | `apple-isp` | ISP domains off when idle |
| Wi-Fi | Broadcom BCM4378 802.11ax on PCIe 01:00.0 | `brcmfmac` | no 160 MHz |
| Bluetooth | BCM4378 function 01:00.1 | `hci_bcm4377` | |
| Storage | Apple ANS2 NVMe controller, 251 GB (nvme0n1, root on dm-crypt) | `nvme-apple` | |
| SPI flash | NOR on spi0 (system firmware NVRAM) | `spi-nor` | |
| GPU | Apple G13G (AGX) at 0x206400000 | `aurora` | `gfx` domain off when idle (auto) |
| Neural Engine | ANE at 0x26bc04000 | `ane` | all ANE domains off |
| Video decoder | AVD | `avd` | off when idle |
| Video encoder, JPEG, scaler | venc_*, jpg, msr domains | none bound in this list | all off |
| Secure Enclave | SEP at 0x242400000 | **none bound** on the stock kernel | no Touch ID; the S2R test kernels load an `apple-sep` driver |
| SMC | system management controller at 0x23e400000 (1445 keys) | `macsmc` + `-rtc`, `-reboot`, `-power`, `-input`, `-hwmon`, `-gpio` | |
| Power chip (PMU) | on SPMI bus 0 (0x23d0d9300), slave 0xf | `apple-spmi`, `apple-spmi-nvmem` | named cells: boot-stage 0x9f01, boot-error-count / panic-count 0x9f02, boot-error-stage 0x9f03, shutdown-flag 0x9f0f bit 3, fault-shadow 0xa67b (16), socd 0xab00 (1 KiB), pm-setting 0xd001, rtc-offset 0xd100 (6). The S2R work also uses 0x0201 (start kind: 04 after a power-button start, 01 after a wake-restart) and scratch 0x9f04-0x9f1e |
| Watchdog | WDT block 0x23d2b0000: wd0 (m1power's wake timer, BARK only), wd1 (apple_wdt, systemd), wd2 (armed by the always-on engine itself) | `apple-watchdog` | |
| IOMMUs | 20 DARTs + 1 SART | `apple-dart`, `apple-sart` | |
| Interrupts | AIC at 0x23b100000 | (core) | |
| Temperature / power sensors | SMC (macsmc_hwmon), battery, AC, NVMe, both amplifiers, both PD controllers | hwmon0-7 | thousands more values in the SMC keys (T* temperatures, P* power, V* voltage, I* current) |

## Observations that matter for power and sleep

- **Battery wear**: 74.6 % of design capacity left at 767 cycles. Every hour of sleep drain costs
  proportionally more runtime than on a new battery.
- **CPU governor `performance`** on the stock kernel right now (cores held high); earlier records
  show `schedutil`. Not changed (standing rule: no changes to the M1's defaults to stabilise tests).
- **External-display DCP running** (`dispext_cpu0` partly on) with nothing connected.
- **SEP has no driver** on the stock kernel; it powers itself down.
- **Charging over the Thunderbolt cable** is 5 V / 3 A at most from the M3 Max (15 W).

## Register reads: what is safe

Reads go through `tools/regmap/mrd-stream.c` (one access per word, `/dev/mem` with O_SYNC = device
memory, a "reading <addr>" line sent over ssh before each read so a crash still names the word).
The first attempt (2026-11-16 03:20, list starting at the MCC bases 0x200000000 / 0x200100000)
took the M1 down within its first reads; nothing survived on its disk (`read_fault` table).
Never read: event / acknowledge registers (AIC_CPU_EVT), mailbox FIFOs (coprocessor +0x8800
range), UART / I2C / SPI data registers, the NVMe controller, unmapped gaps between blocks.
Because an M1 crash re-trains the Thunderbolt link and the M3 Max has reset itself after link
events (memory: m3-silent-resets-tb-link), deliberate crash-risk reads are done with the cable
out, or accepted explicitly.

## Register coverage (2026-11-16, awake, stock kernel, no cable)

83,002 words read with `tools/regmap/scan.sh` (Wi-Fi, fast mode with slow re-stepping after a crash,
page/block skipping after repeated faults); values in the database only.

| Block | Words read | Faults | Notes |
|---|---|---|---|
| PMGR 0x23b700000 (0x14000) | 20480 | 0 | 159 non-zero words on five pages (+0x0, +0x4000, +0x8000, +0xc000, +0x10000): the 146 power-state words and their neighbours |
| PMGR always-on 0x23d280000 (0x4000) | 4096 | 0 | 14 non-zero words, the always-on domains' power states at +0x58..+0xc0 |
| Watchdog 0x23d2b0000 (0x4000) + engine words | 4096 + 7 | 0 | |
| NCO clock generator 0x23b044000 | 4096 (of 0x14000) | 0 | |
| Pin controllers x5 | 20480 | 0 | 0x23c100000 holds 169 informative words |
| IOMMUs (DART) x7 with their domains on | 28672 | 0 | |
| Keyboard-backlight PWM 0x235044000 | 1024 | 9 | DT window is 0x4000 but only +0x0..+0xfff answers: every read at +0x1000 and above takes the machine down |
| S2R driver's own words (MCC, AIC config, cluster states, wake mask/status, SPMI status, carry/TVM) | 58 | 2 | the 64-bit read of each cluster's ACC base (0x210e00000, 0x211e00000) takes the machine down |

Not read yet, on purpose: coprocessors (mailboxes and firmware memory), the interrupt controller's
event/acknowledge registers, UART / I2C / SPI / SPMI data, NVMe, PCIe, USB / ATC / Thunderbolt,
display pipes, and every block whose power domain is not fully on (reading a powered-down block
takes the machine down).
