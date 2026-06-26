# ==============================================================
# build_all_windows.ps1
# NeoMOM — full Windows build + package
#
# Harvests the Fortran engine from the Visual Studio Release build,
# builds both Python GUIs with PyInstaller, then assembles the
# package and zip.
#
# Usage (from project root — run once to enable scripts):
#   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
#
# Then run:
#   .\scripts\build_all_windows.ps1
#
# Prerequisites:
#   - Visual Studio Release build already done:
#       engine\windows\x64\Release\neomom.exe must exist
#   - Python venvs populated:
#       %USERPROFILE%\venvs\neomom_input\Scripts\pyinstaller.exe
#       %USERPROFILE%\venvs\neomom_plot\Scripts\pyinstaller.exe
#   - To create venvs:
#       python -m venv "$env:USERPROFILE\venvs\neomom_input"
#       & "$env:USERPROFILE\venvs\neomom_input\Scripts\activate.ps1"
#       pip install -r input_gui\requirements_input.txt
#       pip install pyinstaller
#       deactivate
#       (repeat for neomom_plot)
# ==============================================================

# Stop on any error
$ErrorActionPreference = 'Stop'

# --------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------

$ProjectRoot  = Split-Path -Parent $PSScriptRoot

$EngineExe    = Join-Path $ProjectRoot "engine\windows\x64\Release\neomom.exe"

$InputSpec    = Join-Path $ProjectRoot "input_gui\windows\neomom_input_windows.spec"
$PlotSpec     = Join-Path $ProjectRoot "plot_gui\windows\neomom_plot_windows.spec"

$InputDist    = Join-Path $ProjectRoot "input_gui\build\dist"
$InputWork    = Join-Path $ProjectRoot "input_gui\build\work"
$PlotDist     = Join-Path $ProjectRoot "plot_gui\build\dist"
$PlotWork     = Join-Path $ProjectRoot "plot_gui\build\work"

$PyInstInput  = Join-Path $env:USERPROFILE "venvs\neomom_input\Scripts\pyinstaller.exe"
$PyInstPlot   = Join-Path $env:USERPROFILE "venvs\neomom_plot\Scripts\pyinstaller.exe"

$PackageDir   = Join-Path $ProjectRoot "packages\windows"
$PackageZip   = Join-Path $ProjectRoot "packages\neomom_windows.zip"
$ModelsDir    = Join-Path $ProjectRoot "test_cases\validation_cases"

# --------------------------------------------------------------
# HELPERS
# --------------------------------------------------------------

function Step  { Write-Host "`n==> $args" -ForegroundColor Cyan }
function Ok    { Write-Host "  OK: $args" -ForegroundColor Green }
function Fail  { Write-Host "  FAILED: $args" -ForegroundColor Red; exit 1 }

# --------------------------------------------------------------
# PREFLIGHT CHECKS
# --------------------------------------------------------------

Step "Preflight checks"

if (-not (Test-Path $InputSpec))   { Fail "Input spec not found: $InputSpec" }
if (-not (Test-Path $PlotSpec))    { Fail "Plot spec not found: $PlotSpec" }
if (-not (Test-Path $PyInstInput)) { Fail "PyInstaller not found: $PyInstInput" }
if (-not (Test-Path $PyInstPlot))  { Fail "PyInstaller not found: $PyInstPlot" }
if (-not (Test-Path $EngineExe))   {
    Fail "Engine exe not found: $EngineExe`n  Build the Release configuration in Visual Studio first."
}

Ok "All preflight checks passed"

# --------------------------------------------------------------
# STEP 1 — Fortran engine (already built by Visual Studio)
# --------------------------------------------------------------

Step "Fortran engine — using VS Release build"
Ok "Engine found: $EngineExe"

# --------------------------------------------------------------
# STEP 2 — neomom_input GUI
# --------------------------------------------------------------

Step "Building neomom_input (PyInstaller)"

New-Item -ItemType Directory -Force -Path $InputDist | Out-Null
New-Item -ItemType Directory -Force -Path $InputWork | Out-Null

& $PyInstInput $InputSpec `
    --distpath $InputDist `
    --workpath $InputWork

if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed for neomom_input" }

$InputExe = Join-Path $InputDist "neomom_input.exe"
if (-not (Test-Path $InputExe)) { Fail "neomom_input.exe not found after build" }

Ok "neomom_input built: $InputExe"

# --------------------------------------------------------------
# STEP 3 — neomom_plot GUI
# --------------------------------------------------------------

Step "Building neomom_plot (PyInstaller)"

New-Item -ItemType Directory -Force -Path $PlotDist | Out-Null
New-Item -ItemType Directory -Force -Path $PlotWork | Out-Null

& $PyInstPlot $PlotSpec `
    --distpath $PlotDist `
    --workpath $PlotWork

if ($LASTEXITCODE -ne 0) { Fail "PyInstaller failed for neomom_plot" }

$PlotExe = Join-Path $PlotDist "neomom_plot.exe"
if (-not (Test-Path $PlotExe)) { Fail "neomom_plot.exe not found after build" }

Ok "neomom_plot built: $PlotExe"

# --------------------------------------------------------------
# STEP 4 — Harvest into packages\windows\
# --------------------------------------------------------------

Step "Harvesting package"

# Clean and recreate package tree
if (Test-Path $PackageDir) { Remove-Item $PackageDir -Recurse -Force }

New-Item -ItemType Directory -Force -Path "$PackageDir\neomom"       | Out-Null
New-Item -ItemType Directory -Force -Path "$PackageDir\neomom_input" | Out-Null
New-Item -ItemType Directory -Force -Path "$PackageDir\neomom_plot"  | Out-Null
New-Item -ItemType Directory -Force -Path "$PackageDir\models"       | Out-Null

Copy-Item $EngineExe  "$PackageDir\neomom\"
Copy-Item $InputExe   "$PackageDir\neomom_input\"
Copy-Item $PlotExe    "$PackageDir\neomom_plot\"

if (Test-Path $ModelsDir) {
    Copy-Item "$ModelsDir\*" "$PackageDir\models\" -Recurse
    Ok "Models copied from $ModelsDir"
} else {
    Write-Host "  WARNING: models dir not found, skipping: $ModelsDir" -ForegroundColor Yellow
}

Ok "Package tree assembled: $PackageDir"

# --------------------------------------------------------------
# STEP 5 — Zip
# --------------------------------------------------------------

Step "Creating zip archive"

if (Test-Path $PackageZip) { Remove-Item $PackageZip -Force }

Compress-Archive -Path "$PackageDir\*" -DestinationPath $PackageZip

Ok "Package ready: $PackageZip"

# --------------------------------------------------------------
# DONE
# --------------------------------------------------------------

Write-Host ""
Write-Host "Build complete." -ForegroundColor Green
Write-Host "  Engine  : $PackageDir\neomom\neomom.exe"
Write-Host "  Input   : $PackageDir\neomom_input\neomom_input.exe"
Write-Host "  Plot    : $PackageDir\neomom_plot\neomom_plot.exe"
Write-Host "  Archive : $PackageZip"
Write-Host ""
