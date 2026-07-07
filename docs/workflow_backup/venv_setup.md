# Python Virtual Environment Setup — NeoMOM

## Overview

Two separate venvs — one per GUI component:

| Venv | Used by | Key packages |
|---|---|---|
| `neomom_input` | neomom_input GUI | matplotlib |
| `neomom_plot` | neomom_plot GUI | matplotlib, numpy, pandas |

Venvs live **outside** the project directory and are never committed to Git.

---

## Why separate venvs

- Each GUI has different dependencies
- PyInstaller bundles only what's in the active venv
- Keeps exe sizes minimal — no unused packages bundled

---

## Linux Setup

```bash
# Input GUI venv
python3 -m venv ~/venvs/neomom_input
source ~/venvs/neomom_input/bin/activate
pip install -r input_gui/requirements_input.txt
pip install pyinstaller
deactivate

# Plot GUI venv
python3 -m venv ~/venvs/neomom_plot
source ~/venvs/neomom_plot/bin/activate
pip install -r plot_gui/requirements_plot.txt
pip install pyinstaller
deactivate
```

Venvs live at:
```
~/venvs/neomom_input/
~/venvs/neomom_plot/
```

---

## Windows Setup

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

---

## Verifying venv contents

```bash
# Linux
source ~/venvs/neomom_input/bin/activate
pip list
deactivate
```

Expected output for neomom_input — key packages:
```
matplotlib
numpy
pillow
pyinstaller
```

Expected output for neomom_plot — key packages:
```
matplotlib
numpy
pandas
pillow
pyinstaller
```

---

## Recreating a venv from scratch

If a venv becomes corrupted or Python is upgraded:

```bash
# Linux
rm -rf ~/venvs/neomom_input
python3 -m venv ~/venvs/neomom_input
source ~/venvs/neomom_input/bin/activate
pip install -r input_gui/requirements_input.txt
pip install pyinstaller
deactivate
```

---

## Important rules

- **Never copy venvs between machines** — absolute paths are hardcoded inside
- **Never commit venvs to Git** — they are outside the project directory anyway
- **Always use pip-chill not pip freeze** to regenerate requirements files:
  ```bash
  pip install pip-chill
  pip-chill > requirements_input.txt
  ```
  `pip freeze` dumps everything including indirect dependencies — too noisy.

---

## Working interactively (development/debugging)

To run a GUI script directly without building an exe:

```bash
source ~/venvs/neomom_input/bin/activate
cd input_gui/src
python neomom_input.py
deactivate
```

```bash
source ~/venvs/neomom_plot/bin/activate
cd plot_gui/src
python neomom_plot.py
deactivate
```
