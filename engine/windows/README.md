# NeoMOM Engine — Windows Build (Visual Studio + ifx)

## Prerequisites

- Intel oneAPI HPC Toolkit (provides `ifx`)
  Download: https://www.intel.com/content/www/us/en/developer/tools/oneapi/hpc-toolkit.html
- Visual Studio 2022 (Community edition is fine)
- Intel Fortran compiler extension for Visual Studio (included in oneAPI)

## Solution file

`neomom.sln` — open this in Visual Studio.

## Build output paths

The VS project is configured to output to:

| Configuration | Output |
|---|---|
| Debug   | `engine\windows\x64\Debug\neomom.exe` |
| Release | `engine\windows\x64\Release\neomom.exe` |

The `build_all_windows.ps1` harvest script expects the Release exe at:
```
engine\windows\x64\Release\neomom.exe
```

**If your VS project outputs to a different path**, update `ENGINE_EXE`
in `scripts\build_all_windows.ps1` to match.

## Building

1. Open `neomom.sln` in Visual Studio
2. Select **Release** | **x64** from the toolbar dropdowns
3. Build → Build Solution (Ctrl+Shift+B)
4. Verify: `engine\windows\x64\Release\neomom.exe` exists

Or build from the command line (from a Developer PowerShell):
```powershell
msbuild neomom.sln /p:Configuration=Release /p:Platform=x64
```

## Source files

All Fortran source files are in `engine\src\` and shared with the
Linux build. Do not duplicate source files into the windows folder.

## Notes

- The `.sln` and `.vcxproj` files are Windows-only and gitignored
  on Linux but committed on Windows.
- Module files (`.mod`) and object files (`.obj`) are generated
  into the output directory and are gitignored.
- The `ifx` compiler on Windows uses the same flags as Linux
  with minor differences (no `-fpp`, use `/fpp` instead etc.) —
  these are set inside the VS project properties, not in a makefile.
