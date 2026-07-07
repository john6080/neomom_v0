# ==============================================================
# neomom_Zin.spec
# NeoMOM Impedance Sweep Viewer — PyInstaller one-file build (LINUX)
#
# Repository layout:
#
#   neomom_Zin/
#   ├── linux/
#   │   └── neomom_Zin.spec      <- this file
#   ├── windows/
#   │   └── neomom_Zin.spec      <- Windows version
#   └── src/
#       ├── neomom_Zin.py
#       ├── Zin_reader.py
#       ├── Zin_plots.py
#       └── ham_bands.py
#
# Build command (from project root):
#
#   $HOME/venvs/neomom_plot/bin/pyinstaller \
#       neomom_Zin/linux/neomom_Zin.spec \
#       --distpath neomom_Zin/build/dist \
#       --workpath neomom_Zin/build/work
#
# Output:
#   neomom_Zin/build/dist/neomom_Zin    <- the executable
#
# Uses neomom_plot venv — no separate venv needed.
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# SPECPATH is set automatically by PyInstaller to the directory
# containing this .spec file (neomom_Zin/linux/)
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
# Bundle all .py helpers so cross-module imports work inside
# the frozen one-file bundle.
# --------------------------------------------------------------

all_py = [
    (f, '.')
    for f in glob.glob(os.path.join(SRC, '*.py'))
]

# --------------------------------------------------------------
# ANALYSIS
# --------------------------------------------------------------

a = Analysis(
    [os.path.join(SRC, 'neomom_Zin.py')],

    pathex=[SRC],

    binaries=[],

    datas=all_py,

    hiddenimports=[
        # tkinter submodules
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.font',

        # matplotlib backend for tkinter embedding
        'matplotlib.backends.backend_tkagg',
        'matplotlib.figure',

        # numpy — used in Zin_plots.py and Zin_reader.py
        'numpy',

        # Pillow tkinter bridge — indirect matplotlib dependency
        'PIL._tkinter_finder',
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],

    win_no_prefer_redirects=False,
    win_private_assemblies=False,

    cipher=block_cipher,
    noarchive=False,
)

# --------------------------------------------------------------
# PYZ — compiled bytecode archive
# --------------------------------------------------------------

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# --------------------------------------------------------------
# EXE — one-file bundle
# --------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],

    name='neomom_Zin',

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,

    upx=True,
    upx_exclude=[],

    runtime_tmpdir=None,

    # False = GUI app, no console window on launch
    console=False,

    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
