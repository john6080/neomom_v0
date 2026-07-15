@echo off
:: ==============================================================
:: copy_windows.bat
:: NeoMOM — Windows install/copy launcher
::
:: Copies all built executables (engine + GUI tools) into
:: %USERPROFILE%\bin so they're available wherever you run them
:: from, without needing to know each build\dist path.
::
:: Run this AFTER a successful build_windows.bat. Mirrors the
:: Linux "make copy" target -- see Makefile at project root.
::
:: Run from project root or double-click in Explorer.
:: ==============================================================

setlocal enabledelayedexpansion

set "BINDIR=%USERPROFILE%\bin"
set "ERRORS=0"

echo.
echo NeoMOM Windows Copy
echo ====================
echo Target: %BINDIR%
echo.

if not exist "%BINDIR%" (
    echo Creating %BINDIR% ...
    mkdir "%BINDIR%"
)

call :copy_one "%~dp0engine\windows\x64\Release\neomom.exe"        "neomom.exe"
call :copy_one "%~dp0neomom_input\build\dist\neomom_input.exe"     "neomom_input.exe"
call :copy_one "%~dp0neomom_plot\build\dist\neomom_plot.exe"       "neomom_plot.exe"
call :copy_one "%~dp0neomom_Zin\build\dist\neomom_Zin.exe"         "neomom_Zin.exe"
call :copy_one "%~dp0neomom_current\build\dist\neomom_current.exe" "neomom_current.exe"

echo.
if %ERRORS% neq 0 (
    echo COPY FAILED -- %ERRORS% file^(s^) missing or could not be copied, see above
    pause
    exit /b 1
)

echo All executables copied to %BINDIR%
echo.
echo Make sure %BINDIR% is on your PATH:
echo   echo %%PATH%% ^| findstr /I "%BINDIR%"
echo.
echo If it's missing, add it via:
echo   System Properties -^> Environment Variables -^> Path -^> New
echo.
pause
exit /b 0

:: --------------------------------------------------------------
:: :copy_one  "<source path>"  "<dest filename>"
:: Copies one exe into %BINDIR%, reporting success/failure per
:: file rather than stopping at the first missing one -- so a
:: partial build (e.g. you only rebuilt neomom_plot today) still
:: copies everything that IS available.
:: --------------------------------------------------------------
:copy_one
set "SRC=%~1"
set "NAME=%~2"

if not exist "%SRC%" (
    echo   MISSING  %NAME%   ^(expected at: %SRC%^)
    set /a ERRORS+=1
    exit /b 0
)

copy /Y "%SRC%" "%BINDIR%\%NAME%" >nul
if !ERRORLEVEL! neq 0 (
    echo   FAILED   %NAME%   ^(copy error^)
    set /a ERRORS+=1
) else (
    echo   OK       %NAME%
)
exit /b 0