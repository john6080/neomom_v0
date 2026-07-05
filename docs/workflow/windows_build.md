# Windows Build Guide — NeoMOM

## Prerequisites

### Required software
- Python from python.org — check **Add to PATH** during install
- Git from git-scm.com
- Visual Studio 2022 (Community edition is fine)
- Intel oneAPI HPC Toolkit (provides ifx):
  `https://www.intel.com/content/www/us/en/developer/tools/oneapi/hpc-toolkit.html`

### PowerShell execution policy (one-time setup)
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
If this doesn't take effect (corporate policy), use `build_windows.bat` instead
which bypasses the policy automatically.

### Python venvs
Create once from project root in PowerShell:

```powershell
# Input GUI venv
python -m venv "$env:USERPROFILE\venvs\neomom_input"
& "$env:USERPROFILE\venvs\neomom_input\Scripts\Activate.ps1"
pip install -r input_gui\requirements_input.txt
pip install pyinstaller
deactivate

# Plot GUI venv
python -m venv "$env:USERPROFILE\venvs\neomom_plot"
& "$env:USERPROFILE\venvs\neomom_plot\Scripts\Activate.ps1"
pip install -r plot_gui\requirements_plot.txt
pip install pyinstaller
deactivate
```

Venvs live at:
```
C:\Users\<username>\venvs\neomom_input\
C:\Users\<username>\venvs\neomom_plot\
```

**Note:** Venvs cannot be copied between machines — always create fresh.

---

## Fortran Engine Build (Visual Studio)

Must be done manually before running the build script:

1. Open `engine\windows\neomom.sln` in Visual Studio
2. Select **Release** | **x64** from toolbar dropdowns
3. **Build → Build Solution** (Ctrl+Shift+B)
4. Verify exe exists: `engine\windows\x64\Release\neomom.exe`

See `engine\windows\README.md` for full VS setup details.

---

## Full Build (all three components + package)

After VS Release build is done, from project root:

**Option A — double-click:**
```
build_windows.bat
```

**Option B — from PowerShell:**
```powershell
.\scripts\build_all_windows.ps1
```

**Option C — if execution policy blocks Option B:**
```powershell
PowerShell -ExecutionPolicy Bypass -File .\scripts\build_all_windows.ps1
```

Output:
```
packages\windows\neomom\neomom.exe
packages\windows\neomom_input\neomom_input.exe
packages\windows\neomom_plot\neomom_plot.exe
packages\neomom_windows.zip
```

---

## Build Output Locations

| Component | Final exe |
|---|---|
| Fortran engine (VS) | `engine\windows\x64\Release\neomom.exe` |
| neomom_input | `input_gui\build\dist\neomom_input.exe` |
| neomom_plot | `plot_gui\build\dist\neomom_plot.exe` |
| Package | `packages\neomom_windows.zip` |

All build output is gitignored — never committed to the repo.

---

## PyInstaller Spec Files

```
input_gui\windows\neomom_input.spec
plot_gui\windows\neomom_plot.spec
```

To build manually from project root:
```powershell
& "$env:USERPROFILE\venvs\neomom_input\Scripts\pyinstaller.exe" `
    input_gui\windows\neomom_input.spec `
    --distpath input_gui\build\dist `
    --workpath input_gui\build\work
```

---

## Git on Windows

```powershell
git pull                          # get latest from GitHub
git add .
git status                        # review changes
git commit -m "windows: description"
git push                          # send to GitHub
```

Authentication: uses Personal Access Token (PAT) — same token as Linux.
Paste with **Ctrl+V** in PowerShell (not Ctrl+Shift+V like Linux terminal).

---

## Cloning the repo on a new Windows machine

```powershell
git clone https://github.com/john6080/neomom_v0.git
cd neomom_v0
```

Then set up venvs and do a VS Release build as described above.

---

## Troubleshooting

**Script not digitally signed:**
Use `build_windows.bat` instead — it bypasses execution policy automatically.

**PyInstaller not found:**
```powershell
& "$env:USERPROFILE\venvs\neomom_input\Scripts\Activate.ps1"
pip install pyinstaller
deactivate
```

**Engine exe not found by build script:**
Build the Release configuration in Visual Studio first.
Verify path: `engine\windows\x64\Release\neomom.exe`
If VS outputs elsewhere, update `$EngineExe` in `scripts\build_all_windows.ps1`.

**Missing module error when running exe:**
Add module name to `hiddenimports` in the relevant `.spec` file and rebuild.
