# Trace macOS sleep entry on the M1 under the m1n1 hypervisor

Target: MacBook Air M1 (J313, t8103). Host: the M3 Max running Omarchy (Arch Linux, aarch64).

**What this is for.** Linux on the M1 needs the register sequence that powers
the SoC off: real suspend-to-RAM (S2R). That sequence is not documented for
t8103, and only macOS runs it. This kit records macOS running it once. It does
not measure macOS's sleep power. The questions it should answer:

- the S2R timer address;
- the cluster-control, power-gate, clock-mux and CLLT writes;
- the Sera PMU "go hib" register and value (0xd001?), if the main CPU writes it at all;
- the SMC `MBSE` value;
- the PMP and secondary-PMIC sleep messages;
- the order of all of the above.

Linux then replays only the writes the trace shows.

## Tomorrow at a glance

| Stage | Where | What | Time | Touches |
|---|---|---|---|---|
| 0 | M3 Max | Copy the kit, build m1n1, make the Python venv | 30-45 min | host only |
| A | Omarchy, then main macOS | Check free space and the disk layout (read-only) | 15-20 min | nothing |
| B | main macOS, then macOS 13.5 | Add a volume, install macOS 13.5 into it, set it up | about 2 h, mostly waiting | **DISK** |
| C | 1TR, then Omarchy, then M3 Max | Lower security for the 13.5 volume only, install m1n1 as its boot object, get the kernelcache to the host | 30-40 min | **SECURITY**, **STARTUP DISK** |
| D | M3 Max + the Mac | The trace session (one sleep attempt per run) | 45-60 min per run | **PMU WRITE** only by upstream `run_guest.py` |
| E | the Mac, M3 Max | Clear PMU counters, back to Omarchy, optional clean-up | 15-30 min | **PMU WRITE**, **STARTUP DISK**, optional **DISK** |

Do not start before the overnight measurement on the M1 has finished.

**Markers used below**

- **[DISK]**: the step changes the disk: volumes, files on the EFI partition, or deletes data.
- **[SECURITY]**: the step changes a boot policy, SIP, or the boot object.
- **[STARTUP DISK]**: the step changes which OS boots by default.
- **[PMU WRITE]**: the step writes a PMU register over SPMI.
- **[STOP POINT]**: check the stated condition; if it fails, stop and ask before going on.

Things this plan never does: resize or add partitions, touch the Omarchy or
Asahi stub volumes, change the main macOS's security, change `boot-args`,
change any network settings in Omarchy, or use an IPSW.

---

## Stage 0. Host preparation (M3 Max, no Mac needed): 30-45 min

1. The kit lives in the m1-power-lab repo at `tools/hv-trace-kit`. Run, trace and kernelcache
   files it creates (`runs/`, `prep/`, `kc/`) are git-ignored; the kernelcache is Apple's binary and
   must never be committed.
   ```sh
   KIT=~/Projects/m1-power-lab/tools/hv-trace-kit
   ```
2. Install the build tools. The host is aarch64, so m1n1 builds natively with gcc (`Makefile:27-31`); its Rust part needs `rustup`.
   ```sh
   sudo pacman -S --needed git base-devel python rustup lzfse
   rustup default stable && rustup target add aarch64-unknown-none-softfloat
   ```
3. Build m1n1 at the pinned commit.
   ```sh
   git clone https://github.com/AsahiLinux/m1n1 ~/m1n1
   git -C ~/m1n1 checkout 70757dc74c2dac485188acaa2fa7e73be5b108ee
   git -C ~/m1n1 submodule update --init
   make -C ~/m1n1 -j"$(nproc)"              # -> ~/m1n1/build/m1n1.bin (debug build: proxy runs unconditionally)
   sha256sum ~/m1n1/build/m1n1.bin | tee ~/m1n1/build/m1n1.bin.sha256
   ```
   **Do not mix commits.** The `m1n1.bin` installed on the Mac and the host's
   `proxyclient` must come from the same commit; the proxy ABI is not stable
   (`m1n1-hypervisor.md`, "m1n1 ABI synchronisation").
4. Make the Python environment and check the host.
   ```sh
   python3 -m venv "$KIT/venv" && "$KIT/venv/bin/pip" install -r ~/m1n1/requirements.txt
   "$KIT/session.sh" check                  # all items but the kernelcache should pass now
   ```
5. Device access. The lab's recorded path is `/dev/ttyACM0` (proxy) and
   `/dev/ttyACM1` (console), owned `root:uucp`, mode 0660
   (`docs/LAB-INVENTORY.md:61-74`). Your user is not in `uucp`, so run every
   device command in Stage D/E as:
   ```sh
   S="sudo -E -u $USER -g uucp"          # -E keeps S2R_*, BOOTARGS, M1N1* settings across sudo
   $S ./session.sh <command>
   ```
   This is the same temporary-group method used before (`docs/PROXY-HARNESS.md:46-49`).
   `session.sh` finds the m1n1 ttys itself (USB 1209:316d, interface 00 and 02);
   `./session.sh devices` shows what it sees. The udev rule in `host/` is
   optional; it adds `/dev/m1n1` names and `uaccess` and is not needed.
6. Cable. Use a USB-C data cable from an M3 Max port to the Mac's **rear left
   port** (the DFU port on MacBooks, `dev-quickstart.md`, "Getting a serial
   console"). Charge the Mac from its other port, or start with the battery above 60 %.
   - What is known: the m1n1 proxy on this Mac has enumerated over USB before,
     from the ThinkPad host (USB-A to USB-C, `LAB-INVENTORY.md:61-74`).
   - What is not known: whether the M3 Max's ports enumerate it. `docs/LIVE.md`
     says the cable "carries power only". That is about Omarchy's kernel on the
     M1, which has no USB gadget support. m1n1 brings its own USB device stack,
     so it does not apply here.
   - Fallback: run Stage D from the ThinkPad. The proxyclient is plain Python.
     Use the same m1n1 checkout and the same commands.

---

## Stage A. Check free space and the disk layout (read-only): 15-20 min

Nothing in this stage changes anything.

### A1. From Omarchy (5 min)

1. Open a terminal and run:
   ```sh
   lsblk -o NAME,SIZE,TYPE,FSTYPE,PARTTYPENAME,PARTLABEL,PARTUUID,MOUNTPOINTS /dev/nvme0n1
   sudo sfdisk -l /dev/nvme0n1               # lists the partition table, writes nothing
   findmnt -t vfat                           # where the EFI system partition (ESP) is mounted
   df -h / "$(findmnt -n -o TARGET -t vfat | head -1)"
   for f in system-fw-version os-fw-version m1n1-stage2-version; do
       printf '%s: ' "$f"; tr -d '\0' < /proc/device-tree/chosen/asahi,$f 2>/dev/null; echo
   done
   ```
2. Write down:
   - the ESP mount point (`/boot` or `/boot/efi`) and its **PARTUUID**. You will use the PARTUUID to find the same partition from 1TR;
   - which partition is the large Apple APFS container (normally the first big one; that is the main macOS);
   - the firmware lines. Checked 2026-11-06: `system-fw-version: 27.0`, `os-fw-version: 13.5`, `m1n1-stage2-version: bc79acc4-dirty`; ESP `/boot/efi` (PARTUUID `5bc75aee-87d2-4ae9-8a97-73305ca29aa0`) 192 MB free; main macOS container `nvme0n1p2` (163.5 GB).
3. **[STOP POINT]** The ESP needs at least 150 MB free (the `df` line above). B5 copies the
   13.5 kernelcache (about 26 MB) and m1n1 onto it, and Omarchy's kernel and initramfs updates
   also land there if it is `/boot`. If it has less, stop and ask Claude.
4. Linux cannot see the free space inside an APFS container. A2 checks that.

### A2. From the main macOS (10-15 min)

1. Shut down. Press and hold the power button until "Loading startup options..." appears.
   Pick the main macOS and click **Continue**. Do **not** click "Always Use".
2. In Terminal:
   ```sh
   sw_vers
   system_profiler SPHardwareDataType | grep -E 'System Firmware|OS Loader'
   diskutil list
   diskutil apfs list | grep -E 'Container disk|Capacity|Not Allocated|Name:|Role|FileVault'
   diskutil apfs listVolumeGroups
   csrutil status
   ```
3. **[STOP POINT]** Check:
   - the APFS container that holds the main macOS has **at least 40 GB** "Capacity Not Allocated" (free). macOS 13.5 needs about 25-35 GB. The new volume shares this free space; no partition is resized;
   - `sw_vers` is **not** 13.5 or 14.8.3. If it is, the main volume could in principle be used directly, but the m1n1 docs advise against it; keep to the separate volume anyway;
   - note the container's name (for example `disk3`) and the "System Firmware Version" (the Asahi side reports system firmware 27.0; note macOS's exact string).

   If there is less than 40 GB free, free space inside the main macOS (delete files). Do not resize partitions. If that is not possible, stop.

---

## Stage B. Install macOS 13.5 into a new, separate volume: about 2 h, mostly waiting

### B0. What this does to firmware, and what Apple allows (read once)

- **Same container as the main macOS.** The new volume is added inside the
  main macOS's APFS container. The installer turns it into a second OS (a
  "volume group": `macOS135` plus `macOS135 - Data`). It shares that
  container's Preboot, Recovery, Update and VM volumes with the main macOS
  (`stock-partition-layout.md`, "Summary"). No partition is created or resized.
  The Omarchy partitions and the Asahi stub container are separate, and the
  installer does not touch them.
- **What the 13.5 install brings.** It brings its own OS loader (iBoot2), its
  own OS-paired coprocessor firmware in Preboot, and its own paired recoveryOS
  in Recovery (`introduction.md`, "NVMe is a GPT volume"). That is the point:
  under the hypervisor, macOS then runs on 13.5 OS firmware. The hypervisor
  supports that, and the Asahi stub uses the same OS firmware
  (`LAB-INVENTORY.md:78`).
- **System firmware is never downgraded.** System firmware means iBoot1 in
  NOR, the iBoot System Container and the System recoveryOS, together "SFR".
  It only moves forward in version, never backwards, except through a full
  wipe (`glossary.md:112`, `dev-quickstart.md`: "Downgrade protected"). A
  macOS installer updates system firmware only when its own is newer. The
  13.5 installer's system firmware is older than this Mac's (27.0), so
  it leaves it alone. Step B6 checks this.
- **What Apple allows.** Apple supports installing an older macOS that the Mac
  can run on a separate APFS volume; the M1 Air runs macOS 13. A Full Security
  install must get a signature from Apple at install time ("phone home",
  `introduction.md`, "Security modes"). So the installer needs internet during
  its first phase, which runs inside the main macOS on its usual network. If
  Apple no longer signs 13.5 for this Mac, the installer stops with an error.
  **[STOP POINT]** In that case stop. Do not try other routes.
- **Do not use an IPSW.** An IPSW is a whole-disk restore image. Restoring it
  through DFU erases the entire internal SSD, including the main macOS,
  Omarchy and all data. A DFU "revive" only reinstalls the current firmware
  and recovery. Neither gives you a 13.5 volume next to the others.

### B1. Get the 13.5 installer (main macOS, 20-60 min download, 11.9 GB)

Checked 2026-11-06: Apple's update catalog no longer offers 13.5 (its only macOS 13
installer is 13.7.8, 22H730, which the m1n1 hypervisor does not support), so
`softwareupdate --fetch-full-installer --full-installer-version 13.5` will fail. Use the
archived package the m1n1 docs link (`m1n1-hypervisor.md:39-47`). archive.org is a
third-party mirror, so the package is checked twice before it is opened.

1. Download it in the main macOS (Safari, or Terminal):
   ```sh
   cd ~/Downloads
   curl -L -o InstallAssistant.pkg https://archive.org/download/install-assistant_20240930/InstallAssistant.pkg
   ```
2. Check it is the archived file (size 11934300398 bytes):
   ```sh
   shasum -a 1 InstallAssistant.pkg   # must be 9ceeac3a75aaf3d6e477990caaf2c695f31624e2
   ```
3. Check that Apple signed it:
   ```sh
   pkgutil --check-signature InstallAssistant.pkg   # must say "Status: signed by a certificate trusted by macOS"
                                                     # and the chain must be Software Update / Apple
   ```
   **[STOP POINT]** If either check fails, delete it and stop.
4. Open the package. It extracts "Install macOS Ventura.app" into `/Applications`.
5. Check the app:
   ```sh
   codesign -dv --verbose=2 "/Applications/Install macOS Ventura.app" 2>&1 | grep Authority   # Apple authorities only
   /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "/Applications/Install macOS Ventura.app/Contents/Info.plist"   # installer app version (18.x for 13.5)
   ```
   Copy the app somewhere first if you want to keep it; it deletes itself after one install.

**Signing is only known by trying.** The installer asks Apple to personalize 13.5 for this
Mac during B3. Public "signed" lists (ipsw.me) mark every macOS build as signed and cannot be
trusted for this. If B3 stops with a personalization or "could not be verified" error, that
is the answer: stop there (B0).

### B2. Add the volume (main macOS, 2 min). **[DISK]**

Use either way.

- **Disk Utility.**
  1. View → Show All Devices.
  2. Select the main macOS **container**, the one from A2, not a volume.
  3. Click "+" (Add APFS Volume).
  4. Name `macOS135`, format APFS. Leave "Add to volume group" unchecked and give it no role.
  5. Click Add.
- **Terminal.** Here `diskN` is the container from A2:
  ```sh
  diskutil apfs addVolume diskN APFS macOS135
  diskutil apfs list | grep -B1 -A3 macOS135        # check: one new volume, no role
  ```

Do not give it a system role. That would interfere with the existing system and
leave 1TR with no valid users (`m1n1-hypervisor.md:25-30`).

### B3. Install (30-45 min, two automatic restarts)

1. Open "Install macOS Ventura". Click Continue and agree.
2. At the disk choice, click **Show All Disks...** and select **macOS135**.
   **[STOP POINT]** The target must be `macOS135`, never "Macintosh HD" or the Asahi/Omarchy volume.
3. Authenticate with the main macOS admin password when asked.
4. Leave the Mac on power. It restarts by itself and ends in the 13.5 Setup Assistant.
5. If the app refuses to open on the newer main macOS, there is a fallback (not tested here):
   1. Make a USB installer with `sudo "/Applications/Install macOS Ventura.app/Contents/Resources/createinstallmedia" --volume /Volumes/<16GB+ USB stick>`. **[DISK]** This erases the USB stick.
   2. Boot it from Startup Options.
   3. Pick `macOS135` as the target.
6. **Tried 2026-11-06.** The app refused to open on 27.0.1, so the USB route above was used. The
   installer then stopped several times with "Failed to download required installer asset (SFR)".
   The clock was correct. What we found:
   - Apple's asset server (`gdmf.apple.com/v2/assets`) answers an SFR request for J313AP with
     only the newest firmware, **27.2 (26B123)**, whatever version is asking. The 13.5 SFR zip is
     still on `updates.cdn-apple.com`, but it is no longer offered. Apple still signs the 13.5 OS
     (TSS `STATUS=0`). So any install from now on, of any version, moves the system firmware to 27.2.
     Firmware never goes backwards.
   - The installer needs the network to fetch that firmware. Before a retry, from Utilities >
     Terminal in the installer:
     `date -u; curl -sS -o /dev/null -w 'gs:%{http_code}\n' https://gs.apple.com/`.
     After a failure, Window > Installer Log, search "SFR".
   - AsahiLinux/docs#274 (2026-07) installed 14.8.3 from a createinstallmedia stick on a 26.6
     host, so older installers can take newer firmware. Whether 13.5 accepts the 27.2 package is
     unknown.
   - The macOS 14.8.3 SFR is also no longer offered. Apple still serves full installers for
     14.8.9 and 13.7.8, but neither is a documented m1n1 guest.

### B4. Setup Assistant in 13.5 (10 min)

1. Create a local admin account. Note the password: 1TR asks for it in Stage C.
2. Skip the Apple ID.
3. **Turn FileVault off** (uncheck it if it is offered).
4. At the network step, choose "Other Network Options", then "My computer does not connect to the Internet".
   If Setup Assistant will not continue without a network, joining the usual
   Wi-Fi in this volume only is your call. It changes no Omarchy or main macOS setting.
5. Decline analytics, Siri and Screen Time.
6. After login: System Settings → General → Software Update → Automatic
   updates → turn everything **off**. 13.5 must not update itself.

### B5. Prepare the 13.5 volume for the trace (10 min)

1. **[STOP POINT]** Check the version and the firmware:
   ```sh
   sw_vers                                     # ProductVersion 13.5 (build 22G74)
   system_profiler SPHardwareDataType | grep -E 'System Firmware|OS Loader'
   ```
   - "System Firmware Version" must be unchanged from A2.
   - "OS Loader Version" should be the 13.5 one (`iBoot-8422.141.2`).
   - If the system firmware changed, stop and write down both values.
2. Set the sleep options for run 1. They apply to this volume only (`-a` writes this volume's power settings):
   ```sh
   pmset -g > /tmp/pmset-before.txt
   sudo pmset -a hibernatemode 0 standby 0 autopoweroff 0 powernap 0 tcpkeepalive 0
   pmset -g > /tmp/pmset-after.txt; cat /tmp/pmset-after.txt
   ```
   If pmset rejects one keyword (for example `autopoweroff`), drop it and run the line again.
   Why: with the laptop default `hibernatemode 3`, macOS writes a RAM-sized
   sleep image under the hypervisor before the sleep program, and that
   involves SEP hibernation. Run 1 avoids both. A later run can restore 3 (R4).
3. Mount the Omarchy ESP **[DISK]** (files only) and copy the evidence and kernelcache there.
   ```sh
   diskutil list | grep -iE 'EFI|FAT'          # candidate FAT partitions, diskXsY
   diskutil info diskXsY | grep -i 'Partition UUID'   # must equal the ESP PARTUUID from A1
   sudo diskutil mount diskXsY                 # mounts at /Volumes/<EFI name>
   E="/Volumes/<EFI name>/s2r"; ls -l "$E"     # m1n1-70757dc.bin is there only if you did C0 already
   ```
   Find this volume group's kernelcache. Preboot is shared, so there are at
   least two candidates:
   ```sh
   VG=$(diskutil info / | awk -F': +' '/APFS Volume Group/{print $2}'); echo "VG=$VG"
   ls -d /System/Volumes/Preboot/*/boot/*/System/Library/Caches/com.apple.kernelcaches/kernelcache
   diskutil apfs listVolumeGroups              # the group whose volumes are macOS135 / macOS135 - Data
   ```
   If `VG` is empty, take the UUID of the `macOS135` group from
   `listVolumeGroups`. **[STOP POINT]** The path you copy must contain that UUID.
   ```sh
   KC=$(ls /System/Volumes/Preboot/$VG/boot/*/System/Library/Caches/com.apple.kernelcaches/kernelcache)
   sudo mkdir -p "$E"
   sudo cp "$KC" "$E/kernelcache-13.5.img4"
   sw_vers | sudo tee "$E/sw_vers.txt"
   system_profiler SPHardwareDataType | grep -E 'System Firmware|OS Loader' | sudo tee "$E/firmware.txt"
   diskutil apfs listVolumeGroups | sudo tee "$E/volume-groups.txt"
   sudo cp /tmp/pmset-before.txt /tmp/pmset-after.txt "$E/"
   diskutil unmount "/Volumes/<EFI name>"
   ```
4. **[STARTUP DISK]** System Settings → General → Startup Disk → select
   `macOS135` (the installer has usually done this already). It must be the
   default before 1TR: 1TR loads the recoveryOS paired with the default OS, and
   can only change that OS (`tethered-boot.md:67`, `security.md`, "Paired recovery").
5. Shut down.

---

## Stage C. 1TR for the 13.5 volume only: 30-40 min

### C0. Put m1n1.bin on the ESP (Omarchy, 5 min). **[DISK]** (one file)

This needs to happen before C2. Do it in Stage A1 if you like.

1. Copy `~/m1n1/build/m1n1.bin` and its `.sha256` from the host to the M1, over the network Omarchy already uses (for example `scp`).
2. On the M1:
   ```sh
   ESP=$(findmnt -n -o TARGET -t vfat | head -1); echo "$ESP"     # same mount point as A1
   sudo install -D -m644 m1n1.bin "$ESP/s2r/m1n1-70757dc.bin"
   sha256sum "$ESP/s2r/m1n1-70757dc.bin"                         # must match m1n1.bin.sha256
   ```

### C1. Enter 1TR paired with macOS135 (3 min)

1. With macOS135 the default (B5 step 4) and the Mac fully off, press and hold the power button until "Loading startup options..." appears.
2. Click **Options**, then Continue. Authenticate if asked.
3. **[STOP POINT]** The recovery menu must offer "Reinstall macOS **Ventura**". That shows you are in macOS135's paired recoveryOS. If it shows the main macOS's version, the default is wrong: go back to B5 step 4.
4. Utilities → **Terminal**.

### C2. Identify the volume and the ESP (read-only, 3 min)

```sh
diskutil apfs listVolumeGroups               # note the Volume Group UUID of macOS135; compare with s2r/volume-groups.txt
diskutil list                                # find the FAT "EFI - ..." partition, diskXsY
diskutil info diskXsY | grep -i 'Partition UUID'   # must equal the PARTUUID from A1
diskutil mount diskXsY
ls -l "/Volumes/<EFI name>/s2r/"             # m1n1-70757dc.bin must be listed
ls /Volumes/                                 # macOS135 should be listed; if not: diskutil apfs list, then diskutil mount <macOS135 system volume>
```

### C3. Lower security for macOS135 only (5 min). **[SECURITY]**

These changes are per OS. The main macOS keeps Full Security, and the Asahi
stub keeps its own settings (`tethered-boot.md:57`, `introduction.md`,
"Security modes").

1. **[SECURITY]** Allow a custom boot object on macOS135 (Permissive Security):
   ```sh
   bputil -nkcas
   ```
   - When it lists OS installs, choose the **macOS135** Volume Group UUID from C2.
   - Authenticate with the 13.5 admin account from B4.
2. **[SECURITY]** Disable SIP for macOS135 (bputil resets SIP):
   ```sh
   csrutil disable
   ```
   Choose **macOS135** when asked, then authenticate.
3. **[SECURITY]** Install m1n1 as macOS135's boot object:
   ```sh
   kmutil configure-boot -c "/Volumes/<EFI name>/s2r/m1n1-70757dc.bin" --raw \
       --entry-point 2048 --lowest-virtual-address 0 -v /Volumes/macOS135
   ```
4. Optional read-only check: `bputil -d`. Choose macOS135; it should now show a reduced or permissive policy with a custom boot object.
5. Do **not** run `nvram boot-args=...`. This m1n1 build does not need `-v`, and NVRAM boot-args are shared with the Asahi stage 1 backdoor.
6. If `bputil` reports a pairing error, or `csrutil` says "Failed to create local policy", the default OS is not macOS135. See E7, item 5.
7. Apple menu → **Shut Down**.

### C4. Check that m1n1 starts (2 min)

1. Press the power button normally, without holding it.
2. You should see the Apple logo, then m1n1's text console on the Mac's screen ending in "Running proxy...", and it stays there.
   That is success: macOS135 now boots into m1n1 proxy mode and waits for a host (`src/main.c:114-133`).
3. Hold the power button about 10 s until the Mac is off.

### C5. Get the kernelcache to the host (Omarchy once, then M3 Max, 15 min)

**Already done (2026-11-06):** `kc/kernelcache-13.5.macho` was extracted from Apple's public
13.5 (22G74) restore image for j313 (`kernelcache.release.mac13g`, Mach-O sha256
`861adca1...`, Darwin 22.6.0 `RELEASE_ARM64_T8103`), the same build the installer puts in
Preboot, and `session.sh check` passes. Skip this step unless B6 shows a build other than
22G74.


0. If the USB-C cable to the host is attached or a `session.sh console` is open, press Ctrl-C in
   that terminal and unplug the cable first. Opening the tty during boot stops the Asahi stage 1 in
   proxy mode instead of booting Omarchy (see R5).
1. Hold power → Startup Options → choose **Omarchy** → **Continue**.
   Do not click "Always Use": macOS135 stays the default for Stage D, so every forced reboot comes back to the proxy.
2. Copy `$ESP/s2r/` (kernelcache, sw_vers, firmware, volume-groups, pmset files) to the host, over the same network as C0.
3. On the host:
   ```sh
   mkdir -p "$KIT/kc" "$KIT/prep" && cp s2r/*.txt "$KIT/prep/"
   python3 -I "$KIT/kc_extract.py" s2r/kernelcache-13.5.img4 "$KIT/kc/kernelcache-13.5.macho"
   strings "$KIT/kc/kernelcache-13.5.macho" | grep -m1 'Darwin Kernel Version'   # expect 22.6.0 (macOS 13.5)
   "$KIT/session.sh" check                                                        # must end with CHECK OK
   ```
4. Do not share the kernelcache; it is Apple's binary (`docs/sw/macos-kernelcache.md`).
5. Leave Omarchy running if you want to; shut it down before Stage D.

---

## Stage D. The trace session (owner present): 45-60 min per run

Keep three host terminals in `$KIT`:

- **T1**: console;
- **T2**: control;
- **T3**: notes.

Device commands run through the temporary `uucp` group (Stage 0 step 5). In every terminal first run `cd "$KIT"; S="sudo -E -u $USER -g uucp"; export RUN="$KIT/runs/session1"` (a fixed `RUN` keeps all files of a session together even if it runs past midnight; use `session2` for a second day). Option variables go in front of `$S`, for example `S2R_STOP=1 $S ./session.sh guest`; `-E` passes them through sudo.

1. **T1:** `$S ./session.sh console`. It waits for the m1n1 console tty and logs XNU's serial output to `runs/<date>/vuart.log`.
2. Cable the Mac's rear left port to the host. Optionally plug the charger into the other port.
3. Power on the Mac normally. Default is macOS135, so it lands in m1n1 proxy mode.
4. **T2:** `$S ./session.sh wait && $S ./session.sh ping`. Expect `chip id 0x8103`.
   **[STOP POINT]** If nothing enumerates within 1 min, run `./session.sh devices` and try the other Mac port. If still nothing, move to the ThinkPad (Stage 0 step 6).
5. **T2:** `$S ./session.sh postmortem baseline`. It is read-only and must run before `guest`, because `run_guest.py:161` zeroes the PMU panic and boot-error counts. It reads:
   - Sera PMU `leg_scrpad`, `fault_log`, both `fault_shadow` candidates, the alarm block `0xd000-0xd00f` and `pm_setting`;
   - Simetra `fault_log`;
   - the AON watchdog;
   - the wake-block words. Their first read is the one that counts, because they may be read-to-clear.
6. Copy the prep files into the run: `cp "$KIT"/prep/*.txt "$KIT/runs/$(date +%Y%m%d)/"`.
7. **T2:** `$S ./session.sh guest`. This runs `run_guest.py -m hv_s2r_trace.py <kc> -- "debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam wdt=-1 clpc=0"`. Those boot arguments come from `m1n1-hypervisor.md:122-125`.
   - **[PMU WRITE]** `run_guest.py` itself clears the PMU panic counter (upstream behaviour, `run_guest.py:161`).
   - The `[s2r]` banner lists zones. Any `WARNING: zone ... NOT armed` line means the live device tree differs from the t8103 table. Note it in T3. The run is still useful.
   - macOS boots on the Mac's own screen in a few minutes. Log in with the internal keyboard and trackpad.
8. **On the Mac,** in Terminal:
   ```sh
   pmset -g | grep -E 'hibernatemode|standby|powernap|tcpkeepalive|autopoweroff'   # expect 0s; copy into T3
   sudo pmset relative wake 120        # makes macOS program a wake alarm
   sleep 20; pmset sleepnow
   ```
9. **Within those 20 s, in T2:** press Ctrl-C. When "Entering hypervisor shell" appears, type:
   ```
   s2r_go("run1")
   ```
   This arms the sleep-path zones and resumes the guest. (`S2R_ARM_AT_START=1 $S ./session.sh guest` arms from boot instead, with no Ctrl-C, but it is heavier.)
10. **Watch T2.** `[s2r]` lines may show, roughly in this order:
    - SMC `WRITE_KEY` lines, `MBSE` among them;
    - PMP `mgmt SET_AP_POWER`/`SET_IOP_POWER`;
    - PMGR, clkgen and AON writes;
    - possibly `nub-spmi -> s0xf EXT_WRITEL reg 0xd008 [rtc_alarm] ...`, `0xd00e`, `0xd000`, `0xd001 [pm_setting]`. **These may not appear at all.** The PMP coprocessor has its own mapping of the nub-spmi page (pmp reg[32] = 0x23d0d8000+0x4000), and the SMC also talks to the PMU. So the alarm, pm_setting and SLEEP commands may be sent by PMP or SMC firmware, which this kit cannot see. The mailbox records are then the evidence (R3);
    - `hv` lines `CPUSTART W 23b754000+0:32 = 0x..`, `Skip: msr ACC_OVRD_EL1 ...` and `Skip: msr CYC_OVRD_EL1, xN = ...`;
    - `[s2r] cpuN entered its sleep WFI path` for each core, then `exit-cpu ... hw CYC_OVRD_EL1 = 0x...`;
    - `snapshot 'last-cpu'`: the watchdog words when the last core leaves.
11. **Classify the outcome** with the table in R3, then recover as it says.
12. When the Mac is back in proxy mode (it reboots into macOS135): **T2:** `$S ./session.sh postmortem after-run1`. Run this before any new `guest`.
13. **T2:** `./session.sh summarize`. This writes `runs/<date>/summary-*.txt`, the ordered write list.
14. More runs are optional (R4). Then do Stage E.

Files to keep from `runs/<date>/`:

- `s2r-trace-*.jsonl`: every event, one JSON object per line;
- `hv-*.log`;
- `vuart.log`;
- `postmortem-*.txt`/`.json`;
- `summary-*.txt`;
- the prep `.txt` files;
- `clear-counters-*.txt`.

---

## Stage E. Undo everything, and recovery: 15-30 min

### E1. Clear the PMU counters (Mac in proxy mode, 3 min). **[PMU WRITE]**

Do this last, after every postmortem file is saved. The forced reboots raised
the PMU boot-error and panic counters, and upstream clears them on every
session so iBoot does not see a boot-failure loop.

```sh
$S ./session.sh clear-counters          # dry run: prints leg_scrpad+2, writes nothing
$S ./session.sh clear-counters --yes    # one SPMI write of 0, the same as upstream hw/pmu.py:28-31; prints before/after
```

### E2. Make Omarchy the default again (3 min). **[STARTUP DISK]**

0. In T1, press Ctrl-C to stop `session.sh console` (it reconnects by itself otherwise), and
   **unplug the USB-C cable** from the Mac. If the console tty is opened while the Mac boots, the
   Asahi stage 1 stays in proxy mode instead of booting Omarchy (R5).
1. Hold the power button about 10 s until the Mac is off.
2. Hold it again until "Loading startup options..." appears.
3. Select **Omarchy**, hold the **Option** key, and click **Always Use**.
4. Check: Omarchy boots.

Nothing on the Asahi or Omarchy side was changed: not stage 1, not stage 2, not its SIP or `boot-args`.

### E3. Remove the kit files from the ESP (Omarchy, 1 min). **[DISK]** (files only)

```sh
ESP=$(findmnt -n -o TARGET -t vfat | head -1); sudo rm -r "$ESP/s2r"   # m1n1 copy and Apple's kernelcache
```

macOS135 keeps its own copy of m1n1 as its boot object, so this does not break it.

### E4. Optional: delete the 13.5 volume (main macOS, 5 min). **[DISK]** (permanent)

You can keep macOS135 for later runs. It costs only disk space, and its
lowered security applies only when it is booted. If you delete it, the custom
boot object and the lowered security go with it.

1. Startup Options → main macOS → **Continue**.
2. Find the group and delete it:
   ```sh
   diskutil apfs listVolumeGroups           # the group whose volumes are "macOS135" and "macOS135 - Data"
   diskutil apfs deleteVolumeGroup <that Volume Group UUID>
   ```
   Or in Disk Utility: select `macOS135`, click "-" and choose "Delete Volume Group".
   **[STOP POINT]** Read the UUID twice. Never pick the group that holds the main macOS.
3. Small leftovers in the shared Preboot and Recovery volumes, and its unused boot policy, are harmless.
   The boot picker no longer lists macOS135.

### E5. Alternative to E4: keep the volume and restore Full Security. **[SECURITY]**

1. Make macOS135 the default.
2. 1TR (C1) → Utilities → Startup Security Utility → macOS135 → Full Security.
   - This needs internet in recoveryOS, and Apple must still sign 13.5.
   - It also removes the m1n1 boot object.
3. Make Omarchy the default again (E2).

If this fails, use E4.

### E6. Host clean-up (1 min)

- If you installed the optional udev rule: `sudo rm /etc/udev/rules.d/70-m1n1.rules && sudo udevadm control --reload`.
- Keep `runs/`. Do not share the `kc/` kernelcache.

### E7. If the Mac will not boot normally

Work down this list. None of the steps in this plan touch the NOR system firmware, so the Mac cannot be bricked by them (`dev-quickstart.md`, "If things go wrong").

1. **It shows m1n1 text and stays there.** Two causes, both harmless:
   - macOS135 is still the default (its boot object is m1n1). Hold power 10 s, then do E2.
   - Omarchy is the default, but the USB-C cable is attached and a host terminal opened the console tty during boot, so stage 1 stayed in proxy mode. Ctrl-C every `session.sh` on the host, unplug the cable, hold power 10 s, and power on again.
2. **Black screen or hang during a sleep test.** Hold power 10 s, then press it again. With macOS135 as default it comes back in proxy mode and `postmortem` works.
3. **Startup Options does not appear.** Start from fully off, press and **keep holding** the power button until "Loading startup options..." appears. It can take more than 10 s.
4. **1TR does not start, or its menu looks wrong.** Use the fallback System recoveryOS:
   1. From fully off, press and release the power button.
   2. Immediately press and hold it again.
   3. In that recovery, use Apple menu → Startup Disk to pick Omarchy or the main macOS.
5. **Pairing error or "Failed to create local policy" in C3.** The 1TR you are in belongs to another OS.
   1. **[STARTUP DISK]** Shut down, hold power until "Loading startup options...", select macOS135, hold Option and click "Always Use".
   2. Shut down again and enter 1TR again (C1). Check for "Reinstall macOS Ventura".
   3. If "Failed to create local policy" persists: **[SECURITY]** `csrutil clear`, choosing macOS135 only. It is the documented reset (`dev-quickstart.md`, Step 4). Then redo C3 from step 1.
6. **Asked for credentials in 1TR.**
   - The boot picker's "Options" may ask for a machine owner, which is the main macOS admin.
   - `bputil` and `csrutil` for macOS135 ask for the 13.5 admin from B4.
7. **Nothing boots and no boot picker appears.** This is very unlikely.
   - The documented fix is a DFU **revive** from another Mac running macOS with Apple Configurator. It keeps user data. Never choose **restore**, which erases everything.
   - The M3 Max runs Linux, so this needs a separate Mac running macOS (borrow one, or an Apple Store). Do **not** try `idevicerestore` from Linux: `dev-quickstart.md` says it "isn't ready yet", and a wrong choice there erases the Mac.

---

## Reference

### R1. What this kit can and cannot see

**It records the main-CPU (AP) side of sleep entry.** That covers every write macOS makes to:

- PMGR power states, power gates and the candidate cluster-control and CLLT pages;
- the clock generator;
- AON PMGR, including the S2R-timer candidate `0x23d2d4000` and the watchdog pages `0x23d2b0000`/`0x23d2b8000`;
- the wake block `0x23d004000` (writes only);
- both SPMI buses, with decoded Sera PMU commands, as far as the AP issues them;
- the SMC and PMP mailboxes;
- the per-core stop writes (`CPUSTART W ...`).

The E/P cluster blocks are a run-2 option (R4).

**Per-core system registers: partly.**

- ACC_OVRD writes are skipped and logged: `Skip: msr ACC_OVRD_EL1`, from Python's read-only set (`hv/__init__.py:716-719`).
- CYC_OVRD writes take one of two paths (`src/hv/hv_exc.c:360-366`):
  - A value **without** DISABLE_WFI_RET (bit 0) and **without** FIQ_MODE (bits 21:20) is written to the hardware in C and is **not logged**. That covers IRQ_MODE-only and WFI_MODE values.
  - A value **with** bit 0 or FIQ_MODE goes to Python. It is logged as `Skip: msr CYC_OVRD_EL1, xN = ...` and **not written**. With bit 0 the core leaves the guest (`hv/__init__.py:731-738`).
  - The kit's exit-cpu hook reads CYC_OVRD back from the hardware (`hw CYC_OVRD_EL1 = ...`). That gives the last value that did land, so the C-path writes are covered at that moment, though not their order.

**It cannot complete a real sleep, and nothing wakes.**

- m1n1 swallows the per-core stop writes (`hv/__init__.py:1606-1631`).
- No core executes its sleep WFI with DISABLE_WFI_RET set. The deep-WFI CYC_OVRD modes do reach the hardware, but m1n1 has no RVBAR re-entry for a woken core.
- Plan on a forced reboot after every attempt.

**It changes nothing macOS does.**

- Writes are logged, then performed unchanged.
- No zone uses a synchronous Python round trip on the sleep path. That is aura PR #70's lesson: whole-block synchronous trapping slowed XNU past a roughly 5 s watchdog.
- Zones use `UNBUF` or `ASYNC`, which m1n1's C code emulates without stopping the guest (`hv_vm.c:860-883`).
- UNBUF sends each event over USB **before** the write lands (`hv_vm.c:1000-1013`).
- Stop mode (R4) holds exactly one write.

**Guard rails in the tracer.**

- Each PMGR zone is armed only if the live ADT reg[] entry equals the t8103 table (`T8103_PMGR_REG`). A different entry is refused with a warning.
- No zone may be larger than 1 MiB.
- No zone may overlap a 16 KiB page that holds a cpm SError word (R4).
- The guest-side snapshot no longer reads the wake block (`S2R_SNAP_WAKE=0`); `pmu_postmortem.py` reads it after the reboot.

### R2. Why a separate macOS 13.5 volume

The installed Asahi stage 1 m1n1 boots from the Asahi stub OS. Its firmware is
13.5, but the stub has no macOS system to boot. The documented way to run
macOS under the hypervisor is different: m1n1 must be the **boot object of a
macOS 13.5 (or 14.8.3) volume** (`m1n1-hypervisor.md`, "Preparation",
"Installing m1n1 as the macOS kernel"). The main macOS is newer (system
firmware `mBoot-20457`). So the plan uses a separate macOS 13.5 volume and
leaves the main macOS and Omarchy alone.

### R3. What to expect after `pmset sleepnow`

| Seen | Meaning | Do |
|---|---|---|
| All cores print `entered its sleep WFI path`, then a `last-cpu` snapshot, then "Hypervisor exited. Entering shell." | The full AP-side entry was traced. The SoC is still on. | `s2r_snap("after-exit")`, wait 10 s. If USB drops by itself, note the time (a reconfiguration-watchdog reset). Otherwise `reboot()`. |
| No `nub-spmi` writes at all, but SMC `WRITE_KEY` (`MBSE`) and PMP `SET_AP_POWER`/`SET_IOP_POWER` mailbox traffic, then cores exit | The PMU sleep, alarm and pm_setting commands are sent by PMP or SMC firmware, not by the AP. This is a valid result, not a failure. | Keep the `smc-*`/`pmp-*` records and their order relative to the PMGR/AON writes. They are the evidence for this path. Then recover as in row 1. |
| USB disconnects right after a `nub-spmi` write (0xd001 or SLEEP) | The PMU cut the SoC rails. The UNBUF log holds that last write. | Wait 150 s (alarm at 120 s). If a new m1n1 proxy enumerates **without** the Apple logo or chime, note it: that would be a warm entry. Otherwise hold power 10 s and power on. |
| USB disconnects about 5 s after a write in `0x23d2b0000-0x23d2b8fff` or after the last core exits | The reconfiguration watchdog reset the Mac. | Power on if needed, then `postmortem` (`fault_log`/`fault_shadow` bit 11 `wdog,reset_in_1`). |
| No `CPUSTART`/`ACC_OVRD` lines within 60 s | A driver vetoed sleep. | Read `vuart.log` (search "Sleep", "PMRD", "veto"). Ctrl-C, `s2r_disarm()`, Ctrl-D. In macOS, run `pmset -g assertions`. Retry once. |
| Guest exception, SError or panic shell | XNU or the hypervisor crashed. | Save the logs, then `reboot()`. If it happened with `S2R_CLUSTER=1`, turn it off again. |

The guest runs with `wdt=-1`. That keeps XNU's runtime watchdog from firing
while Ctrl-C has the guest paused, and it may also stop XNU arming the sleep
watchdog. R4 has a variant without it.

### R4. Further runs (same session, if time allows)

- **Stop mode: `S2R_STOP=1 $S ./session.sh guest`.**
  - The first write into `S2R_STOP_ZONES` is held, a snapshot is taken and a shell opens. The default zone is the 16 bytes at the S2R-timer candidate, `0x23d2d4000`.
  - `S2R.drop_next=True` drops the write; Ctrl-D performs it.
  - Use it to confirm the S2R timer address. Stay under about 3 s in the shell, because a reconfiguration watchdog may already be armed.
  - Keep the zones small. **Every read inside a HOOK zone becomes a synchronous proxy round trip** (`hv/__init__.py:552-574`), and status polling there brings back the slowdown aura PR #70 measured.
  - Other zones: `S2R_STOP_ZONES=0xADDR:0xSIZE,...`, each at most 16 KiB.
- **Cluster blocks: `S2R_CLUSTER=1`.**
  - This traces pmgr reg[5], [7], [9], [14], [16] and [18].
  - For the two cpm-impl-reg blocks (`0x210e40000`, `0x211e40000`), only the first 16 KiB page is traced. Touching offsets 0x8000, 0x8008 and 0x40f8, and 12 more slots at 0x4008 + n*0x10, raises SErrors (`src/hv/hv_cpu_power.c:20-29`). An emulated access would take the SError in m1n1.
  - A word-sized carve-out cannot avoid that: a `TraceMode.OFF` range that is not page-aligned is still emulated (`hv/__init__.py:212-234`). So those whole pages stay untraced.
  - These blocks are hot during CPU idle. If sleep stalls or the hypervisor dies, turn the option off.
- **Watchdog programming:** `BOOTARGS="debug=0x14e serial=3 apcie=0xfffffffe -enable-kprintf-spam clpc=0" S2R_ARM_AT_START=1 $S ./session.sh guest`. This drops `wdt=-1` and arms from boot, so Ctrl-C is never needed (a paused guest would trip XNU's watchdog).
- **Internal PCIe and Wi-Fi quiesce:** remove `apcie=0xfffffffe` from `BOOTARGS`. This is untested under the hypervisor.
- **Hibernation path, a separate later run:** in the guest, run `sudo pmset -a hibernatemode 3`, then run as normal. Expect minutes of sleep-image writing first. Set it back to 0 afterwards.
- **Noisier blocks:** `S2R_AIC=1` traces AIC writes; `S2R_CONSOLE=2` prints every event.
- **Wake-block reads in the guest snapshot:** `S2R_SNAP_WAKE=1`. Avoid it unless the wake block's read semantics are known.

### R5. The installed Asahi m1n1: proxy for one boot, and back

This is useful as a cable test before Stage D. The default must be Omarchy for it.

- **Requirements.**
  - Stage 1 is a release build with `EARLY_PROXY_TIMEOUT 5` (`config.h:31-32`).
  - It waits 5 s for the host only when verbose mode (`-v`) is set and SIP is disabled for the Asahi volume (`src/main.c:79-110`).
  - Both are **already in place** on this Mac for the Asahi volume (the lab reached this proxy before, `LAB-INVENTORY.md:61-79`). Do not change them; this plan never touches the Asahi volume's SIP or `boot-args`.
- **Enter.**
  1. Start `$S ./session.sh console` in T1 *before* powering on. Opening either tty breaks in.
  2. Power on and boot Omarchy. Stage 1 stays in proxy mode.
  3. Run **only** `$S ./session.sh ping` (expect `0x8103`).
- **Do not run `postmortem`, `guest` or `clear-counters` against stage 1.**
  - Stage 1 is the installer's m1n1 (the lab saw v1.6.1), not 70757dc. Those commands build `ProxyUtils`, which allocates heap and pulls the ADT (`proxyutils.py:44-95`). A proxy ABI mismatch there does undefined work.
  - If you need them on this boot, first run `chainload.py -r ~/m1n1/build/m1n1.bin` (`m1n1-user-guide.md:199`).
- **Back.**
  1. Stop the console (Ctrl-C in T1), then run `$S ./session.sh reboot` (`p.reboot()` only, no PMU write).
  2. With no tty opened, the 5 s window times out and the normal chain runs.

### R6. m1n1 interfaces this kit relies on (checked at 70757dc)

| What | Where |
|---|---|
| `run_guest.py` options `-m` script, `-l` log, payload and boot args; scripts run before `hv.start()`; PMU counter reset | `proxyclient/tools/run_guest.py:14,19,42-43,161-168` |
| `HV.add_tracer` (OFF/RESERVED/BYPASS need no handler), `clear_tracers`, `trace_range` | `proxyclient/m1n1/hv/__init__.py:313-345` |
| Mode to page-table mapping (UNBUF/ASYNC software-mapped, HOOK/SYNC/WSYNC proxied, OFF via `map_hw`) | `hv/__init__.py:348-421` |
| `map_hw` software-maps any part of a range that is not 16 KiB aligned | `hv/__init__.py:212-234`, `src/hv/hv_vm.c:308-320` |
| Default "HW" OFF tracer over every `/arm-io` range (what disarm falls back to) | `hv/__init__.py:1458-1461` |
| Async event dispatch (`handler(evt, **kwargs)`) | `hv/__init__.py:494-524` |
| HOOK write handler `write(addr, val, width_bits, **kwargs)`; reads in a HOOK zone without a read handler are proxied synchronously | `hv/__init__.py:526-633` (`:552-574`, `:620-623`) |
| Same-ident overlap replaces the sub-range | `m1n1/utils.py:730-737` (`DictRangeMap`) |
| `run_script` / `run_shell` / `cont` / `reboot` | `hv/__init__.py:2306-2309, 454-475, 1148-1149, 1303-1306` |
| ACC_OVRD skipped (ro set); CYC_OVRD with bit 0 exits the CPU; `u.mrs` from the trapping core | `hv/__init__.py:716-738, 750-762` |
| CYC_OVRD: values without bit 0 / FIQ_MODE written in C, unlogged | `src/hv/hv_exc.c:353-366`; fields `src/cpu_regs.h:533-542` |
| cpm SError offsets (0x8000, 0x8008, 0x40f8, 0x4008+n*0x10) | `src/hv/hv_cpu_power.c:20-29, 119-125` |
| PMGR hooks for UART0/ATC power states; CPU_START hook; proxy port removed from the guest ADT | `hv/__init__.py:1532-1631, 1683-1712` |
| `TraceMode`, `MMIOTraceFlags`/`EvtMMIOTrace` | `proxyclient/m1n1/hv/types.py:12-26, 50-61` |
| UNBUF: event flushed before the write | `src/hv/hv_vm.c:860-883, 996-1013` |
| PMGR device power-state address walk | `proxyclient/hv/trace_pmgr.py:125-147` |
| SPMI command and reply words, opcodes, `read_extl`, `write8` | `proxyclient/m1n1/hw/spmi1.py:4-14`, `hw/spmi.py:9-22, 45-71, 125-153` |
| Upstream `hv/trace_spmi.py` cannot load at this commit (`trace/spmi.py:5` imports `SPMIRegs`, which `hw/spmi.py` does not define), hence the kit's own decoder | `proxyclient/m1n1/trace/spmi.py:5`, `hw/spmi.py:4-7` |
| `PMU.reset_panic_counter()`: `write8(slave, leg_scrpad+2, 0)` (used by `pmu_clear_counters.py`) | `proxyclient/m1n1/hw/pmu.py:28-31` |
| ASC mailbox offsets; SMC and RTKit management layouts; SMC SRAM address from the first reply | `hw/asc.py:24-43`, `fw/smc.py:9-50`, `fw/asc/mgmt.py:7-50`, `proxyclient/hv/trace_smc.py:65-67` |
| PMU ADT `info-*` parsing | `proxyclient/m1n1/adt.py:318-322, 666-667` |
| `m1n1.setup` resets the panic counter (why `pmu_postmortem.py` does not import it) | `proxyclient/m1n1/setup.py:31` |
| Debug m1n1 with no payload runs the proxy unconditionally | `src/main.c:114-133` |
| `/chosen/asahi,system-fw-version`, `asahi,os-fw-version` (Stage A1) | `src/kboot.c:291-313` |

### R7. Files in this kit

| File | Purpose |
|---|---|
| `hv_s2r_trace.py` | Hypervisor module: validated zones, go/stop modes, SPMI/SMC/PMP decoding, `hv.log` tee, CYC_OVRD readback, last-core snapshot. Shell commands `s2r_go`, `s2r_arm`, `s2r_disarm`, `s2r_snap`, `s2r_mark`, `s2r_status` |
| `s2r_decode.py` | Pure-Python decoders and t8103 labels; `selftest`; `summarize` |
| `pmu_postmortem.py` | Read-only Sera/Simetra/AON readout (`--no-wake` skips the wake block) |
| `pmu_clear_counters.py` | Prints, then with `--yes` clears, the PMU boot-error/panic counters (one SPMI write, same as upstream) |
| `kc_extract.py` | IMG4/IM4P kernelcache to Mach-O (with `--selftest`) |
| `session.sh` | Host helper: check, devices, wait, console, ping, postmortem, guest, reboot, clear-counters, summarize |
| `host/70-m1n1.rules` | Optional udev rule |
| `work/mock_test.py` | Offline test of `hv_s2r_trace.py` against a fake hypervisor (default run, `S2R_CLUSTER=1`, wrong-ADT) |
