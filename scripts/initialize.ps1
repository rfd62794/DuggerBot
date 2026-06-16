<#
.SYNOPSIS
    DuggerBot Initializer — first-time setup and NSSM service registration.
    Idempotent: safe to run on existing installations.
    Test on Nitro 5 before running on Tower.

.PARAMETER RepoPath
    Path to DuggerBot repo. Default: C:\Github\DuggerBot

.PARAMETER ServiceName
    NSSM service name. Default: DuggerBot

.PARAMETER PythonPath
    Path to uv executable. Default: auto-detected from PATH.
#>
param(
    [string]$RepoPath = "C:\Github\DuggerBot",
    [string]$ServiceName = "DuggerBot",
    [string]$PythonPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step { param([string]$msg) Write-Host "→ $msg" -ForegroundColor Cyan }
function Write-OK   { param([string]$msg) Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Fail { param([string]$msg) Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

# 1. Verify prerequisites
Write-Step "Checking prerequisites"
foreach ($cmd in @("git", "uv", "nssm")) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Fail "$cmd not found in PATH. Install it and re-run."
    }
    Write-OK "$cmd found"
}

# 2. Clone or pull repo
Write-Step "Updating repo at $RepoPath"
if (-not (Test-Path $RepoPath)) {
    git clone https://github.com/rfd62794/DuggerBot.git $RepoPath
    Write-OK "Cloned"
} else {
    Set-Location $RepoPath
    git pull origin main
    Write-OK "Pulled"
}
Set-Location $RepoPath

# 3. Install dependencies
Write-Step "Installing dependencies"
uv sync
Write-OK "Dependencies installed"

# 4. Check .env.local
Write-Step "Checking .env.local"
if (-not (Test-Path "$RepoPath\.env.local")) {
    Write-Host "  .env.local not found. Copy .env.example and fill in values:" -ForegroundColor Yellow
    Write-Host "  $RepoPath\.env.example" -ForegroundColor Yellow
    Write-Fail "Create .env.local and re-run."
}
Write-OK ".env.local present"

# 5. Install pre-commit hook (bakes revision into _version_info.py)
Write-Step "Installing pre-commit hook"
Copy-Item "$RepoPath\scripts\hooks\pre-commit" "$RepoPath\.git\hooks\pre-commit" -Force
Write-OK "Pre-commit hook installed"

# 6. SOUL_PATH reminder
Write-Host ""
Write-Host "  REMINDER: Soul documents must be placed at the path in SOUL_PATH" -ForegroundColor Yellow
Write-Host "  Copy via Tailscale or RDP — they are not in the repo." -ForegroundColor Yellow
Write-Host ""

# 6. Register or update NSSM service
Write-Step "Configuring NSSM service: $ServiceName"
$uvExe = if ($PythonPath) { $PythonPath } else { (Get-Command uv).Source }

$existing = nssm status $ServiceName 2>&1
if ($LASTEXITCODE -ne 0) {
    # Service doesn't exist — create it
    nssm install $ServiceName $uvExe
    Write-OK "Service installed"
} else {
    Write-OK "Service exists — updating config"
    nssm stop $ServiceName 2>$null
}

# Apply prescriptive config per ADR-009
nssm set $ServiceName Application $uvExe
nssm set $ServiceName AppParameters "run python -m duggerbot.main"
nssm set $ServiceName AppDirectory $RepoPath
nssm set $ServiceName AppEnvironmentExtra "PYTHONUNBUFFERED=1"
nssm set $ServiceName AppExit default Restart    # Exit 0 → restart (clean update)
nssm set $ServiceName AppExit 1 Stop             # Exit 1 → stop (error, no loop)
nssm set $ServiceName AppRestartDelay 5000       # 5s delay before restart
nssm set $ServiceName AppThrottle 10000          # Throttle rapid restarts
nssm set $ServiceName AppStopMethodConsole 1500  # Graceful shutdown window
nssm set $ServiceName AppStopMethodWindow 1500
nssm set $ServiceName AppStopMethodThreads 1500
nssm set $ServiceName Start SERVICE_AUTO_START
nssm set $ServiceName ObjectName LocalSystem

Write-OK "NSSM config applied (ADR-009 prescriptive settings)"

# 7. Start service
Write-Step "Starting $ServiceName"
nssm start $ServiceName
Start-Sleep -Seconds 3

# 8. Verify /health
Write-Step "Verifying service health"
$port = "8001"
$envFile = "$RepoPath\.env.local"
if (Test-Path $envFile) {
    $portLine = Get-Content $envFile | Select-String "MCP_PORT"
    if ($portLine) {
        $port = $portLine.ToString().Split("=")[1].Trim()
    }
}

$attempts = 0
$maxAttempts = 10
while ($attempts -lt $maxAttempts) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:$port/health" -TimeoutSec 3
        Write-OK "Health check passed: $($response.version)"
        break
    } catch {
        $attempts++
        if ($attempts -eq $maxAttempts) {
            Write-Fail "Service did not respond at /health after 30 seconds. Check nssm logs."
        }
        Start-Sleep -Seconds 3
    }
}

Write-Host ""
Write-Host "DuggerBot initialized successfully." -ForegroundColor Green
