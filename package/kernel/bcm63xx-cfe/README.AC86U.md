<!-- <FILE>package/kernel/bcm63xx-cfe/README.AC86U.md</FILE> - <DESC>Shared ASUS BCM4908 CFE preparation contract.</DESC> -->
<!-- <VERS>VERSION: 0.1.1</VERS> -->
<!-- <WCTX>Reuse the published CFE payload for the two ASUS BCM4908 image consumers.</WCTX> -->
<!-- <CLOG>Record both integrated ASUS profile consumers of the byte-preserving shared package path.</CLOG> -->

# Shared ASUS BCM4908 CFE

The package continues to fetch its original published source archive from OpenWrt's bcm63xx-cfe Git repository at 2025-04-02, commit b8128fa4bdcdaf97549138965b00d5d7ceb7bb0f. The source URL, revision and mirror hash remain unchanged. No additional vendor binary or private source location is required.

## Module plan and boundary contract

The package Makefile owns preparation and staging of CFE assets; it does not own image profiles, wireless drivers, calibration, board identity or per-unit data. After upstream Build/Prepare/Default unpacks and patches the source, Build/Prepare requires the existing physical asus,gt-ac5300/cferam.000 file, moves it to asus,bcm4908-family/cferam.000, and creates the relative compatibility symlink ../asus,bcm4908-family/cferam.000 at its old name. Missing or non-regular source payloads fail loudly before relocation. Preparation runs on a freshly unpacked package tree; retry/re-extraction remains owned by OpenWrt's package lifecycle.

The staged-file boundary provides a physical shared payload and the legacy relative alias beneath $(STAGING_DIR_IMAGE)/bcm63xx-cfe. Build/InstallDev retains upstream $(CP) -r semantics; rules.mk defines CP as cp -fpR, preserving the symlink. Removing the legacy alias cannot remove or invalidate the shared physical file. Payload bytes are unchanged. GNU make expands the preparation macro and its default call; comma-containing path names appear as literal recipe operands rather than function arguments.

Two image consumers, ASUS GT-AC5300 and ASUS RT-AC86U, explicitly select the shared family path in target/linux/bcm4908/image/Makefile. The existing GT-AC5300 source-name lookup remains available through the compatibility alias. This mapping is independent of driver and calibration changes; successful package preparation alone does not validate hardware behavior.

Owned files are this package Makefile, this contract and contrib/ac86u/tests/test_cfe_shared_mapping.py. Dependencies flow from image consumers to staged package assets. No source pin change, new binary, extra tooling framework, host-specific path or router operation belongs to this slice.

## Acceptance

The focused Python tests extract the actual package make macros and execute them through GNU make with a synthetic payload. They exercise default-prepare ordering, the real staging copy flags from rules.mk, physical shared-file ownership, relative alias bytes and link text, alias removal and missing-source failure. An optional AC86U_CFE_ARCHIVE environment variable enables integration against a local copy of the original archive: SHA-256 d33fad4fb5f4419bb287f3c3df6cceabab01fc7852c24cf29a15befa38cc0d45. Its GT-AC5300 payload must remain 355110 bytes with SHA-256 14ff148b6a183ddd76f7fea362672eb2af486b0a9be1d20cfdb7b9a9acbf1824. The public tests contain no vendor payload. Run them through the required compute admission using python3 -m unittest discover -s contrib/ac86u/tests -p test_cfe_shared_mapping.py.

<!-- <FILE>package/kernel/bcm63xx-cfe/README.AC86U.md</FILE> - <DESC>Shared ASUS BCM4908 CFE preparation contract.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.1</VERS> -->
