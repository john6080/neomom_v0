# ==============================================================
# neomom_plot.spec
# NeoMOM Plot GUI — PyInstaller one-file build (LINUX)
#
# Repository layout:
#
#   neomom_plot/
#   ├── linux/
#   │   └── neomom_plot.spec      <- this file
#   ├── windows/
#   │   └── neomom_plot.spec      <- Windows version
#   └── src/
#       ├── neomom_plot.py
#       ├── data_reader.py
#       ├── display_config.py
#       ├── pattern_math.py
#       ├── plot_3d.py
#       └── plot_panel.py
#
# Build command (from project root):
#
#   $HOME/venvs/neomom_plot/bin/pyinstaller \
#       neomom_plot/linux/neomom_plot.spec \
#       --distpath neomom_plot/build/dist \
#       --workpath neomom_plot/build/work
#
# Output:
#   neomom_plot/build/dist/neomom_plot    <- the executable
#
# Note on cartopy:
#   cartopy >= 0.22 provides binary wheels — pip install cartopy
#   Submodules must be listed explicitly in hiddenimports because
#   cartopy uses dynamic/conditional imports that PyInstaller
#   static analysis cannot detect.
# ==============================================================

import os
import glob

block_cipher = None

# --------------------------------------------------------------
# PATHS
# SPECPATH is set by PyInstaller to the directory containing
# this .spec file (neomom_plot/linux/)
# --------------------------------------------------------------

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

# --------------------------------------------------------------
# DATA FILES
# Bundle all .py helpers for cross-module imports in frozen bundle
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
        # tkinter submodules
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.font',

        # matplotlib backends and 3D toolkit
        'matplotlib.backends.backend_tkagg',
        'mpl_toolkits.mplot3d',

        # numpy and pandas
        'numpy',
        'pandas',

        # Pillow tkinter bridge
        'PIL._tkinter_finder',

        # cartopy — map overlay feature
        # Submodules listed explicitly: cartopy uses dynamic imports
        # that PyInstaller static analysis cannot detect.
        'cartopy',
        'cartopy.crs',
        'cartopy.feature',
        'cartopy.io',
        'cartopy.io.shapereader',
        'cartopy.mpl',
        'cartopy.mpl.geoaxes',
        'cartopy.mpl.ticker',
        'cartopy.mpl.gridliner',

        # pyproj — coordinate projections (cartopy dependency)
        'pyproj',
        'pyproj.transformer',
        'pyproj._transformer',
        'pyproj.crs',
        'pyproj._crs',

        # shapely — geometry (cartopy dependency)
        'shapely',
        'shapely.geometry',
        'shapely.ops',
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

    name='neomom_plot',

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
