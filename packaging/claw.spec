# PyInstaller spec for the `claw` CLI binary.
#
# Build (one-file, default)::
#
#   uv pip install -e ".[dev]" pyinstaller
#   uv run pyinstaller packaging/claw.spec --clean --noconfirm
#   ./dist/claw --version
#
# Build (one-dir, faster startup)::
#
#   PYINSTALLER_ONEDIR=1 uv run pyinstaller packaging/claw.spec --clean --noconfirm
#   ./dist/claw/claw --version
#
# `torch` and `diffusers` are excluded — they're behind the `local` extra and
# would balloon the binary by hundreds of MB. If a user actually needs the
# local-inference path they should install via wheel + extras instead.

# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

ONEDIR = os.environ.get("PYINSTALLER_ONEDIR") == "1"

hidden = (
    collect_submodules("videoclaw")
    + collect_submodules("typer")
    + collect_submodules("pydantic")
    + collect_submodules("rich")
    + collect_submodules("litellm")
)

datas = collect_data_files("videoclaw") + collect_data_files("litellm")

# Bundle skills/ from the repo root into the binary as videoclaw/_skills/
# so `claw setup` can find them at sys._MEIPASS at runtime — same logical
# path as the wheel's `force-include` rule in pyproject.toml.
datas += [("../skills", "videoclaw/_skills")]

# Don't bundle the heavy local-inference path.
excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "diffusers",
    "transformers",
    "accelerate",
    "safetensors",
    "fastapi",
    "uvicorn",
]

a = Analysis(
    ["_entry.py"],
    pathex=["../src", "."],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEDIR:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="claw",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="claw",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="claw",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
    )
