"""Application resources and writable configuration paths.

Resource constants retain their historical meaning. Use get_config_directory()
for editable config, never assume a packaged application's resources are writable.
Path helpers do not create directories or migrate files on import.
"""
from pathlib import Path
import os
import sys


def is_packaged():
    return bool(getattr(sys, "frozen", False))


def get_project_root():
    """Resource root in a source checkout or PyInstaller bundle."""
    if is_packaged():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def get_user_data_directory():
    """Writable per-user application data; no directory is created here."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MEOSAR Scheduler"
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "MEOSAR Scheduler"
    configured = os.environ.get("XDG_DATA_HOME", "")
    base = Path(configured) if configured and Path(configured).is_absolute() else Path.home() / ".local" / "share"
    return base / "MEOSAR Scheduler"


def get_config_directory():
    """Source: existing project config. Packaged: editable user config."""
    configured = os.environ.get("MEOSAR_CONFIG_DIR")
    if configured:
        directory = Path(configured).expanduser()
        if not directory.is_absolute():
            raise ValueError("MEOSAR_CONFIG_DIR must be an absolute directory path.")
        return directory
    if is_packaged():
        return get_user_data_directory() / "config"
    return get_project_root() / "config"


PROJECT_ROOT = get_project_root()
# Backward-compatible RESOURCE constants. These are not writable-data promises.
CONFIG_DIRECTORY = PROJECT_ROOT / "config"
ASSETS_DIRECTORY = PROJECT_ROOT / "assets"
SATELLITES_CONFIG = CONFIG_DIRECTORY / "satellites.json"
# New explicit writable/active configuration location.
ACTIVE_CONFIG_DIRECTORY = get_config_directory()
