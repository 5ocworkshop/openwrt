@echo off
rem <FILE>contrib/ac86u/tools/windows-recovery/ASUS-Recovery.cmd</FILE> - <DESC>Launch the local ASUS recovery PowerShell window on Windows.</DESC>
rem <VERS>VERSION: 0.1.1</VERS>
rem <WCTX>Run the recovery uploader without installing dependencies or changing global execution policy.</WCTX>
rem <CLOG>Relocate the existing Windows recovery utility and focused local-only tests into public AC86U tooling.</CLOG>
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File "%~dp0ASUS-Recovery.ps1" %*
if errorlevel 1 pause
rem <FILE>contrib/ac86u/tools/windows-recovery/ASUS-Recovery.cmd</FILE> - <DESC>Launch the local ASUS recovery PowerShell window on Windows.</DESC>
rem <VERS>END OF VERSION: 0.1.1</VERS>
