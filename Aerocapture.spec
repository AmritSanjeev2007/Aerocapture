# -*- mode: python ; coding: utf-8 -*-

# Builds a single Aerocapture.exe with the textures and shaders bundled in. Run from the repository's root:
#
#     pyinstaller Aerocapture.spec
#
# The result is written to dist/Aerocapture.exe.

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[("calc/native.dll", "calc")],  # The C++ calculations: run "py -m calc.native" first.
    datas=[("assets", "assets"), ("shaders", "shaders"), ("calc/titan_height_density.csv", "calc")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Aerocapture",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Compressing the large OpenCV and numpy libraries would make every launch slower.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to True to see printed messages and errors in a terminal.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
