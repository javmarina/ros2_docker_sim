# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from pathlib import Path

block_cipher = None

spec_dir = Path(globals().get("SPECPATH", os.getcwd())).resolve()
assets_dir = spec_dir / "assets"
icon_path = str(assets_dir / "app_icon.ico" if (assets_dir / "app_icon.ico").is_file() else assets_dir / "favicon.ico")

datas = [
    (str(assets_dir), 'assets'),
    (str(spec_dir / 'version.json'), '.'),
    (str(spec_dir / 'Dockerfile'), '.'),
]

hiddenimports = [
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'config_store',
    'docker_service',
    'embedded_icon',
    'robot_registry',
    'updater',
]

a = Analysis(
    ['launch_simulation.py'],
    pathex=[str(spec_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy', 'pandas', 'cv2'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ros2_sim_launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
