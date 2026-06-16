# Predictive Maintenance - Desktop Shortcut Installer
# Run once after cloning: powershell -ExecutionPolicy Bypass -File setup_shortcut.ps1

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$DesktopDir = [Environment]::GetFolderPath('Desktop')
$ShortcutName = 'Predictive Maintenance.lnk'
$ShortcutPath = Join-Path $DesktopDir $ShortcutName
$IconPath = Join-Path $ScriptDir 'icon.ico'

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Predictive Maintenance - Shortcut Installer" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Generate icon
Write-Host "[1/2] Generating app icon..." -ForegroundColor Yellow

$pillowOk = $false
try {
    $check = python -c "from PIL import Image, ImageDraw; print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) { $pillowOk = $true }
} catch {}

if ($pillowOk) {
    $pyScript = Join-Path $env:TEMP 'gen_icon.py'
    @'
from PIL import Image, ImageDraw
import math

size = 64
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
cx, cy = size // 2, size // 2

# Dark circular background
draw.ellipse([2, 2, size - 2, size - 2], fill=(15, 20, 30, 255))
# Outer ring (cyan)
draw.ellipse([2, 2, size - 2, size - 2], outline=(102, 217, 200, 255), width=3)
# Cross shape
r = 18
draw.line([(cx - r, cy), (cx + r, cy)], fill=(102, 217, 200, 255), width=4)
draw.line([(cx, cy - r), (cx, cy + r)], fill=(102, 217, 200, 255), width=4)
# Center dot (purple accent)
draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(191, 90, 242, 255))
# Corner dots (blue accents)
for angle in [30, 120, 210, 300]:
    rad = angle * math.pi / 180
    dx = int((r + 4) * math.cos(rad))
    dy = int((r + 4) * math.sin(rad))
    draw.ellipse([cx + dx - 4, cy + dy - 4, cx + dx + 4, cy + dy + 4], fill=(109, 181, 249, 200))

ico32 = img.resize((32, 32), Image.LANCZOS)
ico32.save(r"__ICON_PATH__", format="ICO", sizes=[(32, 32)])
'@ -replace '__ICON_PATH__', $IconPath.Replace('\', '\\') | Out-File -FilePath $pyScript -Encoding utf8

    python $pyScript 2>&1 | Out-Null
    Remove-Item $pyScript -Force -ErrorAction SilentlyContinue

    if (Test-Path $IconPath) {
        Write-Host "  Icon generated (Pillow): $IconPath" -ForegroundColor Green
    } else {
        Write-Host "  Icon generation failed, using default" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  Pillow not available (pip install pillow), using default icon" -ForegroundColor DarkYellow
}

# Step 2: Create desktop shortcut
Write-Host "[2/2] Creating desktop shortcut..." -ForegroundColor Yellow

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = 'wscript.exe'
$Shortcut.Arguments = '//B "' + $ScriptDir + '\launcher.vbs"'
$Shortcut.WorkingDirectory = $ScriptDir
$Shortcut.Description = 'Industrial Predictive Maintenance Platform - One-Click Launch'
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = $IconPath
}
$Shortcut.Save()

if (Test-Path $ShortcutPath) {
    Write-Host "  Shortcut created: $ShortcutPath" -ForegroundColor Green
} else {
    Write-Host "  Failed to create shortcut - check permissions" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Double-click 'Predictive Maintenance' on your desktop to launch." -ForegroundColor White
Write-Host "  The server starts in the background - browser opens in 5-15s." -ForegroundColor Gray
