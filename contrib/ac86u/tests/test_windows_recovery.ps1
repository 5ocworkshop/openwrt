# <FILE>contrib/ac86u/tests/test_windows_recovery.ps1</FILE> - <DESC>Native Windows managed ASUS recovery acceptance against a local simulator.</DESC>
# <VERS>VERSION: 0.3.2</VERS>
# <WCTX>Verify source binding, ASUS flash completion and cleanup without contacting a router.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
param([string]$SourceIP = '127.0.0.1')
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
$appDirectory = Join-Path $repository 'tools/windows-recovery'
$app = Join-Path $appDirectory 'ASUS-Recovery.ps1'
$scratch = Join-Path $env:TEMP ('ASUS recovery & fixture ' + [guid]::NewGuid().ToString('N'))
$checks = 0; $passed = $false; $simulator = $null; $script:job = $null
function Invoke-NativeApp([string[]]$Arguments, [string]$Label) {
    $output = Join-Path $scratch ($Label + '-output.log'); $errorLog = Join-Path $scratch ($Label + '-error.log')
    $quoted = @(@('-NoProfile','-ExecutionPolicy','Bypass','-STA','-File') + $Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' '
    $child = Start-Process powershell.exe -ArgumentList $quoted -WorkingDirectory $scratch -PassThru -WindowStyle Hidden -RedirectStandardOutput $output -RedirectStandardError $errorLog
    $null = $child.Handle
    try {
        if (-not $child.WaitForExit(60000)) { $child.Kill(); $child.WaitForExit(); throw ($Label + ' timed out; evidence: ' + $scratch) }
        if ($null -eq $child.ExitCode) { throw ($Label + ' has no exit code') }
        [pscustomobject]@{ code = $child.ExitCode; output = [IO.File]::ReadAllText($output); error = [IO.File]::ReadAllText($errorLog) }
    } finally { if (-not $child.HasExited) { $child.Kill(); $child.WaitForExit() }; $child.Dispose() }
}
function Assert-SessionStopped([object]$Session) {
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while (-not $Session.IsStopped -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 20 }
    if (-not $Session.IsStopped) { throw 'Owned recovery worker did not stop within five seconds' }
    $endpoint = $Session.GetSnapshot().LocalEndpoint
    if ([string]::IsNullOrWhiteSpace($endpoint)) { throw 'Fault fixture did not reach a bound UDP socket' }
    $probe = New-Object Net.Sockets.UdpClient
    try { $probe.Client.Bind((New-Object Net.IPEndPoint ([Net.IPAddress]::Parse($SourceIP)), ([int]($endpoint.Split(':')[-1])))) }
    finally { $probe.Dispose() }
}
try {
    if (-not (Get-NetIPAddress -AddressFamily IPv4 -IPAddress $SourceIP -ErrorAction SilentlyContinue)) { throw 'Test address is not assigned locally' }
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($app, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }; $checks++
    [void][IO.Directory]::CreateDirectory($scratch)
    $appSource = [IO.File]::ReadAllText($app); $uiAnchor = '[Windows.Forms.Application]::Run($form)'
    if (-not $appSource.Contains($uiAnchor)) { throw 'Cannot locate GUI message loop' }
    $uiAssertions = 'if ($form.Controls.Count -lt 10 -or $send.Text -ne "Upload" -or $sourceBox.Text -ne "192.168.1.10" -or $routerBox.Text -ne "192.168.1.1") { throw "Incorrect GUI controls" }; Write-Output "PASS: native WinForms controls constructed"'
    $guiProbe = Join-Path $scratch 'gui-probe.ps1'
    [IO.File]::WriteAllText($guiProbe, $appSource.Replace($uiAnchor, $uiAssertions))
    Copy-Item -LiteralPath (Join-Path $appDirectory 'cls_RecoveryImageHash.cs') -Destination (Join-Path $scratch 'cls_RecoveryImageHash.cs')
    $result = Invoke-NativeApp @($guiProbe) 'gui-construction'
    if ($result.code -ne 0 -or $result.output -notmatch 'PASS: native WinForms') { throw ('GUI construction failed: ' + $result.error) }; $checks++
    Write-Output 'PASS: native Windows GUI construction; no message loop or upload'
    $sources = @('RecoveryContracts.cs','cls_AsusRecoveryPackets.cs','cls_AsusRecoveryChannel.cs','cls_AsusRecoverySession.cs') | ForEach-Object { Join-Path $appDirectory $_ }
    Add-Type -Path @($sources + (Join-Path $PSScriptRoot 'cls_AsusRecoverySimulator.cs'))
    $firmware = Join-Path $scratch 'firmware & sample.bin'
    [AsusRecoveryTests.AsusRecoverySimulator]::CreateFixture($firmware, 256)
    $logRoot = Join-Path $env:LOCALAPPDATA 'ASUSRecovery'
    $before = @(); if (Test-Path -LiteralPath $logRoot) { $before = @(Get-ChildItem -LiteralPath $logRoot | ForEach-Object Name) }
    $result = Invoke-NativeApp @($app,'-Firmware',$firmware,'-SourceIP',$SourceIP,'-RouterIP',$SourceIP,'-DryRun','-UnicastDiscovery') 'dry-run'
    if ($result.code -ne 0) { throw ('Dry run failed: ' + $result.error) }
    $plan = $result.output | ConvertFrom-Json
    if ($plan.source_ip -ne $SourceIP -or $plan.protocol -ne 'asus-recovery' -or $plan.firmware -ne $firmware -or $plan.discovery -ne $SourceIP -or $plan.expected_sha256 -ne (Get-FileHash -LiteralPath $firmware -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Incorrect bound managed plan or selected image hash' }
    $after = @(); if (Test-Path -LiteralPath $logRoot) { $after = @(Get-ChildItem -LiteralPath $logRoot | ForEach-Object Name) }
    if (($before -join [char]0) -ne ($after -join [char]0)) { throw 'Dry run created logs' }; $checks++
    $result = Invoke-NativeApp @($app,'-Firmware',$firmware,'-SourceIP','203.0.113.254','-RouterIP',$SourceIP,'-DryRun') 'invalid-source'
    if ($result.code -eq 0) { throw 'Unassigned source address accepted' }; $checks++
    $result = Invoke-NativeApp @($app,'-Firmware',$firmware,'-SourceIP',$SourceIP,'-RouterIP',$SourceIP,'-Headless') 'missing-authorization'
    if ($result.code -eq 0) { throw 'Headless recovery accepted without -Upload' }; $checks++
    $definitions = @($ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false))
    foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
    $UnicastDiscovery = $true; $DiscoverySettleMilliseconds = 0; $TransferTimeoutSeconds = 10; $FlashTimeoutSeconds = 2; $MaxFlashWaitSeconds = 3
    $simulator = New-Object AsusRecoveryTests.AsusRecoverySimulator('cancel_flash',256,$SourceIP)
    $faultPlan = [pscustomobject]@{ firmware = $firmware; bytes = 256; source_ip = $SourceIP; router_ip = $SourceIP; adapter = 'local test'; port = $simulator.Port; protocol = 'asus-recovery'; flash_timeout_seconds = 2 }
    $script:injectedWrites = 0
    Set-Item Function:Write-RecoveryStatus -Value {
        param($Stage, $Code)
        $script:injectedWrites++
        if ($script:injectedWrites -ge 2) {
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            while (-not $script:job.session.GetSnapshot().LocalEndpoint -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 10 }
            throw 'Injected status-write failure after session start'
        }
        $script:job.stage = $Stage; $script:job.lastHeartbeat = [DateTime]::UtcNow
    }
    $startupFailed = $false
    try { Start-RecoveryUpload $faultPlan } catch { $startupFailed = $true }
    if (-not $startupFailed -or -not $script:job.session) { throw 'Startup fault did not reach a managed session' }
    Assert-SessionStopped $script:job.session
    $script:job.session.Dispose(); $script:job = $null; $simulator.Dispose(); $simulator = $null; $checks++
    Write-Output 'PASS: startup logging failure stops real worker and releases its bound socket'
    $writer = $definitions | Where-Object Name -eq 'Write-RecoveryStatus'; . ([scriptblock]::Create($writer.Extent.Text))
    $simulator = New-Object AsusRecoveryTests.AsusRecoverySimulator('cancel_flash',256,$SourceIP)
    $faultPlan.port = $simulator.Port
    Start-RecoveryUpload $faultPlan
    $deadline = [DateTime]::UtcNow.AddSeconds(5)
    while (-not $script:job.session.GetSnapshot().LocalEndpoint -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 10 }
    Set-Item Function:Update-RecoveryUpload -Value { throw 'Cancellation must not call the failed monitor' }
    Stop-RecoveryUpload -NoStatus
    Assert-SessionStopped $script:job.session
    if ($script:job.session.GetSnapshot().Stage -ne 'cancelled') { throw 'Cancellation did not reach terminal state' }
    $updater = $definitions | Where-Object Name -eq 'Update-RecoveryUpload'; . ([scriptblock]::Create($updater.Extent.Text))
    Update-RecoveryUpload
    if ($script:job.stage -ne 'cancelled') { throw 'Cancellation was not recorded in status' }
    $script:job.session.Dispose(); $script:job = $null; $simulator.Dispose(); $simulator = $null; $checks++
    Write-Output 'PASS: cancellation ignores broken monitoring and releases the real UDP endpoint'
    foreach ($length in @(513,1024)) {
        $file = Join-Path $scratch ("firmware & sample-$length.bin")
        [AsusRecoveryTests.AsusRecoverySimulator]::CreateFixture($file,$length)
        $simulator = New-Object AsusRecoveryTests.AsusRecoverySimulator('progress_success',$length,$SourceIP)
        $result = Invoke-NativeApp @($app,'-Firmware',$file,'-SourceIP',$SourceIP,'-RouterIP',$SourceIP,'-Port',[string]$simulator.Port,'-Headless','-Upload','-UnicastDiscovery','-DiscoverySettleMilliseconds','0','-FlashTimeoutSeconds','2','-MaxFlashWaitSeconds','4') ("success-$length")
        if ($result.code -ne 0) { throw ('Synthetic ASUS recovery failed: ' + $result.error + $result.output) }
        if ($simulator.Error -or -not $simulator.FinalAckSent -or -not $simulator.SuccessSent -or -not $simulator.PayloadMatches -or -not $simulator.ClientPortStable -or $simulator.BytesReceived -ne $length -or $simulator.FinalDataLength -ne ($length % 512)) { throw ('Simulator rejected transfer: ' + $simulator.Error) }
        $match = [regex]::Match($result.output,'(?m)^Recovering .* Logs: (.+)\r?$'); if (-not $match.Success) { throw 'Application omitted logs' }
        $run = $match.Groups[1].Value.Trim()
        $state = [IO.File]::ReadAllText((Join-Path $run 'status.json')) | ConvertFrom-Json
        $events = [IO.File]::ReadAllText((Join-Path $run 'events.log'))
        if ($state.stage -ne 'recovery_success' -or $state.returncode -ne 0 -or $state.vendor_status -ne 1 -or $state.local_endpoint -notlike ($SourceIP + ':*') -or $events -notmatch 'waiting_for_flash' -or $state.expected_sha256 -ne (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Status failed to distinguish image identity, bound upload, flash waiting and vendor success' }
        $checks++; Write-Output "PASS: $length bytes from $SourceIP, stable endpoint, final DATA $($simulator.FinalDataLength) bytes, flash waiting then vendor6/1; logs: $run"
        $simulator.Dispose(); $simulator = $null
    }
    $simulator = New-Object AsusRecoveryTests.AsusRecoverySimulator('flash_timeout',256,$SourceIP)
    $result = Invoke-NativeApp @($app,'-Firmware',$firmware,'-SourceIP',$SourceIP,'-RouterIP',$SourceIP,'-Port',[string]$simulator.Port,'-Headless','-Upload','-UnicastDiscovery','-DiscoverySettleMilliseconds','0','-FlashTimeoutSeconds','1','-MaxFlashWaitSeconds','2') 'missing-flash-status'
    if ($result.code -eq 0 -or -not $simulator.FinalAckSent -or $simulator.SuccessSent) { throw 'TFTP-only completion accepted as recovery success' }
    $match = [regex]::Match($result.output,'(?m)^Recovering .* Logs: (.+)\r?$'); if (-not $match.Success) { throw 'Failed session omitted logs' }
    $run = $match.Groups[1].Value.Trim(); $state = [IO.File]::ReadAllText((Join-Path $run 'status.json')) | ConvertFrom-Json
    if ($state.stage -ne 'failed' -or $state.error_kind -ne 'flash_timeout' -or $state.acknowledged_bytes -ne 256 -or $state.returncode -eq 0) { throw 'Missing flash result lacked distinct failed status' }
    $simulator.Dispose(); $simulator = $null; $checks++
    Write-Output "PASS: final TFTP ACK without vendor success fails; logs: $run"
    Write-Output "PASS: $checks native Windows managed recovery checks; only local PC address contacted, no router or broadcast"
    $passed = $true
} catch {
    Write-Error -ErrorAction Continue ("Windows acceptance failed: $($_.Exception.Message); evidence: $scratch")
    exit 1
} finally {
    if ($script:job -and $script:job.session) { try { $script:job.session.Cancel(); $script:job.session.Dispose() } catch { [Console]::Error.WriteLine('Test cleanup failed: ' + $_.Exception.Message) } }
    if ($simulator) { $simulator.Dispose() }
    if ($passed -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
# <FILE>contrib/ac86u/tests/test_windows_recovery.ps1</FILE> - <DESC>Native Windows managed ASUS recovery acceptance against a local simulator.</DESC>
# <VERS>END OF VERSION: 0.3.2</VERS>
