# Predictive Maintenance - One-Click Launcher
# Silent launch via launcher.vbs, or visible with: powershell -File launcher.ps1 -Visible
param([switch]$Visible)

$ErrorActionPreference = 'Stop'

# Paths
$ProjectDir = Split-Path -Parent $PSScriptRoot
$AppDir = $PSScriptRoot
$LogFile = "$env:TEMP\predictive_maintenance_server.log"
$Port = 8765
$HealthUrl = "http://localhost:$Port/health"
$AppUrl = "http://localhost:$Port"

# Logging
function Write-Log {
    param([string]$Message)
    $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    "$ts  $Message" | Out-File -FilePath $LogFile -Append -Encoding utf8
}

# Rotate log (keep last 200KB)
if (Test-Path $LogFile) {
    $size = (Get-Item $LogFile).Length
    if ($size -gt 200KB) {
        $tail = Get-Content $LogFile -Tail 100 -Encoding utf8
        $tail | Out-File -FilePath $LogFile -Encoding utf8
    }
}

Write-Log "=== Launcher started (PID $PID) ==="
Write-Log "Project: $ProjectDir"
Write-Log "App dir: $AppDir"

# Show message dialog (when no console is visible)
function Show-Dialog {
    param([string]$Title, [string]$Message)
    Write-Log "[DIALOG] $Title : $Message"
    Add-Type -AssemblyName Microsoft.VisualBasic
    [Microsoft.VisualBasic.Interaction]::MsgBox($Message, "OKOnly,SystemModal", $Title) | Out-Null
}

# Find Python installation
function Find-Python {
    try {
        $v = & python --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Python found on PATH: $v"
            return 'python'
        }
    } catch {}
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "C:\Python312\python.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            Write-Log "Python found at: $c"
            return $c
        }
    }
    return $null
}

# Check required packages
function Test-Dependencies {
    param([string]$Python)
    $imports = @('fastapi', 'uvicorn', 'dotenv')
    $missing = @()
    foreach ($mod in $imports) {
        try {
            & $Python -c "import $mod" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) { $missing += $mod }
        } catch { $missing += $mod }
    }
    if ($missing.Count -gt 0) {
        $msg = "Missing Python dependencies:`n`n  $($missing -join ', ')`n`nPlease run:`n  pip install -r web-dashboard\requirements.txt"
        Show-Dialog -Title 'Missing Dependencies' -Message $msg
        Write-Log "Missing dependencies: $($missing -join ', ')"
        return $false
    }
    Write-Log "All dependencies present"
    return $true
}

# Check if server is responding to health checks
function Test-ServerHealthy {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            Write-Log "Server is healthy (status 200)"
            return $true
        }
    } catch {}
    return $false
}

# =====================================================================
# Main
# =====================================================================

# 1. Find Python
$Python = Find-Python
if (-not $Python) {
    Show-Dialog -Title 'Python Not Found' -Message 'Python 3.12 is not installed or not on PATH. Please install Python 3.12 and add it to your PATH environment variable.'
    Write-Log 'ERROR: Python not found'
    exit 1
}

# 2. Check dependencies
if (-not (Test-Dependencies -Python $Python)) {
    exit 1
}

# 3. Server already running? Open browser and exit
if (Test-ServerHealthy) {
    Write-Log 'Server already running, opening browser'
    Start-Process $AppUrl
    exit 0
}

# 4. Check if port is occupied by a non-healthy process
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect('localhost', $Port)
    $tcp.Close()
    Write-Log "Port $Port is occupied but /health failed"
    Show-Dialog -Title 'Port Conflict' -Message "Port $Port is already in use by another program.`n`nPlease close the conflicting program and try again."
    exit 1
} catch {
    Write-Log "Port $Port is free"
}

# 5. Start server as background job
Write-Log "Starting server: $Python app.py"
Push-Location $AppDir
try {
    $job = Start-Job -Name 'PredictiveMaintenance' -ScriptBlock {
        param($py, $wd, $log)
        Set-Location $wd
        & $py app.py *>> $log
    } -ArgumentList $Python, $AppDir, $LogFile
    Write-Log "Server job started (Job ID: $($job.Id))"
} catch {
    Write-Log "ERROR: Failed to start server: $_"
    Show-Dialog -Title 'Startup Failed' -Message "Failed to start the server:`n`n$_`n`nCheck the log file for details:`n$LogFile"
    Pop-Location
    exit 1
}
Pop-Location

# 6. Poll health endpoint with progressive backoff
$waits = @(1, 2, 3, 4, 5, 5, 5, 5)  # up to 30s
$ready = $false
foreach ($w in $waits) {
    Start-Sleep -Seconds $w
    if (Test-ServerHealthy) {
        $ready = $true
        Write-Log "Server ready after ~${w}s of waiting"
        break
    }
    Write-Log "Waiting... (${w}s elapsed)"
}

if (-not $ready) {
    Write-Log 'ERROR: Server startup timed out (30s)'
    Show-Dialog -Title 'Startup Timeout' -Message "Server did not start within 30 seconds.`n`nPlease check the log file for details:`n$LogFile"
    exit 1
}

# 7. Open browser
Write-Log 'Opening browser'
Start-Process $AppUrl
Write-Log "=== Launcher finished successfully ==="
exit 0
