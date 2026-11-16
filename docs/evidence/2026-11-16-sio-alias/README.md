# SIO set up by m1n1 after adding the `sio` alias (2026-11-16)

**Question.** Why does the SIO coprocessor never start on the Air, and does it start once m1n1 can find it?

**Cause.** Every boot (stock kernel and lab run kernels) uses the j313 device tree stored in m1n1's second stage, `/boot/efi/m1n1/boot.bin`. The kernel images carry no device tree, and run boots show m1n1's own firmware reservations. That stored tree had no `sio` alias. m1n1's `dt_setup_sio` finds the SIO node only through that alias, so it skipped SIO. The node stayed `disabled` with no `apple,sio-firmware-params`, and `apple-sio` never probed.

**Change.** `tools/m1n1/dt-alias.py` added `/aliases/sio = "/soc/sio@236400000"` to the j313 tree inside boot.bin and changed nothing else. The other payloads are byte-identical, and dtc shows only the one alias line differing. The Air now boots this boot.bin. The previous one is kept beside it as `boot.bin.pre-sio-26844aaf`, and `restore-pre-sio.sh` puts it back.

**Result (stock kernel 7.3.0-0test5, first boot).**

- The alias is present, the node reads `okay`, and the node has 112 bytes of `apple,sio-firmware-params` and a `memory-region`.
- There are four new `sio-firmware-data` reservations and two more `asc-firmware` reservations.
- `apple-sio` is bound and logs `SIO protocol v9`. The coprocessor's CPU control reads RUN.
- Under hardware auto power management, SIO's three power states sit at a clock-gated idle level instead of fully on.
- No new errors. No failed units. Audio (speakers, DP), Wi-Fi, displays and the Thunderbolt link are present. The only display-firmware warning (`pmu ram read error`) also appears in the two previous boots.

**Not yet done.** The driver's suspend hook is still a TODO, so SIO has no sleep handshake before suspend-to-RAM. Testing gate #45 with SIO running needs that step in the run kernel.
