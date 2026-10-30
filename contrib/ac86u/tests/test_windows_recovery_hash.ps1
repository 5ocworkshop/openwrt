# <FILE>contrib/ac86u/tests/test_windows_recovery_hash.ps1</FILE> - <DESC>Native checksum preview, identity and GUI gating acceptance without recovery traffic.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Make the selected image SHA256 visible and authoritative before Upload becomes available.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
param([string]$SourceIP = '127.0.0.1')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$directory = Join-Path $root 'tools/windows-recovery'
$app = Join-Path $directory 'ASUS-Recovery.ps1'
$helper = Join-Path $directory 'cls_RecoveryImageHash.cs'
$scratch = Join-Path $env:TEMP ('ASUS hash fixture ' + [guid]::NewGuid().ToString('N'))
$passed = $false; $hasher = $null; $child = $null; $checks = 0
function Wait-ImageHash([object]$Worker) {
    $deadline = [DateTime]::UtcNow.AddSeconds(20)
    while (-not $Worker.IsStopped -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 20 }
    if (-not $Worker.IsStopped) { throw 'Hash worker did not stop before the test deadline' }
    $Worker.GetSnapshot()
}
try {
    if (-not (Test-Path -LiteralPath $helper)) { throw 'Image-hash helper is missing' }
    Add-Type -Path $helper
    [void][IO.Directory]::CreateDirectory($scratch)
    $file = Join-Path $scratch 'firmware & abc.bin'
    [IO.File]::WriteAllBytes($file, [Text.Encoding]::ASCII.GetBytes('abc'))
    $expected = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    $hasher = New-Object AsusRecovery.RecoveryImageHash($file)
    $snapshot = Wait-ImageHash $hasher
    if ($snapshot.Hash -ne $expected -or $snapshot.Length -ne 3 -or $snapshot.BytesRead -ne 3 -or -not $snapshot.Terminal -or $snapshot.Error) { throw 'Known SHA256 or progress is incorrect' }
    if ([object]::ReferenceEquals($snapshot, $hasher.GetSnapshot())) { throw 'Hash snapshots are not detached' }
    $hasher.Dispose(); $hasher = $null; $checks++
    $hasher = New-Object AsusRecovery.RecoveryImageHash((Join-Path $scratch 'missing.bin'))
    $failed = Wait-ImageHash $hasher
    if (-not $failed.Terminal -or -not $failed.Error -or $failed.Hash) { throw 'Missing file did not fail visibly' }
    $hasher.Dispose(); $hasher = $null; $checks++
    $large = Join-Path $scratch 'cancel.bin'; $stream = [IO.File]::Create($large)
    try { $stream.SetLength(536870912) } finally { $stream.Dispose() }
    $hasher = New-Object AsusRecovery.RecoveryImageHash($large); $hasher.Cancel(); $hasher.Dispose()
    if (-not $hasher.IsStopped -or -not $hasher.GetSnapshot().Terminal) { throw 'Cancelled hashing left an active worker' }
    $hasher = $null; $checks++
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($app, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    foreach ($definition in $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Get-RecoveryPath','Get-RecoveryPlan','Test-RecoveryImageIdentity') },$false)) { . ([scriptblock]::Create($definition.Extent.Text)) }
    $hasher = New-Object AsusRecovery.RecoveryImageHash((Get-RecoveryPath ('"' + $app + '"')))
    $uncHash = Wait-ImageHash $hasher
    if ($uncHash.Hash -ne (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'Quoted application UNC path did not hash correctly' }
    $hasher.Dispose(); $hasher = $null; $checks++
    $Port = 69; $FlashTimeoutSeconds = 0; $UnicastDiscovery = $true
    $quoted = '"' + $file + '"'
    $plan = Get-RecoveryPlan $quoted $SourceIP $SourceIP $expected
    if ($plan.expected_sha256 -ne $expected -or -not (Test-RecoveryImageIdentity $snapshot $plan)) { throw 'Quoted path or checksum identity was not retained' }
    [IO.File]::WriteAllText($file, 'abcd')
    $changedPlan = Get-RecoveryPlan $quoted $SourceIP $SourceIP $expected
    if (Test-RecoveryImageIdentity $snapshot $changedPlan) { throw 'Changed file retained the old checksum identity' }; $checks++
    [IO.File]::WriteAllText($file, 'abc')
    [IO.File]::SetLastWriteTimeUtc($file, $snapshot.LastWriteUtc.AddSeconds(2))
    $changedTime = Get-RecoveryPlan $quoted $SourceIP $SourceIP $expected
    if (Test-RecoveryImageIdentity $snapshot $changedTime) { throw 'Changed timestamp retained the reviewed identity' }; $checks++
    $otherFile = Join-Path $scratch 'same bytes at another path.bin'
    [IO.File]::WriteAllText($otherFile, 'abc'); [IO.File]::SetLastWriteTimeUtc($otherFile, $snapshot.LastWriteUtc)
    $changedPath = Get-RecoveryPlan $otherFile $SourceIP $SourceIP $expected
    if (Test-RecoveryImageIdentity $snapshot $changedPath) { throw 'A different path retained the reviewed identity' }; $checks++
    [IO.File]::WriteAllText($file, 'abc')
    $source = [IO.File]::ReadAllText($app)
    $anchor = '[Windows.Forms.Application]::Run($form)'
    if (-not $source.Contains($anchor)) { throw 'Cannot locate the real GUI message loop' }
    $quotedFile = "'" + $file.Replace("'", "''") + "'"
    $quotedIP = "'" + $SourceIP.Replace("'", "''") + "'"
    $acceptance = @'
if ($send.Enabled -or -not $hashBox.ReadOnly -or $hashBox.Text) { throw 'Upload or checksum controls start in an unsafe state' }
$sourceBox.Text = __SOURCE_IP__; $routerBox.Text = __SOURCE_IP__
$fileBox.Text = '"' + __FILE__ + '"'
$deadline = [DateTime]::UtcNow.AddSeconds(20)
while (-not $send.Enabled -and [DateTime]::UtcNow -lt $deadline) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 20 }
if (-not $send.Enabled -or $hashBox.Text -ne 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad') { throw ('GUI did not display the selected image hash: ' + $status.Text) }
$hashBox.SelectAll(); if ($hashBox.SelectedText -ne $hashBox.Text) { throw 'Displayed checksum cannot be selected for copying' }
$fileBox.Text = ' ' + $fileBox.Text
if ($send.Enabled -or $hashBox.Text) { throw 'Editing a pasted path retained an enabled upload or stale checksum' }
$deadline = [DateTime]::UtcNow.AddSeconds(20)
while (-not $send.Enabled -and [DateTime]::UtcNow -lt $deadline) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 20 }
if (-not $send.Enabled) { throw 'Equivalent normalized pasted path was not rehashed' }
[IO.File]::WriteAllText(__FILE__, 'abcd')
$script:testStarted = 0
Set-Item Function:Start-RecoveryUpload -Value { param($Plan) $script:testStarted++ }
$click = [Windows.Forms.Control].GetMethod('OnClick', [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::NonPublic)
$click.Invoke($send, [object[]]@([EventArgs]::Empty))
if ($script:testStarted -ne 0 -or $send.Enabled -or $hashBox.Text) { throw ('A changed image bypassed checksum review: starts=' + $script:testStarted + ' enabled=' + $send.Enabled + ' hash=' + $hashBox.Text) }
$deadline = [DateTime]::UtcNow.AddSeconds(20)
while (-not $send.Enabled -and [DateTime]::UtcNow -lt $deadline) { [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 20 }
if (-not $send.Enabled) { throw 'Changed image was not recalculated for operator review' }
$reviewed = $hashBox.Text
$click.Invoke($send, [object[]]@([EventArgs]::Empty)); $timer.Stop()
if ($script:testStarted -ne 1 -or $hashBox.Text -ne $reviewed -or $hashBox.Text.Length -ne 64) { throw 'Reviewed pasted-path hash disappeared when the upload started' }
$terminal = [pscustomobject]@{ Stage = 'failed'; ErrorKind = 'image_changed'; Terminal = $true; Percent = 0; Message = 'Image changed before discovery' }
$fakeSession = [pscustomobject]@{ Snapshot = $terminal; IsStopped = $true }
$fakeSession | Add-Member -MemberType ScriptMethod -Name GetSnapshot -Value { $this.Snapshot }
$script:job = @{ session = $fakeSession; directory = 'synthetic UI fixture' }
Set-Item Function:Update-RecoveryUpload -Value { }
$tick = [Windows.Forms.Timer].GetMethod('OnTick', [Reflection.BindingFlags]::Instance -bor [Reflection.BindingFlags]::NonPublic)
$tick.Invoke($timer, [object[]]@([EventArgs]::Empty))
if ($send.Enabled -or $hashBox.Text -or $script:hashResult) { throw 'Backend image_changed left a stale checksum available for retry' }
$timer.Stop(); $hashTimer.Stop(); $script:job = $null
Write-Output 'PASS: native GUI displays/selects SHA256, clears stale hashes and blocks changed-image upload'
'@
    $acceptance = $acceptance.Replace('__FILE__',$quotedFile).Replace('__SOURCE_IP__',$quotedIP)
    $probe = Join-Path $scratch 'gui-hash-probe.ps1'
    [IO.File]::WriteAllText($probe,$source.Replace($anchor,$acceptance))
    Copy-Item -LiteralPath $helper -Destination (Join-Path $scratch 'cls_RecoveryImageHash.cs')
    $output = Join-Path $scratch 'gui-output.log'; $errorLog = Join-Path $scratch 'gui-error.log'
    $child = Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -STA -File "' + $probe + '"') -PassThru -WindowStyle Hidden -RedirectStandardOutput $output -RedirectStandardError $errorLog
    $null = $child.Handle
    if (-not $child.WaitForExit(60000)) { $child.Kill(); $child.WaitForExit(); throw 'GUI hash acceptance timed out' }
    if ($child.ExitCode -ne 0 -or [IO.File]::ReadAllText($output) -notmatch 'PASS: native GUI') { throw ('GUI checksum acceptance failed: ' + [IO.File]::ReadAllText($errorLog)) }
    $child.Dispose(); $child = $null; $checks++
    $output = Join-Path $scratch 'unc-dryrun.json'; $errorLog = Join-Path $scratch 'unc-dryrun-error.log'
    $arguments = '-NoProfile -ExecutionPolicy Bypass -STA -File "' + $app + '" -Firmware "' + $app + '" -SourceIP ' + $SourceIP + ' -DryRun'
    $child = Start-Process powershell.exe -ArgumentList $arguments -PassThru -WindowStyle Hidden -RedirectStandardOutput $output -RedirectStandardError $errorLog
    $null = $child.Handle
    if (-not $child.WaitForExit(30000)) { $child.Kill(); $child.WaitForExit(); throw 'UNC checksum dry-run timed out' }
    if ($child.ExitCode -ne 0) { throw ('UNC checksum dry-run failed: ' + [IO.File]::ReadAllText($errorLog)) }
    $uncPlan = [IO.File]::ReadAllText($output) | ConvertFrom-Json
    if ($uncPlan.expected_sha256 -ne (Get-FileHash -LiteralPath $app -Algorithm SHA256).Hash.ToLowerInvariant()) { throw 'UNC dry-run did not print the actual selected image SHA256' }
    $child.Dispose(); $child = $null; $checks++
    Write-Output ('PASS: ' + $checks + ' native checksum checks; no recovery session or recovery datagram created')
    $passed = $true
} catch {
    Write-Error -ErrorAction Continue ('Checksum acceptance failed: ' + $_.Exception.Message + '; evidence: ' + $scratch)
    exit 1
} finally {
    if ($hasher) { $hasher.Cancel(); $hasher.Dispose() }
    if ($child) { if (-not $child.HasExited) { $child.Kill(); $child.WaitForExit() }; $child.Dispose() }
    if ($passed -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
# <FILE>contrib/ac86u/tests/test_windows_recovery_hash.ps1</FILE> - <DESC>Native checksum preview, identity and GUI gating acceptance without recovery traffic.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
