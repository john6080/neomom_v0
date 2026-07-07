# ==============================================================
# neomom_Zin.spec
# NeoMOM Impedance Sweep Viewer — PyInstaller one-file build (WINDOWS)
#
# Repository layout:
#
#   neomom_Zin/
#   ├── linux/
#   │   └── neomom_Zin.spec      <- Linux version
#   ├── windows/
#   │   └── neomom_Zin.spec      <- this file
#   └── src/
#       ├── neomom_Zin.py
#       ├── Zin_reader.py
#       ├── Zin_plots.py
#       └── ham_bands.py
#
# Build command (from project root):
#
#   & "$env:USERPROFILE\venvs\neomom_plot\Scripts\pyinstaller.exe" `
#       neomom_Zin\windows\neomom_Zin.spec `
#       --distpath neomom_Zin\build\dist `
#       --workpath neomom_Zin\build\work
#
# Output:
#   neomom_Zin\build\dist\neomom_Zin.exe    <- the executable
#
# Uses neomom_plot venv — no separate venv needed.
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
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

        # numpy
        'numpy',

        # Pillow tkinter bridge
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
# PYZ
# --------------------------------------------------------------

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

# --------------------------------------------------------------
# EXE
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

    console=False,

    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
