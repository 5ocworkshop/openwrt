<!-- <FILE>contrib/ac86u/NOHUP-IMPLEMENTATION.md</FILE> - <DESC>Design and acceptance plan for firmware nohup support.</DESC> -->
<!-- <VERS>VERSION: 0.1.0</VERS> -->
<!-- <WCTX>Add the BusyBox nohup applet without changing the native build pipeline.</WCTX> -->
<!-- <CLOG>Define configuration ownership, incremental rebuild and firmware acceptance checks.</CLOG> -->

# Firmware nohup

## Contract and ownership

Enable `BUSYBOX_DEFAULT_NOHUP` in `package/utils/busybox/Config-defaults.in`.
That file owns the default applet policy; retain its upstream Kconfig layout.
Do not enable custom BusyBox configuration or change unrelated applets.
The existing package Makefile selects DEFAULT versus CONFIG according to
`BUSYBOX_CUSTOM`, translates the selected symbols into BusyBox `.config`,
and owns compilation and installation. No new runtime module or FSM is needed.

The external interface is the existing BusyBox `nohup COMMAND [ARG...]`
applet and its installed command link. BusyBox owns argument handling,
SIGHUP behavior, output redirection and errors; this change adds availability,
not new command semantics. Acceptance must inspect the rebuilt applet list
and command link in the firmware filesystem. Router execution remains
user-operated; do not flash, publish or contact hardware.

```text
fork Kconfig defaults -> OpenWrt .config -> BusyBox .config
                                              |
                                              v
                                     BusyBox applet + link
                                              |
                                              v
                                     rebuilt firmware image
```

```mermaid
flowchart LR
  Defaults[Kconfig defaults] --> Config[OpenWrt config]
  Config --> BusyBox[BusyBox package]
  BusyBox --> Root[Root filesystem]
  Root --> Image[Firmware image]
```

## Implementation and verification

- Keep the existing topology and native package boundary; no adapter or new library.
- `contrib/ac86u/tests/test_build_seed.py` owns the default-policy regression.
  Add a failing check for the nohup default before changing it.
- Change only the nohup default and required file metadata. The generated
  Kconfig table remains cohesive despite exceeding normal authored LOC guidance.
- Normalize the existing `.config` with native `make defconfig`; verify
  `CONFIG_BUSYBOX_DEFAULT_NOHUP=y` and custom configuration remains disabled.
- Use `contrib/ac86u/Makefile firmware` under site compute admission with
  allocated `JOBS`. It stamps a fresh identity and reuses native build caches;
  do not invoke clean, dirclean or download/toolchain replacement.
- Verify successful build status, BusyBox `CONFIG_NOHUP=y`, installed `nohup`
  link and applet name in the regenerated firmware filesystem; record hashes
  and firmware paths. Do not infer on-device success from compilation alone.

<!-- <FILE>contrib/ac86u/NOHUP-IMPLEMENTATION.md</FILE> - <DESC>Design and acceptance plan for firmware nohup support.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.0</VERS> -->
