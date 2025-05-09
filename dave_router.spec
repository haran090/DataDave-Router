# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['dave_router.py'],
    pathex=['/Users/haran/Library/CloudStorage/OneDrive-NVIDIACorporation(2)/Documents/DataAnalysisApp/dave-router/venv/lib/python3.13/site-packages'],
    binaries=[],
    datas=[],
    hiddenimports=['nicegui', 'websocket', 'sqlalchemy', 'pymysql'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='dave_router',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
