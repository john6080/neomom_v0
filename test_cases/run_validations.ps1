# ============================================================
# run_validations.ps1
# Runs neomom on every *.nml file found recursively under
# the 'validations' directory.
#
# Usage:
#   .\run_validations.ps1 [validations_dir] [neomom_path]
#
# Defaults:
#   validations_dir = .\validations_cases
#   neomom_path     = .\bin\neomom.exe
#
# Note: if execution policy blocks this, run once:
#   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# ============================================================

param(
    [string]$ValidationsDir = ".\validations_cases",
    [string]$NeomomPath     = ".\bin\neomom.exe"
)

# ── Sanity checks ────────────────────────────────────────────
if (-not (Test-Path $ValidationsDir)) {
    Write-Host "ERROR: validations directory not found: $ValidationsDir"
    exit 1
}

if (-not (Test-Path $NeomomPath)) {
    Write-Host "ERROR: neomom executable not found: $NeomomPath"
    exit 1
}

# Absolute path to neomom
$NeomomAbs = Resolve-Path $NeomomPath

# ── Find all .nml files, sorted ──────────────────────────────
$NmlFiles = Get-ChildItem -Path $ValidationsDir -Recurse -Filter "*.nml" |
            Sort-Object FullName

$Total  = $NmlFiles.Count
$Passed = 0
$Failed = 0
$FailedList = @()

if ($Total -eq 0) {
    Write-Host "No .nml files found under $ValidationsDir"
    exit 0
}

Write-Host "============================================================"
Write-Host "  neomom validation run"
Write-Host "  Executable : $NeomomAbs"
Write-Host "  Search dir : $ValidationsDir"
Write-Host "  Found      : $Total .nml file(s)"
Write-Host "============================================================"
Write-Host ""

# ── Run neomom on each .nml file ─────────────────────────────
foreach ($NmlFile in $NmlFiles) {
    Write-Host "--------------------------------------------------------------"
    Write-Host "  Running : $($NmlFile.FullName)"

    # Run from the directory containing the .nml file
    Push-Location $NmlFile.DirectoryName
    & $NeomomAbs $NmlFile.Name
    $Status = $LASTEXITCODE
    Pop-Location

    if ($Status -eq 0) {
        Write-Host "  Result  : PASSED"
        $Passed++
    } else {
        Write-Host "  Result  : FAILED (exit code $Status)"
        $Failed++
        $FailedList += $NmlFile.FullName
    }
}

# ── Summary ──────────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================"
Write-Host "  SUMMARY"
Write-Host "  Total  : $Total"
Write-Host "  Passed : $Passed"
Write-Host "  Failed : $Failed"

if ($Failed -gt 0) {
    Write-Host ""
    Write-Host "  Failed cases:"
    foreach ($F in $FailedList) {
        Write-Host "    - $F"
    }
    Write-Host "============================================================"
    exit 1
} else {
    Write-Host "============================================================"
    exit 0
}
