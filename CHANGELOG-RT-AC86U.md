<!-- <FILE>CHANGELOG-RT-AC86U.md</FILE> - <DESC>Detailed AC86U fork change record.</DESC> -->
<!-- <VERS>VERSION: 0.1.0</VERS> -->
<!-- <WCTX>Keep detailed changes in one durable record while commit descriptions remain short.</WCTX> -->
<!-- <CLOG>Record the environment setup seam separately from the hardware changes awaiting integration.</CLOG> -->

# ASUS RT-AC86U changelog

This personal fork starts from official OpenWrt25.12.6. Testing is limited to
ASUS RT-AC86U hardware revision R1.5; other revisions and models are unverified.
The experimental-use and warranty notice in README.md applies.

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
are a subsequent implementation seam and are not claimed as landed by this entry.

<!-- <FILE>CHANGELOG-RT-AC86U.md</FILE> - <DESC>Detailed AC86U fork change record.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.0</VERS> -->
