# <FILE>contrib/ac86u/tests/test_windows_recovery_reporting.ps1</FILE> - <DESC>Preserve authoritative recovery outcomes when status logging fails.</DESC>
# <VERS>VERSION: 0.1.1</VERS>
# <WCTX>Keep terminal ASUS session results separate from local reporting failures.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
$ErrorActionPreference = 'Stop'
$app = Join-Path (Split-Path $PSScriptRoot -Parent) 'tools/windows-recovery/ASUS-Recovery.ps1'
$scratch = Join-Path $env:TEMP ('ASUS reporting fixture ' + [guid]::NewGuid().ToString('N'))
$passed = $false
function Invoke-ReportingScenario([string]$Label, [string]$TerminalStage, [int]$VendorStatus, [int]$Code, [string]$ErrorKind) {
    $directory = Join-Path $scratch $Label
    [void][IO.Directory]::CreateDirectory((Join-Path $directory 'events.log'))
    $snapshot = [pscustomobject]@{ Terminal = $true; Stage = $TerminalStage; VendorStatus = $VendorStatus;
        Percent = 100; AcknowledgedBytes = 513; FileBytes = 513; LocalEndpoint = '127.0.0.1:12345';
        PeerEndpoint = '127.0.0.1:69'; ErrorKind = $ErrorKind; Message = 'Authoritative terminal session result' }
    $session = [pscustomobject]@{ Snapshot = $snapshot; IsStopped = $true }
    $session | Add-Member -MemberType ScriptMethod -Name GetSnapshot -Value { $this.Snapshot }
    $script:job = @{ session = $session; directory = $directory; started = [DateTime]::UtcNow.ToString('o');
        plan = [pscustomobject]@{ source_ip = '127.0.0.1'; router_ip = '127.0.0.1'; firmware = 'synthetic.bin' }; stage = 'ready' }
    $caught = 0
    try { Write-RecoveryStatus $TerminalStage $Code } catch { $caught++ }
    $fallback = 'recovery_success'; $fallbackCode = 0
    if ($TerminalStage -eq 'recovery_success') { $fallback = 'failed'; $fallbackCode = 1 }
    try { Write-RecoveryStatus $fallback $fallbackCode } catch { $caught++ }
    if ($caught -ne 2) { throw 'The fixture did not force both append failures after JSON publication' }
    [IO.File]::ReadAllText((Join-Path $directory 'status.json')) | ConvertFrom-Json
}
try {
    $tokens = $null; $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($app, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $definition = @($ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Write-RecoveryStatus' }, $false))
    if ($definition.Count -ne 1) { throw 'Cannot identify the authoritative reporting function' }
    $terminalGuard = @($definition[0].FindAll({ param($node) $node -is [System.Management.Automation.Language.IfStatementAst] -and $node.Extent.Text.StartsWith('if ($snapshot.Terminal)') }, $true))
    if ($terminalGuard.Count -ne 1) { throw 'Cannot identify the terminal-snapshot override for the negative control' }
    [void][IO.Directory]::CreateDirectory($scratch)
    $legacyDefinition = $definition[0].Extent.Text.Replace($terminalGuard[0].Extent.Text, '')
    . ([scriptblock]::Create($legacyDefinition))
    $legacy = Invoke-ReportingScenario 'legacy-negative-control' 'recovery_success' 1 0 ''
    if ($legacy.stage -ne 'failed' -or $legacy.returncode -ne 1 -or $legacy.vendor_status -ne 1) { throw 'Negative control failed to reproduce the former success-to-failure overwrite' }
    Write-Output 'PASS: negative control reproduces incorrect failure after vendor success when the terminal guard is absent'
    . ([scriptblock]::Create($definition[0].Extent.Text))
    foreach ($case in @(
        @{ label = 'success'; stage = 'recovery_success'; vendor = 1; code = 0; error = '' },
        @{ label = 'failure'; stage = 'failed'; vendor = 2; code = 1; error = 'flash_rejected' },
        @{ label = 'cancelled'; stage = 'cancelled'; vendor = 0; code = 130; error = 'cancelled' }
    )) {
        $state = Invoke-ReportingScenario $case.label $case.stage $case.vendor $case.code $case.error
        if ($state.stage -ne $case.stage -or $state.returncode -ne $case.code -or $state.vendor_status -ne $case.vendor -or $state.error_kind -ne $case.error -or -not $state.reporting_error -or -not $state.worker_stopped) {
            throw ('Reporting changed the terminal outcome or lost the separate diagnostic: ' + $case.label)
        }
        Write-Output ('PASS: terminal ' + $case.stage + ' remains authoritative through both forced reporting failures')
    }
    Write-Output 'PASS: 4 native reporting checks; fake snapshots only, no socket or worker created'
    $passed = $true
} catch {
    Write-Error -ErrorAction Continue ('Reporting regression failed: ' + $_.Exception.Message + '; evidence: ' + $scratch)
    exit 1
} finally {
    $script:job = $null
    if ($passed -and (Test-Path -LiteralPath $scratch)) { Remove-Item -LiteralPath $scratch -Recurse -Force }
}
# <FILE>contrib/ac86u/tests/test_windows_recovery_reporting.ps1</FILE> - <DESC>Preserve authoritative recovery outcomes when status logging fails.</DESC>
# <VERS>END OF VERSION: 0.1.1</VERS>
