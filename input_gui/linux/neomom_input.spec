# ==============================================================
# neomom_input.spec
# NeoMOM Input GUI — PyInstaller one-file build
#
# Repository layout:
#
#   input_gui/
#   ├── linux/
#   │   └── neomom_input.spec     <- this file
#   ├── windows/
#   │   └── neomom_input.spec     <- copy and adjust for Windows
#   └── src/
#       ├── neomom_input.py
#       ├── constants.py
#       ├── maa_parser.py
#       ├── neomom_model.py
#       ├── nml_io.py
#       ├── nml_to_maa.py
#       └── nml_to_nec.py
#
# Build command (from project root or scripts/):
#
#   pyinstaller input_gui/linux/neomom_input.spec \
#       --distpath input_gui/build/dist \
#       --workpath input_gui/build/work
#
# Output:
#   input_gui/build/dist/neomom_input    <- the executable
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# SPECPATH is set automatically by PyInstaller to the directory
# containing this .spec file (input_gui/linux/)
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
# Bundle all .py helpers so that the importlib dynamic loads of
# nml_to_nec.py and nml_to_maa.py work inside the frozen bundle.
# PyInstaller static analysis cannot detect these runtime loads.
# At runtime they are extracted to sys._MEIPASS by PyInstaller.
# --------------------------------------------------------------

all_py = [
    (f, '.')
    for f in glob.glob(os.path.join(SRC, '*.py'))
]

# --------------------------------------------------------------
# ANALYSIS
# --------------------------------------------------------------

a = Analysis(
    [os.path.join(SRC, 'neomom_input.py')],

    pathex=[SRC],

    binaries=[],

    datas=all_py,

    hiddenimports=[
        # tkinter submodules — not auto-detected by PyInstaller
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.font',

        # matplotlib backend for tkinter embedding
        'matplotlib.backends.backend_tkagg',
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
# a.binaries, a.zipfiles, a.datas are included directly here
# (no COLLECT block) which is what makes this a one-file build.
# --------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],

    name='neomom_input',

    debug=False,
    bootloader_ignore_signals=False,
    strip=False,

    # UPX compression — reduces exe size if upx is installed.
    # Set to False if build machine does not have upx.
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
