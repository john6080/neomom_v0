# ==============================================================
# neomom_current.spec
# NeoMOM Current Distribution Viewer — PyInstaller one-file build (WINDOWS)
#
# Repository layout:
#
#   neomom_current/
#   ├── linux/
#   │   └── neomom_current.spec      <- Linux version
#   ├── windows/
#   │   └── neomom_current.spec      <- this file
#   └── src/
#       └── neomom_current.py
#
# Build command (from project root):
#
#   & "$env:USERPROFILE\venvs\neomom_plot\Scripts\pyinstaller.exe" `
#       neomom_current\windows\neomom_current.spec `
#       --distpath neomom_current\build\dist `
#       --workpath neomom_current\build\work
#
# Output:
#   neomom_current\build\dist\neomom_current.exe    <- the executable
#
# Uses neomom_plot venv — no separate venv needed.
# ==============================================================

import os
import glob

block_cipher = None

SRC = os.path.abspath(os.path.join(SPECPATH, '..', 'src'))

all_py = [
    (f, '.')
    for f in glob.glob(os.path.join(SRC, '*.py'))
]

a = Analysis(
    [os.path.join(SRC, 'neomom_current.py')],

    pathex=[SRC],

    binaries=[],

    datas=all_py,

    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'tkinter.font',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends._backend_tk',
        'matplotlib.figure',
        'mpl_toolkits.mplot3d',
        'mpl_toolkits.mplot3d.art3d',
        'numpy',
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

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

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

    console=False,

    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
