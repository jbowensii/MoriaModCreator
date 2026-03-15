"""Import helpers for scanning .def files and converting game assets to JSON.

This module provides helper functions used by the combined import dialog to:
- Scan .def files and includes.xml for game file paths to import
- Convert .uasset files to JSON using UAssetGUI

The actual import UI is in combined_import_dialog.py.
"""

import json
import logging
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from src.config import get_appdata_dir


logger = logging.getLogger(__name__)


def scan_def_files_for_mod_paths() -> set[str]:
    """Scan all .def files in Definitions directory and extract mod file paths.

    Returns:
        Set of unique file paths (as they appear in the .def files, with .json extension)
    """
    definitions_dir = get_appdata_dir() / "Definitions"
    mod_paths = set()

    if not definitions_dir.exists():
        logger.warning("Definitions directory does not exist: %s", definitions_dir)
        return mod_paths

    # Find all .def files
    for def_file in definitions_dir.rglob("*.def"):
        try:
            tree = ET.parse(def_file)
            root = tree.getroot()

            # Find all <mod file="..."> elements
            for mod_element in root.findall('.//mod'):
                file_attr = mod_element.get('file', '').strip()
                if file_attr:
                    mod_paths.add(file_attr)

        except ET.ParseError as e:
            logger.warning("Failed to parse %s: %s", def_file.name, e)
        except OSError as e:
            logger.warning("Error reading %s: %s", def_file.name, e)

    logger.info("Found %d unique mod file paths from .def files", len(mod_paths))
    return mod_paths


def scan_includes_xml_for_mod_paths() -> set[str]:
    """Scan includes.xml in Definitions directory and extract mod file paths.

    The includes.xml file uses the same format as .def files with <mod file="..."> elements.
    Files listed here may or may not exist in the game, so callers should handle missing files.

    Returns:
        Set of unique file paths (as they appear in includes.xml, with .json extension)
    """
    definitions_dir = get_appdata_dir() / "Definitions"
    includes_file = definitions_dir / "includes.xml"
    mod_paths = set()

    if not includes_file.exists():
        logger.debug("includes.xml does not exist: %s", includes_file)
        return mod_paths

    try:
        tree = ET.parse(includes_file)
        root = tree.getroot()

        # Find all <mod file="..."> elements
        for mod_element in root.findall('.//mod'):
            file_attr = mod_element.get('file', '').strip()
            if file_attr:
                mod_paths.add(file_attr)

        logger.info("Found %d mod file paths from includes.xml", len(mod_paths))

    except ET.ParseError as e:
        logger.warning("Failed to parse includes.xml: %s", e)
    except OSError as e:
        logger.warning("Error reading includes.xml: %s", e)

    return mod_paths


def convert_json_path_to_uasset(json_path: str) -> str:
    """Convert a .json mod path to the corresponding .uasset game file path.

    Args:
        json_path: Path like "Moria\\Content\\Tech\\Data\\Building\\DT_Items.json"

    Returns:
        Path like "Moria\\Content\\Tech\\Data\\Building\\DT_Items.uasset"
    """
    # Normalize path separators
    normalized = json_path.replace('/', '\\')

    # Change extension from .json to .uasset
    if normalized.lower().endswith('.json'):
        normalized = normalized[:-5] + '.uasset'

    return normalized


# Files that must always be imported — string tables for display names, plus
# core data tables needed by the Constructions view even without .def files.
ALWAYS_IMPORT_FILES = [
    # String tables (display names for UI)
    r"\Moria\Content\Tech\Data\StringTables\Architecture.json",
    r"\Moria\Content\Tech\Data\StringTables\Interactables.json",
    r"\Moria\Content\Tech\Data\StringTables\Items.json",
    # Core data tables for Constructions view
    r"\Moria\Content\Tech\Data\Building\DT_Constructions.json",
    r"\Moria\Content\Tech\Data\Building\DT_ConstructionRecipes.json",
    r"\Moria\Content\Tech\Data\Items\DT_Items.json",
    r"\Moria\Content\Tech\Data\Items\DT_ItemRecipes.json",
    r"\Moria\Content\Tech\Data\Items\DT_Weapons.json",
    r"\Moria\Content\Tech\Data\Items\DT_Armor.json",
    r"\Moria\Content\Tech\Data\Items\DT_Tools.json",
    r"\Moria\Content\Tech\Data\GameWorld\DT_Moria_Flora.json",
    r"\Moria\Content\Character\AI\DT_Loot.json",
]


def get_game_file_paths_to_import() -> list[str]:
    """Get the list of game file paths that need to be imported.

    Scans all .def files and includes.xml, adds always-import files,
    and returns the corresponding .uasset paths.

    Returns:
        List of unique .uasset file paths relative to game directory
    """
    # Get paths from .def files
    mod_paths = scan_def_files_for_mod_paths()

    # Also get paths from includes.xml (these may or may not exist in game)
    includes_paths = scan_includes_xml_for_mod_paths()
    mod_paths.update(includes_paths)

    # Always import critical string table files
    mod_paths.update(ALWAYS_IMPORT_FILES)

    # Convert each .json path to .uasset
    uasset_paths = set()
    for json_path in mod_paths:
        uasset_path = convert_json_path_to_uasset(json_path)
        uasset_paths.add(uasset_path)

    return sorted(uasset_paths)


def convert_file_to_json(
    uassetgui_path: Path,
    source_file: Path,
    retoc_dir: Path,
    jsondata_dir: Path,
) -> tuple[bool, str]:
    """Convert a single uasset file to JSON.

    Args:
        uassetgui_path: Path to UAssetGUI.exe
        source_file: Path to the source uasset file
        retoc_dir: Base retoc directory
        jsondata_dir: Base JSON output directory

    Returns:
        Tuple of (success, message)
    """
    try:
        # Calculate relative path and destination
        rel_path = source_file.relative_to(retoc_dir)
        dest_file = jsondata_dir / rel_path.with_suffix(".json")

        # Create destination directory if needed
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Skip if already converted
        if dest_file.exists():
            return (True, f"Skipped (exists): {rel_path}")

        # Run UAssetGUI tojson command
        cmd = [
            str(uassetgui_path),
            "tojson",
            str(source_file),
            str(dest_file),
            "VER_UE4_27"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=60,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )

        if result.returncode == 0 and dest_file.exists():
            return (True, f"Converted: {rel_path}")
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        return (False, f"Failed: {rel_path} - {error_msg}")

    except subprocess.TimeoutExpired:
        return (False, f"Timeout: {source_file.name}")
    except OSError as e:
        return (False, f"Error: {source_file.name} - {str(e)}")


def strip_duplicate_rows(
    secrets_json_path: Path,
    game_json_path: Path,
) -> tuple[int, int]:
    """Remove DataTable rows from secrets JSON that exist in the game JSON.

    Matches rows by their Name field. Modifies the secrets file in-place.

    Args:
        secrets_json_path: Path to the secrets mod JSON file
        game_json_path: Path to the game's version of the same JSON file

    Returns:
        Tuple of (rows_removed, rows_remaining)
    """
    try:
        with open(secrets_json_path, 'r', encoding='utf-8') as f:
            secrets_data = json.load(f)
        with open(game_json_path, 'r', encoding='utf-8') as f:
            game_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load JSON for comparison: %s", e)
        return (0, 0)

    exports = secrets_data.get("Exports", [])
    game_exports = game_data.get("Exports", [])
    total_removed = 0
    total_remaining = 0

    for idx, export in enumerate(exports):
        table = export.get("Table")
        if not table or "Data" not in table:
            continue

        # Find matching game export by index
        game_export = game_exports[idx] if idx < len(game_exports) else None
        if not game_export:
            continue
        game_table = game_export.get("Table")
        if not game_table or "Data" not in game_table:
            continue

        # Build set of game row names
        game_row_names = {
            row.get("Name") for row in game_table["Data"]
            if isinstance(row, dict) and "Name" in row
        }

        # Filter secrets rows — keep only those NOT in the game
        original_rows = table["Data"]
        filtered_rows = [
            row for row in original_rows
            if not isinstance(row, dict) or row.get("Name") not in game_row_names
        ]

        removed = len(original_rows) - len(filtered_rows)
        total_removed += removed
        total_remaining += len(filtered_rows)
        table["Data"] = filtered_rows

    if total_removed > 0:
        with open(secrets_json_path, 'w', encoding='utf-8') as f:
            json.dump(secrets_data, f, indent=2, ensure_ascii=False)

    return (total_removed, total_remaining)


def merge_secrets_rows(
    game_json_path: Path,
    secrets_json_path: Path,
    dest_json_path: Path,
) -> int:
    """Merge new secrets rows into a game JSON file.

    For DataTable files: appends rows from secrets that don't exist in game.
    For non-DataTable files: copies secrets file as-is.

    Args:
        game_json_path: Path to the game's JSON file (already in build dir)
        secrets_json_path: Path to the secrets mod JSON file (new rows only)
        dest_json_path: Path to write the merged output

    Returns:
        Number of rows merged (0 if non-DataTable or file copy)
    """
    try:
        with open(game_json_path, 'r', encoding='utf-8') as f:
            game_data = json.load(f)
        with open(secrets_json_path, 'r', encoding='utf-8') as f:
            secrets_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load JSON for merge: %s", e)
        return 0

    game_exports = game_data.get("Exports", [])
    secrets_exports = secrets_data.get("Exports", [])
    total_merged = 0

    for idx, secrets_export in enumerate(secrets_exports):
        secrets_table = secrets_export.get("Table")
        if not secrets_table or "Data" not in secrets_table:
            continue

        # Find matching game export by index
        game_export = game_exports[idx] if idx < len(game_exports) else None
        if not game_export:
            continue
        game_table = game_export.get("Table")
        if not game_table or "Data" not in game_table:
            continue

        # Build set of existing game row names to avoid duplicates
        existing_names = {
            row.get("Name") for row in game_table["Data"]
            if isinstance(row, dict) and "Name" in row
        }

        # Append secrets rows that don't already exist in game
        for row in secrets_table["Data"]:
            if isinstance(row, dict) and row.get("Name") not in existing_names:
                game_table["Data"].append(row)
                total_merged += 1

    # Merge secrets NameMap entries into game NameMap
    if total_merged > 0:
        game_namemap = game_data.get("NameMap")
        secrets_namemap = secrets_data.get("NameMap")
        if isinstance(game_namemap, list) and isinstance(secrets_namemap, list):
            existing = set(game_namemap)
            for name in secrets_namemap:
                if name not in existing:
                    game_namemap.append(name)
                    existing.add(name)

        # Also sync any FNames from the merged row data itself
        from src.build_manager import BuildManager  # noqa: C0415
        BuildManager._sync_namemap(game_data)

    # Write merged result (game data with appended secrets rows)
    dest_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_json_path, 'w', encoding='utf-8') as f:
        json.dump(game_data, f, indent=2, ensure_ascii=False)

    return total_merged
