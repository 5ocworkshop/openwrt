<!-- <FILE>CHANGELOG-RT-AC86U.md</FILE> - <DESC>Detailed AC86U fork change record.</DESC> -->
<!-- <VERS>VERSION: 0.4.3</VERS> -->
<!-- <WCTX>Release RC5 with the 2.4 GHz radio changes and tc.</WCTX> -->
<!-- <CLOG>Date the RC5 section and record what was tested on hardware.</CLOG> -->

# ASUS RT-AC86U changelog

This personal fork starts from official OpenWrt25.12.6. Testing is limited to
ASUS RT-AC86U hardware revision R1.5; other revisions and models are unverified.
The experimental-use and warranty notice in README.md applies.

## RC5 — 2026-11-04

* Fix the 2.4 GHz radio; the stability issues appear to be resolved, and testing
  feedback is appreciated. Clients no longer lose the link and fail DHCP once they
  pass traffic, a failure caused by repeated d11 PSM watchdog resets. Patch 875
  sends the radio settings the ASUS RT-AC86U firmware uses when an AP starts,
  including the 2.4 GHz setting this fix depends on. Radios keep the OpenWrt
  firmware 10.28.2.
* Patch 873 skips the OpenWrt country-code interception on this board, so the
  firmware uses the country from the unit's own radio settings.
* Patch 874 repeats the ASUS PCIe coherency write before firmware download. Tests
  with and without it showed no difference; it stays in the series.
* Each radio keeps its own `ccode` and `regrev`. A radio with no `ccode` gets
  CA/987. The device tree no longer hard-codes one country for every unit.
* `ac86u-radio-nvram` starts each radio file with `wlunit` and copies the global
  `boardrev` to a radio without its own.
* Include `tc-full` and `kmod-sched-core` for traffic control and port
  mirroring. These turn on `CONFIG_NET_CLS_ACT` and `CONFIG_NET_EMATCH` in the
  kernel; `act_mirred` is a module. `libxtables`, `libbpf` and `libelf` come in
  as dependencies.
* Report a fixed kernel build identity, `user@UserPC`, in `/proc/version` and
  the boot log.
* Default candidate identity and login banner to RC5-public; preserve RC1–RC4
  releases.
* On the development unit this image boots with `vht_features` 7 on 2.4 GHz and
  6 on 5 GHz and no watchdog resets. Wi-Fi client stability and throughput on
  this exact image, and port mirroring, are not yet tested.

## RC4 — 2026-10-31

* Include `kmod-fs-vfat` with FAT/VFAT modules and native cp437, ISO-8859-1 and
  UTF-8 NLS dependencies. The selected common USB filesystem set is now
  FAT32/vfat, exFAT, NTFS through the kernel NTFS3 driver, and ext4.
* Retain USB mass-storage/UAS, WireGuard kernel/tools/LuCI and BusyBox `nohup`.
  No NTFS-3G userspace fallback is needed for this supported kernel.
* Default candidate identity and login banner to RC4-public; preserve RC1–RC3
  releases. Do not add formatting tools, automatic mount entries or shares.
* Hardware mounting/read/write and encrypted or other filesystem formats remain
  outside build verification; this selection does not cover every USB device.

## RC3 — 2026-10-31

* Include the native `kmod-fs-exfat` filesystem driver and its NLS-base dependency
  for exFAT-formatted USB storage. Keep the existing ext4, NTFS3, USB mass-storage,
  UAS, WireGuard and BusyBox `nohup` selections.
* Default candidate identity and login banner to RC3-public. No automatic mount
  entries, formatting tools, network shares or operator-specific settings are added.
* Preserve the published RC1/RC2 releases. Actual exFAT mounting and read/write
  behavior require user-operated hardware acceptance after the build.

## RC2 — 2026-10-31

* Default candidate identity and login banner to RC2-public while retaining the
  upstream OpenWrt version/revision and unique timestamped build IDs.
* Enable BusyBox `nohup` in the default applet set; custom BusyBox configuration
  is not required.
* Include USB mass-storage and USB Attached SCSI (UAS) drivers, with native SCSI
  dependencies, for USB flash drives and compatible storage enclosures.
* Include ext4 and the kernel NTFS3 read/write filesystem driver, together with
  their native dependencies and `block-mount` configuration tools.
* Include the WireGuard kernel module, `wireguard-tools` and LuCI WireGuard
  protocol support with native crypto and UDP-tunnel dependencies. Do not
  preconfigure keys, peers, VPN interfaces, routes or firewall permissions.
* Keep existing USB controller selections. Do not add automatic mount entries,
  network file sharing, disk formatting or operator-specific storage settings.
* Reuse native incremental build caches. On-device USB enumeration and ext4/NTFS
  read/write behavior remain user-operated acceptance checks, not build claims.

## Hardware support — 2026-10-30

### Image preparation and existing CFE loader

* Keep the original OpenWrt bcm63xx-cfe source URL, pinned revision and archive
  checksum. Prepare the shared loader path from the binary already supplied by
  that package; no private repository URL or replacement vendor blob is needed.
* Move the existing `asus,gt-ac5300/cferam.000` payload to
  `asus,bcm4908-family/cferam.000` during package preparation and leave the old
  path as a relative compatibility symlink. Both GT-AC5300 and RT-AC86U profiles
  explicitly select the shared path; removing the old alias leaves the shared
  payload intact.
* Preserve the355,110-byte payload exactly, SHA256
  `14ff148b6a183ddd76f7fea362672eb2af486b0a9be1d20cfdb7b9a9acbf1824`.
  This packaging change neither recompiles CFE nor changes its compiled board
  tables. The existing payload includes the94906REF descriptor used by AC86U.
* Add the RT-AC86U board description, memory and flash geometry, physical port
  mappings, peripheral connections, ASUS image identifiers and upgrade handling.

### Kernel initialization, storage and peripheral power

* Correct CFE NAND partition parsing so an intentionally skipped backup partition
  is accepted instead of being reported as an error.
* Add the GPIO mux function used by the AC86U USB power-enable path. USB power is
  independent of status LED control; this does not configure mounts or extroot.
* Retain the wired LED controller changes and staged boot feedback that expose
  kernel, storage/root-mount and userspace progress without a serial console.
  Preserve the standard power-LED boot/failsafe/running/upgrade aliases and hand
  the diagnostic channels back to normal LED policy after startup.

### PCIe and radio initialization

* Retain the tested legacy INTx controls, host-window prerequisites and register
  observations used during radio bring-up.
* Apply the AC86U-scoped vendor-style BAR/inbound-RAM-window, remapping, interrupt
  and spread-spectrum-clock compatibility profile. Keep this behavior scoped to
  the supported board.
* Copy firmware-loader-owned radio NVRAM before country-code filtering. The
  loader can supply read-only memory; modifying that buffer caused the earlier
  kernel write fault. Preserve the filtering behavior without modifying its input.
* Correct procd's failed, empty and incomplete firmware transactions, including
  interrupted and partial I/O, so unsuccessful transfers are explicitly aborted.
* Read each unit's preserved factory radio data read-only and publish validated
  radio configuration in RAM. Firmware images contain generic links and helpers,
  never another unit's calibration or MAC addresses.
* Select stock OpenWrt radio firmware and brcmfmac packages, load the PCIe host
  before the radio driver, and retain normal automatic probing on other boards.
* Bound startup observation and additional binds for expected unbound radios,
  using limited retries/backoff and an overall deadline. This startup policy does
  not establish recovery from every runtime radio failure.

### Normal indicators and runtime prerequisites

* Update wireless LED activation/deactivation handling and restore the tested
  firmware LED pattern/duty when enabled. These LEDs belong to radio firmware,
  separate from the board's wired LED controller.
* Implement carrier-first WAN indication: no carrier means off; carrier with an
  installed main-table default route selects white link/activity; carrier without
  a default route selects red. Reconcile link/route events and startup handoff
  while preserving user LED overrides; no Internet reachability probe is used.
* Enable existing BusyBox defaults for `timeout`, `stat`, formatted stat output
  and **fractional-second sleep**, such as `sleep 0.1`. Existing basic/fancy sleep
  defaults remain enabled and explicit custom feature choices remain respected.

### Qualification limits

The combined fork Python suite passed132 tests with the verified published CFE
archive and an explicit pre-871 driver baseline. This includes the native compiled
read-only-buffer/cleanup regression, per-unit data preparation, startup recovery,
WAN policy simulation, wired LEDs and boot handoff/hooks. The separate native
ucode test remains unverified because its host interpreter/development dependencies
were unavailable; no host dependencies were installed for this change.

Earlier release-based images booted on RT-AC86U R1.5 with this stock CFE payload.
Local development tests demonstrated Samsung connectivity on both bands and
Lenovo connectivity on5GHz. The Lenovo2.4GHz PSM-watchdog/DHCP problem also occurred
with the original ASUS/Merlin CFE and is deferred. Antenna-free performance
observations are preliminary; other board revisions/models are unverified.

A new firmware built from this exact fork implementation commit still requires
the user's flash and hardware acceptance test. Private iPXE/nextboot work,
credentials, personal network policy and inactive experiments are excluded.

## Environment setup — 2026-10-30

* Add the portable `contrib/ac86u` build environment without replacing native
  OpenWrt makefiles or changing the hardware implementation in this commit.
* Provide an AC86U-only configuration seed with plain LuCI and ASUS/RT-AC86U
  manufacturer/product metadata. HTTPS remains optional.
* Guard configuration and firmware commands against a missing AC86U profile,
  accidental multi-profile selection and replacement of an existing `.config`.
* Preserve the native OpenWrt release identity and add an exact timestamped build
  reference to the login banner, version description and JSON manifest. Explicit
  build IDs support deliberate reproduction; ownership checks protect existing
  generated files.
* Run native builds with a Linux-only PATH and configurable parallelism, roots
  and output directories. Reuse normal caches; do not inject a private external
  kernel or require a particular developer's filesystem layout.
* Include observable stage execution with unique logs/status files, heartbeats,
  exit results and owned subprocess cleanup.
* Include the existing Windows recovery uploader, launcher and managed helpers.
  The operator selects a local IPv4 source; the socket binds to that IP and its
  outgoing Windows interface index, which is useful on multi-adapter machines.
* Keep recovery defaults/examples generic. Exclude generated plans/logs from
  public source packaging; those can contain operator-entered paths and network
  details. Do not include credentials, unit calibration, MACs or personal SSIDs.
* Include focused build-identity, configuration, subprocess and Windows recovery
  acceptance tests. Recovery tests use synthetic firmware and local simulators.
* Add the personal-fork, RT-AC86U R1.5 test-scope and use-at-own-risk notices while
  preserving the upstream license and documentation.

The hardware patch set, shared-CFE package mapping and BusyBox feature defaults
belong to the subsequent implementation entry above; the environment commit
itself introduced none of those hardware changes.

<!-- <FILE>CHANGELOG-RT-AC86U.md</FILE> - <DESC>Detailed AC86U fork change record.</DESC> -->
<!-- <VERS>END OF VERSION: 0.4.3</VERS> -->
