"""Single JSON configuration reader/writer used by core and GUI libraries.

Source runs retain project/config. Packaged runs seed a missing user config file
from bundled defaults. Corrupt existing user files are reported, never replaced.
"""
import json
import os
import tempfile
from pathlib import Path
from paths import CONFIG_DIRECTORY, get_config_directory

CONFIG_FOLDER = get_config_directory()


def _read_json(path):
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"Invalid JSON configuration file: {path}. Existing file was preserved.") from error


def _seed_missing(filename):
    """Copy bundled defaults only if the active file is absent (exclusive create)."""
    target = CONFIG_FOLDER / filename
    if target.exists():
        return target
    default = CONFIG_DIRECTORY / filename
    if target == default:
        return target
    # Validate the default before creating an editable file.
    content = _read_json(default)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(content, stream, indent=4)
            stream.write("\n")
    except FileExistsError:
        pass  # Another caller seeded it; never replace their data.
    return target


def load_json(filename):
    return _read_json(_seed_missing(filename))


def save_json(filename, data):
    """Write in the target directory and atomically replace the completed file."""
    path = CONFIG_FOLDER / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="." + path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=4)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_satellites():
    return load_json("satellites.json")


def save_satellites(data):
    save_json("satellites.json", data)


def load_antennas():
    return load_json("antennas.json")


def save_antennas(data):
    save_json("antennas.json", data)


def load_locations():
    return load_json("locations.json")


def save_locations(data):
    save_json("locations.json", data)
