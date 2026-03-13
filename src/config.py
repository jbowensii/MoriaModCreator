"""Configuration management for Moria MOD Creator."""

import logging
import os
import configparser
from pathlib import Path

logger = logging.getLogger(__name__)


# Color scheme options
COLOR_SCHEMES = ["Match Windows Theme", "Light Mode", "Dark Mode"]
DEFAULT_COLOR_SCHEME = "Match Windows Theme"


class _ConfigCache:  # pylint: disable=too-few-public-methods
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


def get_prebuilt_modfiles_dir() -> Path:
    """Get the prebuilt modfiles directory for novice mode."""
    return get_appdata_dir() / 'prebuilt modfiles'


def get_default_definitions_dir() -> Path:
    """Get the default MOD Definitions directory."""
    return get_appdata_dir() / 'definitions'


def get_default_final_destination_dir() -> Path:
    """Get the default Final Mod(s) Destination directory (user's Downloads)."""
    return Path.home() / 'Downloads'


def get_buildings_dir() -> Path:
    """Get the buildings New Objects directory."""
    buildings_dir = get_appdata_dir() / 'New Objects' / 'Build'
    buildings_dir.mkdir(parents=True, exist_ok=True)
    return buildings_dir


def get_constructions_dir() -> Path:
    """Get the Constructions directory for user construction packs."""
    constructions_dir = get_appdata_dir() / 'Constructions'
    constructions_dir.mkdir(parents=True, exist_ok=True)
    return constructions_dir


def get_default_changesecrets_dir() -> Path:
    """Get the default Change Secrets directory for secrets change sets."""
    return get_appdata_dir() / 'changesecrets'


def get_default_changeconstructions_dir() -> Path:
    """Get the default Change Constructions directory for construction change sets."""
    return get_appdata_dir() / 'changeconstructions'


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
        config.read(config_path, encoding='utf-8')
        _cache.config = config
        _cache.mtime = current_mtime
        return config

    # No config file, return empty config
    _cache.config = None
    _cache.mtime = None
    return configparser.ConfigParser()


def save_config(  # pylint: disable=too-many-arguments
    game_install_path: str,
    install_type: str,
    utilities_dir: str,
    output_dir: str,
    mymodfiles_dir: str,
    definitions_dir: str,
    color_scheme: str,
    max_workers: int = 1,
    debug: bool = False,
    final_destination_dir: str = ""
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
        max_workers: Number of parallel processes for JSON conversion.
        debug: Enable debug mode for verbose logging.
        final_destination_dir: The path where final built mods are placed.
    """
    # Invalidate cache before saving
    _cache.config = None
    _cache.mtime = None

    # Read existing config to preserve manually-set sections
    config = configparser.ConfigParser()
    config_path = get_config_path()
    if config_path.exists():
        config.read(config_path, encoding='utf-8')

    config['Game'] = {
        'install_path': game_install_path,
        'install_type': install_type
    }
    config['Directories'] = {
        'utilities': utilities_dir,
        'output': output_dir,
        'mymodfiles': mymodfiles_dir,
        'definitions': definitions_dir,
        'final_destination': final_destination_dir or str(get_default_final_destination_dir())
    }
    config['Appearance'] = {
        'color_scheme': color_scheme
    }
    config['Performance'] = {
        'max_workers': str(max_workers)
    }
    config['Debug'] = {
        'debug': str(debug).lower()
    }

    # Create directories if they don't exist
    Path(utilities_dir).mkdir(parents=True, exist_ok=True)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    Path(mymodfiles_dir).mkdir(parents=True, exist_ok=True)
    Path(definitions_dir).mkdir(parents=True, exist_ok=True)
    dest = final_destination_dir or str(get_default_final_destination_dir())
    Path(dest).mkdir(parents=True, exist_ok=True)
    # Also ensure Constructions directory exists
    get_constructions_dir()

    with open(config_path, 'w', encoding='utf-8') as f:
        config.write(f)

    logger.debug("Config saved: install_type=%s, color=%s, workers=%s, debug=%s",
                 install_type, color_scheme, max_workers, debug)


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


def get_final_destination_dir() -> Path:
    """Get the Final Mod(s) Destination directory from config, or default (Downloads)."""
    config = load_config()
    if config.has_option('Directories', 'final_destination'):
        return Path(config.get('Directories', 'final_destination'))
    return get_default_final_destination_dir()


def get_color_scheme() -> str:
    """Get the color scheme from config, or default."""
    config = load_config()
    if config.has_option('Appearance', 'color_scheme'):
        return config.get('Appearance', 'color_scheme')
    return DEFAULT_COLOR_SCHEME


def get_max_workers() -> int:
    """Get the max workers setting from config, or default of 1."""
    config = load_config()
    if config.has_option('Performance', 'max_workers'):
        try:
            return int(config.get('Performance', 'max_workers'))
        except ValueError:
            return 1
    return 1


def get_debug_mode() -> bool:
    """Get the debug mode flag from config, or default False."""
    config = load_config()
    if config.has_option('Debug', 'debug'):
        return config.get('Debug', 'debug').lower() in ('true', '1', 'yes')
    return False


def get_generate_builders_pack() -> bool:
    """Get the GenerateBuildersPack flag from config, or default False.

    This is a manually-set flag in [Advanced Builders Pack] section.
    No UI interface — edit config.ini directly to enable.
    """
    config = load_config()
    if config.has_option('Advanced Builders Pack', 'generatebuilderspack'):
        return config.get('Advanced Builders Pack',
                          'generatebuilderspack').lower() in ('true', '1', 'yes')
    return False


def get_constructions_json_dir() -> Path | None:
    """Get the directory containing construction JSON files from config.

    Returns:
        Path to the directory, or None if not configured.
    """
    config = load_config()
    if config.has_option('Directories', 'constructions_json'):
        path_str = config.get('Directories', 'constructions_json')
        if path_str:
            return Path(path_str)
    return None


def set_constructions_json_dir(path: str | Path) -> None:
    """Save the constructions JSON directory to config.

    Args:
        path: The directory path containing DT_Constructions.json
              and DT_ConstructionRecipes.json files.
    """
    config = load_config()

    # Ensure the Directories section exists
    if not config.has_section('Directories'):
        config.add_section('Directories')

    config.set('Directories', 'constructions_json', str(path))

    # Write updated config
    config_path = get_config_path()
    with open(config_path, 'w', encoding='utf-8') as f:
        config.write(f)

    # Invalidate cache
    _cache.config = None
    _cache.mtime = None


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
EPIC_PATH = r"C:\Program Files\Epic Games\ReturnToMoria"


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

    if issues:
        for issue in issues:
            logger.warning("Config validation: %s", issue)
    else:
        logger.debug("Config validation passed")

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
