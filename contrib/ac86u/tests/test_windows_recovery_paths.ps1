# <FILE>contrib/ac86u/tests/test_windows_recovery_paths.ps1</FILE> - <DESC>Exercise literal pasted paths through the recovery GUI plan provider.</DESC>
# <VERS>VERSION: 0.2.2</VERS>
# <WCTX>Prevent quoted or newline-padded firmware paths failing before upload.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
param([string]$SourceIP = '127.0.0.1')
$ErrorActionPreference = 'Stop'
$app = Join-Path (Split-Path $PSScriptRoot -Parent) 'tools/windows-recovery/ASUS-Recovery.ps1'
$directory = Join-Path $env:TEMP ('ASUS path fixture ' + [guid]::NewGuid().ToString('N'))
try {
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($app, [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw ($errors | Out-String) }
    $definitions = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in @('Get-RecoveryPath','Get-RecoveryPlan') }, $false)
    foreach ($definition in $definitions) { . ([scriptblock]::Create($definition.Extent.Text)) }
    $Port = 69
    $FlashTimeoutSeconds = 0
    $UnicastDiscovery = $false
    [void][IO.Directory]::CreateDirectory($directory)
    $file = Join-Path $directory ('firmware & caf' + [char]0xE9 + '.bin')
    [IO.File]::WriteAllBytes($file, [byte[]](0, 255, 128, 42))
    $cases = @($file, ('"' + $file + '"'), ("'" + $file + "'"), (" `t" + $file + "`r`n"), (" `t" + '"' + $file + '"' + "`r`n"))
    foreach ($inputPath in $cases) {
        $plan = Get-RecoveryPlan $inputPath $SourceIP '192.168.1.1'
        if ($plan.firmware -ne $file -or $plan.bytes -ne 4) { throw 'Pasted path was not normalized to the exact firmware file' }
        if ($plan.protocol -ne 'asus-recovery' -or $plan.source_ip -ne $SourceIP -or $plan.flash_timeout_seconds -ne 450) { throw 'Pasted path did not produce the managed recovery plan' }
        if ($plan.PSObject.Properties.Name -contains 'arguments' -or $plan.PSObject.Properties.Name -contains 'executable') { throw 'Managed recovery plan retained an external uploader command' }
    }
    foreach ($inputPath in @('', '   ', ('"' + $file), ($file + "`nextra"))) {
        $rejected = $false
        try { $null = Get-RecoveryPlan $inputPath $SourceIP '192.168.1.1' } catch {
            $rejected = $true
            if ($_.Exception.Message -match '^Illegal characters in path') { throw 'Unhelpful filesystem error escaped path validation' }
        }
        if (-not $rejected) { throw 'Invalid pasted path was accepted' }
    }
    Write-Output 'PASS: 9 literal GUI path cases and managed ASUS plan fields; no uploader started'
} catch {
    Write-Error -ErrorAction Continue ('Path acceptance failed: ' + $_.Exception.Message)
    exit 1
} finally {
    if (Test-Path -LiteralPath $directory) { Remove-Item -LiteralPath $directory -Recurse -Force }
}
# <FILE>contrib/ac86u/tests/test_windows_recovery_paths.ps1</FILE> - <DESC>Exercise literal pasted paths through the recovery GUI plan provider.</DESC>
# <VERS>END OF VERSION: 0.2.2</VERS>
