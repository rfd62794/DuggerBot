# DuggerBot — Tower NSSM Service Deployment
# Run on Tower only. Requires NSSM installed and in PATH.
#
# This script:
#   1. Creates/updates the DuggerBot NSSM service
#   2. Points it at the uv-managed Python environment
#   3. Configures auto-restart on failure
#
# Usage: .\nssm_deploy.ps1

$ErrorActionPreference = "Stop"

$ServiceName = "DuggerBot"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$AppScript = Join-Path $ProjectRoot "duggerbot\main.py"

Write-Host "DuggerBot NSSM Deployment" -ForegroundColor Cyan
Write-Host "  Service: $ServiceName"
Write-Host "  Project: $ProjectRoot"
Write-Host "  Python:  $PythonPath"

# Check prerequisites
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) {
    Write-Error "NSSM not found in PATH. Install NSSM first."
    exit 1
}

if (-not (Test-Path $PythonPath)) {
    Write-Error "Python not found at $PythonPath. Run 'uv sync' first."
    exit 1
}

# Install or update service
$existing = nssm status $ServiceName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Updating existing service..." -ForegroundColor Yellow
    nssm stop $ServiceName
    nssm set $ServiceName Application $PythonPath
    nssm set $ServiceName AppParameters $AppScript
} else {
    Write-Host "  Installing new service..." -ForegroundColor Green
    nssm install $ServiceName $PythonPath $AppScript
}

# Configure
nssm set $ServiceName AppDirectory $ProjectRoot
nssm set $ServiceName AppStdout (Join-Path $ProjectRoot "logs\service.log")
nssm set $ServiceName AppStderr (Join-Path $ProjectRoot "logs\error.log")
nssm set $ServiceName AppRestartDelay 5000

Write-Host "`nService configured. Start with: nssm start $ServiceName" -ForegroundColor Green
