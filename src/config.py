"""Configuration management for Moria MOD Creator."""

import os
import configparser
from pathlib import Path


# Color scheme options
COLOR_SCHEMES = ["Match Windows Theme", "Light Mode", "Dark Mode"]
DEFAULT_COLOR_SCHEME = "Match Windows Theme"


class _ConfigCache:
    """Internal class to hold config cache state without using globals."""
    config: configparser.ConfigParser | None = None
    mtime: float | None = None


_cache = _ConfigCache()


def get_appdata_dir() -> Path:
    r"""Get the application data directory in %APPDATA%\MoriaMODCreator."""
    appdata = os.environ.get('APPDATA')
    if not appdata:
        appdata = Path.home() / 'AppData' / 'Roaming'
    app_dir = Path(appdata) / 'MoriaMODCreator'
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_default_utilities_dir() -> Path:
    """Get the default utilities directory."""
    return get_appdata_dir() / 'utilities'


def get_default_output_dir() -> Path:
    """Get the default output directory."""
    return get_appdata_dir() / 'output'


def get_default_mymodfiles_dir() -> Path:
    """Get the default My MOD Files directory."""
    return get_appdata_dir() / 'mymodfiles'


def get_default_definitions_dir() -> Path:
    """Get the default MOD Definitions directory."""
    return get_appdata_dir() / 'definitions'


def get_buildings_dir() -> Path:
    """Get the buildings New Objects directory."""
    buildings_dir = get_appdata_dir() / 'New Objects' / 'Build'
    buildings_dir.mkdir(parents=True, exist_ok=True)
    return buildings_dir


def get_config_path() -> Path:
    """Get the path to the config.ini file."""
    return get_appdata_dir() / 'config.ini'


def config_exists() -> bool:
    """Check if the configuration file exists."""
    return get_config_path().exists()


def load_config() -> configparser.ConfigParser:
    """Load the configuration from config.ini with caching.

    The config is cached and only reloaded if the file has been modified.
    """
    config_path = get_config_path()

    # Check if we need to reload
    if config_path.exists():
        current_mtime = config_path.stat().st_mtime
        if _cache.config is not None and _cache.mtime == current_mtime:
            return _cache.config

        # Load and cache
        config = configparser.ConfigParser()
        config.read(config_path)
        _cache.config = config
        _cache.mtime = current_mtime
        return config
    else:
        # No config file, return empty config
        _cache.config = None
        _cache.mtime = None
        return configparser.ConfigParser()


def save_config(
    game_install_path: str,
    install_type: str,
    utilities_dir: str,
    output_dir: str,
    mymodfiles_dir: str,
    definitions_dir: str,
    color_scheme: str
) -> None:
    """Save the configuration to config.ini.

    Args:
        game_install_path: The path to the game installation.
        install_type: The type of installation (Steam, Epic Games, or Custom).
        utilities_dir: The path to the utilities directory.
        output_dir: The path to the output directory.
        mymodfiles_dir: The path to the My MOD Files directory.
        definitions_dir: The path to the MOD Definitions directory.
        color_scheme: The color scheme setting.
    """
    # Invalidate cache before saving
    _cache.config = None
    _cache.mtime = None

    config = configparser.ConfigParser()
    config['Game'] = {
        'install_path': game_install_path,
        'install_type': install_type
    }
    config['Directories'] = {
        'utilities': utilities_dir,
        'output': output_dir,
        'mymodfiles': mymodfiles_dir,
        'definitions': definitions_dir
    }
    config['Appearance'] = {
        'color_scheme': color_scheme
    }

    # Create directories if they don't exist
    Path(utilities_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(mymodfiles_dir).mkdir(parents=True, exist_ok=True)
    Path(definitions_dir).mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        config.write(f)


def get_game_install_path() -> str | None:
    """Get the game install path from config, or None if not configured."""
    config = load_config()
    if config.has_option('Game', 'install_path'):
        return config.get('Game', 'install_path')
    return None


def get_utilities_dir() -> Path:
    """Get the utilities directory from config, or default."""
    config = load_config()
    if config.has_option('Directories', 'utilities'):
        return Path(config.get('Directories', 'utilities'))
    return get_default_utilities_dir()


def get_output_dir() -> Path:
    """Get the output directory from config, or default."""
    config = load_config()
    if config.has_option('Directories', 'output'):
        return Path(config.get('Directories', 'output'))
    return get_default_output_dir()


def get_mymodfiles_dir() -> Path:
    """Get the My MOD Files directory from config, or default."""
    config = load_config()
    if config.has_option('Directories', 'mymodfiles'):
        return Path(config.get('Directories', 'mymodfiles'))
    return get_default_mymodfiles_dir()


def get_definitions_dir() -> Path:
    """Get the MOD Definitions directory from config, or default."""
    config = load_config()
    if config.has_option('Directories', 'definitions'):
        return Path(config.get('Directories', 'definitions'))
    return get_default_definitions_dir()


def get_color_scheme() -> str:
    """Get the color scheme from config, or default."""
    config = load_config()
    if config.has_option('Appearance', 'color_scheme'):
        return config.get('Appearance', 'color_scheme')
    return DEFAULT_COLOR_SCHEME


def apply_color_scheme(scheme: str) -> None:
    """Apply the color scheme to CustomTkinter.

    Args:
        scheme: The color scheme to apply.
    """
    import customtkinter as ctk

    if scheme == "Light Mode":
        ctk.set_appearance_mode("light")
    elif scheme == "Dark Mode":
        ctk.set_appearance_mode("dark")
    else:  # Match Windows Theme
        ctk.set_appearance_mode("system")


# Known game installation paths
STEAM_PATH = r"C:\Program Files (x86)\Steam\steamapps\common\The Lord of the Rings Return to Moria™"
EPIC_PATH = r"C:\Program Files\Epic Games\ReturnToMoria\Moria\Content\Paks"


def validate_config() -> list[str]:
    """Validate the current configuration and return a list of issues.

    Returns:
        List of validation issue messages. Empty if all valid.
    """
    issues = []

    # Check utilities directory
    utilities_dir = get_utilities_dir()
    if not utilities_dir.exists():
        issues.append(f"Utilities directory not found: {utilities_dir}")
    else:
        # Check for required executables
        required_utils = ['UAssetGUI.exe', 'retoc.exe']
        for util in required_utils:
            if not (utilities_dir / util).exists():
                issues.append(f"Required utility not found: {util}")

    # Check output directory
    output_dir = get_output_dir()
    if not output_dir.exists():
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            issues.append(f"Cannot create output directory: {e}")

    # Check mymodfiles directory
    mymodfiles_dir = get_default_mymodfiles_dir()
    if not mymodfiles_dir.exists():
        try:
            mymodfiles_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            issues.append(f"Cannot create mymodfiles directory: {e}")

    # Check definitions directory
    definitions_dir = get_definitions_dir()
    if not definitions_dir.exists():
        try:
            definitions_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            issues.append(f"Cannot create definitions directory: {e}")

    # Check game install path
    game_path = get_game_install_path()
    if game_path and not Path(game_path).exists():
        issues.append(f"Game installation path not found: {game_path}")

    return issues


def is_config_valid() -> bool:
    """Check if the configuration is valid.

    Returns:
        True if configuration is valid, False otherwise.
    """
    return len(validate_config()) == 0


def check_steam_path() -> bool:
    """Check if the Steam installation path exists."""
    return Path(STEAM_PATH).exists()


def check_epic_path() -> bool:
    """Check if the Epic Games installation path exists."""
    return Path(EPIC_PATH).exists()


def get_available_install_options() -> list[tuple[str, str]]:
    """Get a list of available installation options.

    Returns:
        List of tuples (display_name, path) for available options.
        Always includes Custom as the last option.
    """
    options = []

    if check_steam_path():
        options.append(("Steam", STEAM_PATH))

    if check_epic_path():
        options.append(("Epic Games", EPIC_PATH))

    options.append(("Custom", ""))

    return options
