"""Shared utilities for import and conversion dialogs.

This module contains constants and helper functions used by both
import_dialog.py and json_convert_dialog.py to avoid code duplication.
"""

import configparser
import json
import logging
from collections import defaultdict
from pathlib import Path

from src.config import get_output_dir, get_appdata_dir

logger = logging.getLogger(__name__)

# File extensions to convert
UASSET_EXTENSIONS = {".uasset", ".umap"}

# Buildings cache filename
BUILDINGS_CACHE_FILENAME = "buildings_cache.ini"


def get_retoc_dir() -> Path:
    """Get the retoc output directory."""
    return get_output_dir() / "retoc"


def get_jsondata_dir() -> Path:
    """Get the JSON data output directory."""
    return get_output_dir() / "jsondata"


def get_buildings_cache_path() -> Path:
    """Get path to buildings INI cache file."""
    return get_appdata_dir() / "New Objects" / "Build" / BUILDINGS_CACHE_FILENAME


def get_files_to_convert() -> list[Path]:
    """Get list of uasset/umap files that need conversion."""
    retoc_dir = get_retoc_dir()
    if not retoc_dir.exists():
        logger.debug("Retoc directory does not exist: %s", retoc_dir)
        return []

    files = []
    for ext in UASSET_EXTENSIONS:
        files.extend(retoc_dir.rglob(f"*{ext}"))
    logger.debug("Found %d files to convert in %s", len(files), retoc_dir)
    return files


def check_jsondata_exists() -> bool:
    """Check if JSON data directory exists and has files."""
    jsondata_dir = get_jsondata_dir()
    if not jsondata_dir.exists():
        return False
    try:
        next(jsondata_dir.rglob("*.json"))
        return True
    except StopIteration:
        return False


def update_buildings_ini_from_json() -> tuple[bool, str]:
    """Scan DT_ConstructionRecipes.json and update the buildings INI cache.

    This reads the game's JSON file and adds values to the buildings INI file,
    ensuring no duplicates per section.

    Returns:
        Tuple of (success, message)
    """
    # Path to the DT_ConstructionRecipes.json
    recipes_path = (get_jsondata_dir() / 'Moria' / 'Content' / 'Tech' / 'Data'
                    / 'Building' / 'DT_ConstructionRecipes.json')

    if not recipes_path.exists():
        return (False, f"DT_ConstructionRecipes.json not found at {recipes_path}")

    try:
        # Load the JSON file
        with open(recipes_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Collect values from NameMap
        collected = defaultdict(set)
        name_map = data.get('NameMap', [])

        for name in name_map:
            # Skip system names
            if name.startswith('/') or name.startswith('$'):
                continue
            if name in ('ArrayProperty', 'BoolProperty', 'IntProperty', 'FloatProperty',
                        'StructProperty', 'ObjectProperty', 'EnumProperty', 'NameProperty',
                        'TextProperty', 'SoftObjectProperty', 'ByteProperty', 'StrProperty',
                        'None', 'Object', 'Class', 'Package', 'Default__DataTable',
                        'DataTable', 'ScriptStruct', 'BlueprintGeneratedClass', 'RowStruct',
                        'RowName', 'ArrayIndex', 'IsZero', 'PropertyTagFlags', 'Value'):
                continue

            # Categorize by pattern
            if name.startswith('E') and '::' in name:
                # Enum value
                enum_type = name.split('::')[0]
                collected[f'Enum_{enum_type}'].add(name)
            elif name.startswith('UI.') and 'Category' in name:
                collected['Tags'].add(name)
            elif name.startswith('Item.'):
                collected['Items'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Ore.'):
                collected['Ores'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Consumable.'):
                collected['Consumables'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Tool.'):
                collected['Tools'].add(name)
            elif name.startswith('Decoration'):
                collected['Decorations'].add(name)
            elif name.endswith('_Fragment'):
                collected['Fragments'].add(name)
                collected['UnlockRequiredFragments'].add(name)
            elif name.startswith('b') and len(name) > 1 and name[1].isupper():
                # Boolean property name - skip
                pass
            elif name.startswith('Mor'):
                # Moria type name - skip
                pass
            elif name.startswith('/Game/'):
                # Asset path
                collected['Actors'].add(name)
            elif '_' in name and not name.startswith('Default'):
                # Likely a construction/building name
                if name[0].isupper():
                    collected['Constructions'].add(name)
                    collected['ResultConstructions'].add(name)
            elif name and name[0].isupper() and not name.startswith('Default'):
                # Could be a construction name
                collected['Constructions'].add(name)

        # Load existing INI file if it exists
        cache_path = get_buildings_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        if cache_path.exists():
            config.read(cache_path, encoding='utf-8')

        # Merge new values with existing, ensuring no duplicates
        total_added = 0
        for section, new_values in collected.items():
            # Get existing values for this section
            existing_values = set()
            if config.has_section(section):
                existing_str = config.get(section, 'values', fallback='')
                existing_values = {v.strip() for v in existing_str.split('|') if v.strip()}
            else:
                config.add_section(section)

            # Merge and deduplicate
            merged = existing_values | new_values
            total_added += len(new_values - existing_values)

            # Save back as sorted, pipe-separated values
            config.set(section, 'values', '|'.join(sorted(merged)))

        # Write the updated INI file
        with open(cache_path, 'w', encoding='utf-8') as f:
            config.write(f)

        logger.info("Updated buildings cache: added %d new values to %d sections",
                     total_added, len(collected))
        return (True, f"Updated buildings cache with {total_added} new values")

    except json.JSONDecodeError as e:
        logger.error("Failed to parse DT_ConstructionRecipes.json: %s", e)
        return (False, f"JSON parse error: {e}")
    except OSError as e:
        logger.error("Error updating buildings INI: %s", e)
        return (False, f"Error: {e}")


# ---------------------------------------------------------------------------
# SEARCH & REPLACE HELPERS
# ---------------------------------------------------------------------------

# Search mode constants
SEARCH_PROPERTIES = "Properties"
SEARCH_VALUES = "Values"
SEARCH_BOTH = "Both"
SEARCH_MODES = [SEARCH_PROPERTIES, SEARCH_VALUES, SEARCH_BOTH]


def find_search_matches(
    pairs_text: list[tuple[str, str]],
    search_text: str,
    search_mode: str,
) -> list[int]:
    """Find indices of pairs matching *search_text* based on *search_mode*.

    Args:
        pairs_text: List of (property_name, value_text) string tuples.
        search_text: The substring to look for (case-insensitive).
        search_mode: One of SEARCH_PROPERTIES, SEARCH_VALUES, or SEARCH_BOTH.

    Returns:
        Sorted list of matching indices.
    """
    needle = search_text.lower()
    matches: list[int] = []
    for i, (prop, val) in enumerate(pairs_text):
        if search_mode == SEARCH_PROPERTIES and needle in prop.lower():
            matches.append(i)
        elif search_mode == SEARCH_VALUES and needle in val.lower():
            matches.append(i)
        elif search_mode == SEARCH_BOTH and (
            needle in prop.lower() or needle in val.lower()
        ):
            matches.append(i)
    return matches


def find_next_match(matches: list[int], current_index: int) -> int | None:
    """Return the next match index after *current_index*, wrapping around.

    Returns ``None`` when *matches* is empty.
    """
    if not matches:
        return None
    for idx in matches:
        if idx > current_index:
            return idx
    return matches[0]  # wrap around


def substring_replace(original: str, search_text: str, replace_text: str) -> str:
    """Case-insensitive substring replacement.

    Replaces every occurrence of *search_text* within *original* with
    *replace_text*, preserving the surrounding text.
    """
    if not search_text:
        return original
    # Use case-insensitive find-and-replace by working through the string
    lower_orig = original.lower()
    lower_search = search_text.lower()
    result: list[str] = []
    start = 0
    while True:
        pos = lower_orig.find(lower_search, start)
        if pos == -1:
            result.append(original[start:])
            break
        result.append(original[start:pos])
        result.append(replace_text)
        start = pos + len(search_text)
    return "".join(result)
