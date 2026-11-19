# Spec gaps reported by the glue tests, round 4d: the `pmp` client (spec round 15f, lab `9444f02`)

From the test author of glue round 4d (tests workspace `~/Work/deepsleep-glue-tests-r4`, commit
`21cbbe9` on `64dc31a`; `TESTS.md` section "Round 4d"). Written from the spec at `9444f02` and the
interface view (`interface/pmp_client.rs.iface`) only. The tests now hold D17 (the 113-page table and
the opening region's image at the TTBR write and at the opening word, macOS's words, the order, no
write after the opening) and leave bits 19 and 22 to the client (D13, D15; D14 withdrawn). The
interface gained `PmpHw::map_dram(iova, bytes) -> bool`, `map_mmio(iova, phys, bytes) -> bool`,
`write_dram(iova, data)` and `Step::Map`. Four places are open; each item names the spec text and
what the tests do until the spec stage answers. G30 and G31 (round 4c) are still open.

- **G32. The form of D13 (d), and whether it applies with bit 19 clear.** D13 (d): "D12 (c)'s first
  line also gives `cand` and names which of bits 18-22 the client acts on." D13's items (a)-(d) are
  listed under "With bits 18 and 19 set, in the boot part only"; D12 (c)'s line already carries
  `cand`. Not stated: in what form the line names the bits (a mask, a list), and whether it does so
  with bit 19 clear. Tests: the `Probe` line has three values (`[spec commit, build commit, cand]`)
  or four; a fourth (by the interface, a mask of the bits of 18-22 the build acts on) is not held.
- **G33. A mapping refused partway.** D17 puts the 13 pages and the 34 ranges "as part of D10 (a)'s
  "buffers before any access"", and D10 (a) says that if a buffer cannot be had "the client makes no
  other access ..., logs which, and its probe returns an error". Not stated: whether the pages and
  ranges already mapped when a later one is refused are kept or unmapped before the probe's error,
  and whether the region's bytes may have been written by then. Tests: nothing held beyond D10 (a)
  (no device access, no word, no wait; the map calls and DRAM writes before the refusal allowed).
- **G34. The form of D17 (g)'s lines.** D17 (g): "D12's lines, which now name each mapped range and
  the region's two non-zero spans in the buffer lines". Not stated: whether a "range" is one of the
  34 MMIO ranges, each DRAM run or page, or each mapping as the client makes it, and whether the DRAM
  pages are named too; how the spans are given. Tests (CHOICE, the interface's): one `Map` line
  `[IOVA, bytes, physical address or 0 for DRAM]` per map call that succeeded, right after it, and
  together naming all 113 pages; the opening's `Buffer` line `[0x20, 0, 0x10000, 0x3c000, 0x2000,
  0x80, 0xe000, 0x290]` (the spans as offset, length).
- **G35. "The buffers' own uses" after the opening.** D17's test form: "after the opening word, no
  write by the client to the 13 pages but the buffers' own uses (none in the boot part)". The client
  never writes a buffer it gave `pmp` (the crash log, ioreport and syslog are `pmp`'s to write; D13
  (c) reads them). Not stated: which uses by the client are meant outside the boot part. Tests: no
  client write into the 13 pages after the opening word in any part (boot, `message`, entry, wake).

Readings, not gaps: (1) D17 (c)'s entry form (address | `0x3`, L1 | `0x1`, the TTBR word) is made by
the kernel side's table, behind `map_dram`/`map_mmio`/`translator_ttbr`; the host tests see pages and
bytes, not entries, so it is listed for the C half's reviewer in `TESTS.md`. (2) At the wake the tests
hold the 113 pages still mapped at R55's +`0x200` write (D11 (a) round 15c, "Every buffer stays
mapped ... R55 writes the boot's table again"), and nothing more of the wake's table (R76, "Not
established: ... the wake's table"). (3) `bit_18_with_every_other_bit_acts_as_bit_18_alone` held
"the other bits are not the client's" since round 4; since round 15e bits 19 and 22 are (D13, D15),
so the test now sets every bit but those two (bits 20 and 21 included, D14 "no longer acted on").
