# Register read

Reads MMIO words on the M1, one access per word through `/dev/mem` as device memory, and loads the values into the hardware database. A read that takes the M1 down is recorded as a fault and skipped; the M1 reboots by itself (about 35 s) and the scan goes on.

## Sub-features

- `reg-list` reads a short named list slowly (exact culprit on a crash).
- `reg-block` reads whole blocks fast, re-stepping slowly after a crash and skipping a page or the rest of a block after repeated faults.
- `reg-query` shows reads joined to the device-tree block they fall in.

## How to get to it (user POV)

- Write a list (`<hex address> <4|8> # label`, one per line) and run `tools/regmap/scan.sh <list> <label> "<state>"`.
- Query `sqlite3 var/hwdb/m1-hw.db "SELECT * FROM reg_map WHERE snapshot=<n>"`.

## Driving it with scan.sh

Preconditions:

- Doctor reports `drivable`. For anything not yet known safe: the cable is OUT (doctor: `cable link down`) and `M1TB_VIA` is unset (the scan runs over Wi-Fi, `m1ts`).
- A power-domain snapshot taken in the current cable state (see hardware-snapshot) shows every domain of the blocks you read at `actual=f`.

- **Read a list.** Run `tools/regmap/scan.sh var/regmap/lists/seq0-gates-pm.txt check-gates "awake, stock"`. Last line: `done: 5 reads, 0 faults`.
- **Read blocks.** Run `FAST=1 tools/regmap/scan.sh var/regmap/lists/<blocks>.txt <label> "<state>"`. The log `var/regmap/scan-<label>/scan.log` names every crash, slow window and skip.
- **Prove the values.** Run `sqlite3 -separator ' ' var/hwdb/m1-hw.db "SELECT addr, value, label FROM reg_map WHERE snapshot=(SELECT max(id) FROM snapshot)"`. Every listed word has a value.
- **Known faults.** Run `sqlite3 var/hwdb/m1-hw.db "SELECT printf('%#x',addr), note FROM read_fault"` before writing a new list and leave those addresses out.

## Gotchas

- Never read: the cluster ACC bases (0x210e00000, 0x211e00000, 64-bit), the PWM block past +0x1000, the AOP's audio DMA (0x24a980000), interrupt-controller +0x2000..+0x5fff (event/acknowledge), mailbox FIFOs (only ASC +0x44/+0x48/+0x8110/+0x8114 are safe), UART/I2C/SPI/SPMI data, NVMe, PCIe, RAM.
- A block whose power domain (or its parent node's) is not `f` takes the M1 down; the cable state changes some domains, so re-snapshot first.
- Fast mode's culprit attribution is unreliable when announcements lag over Wi-Fi (the CIO reset controller crashed three times and read clean slowly): re-read such a block slowly.
- `mrd` prints zero as `0000000000`; the loader handles it, hand parsing must too.
- Values are private: never paste a block dump into `docs/`.
