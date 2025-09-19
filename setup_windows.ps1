# run.ps1
# PowerShell equivalent of the bash snippet
# Stops on errors like `set -e`
$ErrorActionPreference = 'Stop'

Write-Host "Downloading and executing remote installer..."
# download and execute the install.ps1 (explicit full cmdlets for clarity)
$installerScript = Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1'
Invoke-Expression $installerScript

Write-Host "Running 'uv sync'..."
uv sync

# Determine script directory (works when this file is run as a script)
$scriptDir = if ($PSScriptRoot) { $PSScriptRoot } else { Split-Path -Parent $MyInvocation.MyCommand.Definition }

# Prefer Windows venv layout, fall back to POSIX layout, else system 'python'
$winPython = Join-Path $scriptDir '.venv\Scripts\python.exe'
$posixPython = Join-Path $scriptDir '.venv/bin/python3'

if (Test-Path $winPython) {
    $pythonExe = $winPython
} elseif (Test-Path $posixPython) {
    $pythonExe = $posixPython
} else {
    $pythonExe = 'python'  # assume python is on PATH
}

$scriptPath = Join-Path $scriptDir 'script.py'
Write-Host "Running Python script with: $pythonExe $scriptPath"
& $pythonExe $scriptPath

# Activate the virtualenv for the current PowerShell session (if activation script exists)
$activateWin = Join-Path $scriptDir '.venv\Scripts\Activate.ps1'
$activatePosix = Join-Path $scriptDir '.venv/bin/activate'

if (Test-Path $activateWin) {
    Write-Host "Activating venv for this PowerShell session..."
    # dot-source to activate in current session
    . $activateWin
} elseif (Test-Path $activatePosix) {
    Write-Host "POSIX-style activate found; trying to source it via bash (WSL or Git Bash required)..."
    bash -c "source .venv/bin/activate"
} else {
    Write-Host "No activation script found in .venv."
}
