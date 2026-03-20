from __future__ import annotations

import os
import sys
from pathlib import Path


def _path_from_env(name: str) -> Path | None:
    value = str(os.getenv(name, "")).strip()
    if not value:
        return None

    return Path(value).expanduser().resolve()


def _bundle_root() -> Path:
    override = _path_from_env("MOUSETRAINER_BUNDLE_ROOT")
    if override is not None:
        return override

    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))

    return Path(__file__).resolve().parents[2]


def _runtime_root() -> Path:
    override = _path_from_env("MOUSETRAINER_RUNTIME_ROOT")
    if override is not None:
        return override

    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


BUNDLE_ROOT = _bundle_root()
RUNTIME_ROOT = _runtime_root()

CONFIG_DIR = RUNTIME_ROOT / "config"
LOG_DIR = RUNTIME_ROOT / "logs"
DATA_DIR = RUNTIME_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
SESSION_DATA_DIR = DATA_DIR / "sessions"

for path in (CONFIG_DIR, LOG_DIR, RAW_DATA_DIR, SESSION_DATA_DIR):
    path.mkdir(parents=True, exist_ok=True)


def resolve_config_path(name: str) -> Path:
    candidates = [
        CONFIG_DIR / name,
        BUNDLE_ROOT / "config" / name,
        RUNTIME_ROOT / name,
        BUNDLE_ROOT / name,
    ]
    for path in candidates:
        if path.exists():
            return path

    return CONFIG_DIR / name


def resolve_firmware_dir() -> Path:
    candidates = [
        RUNTIME_ROOT / "firmware" / "behavioral_controller",
        BUNDLE_ROOT / "firmware" / "behavioral_controller",
        RUNTIME_ROOT / "behavioral_controller",
        BUNDLE_ROOT / "behavioral_controller",
    ]
    for path in candidates:
        if path.exists():
            return path

    return RUNTIME_ROOT / "firmware" / "behavioral_controller"
