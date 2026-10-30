<!-- <FILE>contrib/ac86u/tools/windows-recovery/README.md</FILE> - <DESC>Run the Windows ASUS recovery uploader with an explicit local IPv4 address.</DESC> -->
<!-- <VERS>VERSION: 0.4.1</VERS> -->
<!-- <WCTX>Provide a small Windows launcher for the RT-AC86U recovery upload.</WCTX> -->
<!-- <CLOG>Add the personal-fork R1.5-only test scope and use-at-own-risk notice.</CLOG> -->

# Windows ASUS recovery uploader

**Use entirely at your own risk.** This personal project has been tested only on
ASUS RT-AC86U revision R1.5. Other revisions and ASUS models are unverified.
The firmware and tools are provided as is without warranty; to the extent
permitted by law, the author accepts no responsibility or liability for damage,
data loss or other consequences. Flashing may erase settings or leave the device
unusable. Existing upstream licenses and notices remain applicable.

Extract the ZIP, then double-click **ASUS-Recovery.cmd**. Keep the whole folder together: the PowerShell script and all **five adjacent C# source files** are required. Windows PowerShell compiles the small managed checksum/recovery helpers using the installed .NET runtime. No installation or administrator elevation is required when the adapter is already configured.

Defaults are source **192.168.1.10** and router **192.168.1.1**. The application verifies that the source address belongs to a local adapter, binds its UDP socket to that address, and selects the adapter's outgoing Windows interface index. It does not change adapter addresses, routes, firewall settings or global execution policy. The launcher sets script execution policy for its own PowerShell process only.

1. Connect Ethernet to a LAN port and enter ASUS rescue mode using Reset during power-on until power flashes slowly.
2. Browse to the correct firmware file or paste a single file path. Surrounding whitespace and matching quotes (Explorer Copy as path) are accepted; embedded line breaks or malformed quotes are rejected before filesystem lookup.
3. Wait for **SHA256** and the image size to appear. The checksum is read-only and selectable for copying. Compare it with the expected image hash before continuing. Hashing runs in the background, including for UNC paths; Upload stays disabled until it finishes. Editing the path immediately clears the old hash.
4. Click **Upload** after reviewing the file and hash. Opening the application, choosing a file and calculating its hash do not start recovery or send recovery packets.
5. Watch the separate discovery, upload, and flash-status stages. The tool keeps its socket open after transfer and waits for the router to report recovery success or failure. On success, keep the router powered while it reboots. Router-reported recovery success does not prove the new operating system booted.

**Cancel upload** closes this session's socket and stops its worker. During flash-status waiting, this becomes **Stop monitoring**: firmware already delivered may still be writing inside the router. Cancellation cannot undo delivered firmware or stop router flash programming. There is no automatic restart of a failed recovery; packet retransmissions are bounded within a session. An already-reported success is not relabeled cancelled. Close/reopen the application to deliberately repeat a successful recovery.

At Upload, the selected path, length and modification time must still match the displayed checksum's file identity. If they changed, the tool recalculates and requires another review/click. The recovery engine also verifies the expected SHA256 against the **same opened, read-shared file stream before creating its UDP channel or sending discovery**, then rewinds that stream for transfer. A content mismatch reports `image_changed` with no recovery packet sent. The displayed hash remains visible during recovery; an `image_changed` result clears it and recalculates before retry is enabled.

Per-run logs are in `%LOCALAPPDATA%\ASUSRecovery\<timestamp-and-id>`. `events.log` records lifecycle changes and heartbeats; `status.json` is atomically updated at least every five seconds while active. It includes the selected SHA256, upload bytes, endpoints, vendor status and errors. Terminal `recovery_success` requires the router's ASUS success packet; `failed` includes phase/timeout or router rejection; `cancelled` means the local session was stopped. A frozen protocol result remains authoritative even if later UI/log reporting fails. Local logging failures are reported and cleanup is independent of logging.

The file-size-derived flash idle timeout follows the inspected ASUS utility: **450 + 24 × floor(file bytes / 1048576) seconds**, refreshed when the router reports it is still writing. For the earlier14,024,724-byte LED image this is762seconds. This is a timeout budget, not a minimum required delay or a completion signal. An additional total-wait bound prevents endless progress messages from keeping the session alive forever.

For preflight that calculates SHA256 and prints the plan without a transfer or a log run:

```powershell
.\ASUS-Recovery.ps1 -Firmware 'C:\firmware\router.bin' -SourceIP 192.168.1.10 -DryRun
```

For an explicitly authorized console recovery:

```powershell
.\ASUS-Recovery.ps1 -Firmware 'C:\firmware\router.bin' -SourceIP 192.168.1.10 -RouterIP 192.168.1.1 -Headless -Upload
```

Use `ASUS-Recovery.cmd -Help` for parameters. Native Windows execution is required to bind a Windows adapter's IP; the WSL NAT interface cannot bind that address directly.

## Packaging and boundary plan

Reuse the existing managed implementation without changing its wire protocol or application defaults. `ASUS-Recovery.cmd` invokes the adjacent PowerShell file through `%~dp0`; the PowerShell provider owns input validation, WinForms, hash review and per-run reports. `RecoveryContracts.cs` owns options and detached snapshots; the packet codec owns byte layout; `RecoveryChannel` owns one local-IP-bound socket and Windows outgoing interface selection (`IP_UNICAST_IF`); `RecoverySession` owns protocol state, bounded retries, cancellation and disposal; `RecoveryImageHash` owns read-only background hashing. They depend only on installed Windows PowerShell/.NET, never curl or external packages.

The public CLI is documented in the examples above and by `-Help`. Local IPv4 must already belong to exactly one adapter; invalid addresses, image identity/hash changes and protocol errors fail without adapter mutation. Firmware is opened read-only, and discovery starts only after explicit Upload. Snapshot/report state includes endpoints, image identity, progress, terminal result and errors. Existing protocol transitions and DTOs are retained; synthetic tests own fixtures and ephemeral local ports, with no live router, firewall or adapter changes. The coherent PowerShell UI and state-machine files are retained rather than split during relocation; this keeps their tested lifecycle and callback ownership intact.

Owned source files are this directory; tests are the adjacent `../../tests/test_windows_recovery*.ps1`, `../../tests/test_asus_recovery_protocol.ps1` and `../../tests/cls_AsusRecoverySimulator.cs`. Packaging must include all five C# files plus both launchers and this README. Exclude generated plans/logs: dry-run output and per-run reports can contain actual IP addresses, full firmware paths and adapter aliases. Logs stay under `%LOCALAPPDATA%\ASUSRecovery` and must not be copied into a public source package.

## ASUS protocol behavior

The same local UDP endpoint survives broadcast discovery, the `ASUSSPACELINK` write request, binary512-byte transfer, and final vendor-status waiting. The desired router address is encoded in the discovery packet; the local source address is selected through socket binding. Valid ASUS status3 means still writing and refreshes the deadline; status1 means recovery succeeded/wait for reboot; other status values mean failure. The tool sends no invented reboot request and does not treat the final ordinary TFTP ACK as flash success. The golden discovery/write-request bytes and simulator exchanges are checked by `../../tests/test_asus_recovery_protocol.ps1`.

## Validation

From native Windows PowerShell at the repository root, run the focused acceptance scripts below. Loopback is the default; `-SourceIP` can select another already configured local test address for the three parameterized scripts. Simulator transfers use the selected local address and ephemeral UDP ports. The test peer validates that its bind address belongs to this PC.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\contrib\ac86u\tests\test_windows_recovery_paths.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\contrib\ac86u\tests\test_windows_recovery_reporting.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\contrib\ac86u\tests\test_windows_recovery_hash.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\contrib\ac86u\tests\test_windows_recovery.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\contrib\ac86u\tests\test_asus_recovery_protocol.ps1
```

When launched through WSL, convert the script path with `wslpath -w` and invoke Windows PowerShell. In this project, all tests and audits must also be admitted through the shared `nfs-job` queue; see the repository execution guidance. The complete protocol script includes its block-rollover case; `-Quick` omits that case for a bounded smoke check. Tests disable broadcast discovery; they never contact the router. Coverage includes checksum preview/copyability, quoted UNC paths, stale-hash clearing, identity/content changes before transfer, exact packet bytes, WinForms construction, dry-run side effects, source validation, explicit authorization, cleanup under injected failures, actual transfers, block rollover, retries, peer filtering, flash-status success/failure/progress/timeouts and cancellation. The engine keeps a selected peer endpoint after the first write ACK; unlike the OEM's fixed-port check, it also accepts standard TFTP transfer-port changes from the configured router.

The PowerShell script owns the UI, input validation and run logs. The five adjacent C# files separate wire encoding, source-bound socket ownership, the asynchronous recovery state machine, options/snapshot contracts and background image hashing. No PowerShell callbacks run on background CLR threads. Cancellation closes the network endpoint promptly; a stalled UNC file operation can delay worker shutdown. Hash edits cannot start a second worker until the previous read stops, and recovery retry remains blocked until its worker stops.

<!-- <FILE>contrib/ac86u/tools/windows-recovery/README.md</FILE> - <DESC>Run the Windows ASUS recovery uploader with an explicit local IPv4 address.</DESC> -->
<!-- <VERS>END OF VERSION: 0.4.1</VERS> -->
