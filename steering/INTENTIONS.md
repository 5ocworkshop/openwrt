<!-- <FILE>steering/INTENTIONS.md</FILE> - <DESC>Purpose and boundaries of the AC86U release-based OpenWrt fork.</DESC> -->
<!-- <VERS>VERSION: 0.1.0</VERS> -->
<!-- <WCTX>Make the AC86U work reproducible in the owner's fork while preserving normal OpenWrt behavior.</WCTX> -->
<!-- <CLOG>Establish release baseline, environment-first commit seam and public build/operator boundaries.</CLOG> -->

# AC86U fork intentions

Base the owner's rtac86u-25.12.6 branch on official OpenWrt25.12.6. Keep OFPF metadata in authored files and retain the normal OpenWrt build system.

Land portable environment, build identity, recovery tools and focused tests as one environment-setup commit. Review the hardware patches afterward and integrate them as one implementation commit, with detailed entries in CHANGELOG-RT-AC86U.md and short commit descriptions.

Keep build configuration explicit and portable: select AC86U, plain LuCI and ASUS/RT-AC86U metadata. HTTPS remains an optional package choice. Preserve real upstream version/revision and display a unique timestamped build ID in each candidate's banner, version description and manifest.

Read factory radio data from each unit at runtime; never embed unit calibration, credentials, keys, personal SSIDs or management firewall settings. Recovery tooling selects the operator's local IP and outgoing Windows interface; generated operator logs are not public source inputs.

Reuse the existing OpenWrt CFE binary. The agreed shared-path arrangement belongs in package preparation or an available source revision, without a private filesystem URL or a new vendor payload.

Keep private iPXE/nextboot experiments outside the default board firmware. Retain the observed Lenovo2.4GHz limitation in test notes; further investigation is deferred. Firmware flashing and hardware observations remain user-operated.

Do not push, publish or contact/reconfigure the router without explicit direction. Preserve concurrent changes and accepted artifacts; run local builds/tests/audits through the owner's shared build queue when that local policy applies.

<!-- <FILE>steering/INTENTIONS.md</FILE> - <DESC>Purpose and boundaries of the AC86U release-based OpenWrt fork.</DESC> -->
<!-- <VERS>END OF VERSION: 0.1.0</VERS> -->
