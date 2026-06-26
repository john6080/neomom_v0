@echo off
:: ============================================================
:: run_validations.bat
:: Runs neomom on every *.nml file found recursively under
:: the 'validations' directory.
::
:: Usage:
::   run_validations.bat [validations_dir] [neomom_path]
::
:: Defaults:
::   validations_dir = .\validations
::   neomom_path     = .\bin\neomom.exe
:: ============================================================

setlocal enabledelayedexpansion

:: ── Arguments with defaults ─────────────────────────────────
if "%~1"=="" (
    set VALIDATIONS_DIR=.\validation_cases
) else (
    set VALIDATIONS_DIR=%~1
)

if "%~2"=="" (
    set NEOMOM= neomom.exe
) else (
    set NEOMOM=%~2
)

:: ── Sanity checks ────────────────────────────────────────────
if not exist "%VALIDATIONS_DIR%" (
    echo ERROR: validations directory not found: %VALIDATIONS_DIR%
    exit /b 1
)

if not exist "%NEOMOM%" (
    echo ERROR: neomom executable not found: %NEOMOM%
    exit /b 1
)

:: ── Get absolute path to neomom ──────────────────────────────
for %%F in ("%NEOMOM%") do set NEOMOM_ABS=%%~fF

:: ── Count and collect .nml files ────────────────────────────
set TOTAL=0
set PASSED=0
set FAILED=0
set FAILED_LIST=

echo ============================================================
echo   neomom validation run
echo   Executable : %NEOMOM_ABS%
echo   Search dir : %VALIDATIONS_DIR%
echo ============================================================
echo.

:: ── Run neomom on each .nml file ────────────────────────────
for /r "%VALIDATIONS_DIR%" %%F in (*.nml) do (
    set /a TOTAL+=1
    set NML_FILE=%%~nxF
    set NML_DIR=%%~dpF

    echo --------------------------------------------------------------
    echo   Running : %%F

    :: Run from the nml file's own directory
    pushd "%%~dpF"
    "%NEOMOM_ABS%" "%%~nxF"
    set STATUS=!errorlevel!
    popd

    if !STATUS!==0 (
        echo   Result  : PASSED
        set /a PASSED+=1
    ) else (
        echo   Result  : FAILED ^(exit code !STATUS!^)
        set /a FAILED+=1
        set FAILED_LIST=!FAILED_LIST! %%F
    )
)

:: ── Summary ──────────────────────────────────────────────────
echo.
echo ============================================================
echo   SUMMARY
echo   Total  : %TOTAL%
echo   Passed : %PASSED%
echo   Failed : %FAILED%

if %FAILED% gtr 0 (
    echo.
    echo   Failed cases:
    for %%F in (%FAILED_LIST%) do echo     - %%F
    echo ============================================================
    exit /b 1
) else (
    echo ============================================================
    exit /b 0
)
