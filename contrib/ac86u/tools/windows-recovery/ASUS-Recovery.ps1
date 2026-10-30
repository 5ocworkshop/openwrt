# <FILE>contrib/ac86u/tools/windows-recovery/ASUS-Recovery.ps1</FILE> - <DESC>Windows ASUS recovery uploader with explicit source IPv4 binding.</DESC>
# <VERS>VERSION: 0.3.1</VERS>
# <WCTX>Run the ASUS recovery exchange through one source-bound managed UDP session without changing networking.</WCTX>
# <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
[CmdletBinding()]
param(
    [string]$Firmware = '',
    [string]$SourceIP = '192.168.1.10',
    [string]$RouterIP = '192.168.1.1',
    [ValidateRange(1,65535)][int]$Port = 69,
    [switch]$DryRun,
    [switch]$Headless,
    [switch]$Upload,
    [switch]$Help,
    [ValidateRange(1,3600)][int]$TransferTimeoutSeconds = 600,
    [ValidateRange(0,86400)][int]$FlashTimeoutSeconds = 0,
    [ValidateRange(0,259200)][int]$MaxFlashWaitSeconds = 0,
    [ValidateRange(0,10000)][int]$DiscoverySettleMilliseconds = 2000,
    [switch]$UnicastDiscovery
)
$ErrorActionPreference = 'Stop'
$script:job = $null
$script:form = $null
$script:hashJob = $null
$script:hashResult = $null
$script:hashDue = [DateTime]::MaxValue
$script:hashClosing = $false

function Get-RecoveryPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Choose a firmware file.' }
    $Path = $Path.Trim()
    if ($Path.Length -ge 2) {
        $first = [int][char]$Path[0]; $last = [int][char]$Path[$Path.Length - 1]
        if (($first -eq 34 -and $last -eq 34) -or ($first -eq 39 -and $last -eq 39)) {
            $Path = $Path.Substring(1, $Path.Length - 2).Trim()
        }
    }
    if ([string]::IsNullOrWhiteSpace($Path)) { throw 'Choose a firmware file.' }
    if ($Path -match '[\x00-\x1f\x7f]') { throw 'Firmware path contains a line break or control character. Paste only one file path.' }
    if ($Path.IndexOfAny([IO.Path]::GetInvalidPathChars()) -ge 0) { throw 'Firmware path contains invalid characters. Paste one file path without embedded quotation marks.' }
    $Path
}
function Get-RecoveryPlan([string]$Path, [string]$LocalIP, [string]$RemoteIP, [string]$ExpectedSha256 = '') {
    $Path = Get-RecoveryPath $Path
    if ($ExpectedSha256 -and $ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Expected SHA256 must contain exactly 64 hexadecimal characters.' }
    foreach ($value in @($LocalIP, $RemoteIP)) {
        $address = $null
        if (-not [Net.IPAddress]::TryParse($value, [ref]$address) -or
            $address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
            throw "Expected an IPv4 address: $value"
        }
    }
    $adapter = @(Get-NetIPAddress -AddressFamily IPv4 -IPAddress $LocalIP -ErrorAction SilentlyContinue)
    if ($adapter.Count -ne 1) { throw "Source IP $LocalIP must belong to exactly one local adapter. Configure the adapter first." }
    $item = Get-Item -LiteralPath $Path -ErrorAction Stop
    if ($item.PSIsContainer -or $item.Length -eq 0) { throw 'Choose a nonempty firmware file.' }
    if ($item.FullName.Contains('"')) { throw 'The firmware path cannot contain a quote.' }
    [pscustomobject]@{ firmware = $item.FullName; bytes = $item.Length; last_write_utc = $item.LastWriteTimeUtc.ToString('o'); expected_sha256 = $ExpectedSha256.ToLowerInvariant();
        source_ip = $LocalIP; router_ip = $RemoteIP; adapter = $adapter[0].InterfaceAlias; port = $Port;
        protocol = 'asus-recovery'; discovery = $(if ($UnicastDiscovery) { $RemoteIP } else { '255.255.255.255' });
        flash_timeout_seconds = $(if ($FlashTimeoutSeconds) { $FlashTimeoutSeconds } else { 450 + 24 * [Math]::Floor($item.Length / 1048576) }) }
}
function Initialize-RecoveryImageHash {
    if (-not ('AsusRecovery.RecoveryImageHash' -as [type])) { Add-Type -Path (Join-Path $PSScriptRoot 'cls_RecoveryImageHash.cs') }
}
function Get-RecoveryImageHash([string]$Path) {
    Initialize-RecoveryImageHash
    $worker = New-Object AsusRecovery.RecoveryImageHash((Get-RecoveryPath $Path))
    try {
        while (-not $worker.IsStopped) { Start-Sleep -Milliseconds 50 }
        $snapshot = $worker.GetSnapshot()
        if ($snapshot.Error -or -not $snapshot.Hash) { throw ('Could not calculate image SHA256: ' + $snapshot.Error) }
        $snapshot
    } finally { $worker.Cancel(); $worker.Dispose() }
}
function Test-RecoveryImageIdentity([object]$Hash, [object]$Plan) {
    $Hash -and $Hash.Terminal -and -not $Hash.Error -and $Hash.Hash -and
        [string]::Equals($Hash.Path, $Plan.firmware, [StringComparison]::OrdinalIgnoreCase) -and
        $Hash.Length -eq $Plan.bytes -and $Hash.LastWriteUtc.ToString('o') -eq $Plan.last_write_utc -and
        [string]::Equals($Hash.Hash, $Plan.expected_sha256, [StringComparison]::OrdinalIgnoreCase)
}
function Reset-RecoveryImageHash {
    $script:hashResult = $null; $hashBox.Clear(); $sizeLabel.Text = ''; $send.Enabled = $false
    if ($script:hashJob) { $script:hashJob.Cancel() }
    $script:hashDue = [DateTime]::UtcNow.AddMilliseconds(350)
    $hashTimer.Start()
}

function Write-RecoveryStatus([string]$Stage, [object]$Code = $null) {
    $snapshot = $script:job.session.GetSnapshot()
    $reportingError = $null
    if ($snapshot.Terminal) {
        if ($Stage -ne $snapshot.Stage) { $reportingError = "Reporting requested $Stage after terminal $($snapshot.Stage)." }
        $Stage = $snapshot.Stage
        if ($Stage -eq 'recovery_success') { $Code = 0 }
        elseif ($Stage -eq 'cancelled') { $Code = 130 }
        else { $Code = 1 }
    }
    $state = [ordered]@{ stage = $Stage; pid = $PID; child_pid = $null;
        updated_utc = [DateTime]::UtcNow.ToString('o'); started_utc = $script:job.started;
        progress_percent = $snapshot.Percent; acknowledged_bytes = $snapshot.AcknowledgedBytes;
        firmware_bytes = $snapshot.FileBytes; local_endpoint = $snapshot.LocalEndpoint;
        peer_endpoint = $snapshot.PeerEndpoint; vendor_status = $snapshot.VendorStatus;
        error_kind = $snapshot.ErrorKind; message = $snapshot.Message; returncode = $Code; reporting_error = $reportingError;
        worker_stopped = $script:job.session.IsStopped;
        source_ip = $script:job.plan.source_ip; router_ip = $script:job.plan.router_ip;
        firmware = $script:job.plan.firmware; expected_sha256 = $script:job.plan.expected_sha256; log_directory = $script:job.directory }
    $target = Join-Path $script:job.directory 'status.json'
    $temporary = "$target.tmp"
    [IO.File]::WriteAllText($temporary, ($state | ConvertTo-Json), (New-Object Text.UTF8Encoding($false)))
    if ([IO.File]::Exists($target)) { [IO.File]::Replace($temporary, $target, [NullString]::Value) }
    else { [IO.File]::Move($temporary, $target) }
    Add-Content -LiteralPath (Join-Path $script:job.directory 'events.log') -Value "$($state.updated_utc) $Stage upload=$($state.progress_percent)% vendor=$($state.vendor_status) $($state.message)"
    $script:job.stage = $Stage
    $script:job.lastHeartbeat = [DateTime]::UtcNow
}
function Start-RecoveryUpload([object]$Plan) {
    if ($script:job) {
        if (-not $script:job.session.IsStopped) { throw 'The previous session is still active. Stop it before retrying.' }
        if ($script:job.session.GetSnapshot().Stage -eq 'recovery_success') { throw 'Recovery already succeeded. Reopen the application to deliberately start another upload.' }
        $script:job.session.Dispose()
    }
    if (-not ('AsusRecovery.RecoverySession' -as [type])) {
        $sources = @('RecoveryContracts.cs','cls_AsusRecoveryPackets.cs','cls_AsusRecoveryChannel.cs','cls_AsusRecoverySession.cs') | ForEach-Object { Join-Path $PSScriptRoot $_ }
        foreach ($source in $sources) { if (-not (Test-Path -LiteralPath $source)) { throw "Missing engine file: $source. Keep the launcher files together." } }
        Add-Type -Path $sources
    }
    $options = New-Object AsusRecovery.RecoveryOptions
    $options.FirmwarePath = $Plan.firmware; $options.SourceIP = $Plan.source_ip
    $options.ExpectedSha256 = $Plan.expected_sha256
    $options.RouterIP = $Plan.router_ip; $options.Port = $Plan.port
    $options.BroadcastDiscovery = -not $UnicastDiscovery
    $options.DiscoverySettleMilliseconds = $DiscoverySettleMilliseconds
    $options.TransferTimeoutMilliseconds = $TransferTimeoutSeconds * 1000
    $options.FlashIdleTimeoutMilliseconds = $FlashTimeoutSeconds * 1000
    $options.MaxFlashWaitMilliseconds = $MaxFlashWaitSeconds * 1000
    $session = New-Object AsusRecovery.RecoverySession($options)
    $directory = Join-Path (Join-Path $env:LOCALAPPDATA 'ASUSRecovery') ((Get-Date -Format 'yyyyMMddTHHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $directory
    $script:job = @{ session = $session; directory = $directory; plan = $Plan; stage = 'ready';
        started = [DateTime]::UtcNow.ToString('o'); lastHeartbeat = [DateTime]::MinValue }
    try {
        $Plan | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $directory 'plan.json')
        Write-RecoveryStatus 'ready'
        $session.Start()
        Update-RecoveryUpload
    } catch {
        $failure = $_.Exception.Message
        try { $session.Cancel(); $session.Dispose() } catch { $failure += '; cleanup: ' + $_.Exception.Message }
        try { Write-RecoveryStatus 'failed' 1 } catch { [Console]::Error.WriteLine('Could not save failure status: ' + $_.Exception.Message) }
        throw $failure
    }
}
function Update-RecoveryUpload {
    if (-not $script:job) { return }
    $snapshot = $script:job.session.GetSnapshot()
    if ($snapshot.Stage -ne $script:job.stage -or ([DateTime]::UtcNow - $script:job.lastHeartbeat).TotalSeconds -ge 5) {
        $code = $null
        if ($snapshot.Stage -eq 'recovery_success') { $code = 0 }
        elseif ($snapshot.Stage -eq 'failed') { $code = 1 }
        elseif ($snapshot.Stage -eq 'cancelled') { $code = 130 }
        Write-RecoveryStatus $snapshot.Stage $code
    }
}
function Stop-RecoveryUpload([switch]$NoStatus) {
    if (-not $script:job) { return }
    $script:job.session.Cancel()
    if (-not $NoStatus) {
        $snapshot = $script:job.session.GetSnapshot()
        $code = $null
        if ($snapshot.Stage -eq 'recovery_success') { $code = 0 }
        elseif ($snapshot.Stage -eq 'failed') { $code = 1 }
        elseif ($snapshot.Stage -eq 'cancelled') { $code = 130 }
        Write-RecoveryStatus $snapshot.Stage $code
    }
}
try {
    if ($Help) {
        Write-Output 'ASUS-Recovery.ps1 [-Firmware FILE] [-SourceIP 192.168.1.10] [-RouterIP 192.168.1.1] [-Port 69]'
        Write-Output 'Default: recovery window. Upload performs ASUS discovery, TFTP PUT and waits for router flash status.'
        Write-Output '-DryRun -Firmware FILE validates and prints the plan without binding a socket or creating logs.'
        Write-Output '-Headless -Upload -Firmware FILE explicitly starts recovery; exit0 requires router-reported recovery success.'
        Write-Output 'Advanced: -FlashTimeoutSeconds 0 (ASUS size-derived default), -MaxFlashWaitSeconds 0 (3x idle), -TransferTimeoutSeconds 600.'
        Write-Output 'Local simulator only: -UnicastDiscovery -DiscoverySettleMilliseconds 0. Production defaults to broadcast discovery.'
        exit 0
    }
    if ($Headless -or $DryRun) {
        if (-not $DryRun -and -not $Upload) { throw '-Headless requires explicit -Upload authorization.' }
        $initialPlan = Get-RecoveryPlan $Firmware $SourceIP $RouterIP
        $imageHash = Get-RecoveryImageHash $initialPlan.firmware
        $plan = Get-RecoveryPlan $Firmware $SourceIP $RouterIP $imageHash.Hash
        if (-not (Test-RecoveryImageIdentity $imageHash $plan)) { throw 'Image metadata changed during checksum calculation. Run again and review the new SHA256.' }
        if ($DryRun) { $plan | ConvertTo-Json -Depth 4; exit 0 }
        Write-Output "SHA256: $($plan.expected_sha256)"
        Start-RecoveryUpload $plan
        Write-Output "Recovering from $SourceIP. Logs: $($script:job.directory)"
        while (-not $script:job.session.GetSnapshot().Terminal -or -not $script:job.session.IsStopped) {
            Update-RecoveryUpload; Start-Sleep -Milliseconds 250
        }
        Update-RecoveryUpload
        $snapshot = $script:job.session.GetSnapshot()
        Write-Output "$($snapshot.Stage): $($snapshot.Message)"
        if ($snapshot.Stage -eq 'recovery_success') { exit 0 }
        if ($snapshot.Stage -eq 'cancelled') { exit 130 }
        exit 1
    }
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Initialize-RecoveryImageHash
    [Windows.Forms.Application]::EnableVisualStyles()
    $script:form = New-Object Windows.Forms.Form
    $form.Text = 'ASUS firmware recovery'; $form.ClientSize = New-Object Drawing.Size(650, 410)
    $form.StartPosition = 'CenterScreen'; $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false
    $notice = New-Object Windows.Forms.Label
    $notice.Text = 'Enter rescue mode first (hold Reset during power-on until power flashes slowly).'; $notice.SetBounds(15, 15, 620, 35)
    $fileBox = New-Object Windows.Forms.TextBox; $fileBox.Text = $Firmware; $fileBox.SetBounds(15, 55, 510, 25)
    $browse = New-Object Windows.Forms.Button; $browse.Text = 'Choose file...'; $browse.SetBounds(535, 53, 100, 27)
    $hashLabel = New-Object Windows.Forms.Label; $hashLabel.Text = 'Selected image SHA256 (select to copy)'; $hashLabel.SetBounds(15, 90, 620, 20)
    $hashBox = New-Object Windows.Forms.TextBox; $hashBox.ReadOnly = $true; $hashBox.SetBounds(15, 112, 620, 25)
    $hashBox.Font = New-Object Drawing.Font('Consolas', 9)
    $sizeLabel = New-Object Windows.Forms.Label; $sizeLabel.SetBounds(15, 145, 620, 25)
    $sourceLabel = New-Object Windows.Forms.Label; $sourceLabel.Text = 'Source IP'; $sourceLabel.SetBounds(15, 185, 85, 20)
    $sourceBox = New-Object Windows.Forms.TextBox; $sourceBox.Text = $SourceIP; $sourceBox.SetBounds(100, 182, 180, 25)
    $routerLabel = New-Object Windows.Forms.Label; $routerLabel.Text = 'Router IP'; $routerLabel.SetBounds(320, 185, 85, 20)
    $routerBox = New-Object Windows.Forms.TextBox; $routerBox.Text = $RouterIP; $routerBox.SetBounds(405, 182, 180, 25)
    $send = New-Object Windows.Forms.Button; $send.Text = 'Upload'; $send.Enabled = $false; $send.SetBounds(15, 225, 110, 30)
    $cancel = New-Object Windows.Forms.Button; $cancel.Text = 'Cancel upload'; $cancel.Enabled = $false; $cancel.SetBounds(135, 225, 130, 30)
    $progress = New-Object Windows.Forms.ProgressBar; $progress.SetBounds(15, 270, 620, 20)
    $status = New-Object Windows.Forms.Label; $status.Text = 'Choose an image to calculate its SHA256 before uploading.'; $status.SetBounds(15, 300, 620, 90)
    $form.Controls.AddRange(@($notice,$fileBox,$browse,$hashLabel,$hashBox,$sizeLabel,$sourceLabel,$sourceBox,$routerLabel,$routerBox,$send,$cancel,$progress,$status))
    $timer = New-Object Windows.Forms.Timer; $timer.Interval = 250
    $hashTimer = New-Object Windows.Forms.Timer; $hashTimer.Interval = 100
    $fileBox.Add_TextChanged({ Reset-RecoveryImageHash })
    $hashTimer.Add_Tick({
        try {
            if ($script:hashJob) {
                $hashState = $script:hashJob.GetSnapshot()
                if (-not $script:hashJob.IsStopped) {
                    if ($script:hashClosing) { $status.Text = 'Waiting for the file read to stop before closing...' }
                    elseif ($script:hashDue -ne [DateTime]::MaxValue) { $status.Text = 'Stopping the previous file read before calculating the new checksum...' }
                    else { $status.Text = "Calculating SHA256: $($hashState.BytesRead) / $($hashState.Length) bytes" }
                    return
                }
                $script:hashJob.Dispose(); $script:hashJob = $null
                if ($script:hashClosing) { $hashTimer.Stop(); $form.Close(); return }
                if ($script:hashDue -eq [DateTime]::MaxValue) {
                    if ($hashState.Error -or -not $hashState.Hash) { $status.Text = 'Checksum unavailable: ' + $hashState.Error }
                    else {
                        $script:hashResult = $hashState; $hashBox.Text = $hashState.Hash
                        $sizeLabel.Text = 'Image size: {0:N0} bytes ({1:N2} MiB)' -f $hashState.Length, ($hashState.Length / 1048576)
                        $send.Enabled = -not $script:job -or ($script:job.session.IsStopped -and $script:job.session.GetSnapshot().Stage -ne 'recovery_success')
                        $status.Text = 'SHA256 ready. Review the selected file and checksum, then click Upload.'
                    }
                }
            }
            if ($script:hashDue -ne [DateTime]::MaxValue -and [DateTime]::UtcNow -ge $script:hashDue) {
                $script:hashDue = [DateTime]::MaxValue
                $path = Get-RecoveryPath $fileBox.Text
                $script:hashJob = New-Object AsusRecovery.RecoveryImageHash($path)
                $status.Text = 'Calculating SHA256...'
            } elseif (-not $script:hashJob -and $script:hashDue -eq [DateTime]::MaxValue) { $hashTimer.Stop() }
        } catch {
            $hashTimer.Stop(); $send.Enabled = $false
            if ($script:hashJob) { $script:hashJob.Cancel() }
            $status.Text = 'Checksum unavailable: ' + $_.Exception.Message
        }
    })
    $browse.Add_Click({
        $dialog = New-Object Windows.Forms.OpenFileDialog
        $dialog.Title = 'Select the firmware image for this router'; $dialog.Filter = 'Firmware images|*.bin;*.w;*.trx|All files|*.*'
        try { if ($dialog.ShowDialog() -eq 'OK') { $fileBox.Text = $dialog.FileName } } finally { $dialog.Dispose() }
    })
    $send.Add_Click({
        try {
            if (-not $script:hashResult) { throw 'Wait for the selected image SHA256 before uploading.' }
            $plan = Get-RecoveryPlan $fileBox.Text $sourceBox.Text $routerBox.Text $script:hashResult.Hash
            if (-not (Test-RecoveryImageIdentity $script:hashResult $plan)) {
                Reset-RecoveryImageHash
                $status.Text = 'The image changed. Calculating a new checksum; review it before clicking Upload again.'
                return
            }
            $status.Text = 'Preparing recovery session...'; $form.Refresh()
            Start-RecoveryUpload $plan
            foreach ($control in @($send,$browse,$fileBox,$sourceBox,$routerBox)) { $control.Enabled = $false }
            $cancel.Enabled = $true; $progress.Value = 0; $timer.Start()
        } catch {
            $message = $_.Exception.Message
            try { Stop-RecoveryUpload -NoStatus } catch { $message += '; cleanup: ' + $_.Exception.Message }
            $status.Text = 'Could not start recovery: ' + $message
            [Windows.Forms.MessageBox]::Show($message, 'Recovery error', 'OK', 'Error') | Out-Null
        }
    })
    $cancel.Add_Click({
        try {
            Stop-RecoveryUpload
            $status.Text = 'Stopping this session. Firmware already delivered may still be writing on the router.'
            $cancel.Enabled = $false
        } catch { $status.Text = 'Cancellation error: ' + $_.Exception.Message }
    })
    $timer.Add_Tick({
        try {
            Update-RecoveryUpload
            $snapshot = $script:job.session.GetSnapshot()
            $status.Text = "$($snapshot.Message)  Logs: $($script:job.directory)"
            if ($snapshot.Stage -eq 'waiting_for_flash') {
                $progress.Style = 'Marquee'; $cancel.Text = 'Stop monitoring'
            } else {
                $progress.Style = 'Continuous'; $progress.Value = [Math]::Min(100, [Math]::Max(0, [int]$snapshot.Percent))
            }
            if ($snapshot.Terminal -and $script:job.session.IsStopped) {
                $timer.Stop(); $cancel.Enabled = $false
                if ($snapshot.Stage -eq 'recovery_success') {
                    $progress.Value = 100
                    $status.Text = "Router reports recovery succeeded. Wait for reboot; OS startup is not yet confirmed. Logs: $($script:job.directory)"
                } else {
                    foreach ($control in @($browse,$fileBox,$sourceBox,$routerBox)) { $control.Enabled = $true }
                    if ($snapshot.ErrorKind -eq 'image_changed') {
                        Reset-RecoveryImageHash
                        $status.Text = 'The image changed before transfer. Calculating a new checksum; review it before retrying.'
                    } else { $send.Enabled = $null -ne $script:hashResult }
                    $send.Text = 'Retry upload'; $cancel.Text = 'Cancel upload'
                }
            }
        } catch {
            $timer.Stop(); $failure = $_.Exception.Message
            try { Stop-RecoveryUpload -NoStatus; $script:job.session.Dispose() } catch { $failure += '; cleanup: ' + $_.Exception.Message }
            try { Write-RecoveryStatus 'failed' 1 } catch { $failure += '; status: ' + $_.Exception.Message }
            $status.Text = 'Recovery monitoring failed: ' + $failure
            $cancel.Enabled = $false
            $send.Enabled = $script:job.session.IsStopped -and $null -ne $script:hashResult
        }
    })
    $form.Add_FormClosing({
        param($sender, $eventArgs)
        if ($script:hashJob) {
            $script:hashJob.Cancel()
            if (-not $script:hashJob.IsStopped) {
                $script:hashClosing = $true; $eventArgs.Cancel = $true; $status.Text = 'Waiting for the file read to stop before closing...'
                $hashTimer.Start(); return
            }
            $script:hashJob.Dispose(); $script:hashJob = $null
        }
        if ($script:job -and -not $script:job.session.IsStopped) {
            $question = 'Stop this session and close? Any firmware already delivered may still be writing on the router.'
            if ([Windows.Forms.MessageBox]::Show($question, 'Recovery active', 'YesNo', 'Warning') -ne 'Yes') { $eventArgs.Cancel = $true; return }
            try { Stop-RecoveryUpload -NoStatus } catch { $eventArgs.Cancel = $true; $status.Text = 'Could not stop session: ' + $_.Exception.Message }
        }
    })
    if (-not [string]::IsNullOrWhiteSpace($fileBox.Text)) { Reset-RecoveryImageHash }
    [Windows.Forms.Application]::Run($form)
} catch {
    $failureMessage = $_.Exception.Message
    if ($script:job) {
        try { Stop-RecoveryUpload -NoStatus; $script:job.session.Dispose() } catch { $failureMessage += '; cleanup: ' + $_.Exception.Message }
        try { Write-RecoveryStatus 'failed' 1 } catch { [Console]::Error.WriteLine('Could not record terminal status: ' + $_.Exception.Message) }
    }
    [Console]::Error.WriteLine('ASUS recovery failed: ' + $failureMessage)
    if ($script:form) { [Windows.Forms.MessageBox]::Show($failureMessage, 'ASUS recovery error', 'OK', 'Error') | Out-Null }
    exit 1
} finally {
    if ($script:job) {
        try {
            Stop-RecoveryUpload -NoStatus
            $script:job.session.Dispose()
            Update-RecoveryUpload
        } catch { [Console]::Error.WriteLine('Recovery cleanup/status: ' + $_.Exception.Message) }
    }
    if ($script:timer) { $timer.Dispose() }
    if ($script:hashTimer) { $hashTimer.Dispose() }
    if ($script:hashJob) {
        try { $script:hashJob.Cancel(); $script:hashJob.Dispose() }
        catch { [Console]::Error.WriteLine('Image hash cleanup: ' + $_.Exception.Message) }
    }
    if ($script:form) { $form.Dispose() }
}
# <FILE>contrib/ac86u/tools/windows-recovery/ASUS-Recovery.ps1</FILE> - <DESC>Windows ASUS recovery uploader with explicit source IPv4 binding.</DESC>
# <VERS>END OF VERSION: 0.3.1</VERS>
