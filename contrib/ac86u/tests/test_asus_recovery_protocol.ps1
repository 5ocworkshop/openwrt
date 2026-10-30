# <FILE>contrib/ac86u/tests/test_asus_recovery_protocol.ps1</FILE> - <DESC>Native Windows acceptance for the persistent-endpoint ASUS recovery protocol.</DESC>
# <VERS>VERSION: 0.3.1</VERS>
# <WCTX>Verify vendor discovery, binary flash status and upload lifecycle using synthetic loopback peers.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
param([switch]$Quick, [switch]$HashOnly)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $env:TEMP ('ASUS protocol fixture ' + [guid]::NewGuid().ToString('N'))
$passed = $false
$count = 0
function New-ProtocolTestOptions([string]$File, [int]$Port) {
    $options = New-Object AsusRecovery.RecoveryOptions
    $options.FirmwarePath = $File; $options.SourceIP = '127.0.0.1'; $options.RouterIP = '127.0.0.1'; $options.Port = $Port
    $options.BroadcastDiscovery = $false; $options.DiscoverySettleMilliseconds = 0
    $options.DiscoveryTimeoutMilliseconds = 2000; $options.RequestTimeoutMilliseconds = 2000
    $options.DiscoveryRetryMilliseconds = 100; $options.RequestRetryMilliseconds = 100
    $options.DataRetryMilliseconds = 100; $options.DataAttempts = 3
    $options.TransferTimeoutMilliseconds = 5000; $options.FlashIdleTimeoutMilliseconds = 500; $options.MaxFlashWaitMilliseconds = 2000
    return $options
}
function Invoke-ProtocolCase([string]$Mode, [int]$Length, [string]$ExpectedStage, [string]$ExpectedError = '') {
    $file = Join-Path $directory ($Mode + '.bin')
    [AsusRecoveryTests.AsusRecoverySimulator]::CreateFixture($file, $Length)
    $simulator = New-Object AsusRecoveryTests.AsusRecoverySimulator($Mode, $Length)
    $options = New-ProtocolTestOptions $file $simulator.Port
    if ($Mode -eq 'rollover') { $options.TransferTimeoutMilliseconds = 150000; $options.DataRetryMilliseconds = 1000 }
    if ($Mode -eq 'progress_success') { $options.FlashIdleTimeoutMilliseconds = 250; $options.MaxFlashWaitMilliseconds = 3000 }
    if ($Mode -eq 'progress_forever') { $options.FlashIdleTimeoutMilliseconds = 250; $options.MaxFlashWaitMilliseconds = 900 }
    if ($Mode -eq 'late_success') { $options.FlashIdleTimeoutMilliseconds = 250 }
    if ($Mode -eq 'transfer_deadline') { $options.DiscoverySettleMilliseconds = 600; $options.TransferTimeoutMilliseconds = 200 }
    if ($Mode -match '^hash_') { $options.ExpectedSha256 = 'c2525d534358baf2020a2560015aa2adbd23d94eeec6455c24092aafdd8cf1b5' }
    if ($Mode -eq 'hash_match') { $options.ExpectedSha256 = $options.ExpectedSha256.ToUpperInvariant() }
    if ($Mode -eq 'hash_mismatch') { $options.ExpectedSha256 = '0' * 64 }
    $session = New-Object AsusRecovery.RecoverySession($options)
    if ($Mode -eq 'options_copy') { $options.FirmwarePath = 'Z:\not-a-real-local-fixture.bin'; $options.SourceIP = 'invalid-after-construction' }
    if ($Mode -eq 'hash_options_copy') { $options.ExpectedSha256 = '0' * 64 }
    if ($Mode -eq 'hash_file_changed') {
        $changed = [IO.File]::ReadAllBytes($file); $changed[0] = 255
        [IO.File]::WriteAllBytes($file, $changed)
    }
    try {
        $session.Start()
        $duplicateRejected = $false
        try { $session.Start() } catch { $duplicateRejected = $true }
        if (-not $duplicateRejected) { throw 'Repeated Start was accepted' }
        $deadline = [DateTime]::UtcNow.AddSeconds($(if ($Mode -eq 'rollover') { 180 } else { 12 }))
        $sawFlashWait = $false; $ordinaryAckObserved = $false; $cancelled = $false
        do {
            $snapshot = $session.GetSnapshot()
            if ($snapshot.Stage -eq 'waiting_for_flash') { $sawFlashWait = $true }
            if ($simulator.FinalAckSent -and -not $simulator.SuccessSent -and $snapshot.Stage -eq 'recovery_success') { throw 'Ordinary final ACK was mistaken for flash success' }
            if ($simulator.FinalAckSent -and -not $simulator.SuccessSent -and $snapshot.Stage -eq 'waiting_for_flash') { $ordinaryAckObserved = $true }
            if (-not $cancelled -and (($Mode -eq 'cancel_upload' -and $simulator.DataPackets -gt 0) -or ($Mode -eq 'cancel_flash' -and $sawFlashWait))) {
                $session.Cancel(); $cancelled = $true
            }
            if ([DateTime]::UtcNow -gt $deadline) { throw "Case deadline exceeded: $Mode stage=$($snapshot.Stage)" }
            if (-not $snapshot.Terminal) { Start-Sleep -Milliseconds 5 }
        } while (-not $snapshot.Terminal)
        if ($snapshot.Stage -ne $ExpectedStage) { throw "$Mode expected $ExpectedStage, got $($snapshot.Stage): $($snapshot.ErrorKind) $($snapshot.Message); simulator=$($simulator.Error) discovery=$($simulator.DiscoveryRequests) wrq=$($simulator.WriteRequests)" }
        if ($ExpectedError -and $snapshot.ErrorKind -ne $ExpectedError) { throw "$Mode expected error $ExpectedError, got $($snapshot.ErrorKind)" }
        if ($simulator.Error) { throw "$Mode simulator rejected exchange: $($simulator.Error)" }
        if ($ExpectedError -eq 'image_changed') {
            Start-Sleep -Milliseconds 150
            if ($simulator.TotalReceivedPackets -ne 0 -or $snapshot.LocalEndpoint) { throw "$Mode sent traffic or opened a channel before rejecting the image hash" }
        }
        if ($ExpectedStage -eq 'recovery_success') {
            if (-not $sawFlashWait -or -not $ordinaryAckObserved) { throw "$Mode skipped observable vendor-status wait" }
            if ($snapshot.AcknowledgedBytes -ne $Length -or $simulator.BytesReceived -ne $Length) { throw "$Mode payload size mismatch" }
            if (-not $simulator.PayloadMatches -or -not $simulator.ClientPortStable) { throw "$Mode payload or source endpoint mismatch" }
            if ($snapshot.VendorStatus -ne 1) { throw "$Mode did not retain vendor success status" }
        }
        if ($Mode -eq 'exact_block' -and $simulator.FinalDataLength -ne 0) { throw 'Exact-block file omitted empty final DATA' }
        if ($Mode -eq 'rollover' -and (-not $simulator.SawRollover -or $simulator.FinalDataLength -ne 0)) { throw '16-bit rollover or empty EOF missing' }
        if ($Mode -match '_retry$' -and $snapshot.Retransmissions -lt 1) { throw "$Mode did not retransmit" }
        if ($Mode -eq 'progress_success' -and $simulator.ProgressSent -lt 3) { throw 'Idle refresh fixture did not span repeated progress' }
        $terminalStage = $snapshot.Stage
        $session.Cancel(); Start-Sleep -Milliseconds 20
        if ($session.GetSnapshot().Stage -ne $terminalStage) { throw 'Cancel overwrote terminal outcome' }
        $session.Dispose()
        if (-not $session.IsStopped) { throw 'Disposed session retained a worker' }
        if ($snapshot.LocalEndpoint) {
            $parts = $snapshot.LocalEndpoint.Split(':')
            $endpoint = New-Object Net.IPEndPoint ([Net.IPAddress]::Parse($parts[0])), ([int]$parts[1])
            $rebind = New-Object Net.Sockets.UdpClient
            try { $rebind.Client.Bind($endpoint) } finally { $rebind.Close() }
        }
        $script:count++
        Write-Output "PASS: $Mode ($Length bytes) -> $terminalStage"
    } finally {
        $session.Cancel(); $session.Dispose(); $simulator.Dispose()
    }
}
try {
    $source = Join-Path $root 'tools/windows-recovery'
    $files = @('RecoveryContracts.cs', 'cls_AsusRecoveryPackets.cs', 'cls_AsusRecoveryChannel.cs', 'cls_AsusRecoverySession.cs') | ForEach-Object { Join-Path $source $_ }
    foreach ($file in $files) { if (-not (Test-Path -LiteralPath $file)) { throw "Missing engine source: $file" } }
    $files += Join-Path $PSScriptRoot 'cls_AsusRecoverySimulator.cs'
    Add-Type -Path $files -ReferencedAssemblies @('System.dll', 'System.Core.dll')
    [void][IO.Directory]::CreateDirectory($directory)
    $rrq = [AsusRecovery.RecoveryPackets]::BuildDiscovery([Net.IPAddress]::Parse('192.168.1.1'))
    $wrq = [AsusRecovery.RecoveryPackets]::BuildWriteRequest()
    $rrqHex = [BitConverter]::ToString($rrq).Replace('-', '').ToLowerInvariant()
    $wrqHex = [BitConverter]::ToString($wrq).Replace('-', '').ToLowerInvariant()
    if ($rrqHex -ne '00014153555353504143454c494e4b0101a8c0006f6374657400') { throw "Incorrect RRQ: $rrqHex" }
    if ($wrqHex -ne '00024153555353504143454c494e4b006f6374657400') { throw "Incorrect WRQ: $wrqHex" }
    $count++; Write-Output 'PASS: golden RRQ/WRQ bytes encode router IP, not source IP'
    $formatFile = Join-Path $directory 'hash-format.bin'
    [AsusRecoveryTests.AsusRecoverySimulator]::CreateFixture($formatFile, 4)
    foreach ($badHash in @(('a' * 63), ('g' * 64), (' ' + ('a' * 64)), 'abc')) {
        $formatOptions = New-ProtocolTestOptions $formatFile 1
        $formatOptions.ExpectedSha256 = $badHash
        $rejected = $false
        try { $invalidSession = New-Object AsusRecovery.RecoverySession($formatOptions); $invalidSession.Dispose() } catch { $rejected = $true }
        if (-not $rejected) { throw 'Malformed expected SHA256 was accepted' }
    }
    $count++; Write-Output 'PASS: four malformed expected SHA256 values rejected before session start'
    Invoke-ProtocolCase 'hash_match' 513 'recovery_success'
    Invoke-ProtocolCase 'hash_options_copy' 513 'recovery_success'
    Invoke-ProtocolCase 'hash_mismatch' 513 'failed' 'image_changed'
    Invoke-ProtocolCase 'hash_file_changed' 513 'failed' 'image_changed'
    if (-not $HashOnly) {
    Invoke-ProtocolCase 'success' 513 'recovery_success'
    Invoke-ProtocolCase 'exact_block' 1024 'recovery_success'
    Invoke-ProtocolCase 'changed_port' 513 'recovery_success'
    Invoke-ProtocolCase 'options_copy' 513 'recovery_success'
    Invoke-ProtocolCase 'discovery_retry' 513 'recovery_success'
    Invoke-ProtocolCase 'request_retry' 513 'recovery_success'
    Invoke-ProtocolCase 'data_retry' 513 'recovery_success'
    Invoke-ProtocolCase 'wrong_packets' 513 'recovery_success'
    Invoke-ProtocolCase 'progress_success' 513 'recovery_success'
    Invoke-ProtocolCase 'flash_failure' 513 'failed' 'flash_rejected'
    Invoke-ProtocolCase 'server_error' 513 'failed' 'server_error'
    Invoke-ProtocolCase 'flash_timeout' 513 'failed' 'flash_timeout'
    Invoke-ProtocolCase 'late_success' 513 'failed' 'flash_timeout'
    Invoke-ProtocolCase 'progress_forever' 513 'failed' 'flash_timeout'
    Invoke-ProtocolCase 'discovery_timeout' 513 'failed' 'discovery_timeout'
    Invoke-ProtocolCase 'request_timeout' 513 'failed' 'request_timeout'
    Invoke-ProtocolCase 'data_timeout' 513 'failed' 'transfer_timeout'
    Invoke-ProtocolCase 'transfer_deadline' 513 'failed' 'transfer_timeout'
    Invoke-ProtocolCase 'cancel_upload' 513 'cancelled'
    Invoke-ProtocolCase 'cancel_flash' 513 'cancelled'
    if (-not $Quick) { Invoke-ProtocolCase 'rollover' (65536 * 512) 'recovery_success' }
    }
    $passed = $true
    Write-Output "PASS: $count ASUS protocol checks; all traffic stayed on IPv4 loopback"
} catch {
    Write-Error -ErrorAction Continue ("ASUS protocol acceptance failed: " + $_.Exception.Message + "; evidence: $directory")
    exit 1
} finally {
    if ($passed -and (Test-Path -LiteralPath $directory)) { Remove-Item -LiteralPath $directory -Recurse -Force }
}
# <FILE>contrib/ac86u/tests/test_asus_recovery_protocol.ps1</FILE> - <DESC>Native Windows acceptance for the persistent-endpoint ASUS recovery protocol.</DESC>
# <VERS>END OF VERSION: 0.3.1</VERS>
