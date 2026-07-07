# ==============================================================
# neomom_current.spec
# NeoMOM Current Distribution Viewer — PyInstaller one-file build (LINUX)
#
# Repository layout:
#
#   neomom_current/
#   ├── linux/
#   │   └── neomom_current.spec      <- this file
#   ├── windows/
#   │   └── neomom_current.spec      <- Windows version
#   └── src/
#       └── neomom_current.py
#
# Build command (from project root):
#
#   $HOME/venvs/neomom_plot/bin/pyinstaller \
#       neomom_current/linux/neomom_current.spec \
#       --distpath neomom_current/build/dist \
#       --workpath neomom_current/build/work
#
# Output:
#   neomom_current/build/dist/neomom_current    <- the executable
#
# Uses neomom_plot venv — no separate venv needed.
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# SPECPATH is set automatically by PyInstaller to the directory
# containing this .spec file (neomom_current/linux/)
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
# Bundle all .py files in src/
# --------------------------------------------------------------

all_py = [
    (f, '.')
    for f in glob.glob(os.path.join(SRC, '*.py'))
]

# --------------------------------------------------------------
# ANALYSIS
# --------------------------------------------------------------

a = Analysis(
    [os.path.join(SRC, 'neomom_current.py')],

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

        # matplotlib backends and 3D toolkit
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends._backend_tk',
        'matplotlib.figure',
        'mpl_toolkits.mplot3d',
        'mpl_toolkits.mplot3d.art3d',

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

    name='neomom_current',

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
