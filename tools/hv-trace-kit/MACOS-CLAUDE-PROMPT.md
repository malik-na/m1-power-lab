You are helping me on my MacBook Air (M1, 2020). We are in its main macOS. Goal: install macOS Ventura 13.5 into a NEW, SEPARATE APFS volume called `macOS135`, so that later, from another computer (an M3 Max running Linux), I can run that 13.5 install under the m1n1 hypervisor and record how macOS puts the M1 chip to sleep. You only do the part that happens in this main macOS. Run the commands yourself where you can, show me the output, and stop at every STOP POINT to check the result with me before going on.

Hard rules (never break these):
- Do not create, delete or resize partitions. The new volume goes inside the existing main macOS APFS container and shares its free space.
- Do not touch the other OSes on this disk: there is a Linux install (Omarchy: a 2 GB ext4 partition and a 60 GB encrypted partition, both "Linux filesystem"), an Asahi stub APFS container (about 2.3 GB) and an EFI partition (500 MB, FAT). Do not change or delete anything on them, except the one file in step 2.
- Do not change this main macOS's security settings, SIP, boot policy, NVRAM or boot-args. Do not use an IPSW or DFU restore (that erases the whole disk).
- Do not change network settings.
- Give the new volume no role (not System, not Data). Never pick "Macintosh HD" as the install target.
- Ask me before every command that writes to disk (marked DISK below).

Step 1. Read-only checks.
Run:
  sw_vers
  system_profiler SPHardwareDataType | grep -E 'System Firmware|OS Loader'
  diskutil list
  diskutil apfs list | grep -E 'Container disk|Capacity|Not Allocated|Name:|Role|FileVault'
  diskutil apfs listVolumeGroups
  csrutil status
STOP POINT: tell me (a) the main macOS version, (b) the System Firmware Version, (c) which APFS container holds this macOS (e.g. disk3) and how much is "Not Allocated". We need at least 40 GB free there. If less, stop: I will free space inside this macOS; never resize partitions.

Step 2. Put the m1n1 boot file on the EFI partition (DISK, one file).
The M3 Max is serving it on my local network for a few hours.
  cd ~/Downloads
  curl -fLo m1n1-70757dc.bin http://192.168.1.3:8731/m1n1-70757dc.bin
  shasum -a 256 m1n1-70757dc.bin
The hash must be exactly 39f9b3c303d21976e90e07811b3cd6a970417a4763547e75ca2c66aeba6a4fd9. If not, delete it and stop.
Find the EFI partition whose Partition UUID is 5BC75AEE-87D2-4AE9-8A97-73305CA29AA0 (check each FAT/"EFI" partition with `diskutil info diskXsY | grep -i 'Partition UUID'`). Only that one. Then:
  sudo diskutil mount diskXsY
  sudo mkdir -p "/Volumes/<its name>/s2r"
  sudo cp ~/Downloads/m1n1-70757dc.bin "/Volumes/<its name>/s2r/m1n1-70757dc.bin"
  shasum -a 256 "/Volumes/<its name>/s2r/m1n1-70757dc.bin"    # same hash as above
  diskutil unmount "/Volumes/<its name>"
Do not touch any other file on that partition.

Step 3. Get the macOS 13.5 installer (11.9 GB).
Apple's catalog no longer offers 13.5, so we use the archived copy that the Asahi Linux m1n1 docs link to, and check it before opening it.
  cd ~/Downloads
  curl -fL -o InstallAssistant.pkg https://archive.org/download/install-assistant_20240930/InstallAssistant.pkg
  stat -f %z InstallAssistant.pkg                 # must be 11934300398
  shasum -a 1 InstallAssistant.pkg                # must be 9ceeac3a75aaf3d6e477990caaf2c695f31624e2
  pkgutil --check-signature InstallAssistant.pkg  # must be signed by Apple (Software Update / Apple Root CA)
STOP POINT: if any check fails, delete the file and stop.
Then (DISK) open the package (double-click, or `sudo installer -pkg ~/Downloads/InstallAssistant.pkg -target /`). It puts "Install macOS Ventura.app" in /Applications. Check it:
  codesign -dv --verbose=2 "/Applications/Install macOS Ventura.app" 2>&1 | grep Authority
  /usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "/Applications/Install macOS Ventura.app/Contents/Info.plist"
Only Apple authorities may appear. Optional: copy the app somewhere first; it deletes itself after one install.

Step 4. Add the empty volume (DISK).
With diskN = the main container from step 1:
  diskutil apfs addVolume diskN APFS macOS135
  diskutil apfs list | grep -B1 -A3 macOS135      # one new volume, no role
STOP POINT: show me the result.

Step 5. Install 13.5 into macOS135.
I open "Install macOS Ventura" myself. Tell me: click Continue, agree, then "Show All Disks..." and choose macOS135 ONLY (never Macintosh HD), authenticate with my normal admin password, keep the charger connected. The Mac restarts by itself into the 13.5 setup screens; you will not be there after that.
- If the installer refuses to open on this newer macOS, or says the version cannot be installed/verified/personalized, STOP and tell me the exact message. Do not try workarounds.
- That last case means Apple no longer signs 13.5 for this Mac; that is a valid result, and we stop the whole plan.

When step 5 has started (or stopped with an error), write me a short summary of steps 1-5 with the key outputs, so I can pass it to the Claude on my M3 Max.
