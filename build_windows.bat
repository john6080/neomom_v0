@echo off
:: ==============================================================
:: build_windows.bat
:: NeoMOM — Windows build launcher
::
:: Launches build_all_windows.ps1 with ExecutionPolicy Bypass
:: so no digital signature or policy change is required.
::
:: Run from project root or double-click in Explorer.
:: ==============================================================

echo.
echo NeoMOM Windows Build
echo ====================

PowerShell -ExecutionPolicy Bypass -File "%~dp0scripts\build_all_windows.ps1"

if %ERRORLEVEL% neq 0 (
    echo.
    echo BUILD FAILED - see errors above
    pause
    exit /b 1
)

pause
