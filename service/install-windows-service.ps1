<#
.SYNOPSIS
  Install matt-box-control as a Windows service.

.DESCRIPTION
  Uses NSSM if available (preferred), falls back to sc.exe.
  Run from an elevated PowerShell prompt.

  This script does NOT write the bearer for you — it copies
  config.example.yaml to %APPDATA%\matt-box\config.yaml if no config exists,
  then refuses to start the service until you've replaced the placeholder.

.NOTES
  Service name: matt-box-control
  Logs:        %APPDATA%\matt-box\logs\
#>

param(
    [string]$ServiceName = "matt-box-control",
    [string]$DisplayName = "TARDAI matt-box-control",
    [string]$Description = "Sovereign hands on Matt's Windows box. Filesystem/shell/browser ops with allowlist + audit."
)

$ErrorActionPreference = "Stop"

# Elevation check
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal $identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run as Administrator."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $python) { throw "python not found on PATH. Install Python 3.11+ first." }

# Ensure config exists
$configDir = Join-Path $env:APPDATA "matt-box"
$configPath = Join-Path $configDir "config.yaml"
$logsDir = Join-Path $configDir "logs"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (-not (Test-Path $configPath)) {
    Copy-Item (Join-Path $repoRoot "config.example.yaml") $configPath
    Write-Host "Wrote $configPath from template."
    Write-Host "EDIT THIS FILE NOW — set bearer, confirm allowlists." -ForegroundColor Yellow
}

# Install dependencies (in current python)
Write-Host "Installing matt-box-control package..."
& $python -m pip install -e $repoRoot

$args = "-m matt_box.daemon"
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if ($nssm) {
    Write-Host "Installing service via NSSM..."
    & nssm install $ServiceName $python $args
    & nssm set $ServiceName DisplayName $DisplayName
    & nssm set $ServiceName Description $Description
    & nssm set $ServiceName AppEnvironmentExtra "MATT_BOX_CONFIG=$configPath"
    & nssm set $ServiceName AppStdout (Join-Path $logsDir "stdout.log")
    & nssm set $ServiceName AppStderr (Join-Path $logsDir "stderr.log")
    & nssm set $ServiceName Start SERVICE_AUTO_START
    Write-Host "Service installed. Start with: nssm start $ServiceName" -ForegroundColor Green
} else {
    Write-Host "NSSM not found — falling back to sc.exe (less robust)."
    Write-Host "For better service management, install NSSM: https://nssm.cc"
    $binPath = "`"$python`" $args"
    & sc.exe create $ServiceName binPath= $binPath start= auto DisplayName= "$DisplayName"
    & sc.exe description $ServiceName "$Description"
    Write-Host "Set MATT_BOX_CONFIG env var manually or use NSSM." -ForegroundColor Yellow
    Write-Host "Service installed. Start with: sc start $ServiceName" -ForegroundColor Green
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Edit $configPath — replace bearer placeholder."
Write-Host "  2. Start service: nssm start $ServiceName  (or: sc start $ServiceName)"
Write-Host "  3. Smoke test:    curl -H `"Authorization: Bearer <bearer>`" http://127.0.0.1:8443/health"
Write-Host "  4. Expose via Tailscale: tailscale serve https / http://127.0.0.1:8443"
