# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd()
ICON_FILE = ROOT / "build" / "icon" / "mouse.ico"

datas = [
    (str(ROOT / "config"), "config"),
    (str(ROOT / "firmware"), "firmware"),
]

hiddenimports = (
    collect_submodules("googleapiclient")
    + collect_submodules("gspread")
    + collect_submodules("pygame")
    + collect_submodules("pynput")
)


analysis = Analysis(
    ["console_launcher.py"],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="MouseTrainerClient",
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MouseTrainerClient",
)
