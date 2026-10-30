<!-- <FILE>contrib/ac86u/README.md</FILE> - <DESC>Portable AC86U build environment and CLI contracts.</DESC> -->
<!-- <VERS>VERSION: 0.1.1</VERS> -->
<!-- <WCTX>Keep the public environment independent of private build hosts and hardware changes.</WCTX> -->
<!-- <CLOG>Link the integrated hardware regression prerequisites and separate native ucode acceptance.</CLOG> -->

# AC86U environment

Hardware support is a separate review and commit. This environment refuses configuration when the ASUS RT-AC86U profile is absent. It does not supply the hardware patches or prove hardware acceptance.

## Module plan and boundaries

The Makefile owns the portable seed/configure/firmware entrypoints, Linux-only PATH and profile guards. It invokes native OpenWrt make in OPENWRT_ROOT (default: this source checkout). It never cleans caches or supplies an external kernel tree. config.seed owns only single-device selection, plain LuCI and ASUS/RT-AC86U identity; normal OpenWrt networking remains upstream-owned. No calibration, credentials, keys, SSIDs or private iPXE inputs belong here. Existing .config is preserved by configure; choose a fresh checkout or reconcile it explicitly.

scripts/fnc_stamp_build_identity.py owns the identity transaction: validated CLI inputs, .config version fields, files/etc/banner, files/usr/lib/ac86u-build.json and .port ownership digests. It consumes native include/version.mk and banner templates. scripts/cls_run_stage.py owns one subprocess and its private log/status lifecycle, without shell expansion. Tests under tests/ own CLI and rendered-template acceptance checks. Neither tool admits compute: operators must use their site scheduler around make.

Identity CLI: --openwrt-root selects its own Git source tree; --run-dir is a new private directory; --variant is safe ASCII; optional --build-id explicitly repeats a known identity; --banner-label selects display text; --manufacturer and --product set OEM fields; --kernel-release is an optional observed release (null when unspecified); --dry-run validates and prints JSON without writes. Defaults retain native version number, distribution and repository. The manifest schema is 1; build_id, variant, time, upstream_commit, kernel_release, banner_sha256 and optional display/OEM fields identify the assignment. Unknown or tampered managed files, symlinks and existing run directories fail before mutation. Repeating an ID requires a fresh run directory; replacement requires matching ownership digests. Each output publishes atomically; an interrupted multi-file transaction remains inspectable and requires reconciliation, never silent recovery.

Run-stage CLI: --run-dir must be new, --cwd must exist, --label names the stage, --heartbeat-seconds must be finite and positive; the command follows --. Optional binary stdout capture uses a safe basename and optional exact byte count. --dry-run prints the invocation without effects. status.json transitions running to complete or failed, with PID, child PID, heartbeat, elapsed time, byte counters and return code. SIGTERM/interrupt terminates the owned process group; failure retains logs and partial captures. Existing artifacts are never overwritten. Scheduling, remote execution and retries remain outside this module.

Architecture checklist: only contrib/ac86u owns this environment; dependencies point toward native OpenWrt, never private host paths; borrowed cohesive identity transaction (~300 lines) and RunStage class remain together to preserve validation/publication and subprocess lifecycle invariants. Size alone does not justify changing proven logic. The two wrapper tests are adapted from the existing 14 identity tests to the native release layout; runner tests retain their original subprocess acceptance coverage.

## Operator commands

Install normal upstream OpenWrt build prerequisites and update/install the pinned release feeds using scripts/feeds before configuring. From the source root run make -f contrib/ac86u/Makefile help. configure starts only when the hardware profile exists and refuses an existing .config. firmware verifies the normalized single-device selection, stamps the identity, normalizes config again and runs native make with preserved caches. JOBS defaults to 1; set it to the scheduler allocation. RUN_DIR defaults to a unique UTC path under .port/runs; explicit directories must be new. BUILD_ID is optional; use a previous exact ID plus a fresh RUN_DIR for deliberate reproduction. BANNER_LABEL defaults to ASUS RT-AC86U 25.12.6 RC1-public. HTTPS is optional: choose packages deliberately after configuration.

Run make -f contrib/ac86u/Makefile test inside the admitted job. The Kconfig normalization test requires scripts/config/conf and reports a skip until upstream configuration tools exist. The suite also includes the hardware regressions documented in [tests/README.md](tests/README.md); the critical read-only-buffer test requires an explicit prepared pre-871 source baseline and fails clearly when that prerequisite is missing. Native ucode acceptance is a separate documented command requiring its host interpreter/modules. These tests use isolated host fixtures and do not flash or contact a router.

<!-- <FILE>contrib/ac86u/README.md</FILE> - <DESC>Portable AC86U build environment and CLI contracts.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.1</VERS> -->
