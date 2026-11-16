# Awake test of the SIO island's power gate #45 (2026-11-16 07:36)

Question: does the SIO island's power-gate record (#45, 0x23b71c090) report ready (bit 30) once the
island is powered off, with the SIO coprocessor stopped as Linux leaves it? (Hypothesis from the
ledger, findings 95/96/73: both stuck islands hold a coprocessor macOS runs and Linux leaves
stopped, SIO in #45 and ANS in #47.)

Method: `tools/regmap/sio-gate-test.py`, run on the M1 as root over Wi-Fi with the Thunderbolt
cable out (validated: no thunderbolt0, no type-C partner on either Mac's ports but the M3 Max's
MagSafe), stock kernel 7.3.0-0test5, on battery. It copies the chip's own sleep program for the
island (decoded program, lines 268-351): arm #44 = 0xc0080860 and #45 = 0x80080860, sio_cpu =
0x80000000 (off + RESET), the 32 children 0, uart_p/spi_p/audio_p/sio_adma 0, sio 0, sio_busif 0,
each waited for bit 11 clear; then watch bit 30 for 2 s; restore. One 32-bit access per register,
/dev/mem O_SYNC, output flushed line by line to the M3 Max.

| Step | Read back on the M1 |
|---|---|
| before | #44 0xc0040301, #45 0x8004030c (bit 30 = 0); SIO coprocessor run 0x0 / status 0x2a (stopped) |
| arm #44 / #45 | **no effect**: still 0xc0040301 / 0x8004030c |
| island off, program order | every word took: bit 11 clear within 1 us; sio_busif 0x0f000300, sio 0x0f000300, sio_cpu 0x8f000300, children 0x300 |
| watch | t = 0: #45 bit 30 = 0; then the M1 stopped answering (no further line within the 2 s) |
| after | the M1 rebooted by itself (boot 12191e7a at 07:37:47); previous boot's journal ends 07:36:30, no panic saved |

## What it establishes

- The power-gate records cannot be written from the application processors: the arming writes
  were ignored, while the power-state words beside them were writable. Only the chip's always-on
  engine arms these gates (as its program does).
- The SIO island can be powered off in the program's order from Linux with every domain settling
  (bit 11 clear), the coprocessor stopped and held in reset.
- The hypothesis is NOT tested: with #45 unarmed, bit 30 has no reason to set, so 0 says nothing
  about the coprocessor. A test needs the engine to arm the gate, i.e. a real sleep entry.
- Powering the SIO island off on a running M1 takes it down within seconds (expected: keyboard,
  trackpad, audio and the type-C controllers' i2c0 live there).
