# Hardware snapshot

A snapshot records, read-only, everything Linux on the M1 can say about its hardware at one moment (devices and drivers, power-domain states, SMC keys, power supplies, type-C ports, inputs, display, audio, sensors) and loads it into `var/hwdb/m1-hw.db` as one `snapshot` row, so two states (cable in / out, awake / after a sleep) can be compared.

## Sub-features

- `snap-collect` collects the inventory tar on the M1 and unpacks it on the M3 Max.
- `snap-load` loads it as a numbered snapshot with a state description.
- `snap-compare` lists power domains whose actual state differs between two snapshots.

## How to get to it (user POV)

- Run `tools/regmap/collect-inventory.sh` on the M1 through `m1tb` or `m1ts`, then `tools/regmap/hwdb.py ... inventory`.
- Query the database with `sqlite3 var/hwdb/m1-hw.db`.

## Driving it with m1tb / sqlite3

Preconditions:

- Doctor reports `drivable` and `M1 m1power_ko loaded` (for the power-domain and SMC tables; without it those two tables stay empty).

- **Collect.** Run `s=$(date +%Y%m%d-%H%M%S); mkdir -p var/hwdb/inv-$s && tools/tb/m1tb -o BatchMode=yes 'lsmod | grep -q m1power || insmod /root/m1power-kmod/m1power.ko; bash -s' < tools/regmap/collect-inventory.sh > var/hwdb/inv-$s.tar && tar -C var/hwdb/inv-$s -xf var/hwdb/inv-$s.tar`. The directory holds `identity.txt`, `platform.tsv`, `pmgr_ps.txt` (146 lines), `smc_keys.txt` (about 1445 lines) and one file per subsystem.
- **Load.** Run `python3 -I tools/regmap/hwdb.py var/hwdb/m1-hw.db inventory var/hwdb/inv-$s "<state, e.g. awake, stock, cable in>"`. It prints `snapshot <n>`.
- **Prove it loaded.** Run `sqlite3 var/hwdb/m1-hw.db "SELECT count(*) FROM power_domain WHERE snapshot=<n>; SELECT count(*) FROM smc_key WHERE snapshot=<n>;"`. Expect `146` and about `1445`.
- **Compare.** Run `sqlite3 var/hwdb/m1-hw.db "SELECT a.name, a.actual, b.actual FROM power_domain a JOIN power_domain b ON a.name=b.name AND a.snapshot=<old> AND b.snapshot=<n> WHERE a.actual!=b.actual"`. Each row is a domain that changed (2026-11-16: cable out turns atc0_cio, atc0_cio_pcie, atc0_cio_usb off).

## Gotchas

- `m1power.ko` is gone after every M1 reboot; the collect command reloads it from `/root/m1power-kmod/` (built for the stock kernel only; on a test kernel it will not load).
- The tar goes to stdout: anything else printed by the remote command corrupts it. Keep extra output on stderr.
- The battery section contains its serial number: never copy `power_supply.txt` into `docs/`.
- `lsusb` and `lspci` are not installed on the M1; their files say so.
