# ==============================================================
# neomom_plot.spec
# NeoMOM Plot GUI — PyInstaller one-file build  (WINDOWS)
#
# Repository layout:
#
#   plot_gui/
#   ├── linux/
#   │   └── neomom_plot.spec      <- Linux version
#   ├── windows/
#   │   └── neomom_plot.spec      <- this file
#   └── src/
#       ├── neomom_plot.py
#       ├── data_reader.py
#       ├── display_config.py
#       ├── pattern_math.py
#       ├── plot_3d.py
#       └── plot_panel.py
#
# Build command (from project root or scripts/):
#
#   & "$env:USERPROFILE\venvs\neomom_plot\Scripts\pyinstaller.exe" `
#       plot_gui\windows\neomom_plot.spec `
#       --distpath plot_gui\build\dist `
#       --workpath plot_gui\build\work
#
# Output:
#   plot_gui\build\dist\neomom_plot.exe    <- the executable
#
# Prerequisites:
#   - Run from project root
#   - venv at %USERPROFILE%\venvs\neomom_plot populated from
#     requirements_plot.txt
#   - tkinter included by default in official python.org installer
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# SPECPATH is set automatically by PyInstaller to the directory
# containing this .spec file (plot_gui/linux/)
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
# Bundle all .py helpers so cross-module imports work correctly
# inside the frozen one-file bundle.
# --------------------------------------------------------------

all_py = [
    (f, '.')
    for f in glob.glob(os.path.join(SRC, '*.py'))
]

# --------------------------------------------------------------
# ANALYSIS
# --------------------------------------------------------------

a = Analysis(
    [os.path.join(SRC, 'neomom_plot.py')],

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

        # matplotlib backends and 3D toolkit
        'matplotlib.backends.backend_tkagg',
        'mpl_toolkits.mplot3d',

        # pandas and numpy internals that PyInstaller may miss
        'pandas',
        'numpy',

        # Pillow tkinter bridge — Pillow is an indirect matplotlib
        # dependency; PyInstaller does not auto-detect this module
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
# a.binaries, a.zipfiles, a.datas included directly here
# (no COLLECT block) — this is what makes it a one-file build.
# --------------------------------------------------------------

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],

    name='neomom_plot',

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
