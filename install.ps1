# install.ps1 - Windows bootstrap for openline-101
#
# Run in PowerShell (no admin needed):
#
#     irm https://raw.githubusercontent.com/jobrac/openline-101/main/install.ps1 | iex
#
# It picks the easiest path for your machine:
#   • If Python is installed  -> downloads openline.py and runs it (needs nothing else).
#   • If Python is NOT installed -> downloads the prebuilt openline.exe and runs it.
#
# Either way you end up at one interactive prompt for your admin password
# (printed on the sticker under the router). Make sure this PC is on the
# router's Wi-Fi with mobile hotspots/other networks off.

$ErrorActionPreference = 'Stop'

# --- EDIT THESE two lines to point at your repo / release ---
$Repo    = 'https://raw.githubusercontent.com/jobrac/openline-101/main'
$ExeUrl  = 'https://github.com/jobrac/openline-101/releases/latest/download/openline.exe'
# ------------------------------------------------------------

$PyUrl   = "$Repo/openline.py"
$WorkDir = Join-Path $env:TEMP 'openline-101'
New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null

function Find-Python {
    foreach ($cmd in @('python', 'python3', 'py')) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($exe) {
            # 'py' / 'python' can be the Windows Store stub that just opens the
            # Store - check it actually runs.
            try {
                & $exe.Source '--version' *> $null
                if ($LASTEXITCODE -eq 0) { return $exe.Source }
            } catch { }
        }
    }
    return $null
}

Write-Host '=== openline-101 (Windows) ===' -ForegroundColor Cyan

$py = Find-Python
if ($py) {
    Write-Host "Python found ($py) - using the script path." -ForegroundColor Green
    $script = Join-Path $WorkDir 'openline.py'
    Invoke-WebRequest -Uri $PyUrl -OutFile $script -UseBasicParsing
    & $py $script
}
else {
    Write-Host 'Python not found - downloading the standalone openline.exe.' -ForegroundColor Yellow
    $exe = Join-Path $WorkDir 'openline.exe'
    Invoke-WebRequest -Uri $ExeUrl -OutFile $exe -UseBasicParsing
    & $exe
}
