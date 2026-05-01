<#
.SYNOPSIS  Uninstall the matt-box-control Windows service.
#>

param([string]$ServiceName = "matt-box-control")

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal $identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run as Administrator."
}

$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssm) {
    & nssm stop $ServiceName 2>$null
    & nssm remove $ServiceName confirm
} else {
    & sc.exe stop $ServiceName 2>$null
    & sc.exe delete $ServiceName
}
Write-Host "Service $ServiceName removed." -ForegroundColor Green
Write-Host "Note: %APPDATA%\matt-box\ (config + logs) preserved. Delete manually if desired."
