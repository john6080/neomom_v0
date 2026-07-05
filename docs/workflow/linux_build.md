# Linux Build Guide — NeoMOM

## Prerequisites

### System packages
```bash
sudo apt install makedepf90       # Fortran dependency generator
sudo apt install python3-tk       # tkinter for Python GUIs
sudo apt install upx              # optional: compresses PyInstaller exe
```

### Intel oneAPI (ifx compiler)
Download and install from:
`https://www.intel.com/content/www/us/en/developer/tools/oneapi/hpc-toolkit.html`

After install, ifx must be on PATH. Verify:
```bash
ifx --version
```

### Python venvs
Create once — recreate if packages change or venv is corrupted:

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

---

## Full Build (all three components + package)

From project root:
```bash
./scripts/build_all_linux.sh              # ifx (default)
./scripts/build_all_linux.sh gfortran     # gfortran
```

Output:
```
packages/linux/neomom/neomom
packages/linux/neomom_input/neomom_input
packages/linux/neomom_plot/neomom_plot
packages/neomom_linux.zip
```

---

## Individual Component Builds

From project root:
```bash
make engine                    # Fortran engine only (ifx)
make engine COMPILER=gfortran  # gfortran
make input                     # neomom_input GUI only
make plot                      # neomom_plot GUI only
```

---

## Engine Only (from engine/linux/)

```bash
cd engine/linux

make                           # ifx Debug (default)
make release                   # ifx Release
make COMPILER=gfortran         # gfortran Debug
make release COMPILER=gfortran # gfortran Release
make clean                     # wipe engine/build/
make distclean                 # wipe engine/build/ + top-level exe
make copy                      # copy exe to ~/bin/
```

---

## Clean Builds

```bash
# From project root:
make -f Makefile clean         # wipe all build/ folders
make -f Makefile distclean     # clean + wipe packages/
```

---

## Build Output Locations

| Component | Build artifacts | Final exe |
|---|---|---|
| Fortran engine | `engine/build/*.o *.mod` | `engine/build/neomom` |
| Installed engine | — | `build/neomom` |
| neomom_input | `input_gui/build/work/` | `input_gui/build/dist/neomom_input` |
| neomom_plot | `plot_gui/build/work/` | `plot_gui/build/dist/neomom_plot` |
| Package | `packages/linux/` | `packages/neomom_linux.zip` |

All build output is gitignored — never committed to the repo.

---

## PyInstaller Spec Files

Spec files live in the platform subfolder:
```
input_gui/linux/neomom_input.spec
plot_gui/linux/neomom_plot.spec
```

To build manually (from project root):
```bash
source ~/venvs/neomom_input/bin/activate
pyinstaller input_gui/linux/neomom_input.spec \
    --distpath input_gui/build/dist \
    --workpath input_gui/build/work
deactivate
```

---

## Venv Contents

### neomom_input venv
```
matplotlib
pyinstaller
```
(numpy, pillow etc. are indirect dependencies installed automatically)

### neomom_plot venv
```
matplotlib
numpy
pandas
pyinstaller
```

To verify venv contents:
```bash
source ~/venvs/neomom_input/bin/activate
pip list
deactivate
```

---

## Troubleshooting

**makedepf90 not found:**
```bash
sudo apt install makedepf90
```

**tkinter not found at runtime:**
```bash
sudo apt install python3-tk
```

**PyInstaller not found:**
```bash
source ~/venvs/neomom_input/bin/activate
pip install pyinstaller
deactivate
```

**Missing module error when running exe:**
Add the module name to `hiddenimports` in the relevant `.spec` file and rebuild.
