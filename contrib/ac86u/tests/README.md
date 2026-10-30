<!-- <FILE>contrib/ac86u/tests/README.md</FILE> - <DESC>Portable requirements and commands for focused AC86U hardware regressions.</DESC> -->
<!-- <VERS>VERSION: 0.1.0</VERS> -->
<!-- <WCTX>Exercise the public hardware support using isolated host fixtures and the actual prepared wireless driver.</WCTX> -->
<!-- <CLOG>Document focused regression ownership, native tools and the explicit pre-871 baseline contract.</CLOG> -->

# Focused hardware regressions

These tests consume native sources under `target/linux/bcm4908/base-files` and
`package/kernel/mac80211/patches/brcm`. They cover radio NVRAM publication,
firmware hotplug, bounded startup recovery, WAN route/carrier policy, wired LED
provisioning, boot handoff and boot hooks. All runtime paths use temporary mocks;
they do not contact a router or write its sysfs, configuration or vendor data.
The native NVRAM harness compiles the actual completion function and checks the
original read-only fault, preserved filtering and allocation/cleanup cases.
These host checks do not establish hardware acceptance.

Requirements: Python 3, POSIX shell, native C compiler `cc`, `patch`, `strace`,
BusyBox, Node.js, and Ruff for Python checks. The native WAN test additionally
needs a native host `ucode` with the `fs`, `rtnl` and `uci` modules.
Keep the host interpreter separate from target ARM64 binaries.
Missing prerequisites or reported skips mean the affected check is unverified.

## Prepared driver contract

Set `AC86U_BRCMF_FIRMWARE_BASELINE` to a readable prepared
`drivers/net/wireless/broadcom/brcm80211/brcmfmac/firmware.c` from the matching
OpenWrt mac80211 backports tree, with all preceding OpenWrt patches applied but
before `871-brcmfmac-preserve-firmware-buffer.patch`.
There is no machine-specific default or bundled driver/vendor fixture.
The harness fails explicitly when this input, compiler or patch tool is absent;
it requires forward application of the complete patch with zero fuzz.

If the prepared matching driver already includes 871, copy that file into a
fresh temporary directory at its original relative path. Reverse only 871 using
`patch --fuzz=0 --batch -R -p1 -i "$patch"`, retain the resulting pre-871 bytes,
then forward-apply the same full patch with zero fuzz and compare the resulting
whole file byte-for-byte with the original prepared source. Only after that
comparison succeeds use the retained pre-871 file as the baseline. Preserve the
source tree; perform these operations on the temporary copy. Do not substitute
a different kernel's driver or remove unrelated patches to force a match.

## Commands

Run from the OpenWrt root after configuring the baseline variable. The following
explicit list excludes build, recovery tooling and private bootstrap suites.
On hosts requiring buildq admission, supply the local buildq path as `NFS_JOB`
and run through its V1 contract:

```sh
export PYTHONPATH="$PWD/contrib/ac86u/tests"
export NFS5_ROOT="$PWD"
"$NFS_JOB" run --project openwrt-ac86u --agent-id ac86u-hardware-tests \
  --lane hardware-tests --memo "Focused public hardware regressions" \
  --duration medium --cores 1 --mem 1 --max 180 -- \
  python3 -m unittest -v \
    test_radio_nvram test_radio_nvram_hotplug test_radio_startup_recovery \
    test_wan_led_policy test_wired_leds test_boot_led_handoff_hook \
    test_boot_zone_hooks test_brcmfmac_nvram_readonly
```

For native WAN execution, configure `UCODE` to the host executable and, when
necessary, `UCODE_MODULE_PATH` to its native module directory. The fixture root
must be a fresh, nonexistent `/tmp/ac86u-wan-fixture-UNIQUE` path; the test retains
its JSON/filesystem evidence. Include the native module search path with another
`-L "$UCODE_MODULE_PATH"` if it is outside the interpreter defaults:

```sh
"$NFS_JOB" run --project openwrt-ac86u --agent-id ac86u-hardware-tests \
  --lane hardware-native-wan --memo "Native ucode WAN policy fixtures" \
  --duration fast --cores 1 --mem 0.2 --max 30 -- \
  "$UCODE" -L "$PWD/target/linux/bcm4908/base-files/usr/share/ac86u" \
  contrib/ac86u/tests/test_wan_led_native.uc \
  --root "/tmp/ac86u-wan-fixture-$(date -u +%Y%m%dT%H%M%S)-$$"
```

The eight Python hardware files can be checked with `ruff check` and
`ruff format --check`, listing the same module filenames above explicitly.
Use the same admission wrapper for these checks where required.

<!-- <FILE>contrib/ac86u/tests/README.md</FILE> - <DESC>Portable requirements and commands for focused AC86U hardware regressions.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.0</VERS> -->
