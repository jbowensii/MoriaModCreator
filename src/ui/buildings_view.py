"""Buildings view for creating and editing construction objects from .def files.

This module provides the UI for the Buildings/Constructions tab, allowing users to:
- Browse and select .def files containing construction definitions
- View and edit construction recipe properties (materials, placement rules, etc.)
- View and edit construction definition properties (display name, actor, tags)
- Create new constructions from scratch or import from existing .def files
- Manage material requirements with autocomplete support

The module handles parsing of UAssetAPI JSON structures embedded in XML .def files,
extracting fields for editing, and rebuilding valid JSON for saving.

Classes:
    FieldTooltip: Hover tooltip for form field labels
    AutocompleteEntry: Entry widget with dropdown autocomplete for comma-separated values
    BuildingsView: Main view frame for building/construction management

Key Functions:
    parse_def_file: Parse .def XML and extract recipe/construction JSON
    extract_recipe_fields: Convert UAssetAPI recipe JSON to editable dict
    extract_construction_fields: Convert UAssetAPI construction JSON to editable dict
"""

import configparser
import json
import logging
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from src.config import get_appdata_dir, get_buildings_dir, get_constructions_dir

logger = logging.getLogger(__name__)


# =============================================================================
# JSON TYPE CONSTANTS
# =============================================================================
# UAssetAPI property type strings used when building JSON structures.
# These are the $type values that identify how each property should be
# serialized in the Unreal Engine data table format.

ENUM_TYPE = "UAssetAPI.PropertyTypes.Structs.EnumPropertyData, UAssetAPI"
BOOL_TYPE = "UAssetAPI.PropertyTypes.Structs.BoolPropertyData, UAssetAPI"
TEXT_TYPE = "UAssetAPI.PropertyTypes.Structs.TextPropertyData, UAssetAPI"
ARRAY_TYPE = "UAssetAPI.PropertyTypes.Structs.ArrayPropertyData, UAssetAPI"
STRUCT_TYPE = "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI"
SOFT_OBJ_TYPE = "UAssetAPI.PropertyTypes.Objects.SoftObjectPropertyData, UAssetAPI"


# =============================================================================
# FIELD DESCRIPTIONS - Hover tooltips for construction form fields
# =============================================================================
# These descriptions appear when users hover over field labels in the form.
# They explain what each field does in the context of Moria's construction system.

FIELD_DESCRIPTIONS = {
    # Basic Information
    "BuildingName": "Internal name used as the row key in data tables. Must be unique.",
    "Title": "Human-readable title shown in the mod description.",
    "Author": "Creator of this construction definition.",
    "DefDescription": "Description text shown in the mod info.",

    # Construction Recipe Fields
    "ResultConstructionHandle": "Reference to the construction definition row this recipe produces.",
    "BuildProcess": "DualMode: Placement then construction. SingleMode: Instant placement.",
    "PlacementType": "SnapGrid: Aligns to grid. FreePlacement: Can place anywhere.",
    "LocationRequirement": ("Where this can be built. Base: Settlement area. "
                            "Anywhere: No restriction. Underground: Below surface only."),
    "FoundationRule": "Never: No foundation. Always: Requires foundation. Optional: Player choice.",
    "MonumentType": "Monument size category. Affects settlement value and placement rules.",

    # Boolean Fields - Recipe
    "bOnWall": "Can be placed on vertical wall surfaces.",
    "bOnFloor": "Can be placed on floor/ground surfaces.",
    "bPlaceOnWater": "Can be placed on water surfaces.",
    "bOverrideRotation": "Uses custom rotation logic instead of standard snap.",
    "bAllowRefunds": "Materials are returned when demolished.",
    "bAutoFoundation": "Automatically creates foundation when placed.",
    "bInheritAutoFoundationStability": "Inherits stability from auto-generated foundation.",
    "bOnlyOnVoxel": "Can only be placed on terrain voxels, not other constructions.",
    "bIsBlockedByNearbySettlementStones": "Cannot place near settlement boundary stones.",
    "bIsBlockedByNearbyRavenConstructions": "Cannot place near raven/enemy constructions.",
    "bHasSandboxRequirementsOverride": "Uses different requirements in sandbox mode.",
    "bHasSandboxUnlockOverride": "Uses different unlock conditions in sandbox mode.",

    # Numeric Fields
    "MaxAllowedPenetrationDepth": "How deep into terrain this can clip. -1 = unlimited.",
    "RequireNearbyRadius": "Distance (in cm) to required nearby objects.",
    "CameraStateOverridePriority": "Priority for camera state when placing. Higher = more priority.",

    # Unlock Fields
    "Recipe_EnabledState": "Live: Active in game. Disabled: Hidden. Testing: Dev only.",
    "DefaultRequiredConstructions": "Constructions that must exist before this can be built.",
    "DefaultUnlocks_UnlockType": "How this recipe is unlocked. Manual: Player discovers. Automatic: Always available.",
    "DefaultUnlocks_NumFragments": "Number of fragments needed to unlock (if fragment-based).",
    "DefaultUnlocks_RequiredItems": "Items player must have obtained to unlock this recipe.",
    "DefaultUnlocks_RequiredConstructions": "Constructions that must be built to unlock this recipe.",
    "DefaultUnlocks_RequiredFragments": "Specific fragment items needed to unlock.",

    # Sandbox Unlock Fields
    "SandboxUnlocks_UnlockType": "Unlock method in sandbox/creative mode.",
    "SandboxUnlocks_NumFragments": "Fragments needed in sandbox mode.",
    "SandboxUnlocks_RequiredItems": "Items required in sandbox mode.",
    "SandboxUnlocks_RequiredConstructions": "Constructions required in sandbox mode.",

    # Construction Definition Fields
    "DisplayName": "Name shown to players in the build menu and UI.",
    "Description": "Tooltip description shown when hovering over this in build menu.",
    "Actor": "Blueprint actor class path that is spawned when this is built.",
    "BackwardCompatibilityActors": "Legacy actor paths for save game compatibility.",
    "Icon": "Index reference to the icon texture in the icon atlas.",
    "Tags": "Category tag for organizing in the build menu (e.g., UI.Construction.Category.Advanced.Walls).",
    "Construction_EnabledState": "Live: Active. Disabled: Hidden from menus. Testing: Dev only.",

    # Materials
    "Materials": "Resources consumed when building this construction.",
    "Material": "Item type required (e.g., Item.Wood, Item.Stone).",
    "Amount": "Quantity of this material needed.",

    # Sandbox Fields
    "SandboxUnlocks_RequiredFragments": "Specific fragment items needed to unlock in sandbox mode.",
    "SandboxRequiredConstructions": "Constructions required before building in sandbox mode.",
    "SandboxRequiredMaterials": "Resources consumed when building in sandbox mode.",

    # Row Identity
    "Construction_Name": "Internal row name in DT_Constructions. Must match recipe's ResultConstructionHandle.",
    "Name": "Internal row name in DT_ConstructionRecipes. Must be unique.",
}


# =============================================================================
# UI HELPER CLASSES
# =============================================================================

class FieldTooltip:
    """Hover tooltip for form field labels.

    Creates a delayed popup tooltip when the user hovers over a widget.
    Used to provide contextual help for construction form fields.

    Args:
        widget: The widget to attach the tooltip to
        text: The tooltip text to display
        delay: Milliseconds to wait before showing tooltip (default 400ms)
    """

    def __init__(self, widget, text: str, delay: int = 400):
        """Initialize the tooltip and bind hover events."""
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.scheduled_id = None

        widget.bind("<Enter>", self._on_enter)
        widget.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        self.scheduled_id = self.widget.after(self.delay, self._show_tooltip)

    def _on_leave(self, event):
        if self.scheduled_id:
            self.widget.after_cancel(self.scheduled_id)
            self.scheduled_id = None
        self._hide_tooltip()

    def _show_tooltip(self):
        if self.tooltip_window:
            return

        x, y, _, height = self.widget.bbox("insert") if hasattr(self.widget, 'bbox') else (0, 0, 0, 0)
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + height + 20

        self.tooltip_window = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        # Create tooltip frame with border
        frame = ctk.CTkFrame(tw, fg_color=("#FFFDD0", "#2d2d2d"), corner_radius=6)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            font=ctk.CTkFont(size=12),
            text_color=("#333333", "#e0e0e0"),
            wraplength=300,
            justify="left"
        )
        label.pack(padx=8, pady=6)

    def _hide_tooltip(self):
        """Destroy the tooltip window if it exists."""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


# =============================================================================
# DEFAULT DROPDOWN OPTIONS
# =============================================================================
# These are fallback values for dropdown fields. The actual options are
# extended by scanning existing .def files and DT_ConstructionRecipes.json
# to include all values found in the game data.

DEFAULT_BUILD_PROCESS = ["EBuildProcess::DualMode", "EBuildProcess::SingleMode"]
DEFAULT_LOCATION = [
    "EConstructionLocation::Base",
    "EConstructionLocation::Anywhere",
    "EConstructionLocation::Underground",
]
DEFAULT_PLACEMENT = ["EPlacementType::SnapGrid", "EPlacementType::FreePlacement"]
DEFAULT_FOUNDATION_RULE = ["EFoundationRule::Never", "EFoundationRule::Always", "EFoundationRule::Optional"]
DEFAULT_MONUMENT_TYPE = ["EMonumentType::None", "EMonumentType::Small", "EMonumentType::Medium", "EMonumentType::Large"]
DEFAULT_ENABLED_STATE = ["ERowEnabledState::Live", "ERowEnabledState::Disabled", "ERowEnabledState::Testing"]
DEFAULT_UNLOCK_TYPE = [
    "EMorRecipeUnlockType::Manual",
    "EMorRecipeUnlockType::DiscoverDependencies",
    "EMorRecipeUnlockType::Automatic",
    "EMorRecipeUnlockType::Never",
]

# Cache filename for storing scanned dropdown options
CACHE_FILENAME = "buildings_cache.ini"


# =============================================================================
# JSON SCANNING AND CACHING FUNCTIONS
# =============================================================================


def _scan_construction_recipes_json() -> dict:
    """Scan DT_ConstructionRecipes.json for construction names and other values.

    Scans both output/jsondata and Secrets Source/jsondata paths.
    Returns a dict with categories -> set of values.
    """
    collected = defaultdict(set)

    # Check both output and Secrets Source paths
    building_subpath = Path('Moria') / 'Content' / 'Tech' / 'Data' / 'Building'
    candidate_paths = [
        get_appdata_dir() / 'output' / 'jsondata' / building_subpath / 'DT_ConstructionRecipes.json',
        get_appdata_dir() / 'Secrets Source' / 'jsondata' / building_subpath / 'DT_ConstructionRecipes.json',
    ]

    for recipes_path in candidate_paths:
        if not recipes_path.exists():
            continue
        try:
            _scan_namemap_from_json(recipes_path, collected)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error scanning %s: %s", recipes_path.name, e)

    # Also scan DT_Constructions.json for Actors
    constructions_paths = [
        get_appdata_dir() / 'output' / 'jsondata' / building_subpath / 'DT_Constructions.json',
        get_appdata_dir() / 'Secrets Source' / 'jsondata' / building_subpath / 'DT_Constructions.json',
    ]
    for constr_path in constructions_paths:
        if not constr_path.exists():
            continue
        try:
            _scan_namemap_from_json(constr_path, collected)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error scanning %s: %s", constr_path.name, e)

    if collected:
        logger.info("Scanned JSON files: found %s values", sum(len(v) for v in collected.values()))

    return {k: sorted(v) for k, v in collected.items()}


def _scan_namemap_from_json(json_path: Path, collected: dict):
    """Extract categorized values from a JSON file's NameMap.

    Args:
        json_path: Path to the JSON file
        collected: defaultdict(set) to add values to
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    name_map = data.get('NameMap', [])

    for name in name_map:
        # Capture /Game/ paths as Actors (before skipping other / paths)
        if name.startswith('/Game/') and not name.endswith('_C'):
            collected['Actors'].add(name)
            continue
        # Skip system names
        if name.startswith('/') or name.startswith('$'):
            continue
        if name in ('ArrayProperty', 'BoolProperty', 'IntProperty', 'FloatProperty',
                    'StructProperty', 'ObjectProperty', 'EnumProperty', 'NameProperty',
                    'None', 'Object', 'Class', 'Package', 'Default__DataTable',
                    'DataTable', 'ScriptStruct', 'BlueprintGeneratedClass', 'RowStruct', 'RowName'):
            continue

        # Categorize by pattern
        if name.startswith('E') and '::' in name:
            # Enum value
            enum_type = name.split('::')[0]
            collected[f'Enum_{enum_type}'].add(name)
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
            collected['Materials'].add(name)
        elif name.startswith('Decoration'):
            collected['Decorations'].add(name)
        elif name.endswith('_Fragment'):
            collected['Fragments'].add(name)
            collected['UnlockRequiredFragments'].add(name)
        elif name.startswith('b') and len(name) > 1 and name[1].isupper():
            # Boolean property name
            pass
        elif '_' in name and not name.startswith('Mor'):
            # Likely a construction/building name
            collected['Constructions'].add(name)
            collected['ResultConstructions'].add(name)
        elif name.startswith('Mor'):
            # Moria type name
            pass
        else:
            # Could be a construction name
            if name and name[0].isupper() and not name.startswith('Default'):
                collected['Constructions'].add(name)


def _load_cached_options(cache_path: Path) -> dict:
    """Load cached dropdown options from INI file."""
    options = {}
    if cache_path.exists():
        config = configparser.ConfigParser()
        config.read(cache_path, encoding="utf-8")
        for section in config.sections():
            options[section] = [v.strip() for v in config.get(section, "values", fallback="").split("|") if v.strip()]
    return options


def _save_cached_options(cache_path: Path, options: dict):
    """Save dropdown options to INI file."""
    config = configparser.ConfigParser()
    for section, values in sorted(options.items()):
        config[section] = {"values": "|".join(sorted(values))}
    with open(cache_path, "w", encoding="utf-8") as f:
        config.write(f)


def _scan_def_files_for_options(buildings_dir: Path) -> dict:
    """Scan all .def files to extract unique values for dropdowns.

    Returns a dict with keys for each category:
        - Materials, Tags, Actors, Constructions
        - Enum_BuildProcess, Enum_PlacementType, etc.
        - UnlockRequiredItems, UnlockRequiredConstructions
    """
    collected = defaultdict(set)

    for def_file in buildings_dir.glob("*.def"):
        try:
            tree = ET.parse(def_file)
            root = tree.getroot()

            for mod in root.findall("mod"):
                add_row = mod.find("add_row")
                if add_row is None or not add_row.text:
                    continue

                data = json.loads(add_row.text)

                # Capture the building name itself
                building_name = data.get("Name", "")
                if building_name:
                    collected["Constructions"].add(building_name)

                for prop in data.get("Value", []):
                    prop_name = prop.get("Name", "")
                    prop_type = prop.get("$type", "")

                    # Capture enum values
                    if "EnumPropertyData" in prop_type:
                        val = prop.get("Value", "")
                        if val:
                            collected[f"Enum_{prop_name}"].add(val)

                    # Capture float values for reference
                    elif "FloatPropertyData" in prop_type:
                        val = prop.get("Value")
                        if val is not None:
                            collected[f"Float_{prop_name}"].add(str(val))

                    # Capture int values for reference
                    elif "IntPropertyData" in prop_type:
                        val = prop.get("Value")
                        if val is not None:
                            collected[f"Int_{prop_name}"].add(str(val))

                    # Capture ResultConstructionHandle
                    elif prop_name == "ResultConstructionHandle":
                        for handle_prop in prop.get("Value", []):
                            if handle_prop.get("Name") == "RowName":
                                val = handle_prop.get("Value", "")
                                if val:
                                    collected["ResultConstructions"].add(val)

                    # Capture materials
                    elif prop_name == "DefaultRequiredMaterials":
                        for mat_entry in prop.get("Value", []):
                            for mat_prop in mat_entry.get("Value", []):
                                if mat_prop.get("Name") == "MaterialHandle":
                                    for handle_prop in mat_prop.get("Value", []):
                                        if handle_prop.get("Name") == "RowName":
                                            val = handle_prop.get("Value", "")
                                            if val:
                                                collected["Materials"].add(val)
                                elif mat_prop.get("Name") == "WildcardHandle":
                                    for handle_prop in mat_prop.get("Value", []):
                                        if handle_prop.get("Name") == "RowName":
                                            val = handle_prop.get("Value", "")
                                            if val and val != "None":
                                                collected["WildcardHandles"].add(val)

                    # Capture SandboxRequiredMaterials
                    elif prop_name == "SandboxRequiredMaterials":
                        for mat_entry in prop.get("Value", []):
                            for mat_prop in mat_entry.get("Value", []):
                                if mat_prop.get("Name") == "MaterialHandle":
                                    for handle_prop in mat_prop.get("Value", []):
                                        if handle_prop.get("Name") == "RowName":
                                            val = handle_prop.get("Value", "")
                                            if val:
                                                collected["Materials"].add(val)

                    # Capture DefaultRequiredConstructions
                    elif prop_name == "DefaultRequiredConstructions":
                        for const_entry in prop.get("Value", []):
                            for const_prop in const_entry.get("Value", []):
                                if const_prop.get("Name") == "RowName":
                                    val = const_prop.get("Value", "")
                                    if val:
                                        collected["RequiredConstructions"].add(val)

                    # Capture SandboxRequiredConstructions
                    elif prop_name == "SandboxRequiredConstructions":
                        for const_entry in prop.get("Value", []):
                            for const_prop in const_entry.get("Value", []):
                                if const_prop.get("Name") == "RowName":
                                    val = const_prop.get("Value", "")
                                    if val:
                                        collected["RequiredConstructions"].add(val)

                    # Capture DefaultUnlocks and SandboxUnlocks
                    elif prop_name in ("DefaultUnlocks", "SandboxUnlocks"):
                        for unlock_prop in prop.get("Value", []):
                            unlock_name = unlock_prop.get("Name", "")
                            unlock_type = unlock_prop.get("$type", "")
                            if unlock_name == "UnlockType" and "EnumPropertyData" in unlock_type:
                                val = unlock_prop.get("Value", "")
                                if val:
                                    collected["Enum_UnlockType"].add(val)
                            elif unlock_name == "UnlockRequiredItems":
                                for item_entry in unlock_prop.get("Value", []):
                                    for item_prop in item_entry.get("Value", []):
                                        if item_prop.get("Name") == "RowName":
                                            val = item_prop.get("Value", "")
                                            if val:
                                                collected["UnlockRequiredItems"].add(val)
                            elif unlock_name == "UnlockRequiredConstructions":
                                for const_entry in unlock_prop.get("Value", []):
                                    for const_prop in const_entry.get("Value", []):
                                        if const_prop.get("Name") == "RowName":
                                            val = const_prop.get("Value", "")
                                            if val:
                                                collected["UnlockRequiredConstructions"].add(val)
                            elif unlock_name == "UnlockRequiredFragments":
                                for frag_entry in unlock_prop.get("Value", []):
                                    for frag_prop in frag_entry.get("Value", []):
                                        if frag_prop.get("Name") == "RowName":
                                            val = frag_prop.get("Value", "")
                                            if val:
                                                collected["UnlockRequiredFragments"].add(val)

                    # Capture tags
                    elif prop_name == "Tags":
                        for tag_prop in prop.get("Value", []):
                            if tag_prop.get("Name") == "Tags":
                                for tag in tag_prop.get("Value", []):
                                    collected["Tags"].add(tag)

                    # Capture actor paths
                    elif prop_name == "Actor" and "SoftObjectPropertyData" in prop_type:
                        asset_path = prop.get("Value", {}).get("AssetPath", {})
                        actor = asset_path.get("AssetName", "")
                        if actor:
                            collected["Actors"].add(actor)

                    # Capture BackwardCompatibilityActors
                    elif prop_name == "BackwardCompatibilityActors":
                        for compat_entry in prop.get("Value", []):
                            for compat_prop in compat_entry.get("Value", []):
                                if "SoftObjectPath" in str(compat_prop.get("$type", "")):
                                    compat_val = compat_prop.get("Value", {})
                                    if isinstance(compat_val, dict):
                                        asset_path = compat_val.get("AssetPath", {})
                                        actor = asset_path.get("AssetName", "")
                                        if actor:
                                            collected["BackwardCompatibilityActors"].add(actor)
        except (ET.ParseError, OSError, KeyError, json.JSONDecodeError) as e:
            logger.debug("Error scanning %s: %s", def_file.name, e)

    # Convert sets to sorted lists
    return {k: sorted(v) for k, v in collected.items()}


# =============================================================================
# DEF FILE PARSING FUNCTIONS
# =============================================================================

def parse_def_file(file_path: Path) -> dict:
    """Parse a .def XML file and extract recipe/construction data.

    The .def file format is XML with embedded JSON in add_row elements:
    - <mod file="...DT_ConstructionRecipes..."> contains recipe JSON
    - <mod file="...DT_Constructions..."> contains construction JSON
    - <add_imports> optionally contains icon import data

    Args:
        file_path: Path to the .def file to parse

    Returns:
        Dict containing:
            name: The building name (from filename)
            title: Human-readable title from <title> element
            author: Author name from <author> element
            description: Description from <description> element
            recipe_json: Parsed JSON object for the recipe row
            construction_json: Parsed JSON object for the construction row
            imports_json: Parsed JSON array for icon imports (or None)
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    result = {
        "name": file_path.stem,
        "title": "",
        "author": "",
        "description": "",
        "recipe_json": None,
        "construction_json": None,
        "imports_json": None,
    }

    # Get metadata
    title_elem = root.find("title")
    if title_elem is not None and title_elem.text:
        result["title"] = title_elem.text

    author_elem = root.find("author")
    if author_elem is not None and author_elem.text:
        result["author"] = author_elem.text

    desc_elem = root.find("description")
    if desc_elem is not None and desc_elem.text:
        result["description"] = desc_elem.text

    # Find mod sections
    for mod in root.findall("mod"):
        file_attr = mod.get("file", "")

        # Recipe file
        if "DT_ConstructionRecipes" in file_attr:
            add_row = mod.find("add_row")
            if add_row is not None and add_row.text:
                try:
                    result["recipe_json"] = json.loads(add_row.text)
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse recipe JSON: %s", e)

        # Construction file
        elif "DT_Constructions" in file_attr:
            add_row = mod.find("add_row")
            if add_row is not None and add_row.text:
                try:
                    result["construction_json"] = json.loads(add_row.text)
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse construction JSON: %s", e)

            add_imports = mod.find("add_imports")
            if add_imports is not None and add_imports.text:
                try:
                    result["imports_json"] = json.loads(add_imports.text)
                except json.JSONDecodeError as e:
                    logger.error("Failed to parse imports JSON: %s", e)

    return result


def extract_recipe_fields(recipe_json: dict) -> dict:
    """Extract editable fields from the UAssetAPI recipe JSON structure.

    The recipe JSON from UAssetAPI has a complex nested structure with
    typed property data. This function flattens it into a simple dict
    for use in form fields.

    The JSON structure looks like:
        {"Name": "RowName", "Value": [
            {"$type": "EnumPropertyData...", "Name": "BuildProcess", "Value": "..."},
            {"$type": "BoolPropertyData...", "Name": "bOnWall", "Value": true},
            ...
        ]}

    Args:
        recipe_json: The parsed JSON object from the .def file

    Returns:
        Dict with field names as keys and simple Python values.
        Nested structures (like DefaultUnlocks) are flattened with
        prefixes (e.g., DefaultUnlocks_UnlockType).
    """
    fields = {
        "Name": recipe_json.get("Name", ""),
        "ResultConstructionHandle": "",
        "BuildProcess": "EBuildProcess::DualMode",
        "LocationRequirement": "EConstructionLocation::Base",
        "PlacementType": "EPlacementType::FreePlacement",
        "bOnWall": False,
        "bOnFloor": True,
        "bPlaceOnWater": False,
        "bOverrideRotation": False,
        "FoundationRule": "EFoundationRule::Never",
        "bAutoFoundation": False,
        "bInheritAutoFoundationStability": False,
        "bAllowRefunds": True,
        "bOnlyOnVoxel": False,
        "bIsBlockedByNearbySettlementStones": False,
        "MonumentType": "EMonumentType::None",
        "bIsBlockedByNearbyRavenConstructions": False,
        "bHasSandboxRequirementsOverride": False,
        "bHasSandboxUnlockOverride": False,
        "MaxAllowedPenetrationDepth": -1.0,
        "RequireNearbyRadius": 300.0,
        "CameraStateOverridePriority": 5,
        "EnabledState": "ERowEnabledState::Live",
        "Materials": [],
        "DefaultRequiredConstructions": [],
        # DefaultUnlocks structure
        "DefaultUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
        "DefaultUnlocks_NumFragments": 1,
        "DefaultUnlocks_RequiredItems": [],
        "DefaultUnlocks_RequiredConstructions": [],
        "DefaultUnlocks_RequiredFragments": [],
        # SandboxUnlocks structure
        "SandboxUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
        "SandboxUnlocks_NumFragments": 1,
        "SandboxUnlocks_RequiredItems": [],
        "SandboxUnlocks_RequiredConstructions": [],
        "SandboxUnlocks_RequiredFragments": [],
        # Sandbox materials and constructions
        "SandboxRequiredMaterials": [],
        "SandboxRequiredConstructions": [],
    }

    # Extract from Value array
    for prop in recipe_json.get("Value", []):
        prop_name = prop.get("Name", "")
        prop_type = prop.get("$type", "")

        if "EnumPropertyData" in prop_type:
            fields[prop_name] = prop.get("Value", "")
        elif "BoolPropertyData" in prop_type:
            fields[prop_name] = prop.get("Value", False)
        elif "FloatPropertyData" in prop_type:
            fields[prop_name] = prop.get("Value", 0.0)
        elif "IntPropertyData" in prop_type:
            fields[prop_name] = prop.get("Value", 0)
        elif prop_name == "ResultConstructionHandle":
            # Extract RowName from the handle
            for handle_prop in prop.get("Value", []):
                if handle_prop.get("Name") == "RowName":
                    fields["ResultConstructionHandle"] = handle_prop.get("Value", "")
        elif prop_name == "DefaultUnlocks":
            # Extract DefaultUnlocks structure
            for unlock_prop in prop.get("Value", []):
                unlock_name = unlock_prop.get("Name", "")
                unlock_type = unlock_prop.get("$type", "")
                if unlock_name == "UnlockType" and "EnumPropertyData" in unlock_type:
                    fields["DefaultUnlocks_UnlockType"] = unlock_prop.get("Value", "EMorRecipeUnlockType::Manual")
                elif unlock_name == "NumFragments":
                    fields["DefaultUnlocks_NumFragments"] = unlock_prop.get("Value", 1)
                elif unlock_name == "UnlockRequiredItems":
                    items = []
                    for item_entry in unlock_prop.get("Value", []):
                        for item_prop in item_entry.get("Value", []):
                            if item_prop.get("Name") == "RowName":
                                items.append(item_prop.get("Value", ""))
                    fields["DefaultUnlocks_RequiredItems"] = items
                elif unlock_name == "UnlockRequiredConstructions":
                    constructions = []
                    for const_entry in unlock_prop.get("Value", []):
                        for const_prop in const_entry.get("Value", []):
                            if const_prop.get("Name") == "RowName":
                                constructions.append(const_prop.get("Value", ""))
                    fields["DefaultUnlocks_RequiredConstructions"] = constructions
                elif unlock_name == "UnlockRequiredFragments":
                    fragments = []
                    for frag_entry in unlock_prop.get("Value", []):
                        for frag_prop in frag_entry.get("Value", []):
                            if frag_prop.get("Name") == "RowName":
                                fragments.append(frag_prop.get("Value", ""))
                    fields["DefaultUnlocks_RequiredFragments"] = fragments
        elif prop_name == "SandboxUnlocks":
            # Extract SandboxUnlocks structure
            for unlock_prop in prop.get("Value", []):
                unlock_name = unlock_prop.get("Name", "")
                unlock_type = unlock_prop.get("$type", "")
                if unlock_name == "UnlockType" and "EnumPropertyData" in unlock_type:
                    fields["SandboxUnlocks_UnlockType"] = unlock_prop.get("Value", "EMorRecipeUnlockType::Manual")
                elif unlock_name == "NumFragments":
                    fields["SandboxUnlocks_NumFragments"] = unlock_prop.get("Value", 1)
                elif unlock_name == "UnlockRequiredItems":
                    items = []
                    for item_entry in unlock_prop.get("Value", []):
                        for item_prop in item_entry.get("Value", []):
                            if item_prop.get("Name") == "RowName":
                                items.append(item_prop.get("Value", ""))
                    fields["SandboxUnlocks_RequiredItems"] = items
                elif unlock_name == "UnlockRequiredConstructions":
                    constructions = []
                    for const_entry in unlock_prop.get("Value", []):
                        for const_prop in const_entry.get("Value", []):
                            if const_prop.get("Name") == "RowName":
                                constructions.append(const_prop.get("Value", ""))
                    fields["SandboxUnlocks_RequiredConstructions"] = constructions
                elif unlock_name == "UnlockRequiredFragments":
                    fragments = []
                    for frag_entry in unlock_prop.get("Value", []):
                        for frag_prop in frag_entry.get("Value", []):
                            if frag_prop.get("Name") == "RowName":
                                fragments.append(frag_prop.get("Value", ""))
                    fields["SandboxUnlocks_RequiredFragments"] = fragments
        elif prop_name == "DefaultRequiredMaterials":
            # Extract materials
            for mat_entry in prop.get("Value", []):
                mat_name = ""
                mat_count = 1
                for mat_prop in mat_entry.get("Value", []):
                    if mat_prop.get("Name") == "MaterialHandle":
                        for handle_prop in mat_prop.get("Value", []):
                            if handle_prop.get("Name") == "RowName":
                                mat_name = handle_prop.get("Value", "")
                    elif mat_prop.get("Name") == "Count":
                        mat_count = mat_prop.get("Value", 1)
                if mat_name:
                    fields["Materials"].append({"Material": mat_name, "Amount": mat_count})
        elif prop_name == "DefaultRequiredConstructions":
            constructions = []
            for const_entry in prop.get("Value", []):
                for const_prop in const_entry.get("Value", []):
                    if const_prop.get("Name") == "RowName":
                        constructions.append(const_prop.get("Value", ""))
            fields["DefaultRequiredConstructions"] = constructions
        elif prop_name == "SandboxRequiredMaterials":
            mats = []
            for mat_entry in prop.get("Value", []):
                mat_name = ""
                mat_count = 1
                for mat_prop in mat_entry.get("Value", []):
                    if mat_prop.get("Name") == "MaterialHandle":
                        for handle_prop in mat_prop.get("Value", []):
                            if handle_prop.get("Name") == "RowName":
                                mat_name = handle_prop.get("Value", "")
                    elif mat_prop.get("Name") == "Count":
                        mat_count = mat_prop.get("Value", 1)
                if mat_name:
                    mats.append({"Material": mat_name, "Amount": mat_count})
            fields["SandboxRequiredMaterials"] = mats
        elif prop_name == "SandboxRequiredConstructions":
            constructions = []
            for const_entry in prop.get("Value", []):
                for const_prop in const_entry.get("Value", []):
                    if const_prop.get("Name") == "RowName":
                        constructions.append(const_prop.get("Value", ""))
            fields["SandboxRequiredConstructions"] = constructions

    return fields


def extract_construction_fields(construction_json: dict) -> dict:
    """Extract editable fields from the UAssetAPI construction JSON structure.

    Similar to extract_recipe_fields, but for the DT_Constructions data.
    This includes display information, actor references, and tags.

    The construction defines what the player sees and what actor is spawned,
    while the recipe defines how it's built.

    Args:
        construction_json: The parsed JSON object from the construction mod section

    Returns:
        Dict with field names and values for the construction definition.
    """
    fields = {
        "Name": construction_json.get("Name", ""),
        "DisplayName": "",
        "Description": "",
        "Icon": None,
        "Actor": "",
        "BackwardCompatibilityActors": [],
        "Tags": [],
        "EnabledState": "ERowEnabledState::Live",
    }

    # Extract from Value array
    for prop in construction_json.get("Value", []):
        prop_name = prop.get("Name", "")
        prop_type = prop.get("$type", "")

        if prop_name == "DisplayName" and "TextPropertyData" in prop_type:
            fields["DisplayName"] = prop.get("Value", "")
        elif prop_name == "Description" and "TextPropertyData" in prop_type:
            fields["Description"] = prop.get("Value", "")
        elif prop_name == "Icon":
            fields["Icon"] = prop.get("Value")  # This is the import index
        elif prop_name == "Actor" and "SoftObjectPropertyData" in prop_type:
            asset_path = prop.get("Value", {}).get("AssetPath", {})
            fields["Actor"] = asset_path.get("AssetName", "")
        elif prop_name == "BackwardCompatibilityActors":
            actors = []
            for compat_entry in prop.get("Value", []):
                for compat_prop in compat_entry.get("Value", []):
                    if "SoftObjectPath" in str(compat_prop.get("$type", "")):
                        compat_val = compat_prop.get("Value", {})
                        if isinstance(compat_val, dict):
                            asset_path = compat_val.get("AssetPath", {})
                            actor = asset_path.get("AssetName", "")
                            if actor:
                                actors.append(actor)
            fields["BackwardCompatibilityActors"] = actors
        elif prop_name == "Tags":
            # Extract tags from GameplayTagContainer
            for tag_prop in prop.get("Value", []):
                if tag_prop.get("Name") == "Tags":
                    fields["Tags"] = tag_prop.get("Value", [])
        elif prop_name == "EnabledState" and "EnumPropertyData" in prop_type:
            fields["EnabledState"] = prop.get("Value", "ERowEnabledState::Live")

    return fields


# =============================================================================
# AUTOCOMPLETE WIDGET
# =============================================================================

class AutocompleteEntry(ctk.CTkFrame):
    """Entry widget with autocomplete dropdown for comma-separated values.

    Provides a text entry that shows a dropdown list of suggestions as the
    user types. Supports comma-separated values, completing only the current
    word being typed.

    Features:
        - Filters suggestions as user types (minimum 2 characters)
        - Keyboard navigation (Up/Down arrows, Enter to select)
        - Limits suggestions to 20 items for performance
        - Handles comma-separated input correctly

    Args:
        parent: Parent widget
        textvariable: StringVar to bind to the entry
        suggestions: List of possible values for autocomplete
        **kwargs: Additional arguments passed to CTkEntry
    """

    def __init__(self, parent, textvariable: ctk.StringVar, suggestions: list[str], **kwargs):
        super().__init__(parent, fg_color="transparent")

        self.textvariable = textvariable
        self.suggestions = sorted(set(suggestions)) if suggestions else []
        self.dropdown_visible = False
        self.dropdown_window = None
        self.listbox = None
        self.current_matches = []
        self.selected_index = -1
        self.listbox_frame = None
        self.item_buttons = []

        # Create the entry widget
        self.entry = ctk.CTkEntry(self, textvariable=textvariable, **kwargs)
        self.entry.pack(fill="x", expand=True)

        # Bind events
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Down>", self._on_down_arrow)
        self.entry.bind("<Up>", self._on_up_arrow)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Escape>", self._hide_dropdown)

    def _get_current_word(self) -> tuple[str, int, int]:
        """Get the current word being typed (for comma-separated values)."""
        text = self.textvariable.get()
        try:
            cursor_pos = self.entry._entry.index("insert")
        except (AttributeError, IndexError, TypeError):
            cursor_pos = len(text)

        # Find word boundaries
        start = text.rfind(",", 0, cursor_pos) + 1
        end = text.find(",", cursor_pos)
        if end == -1:
            end = len(text)

        # Strip whitespace
        word = text[start:cursor_pos].strip()
        return word, start, end

    def _on_key_release(self, event):
        """Handle key release to show/update dropdown."""
        if event.keysym in ("Return", "Tab", "Escape", "Up", "Down"):
            return

        current_word, _, _ = self._get_current_word()

        if len(current_word) >= 2:
            # Filter suggestions
            matches = [s for s in self.suggestions if current_word.lower() in s.lower()]
            if matches:
                self.current_matches = matches[:20]  # Limit to 20 suggestions
                self._show_dropdown()
                return

        self._hide_dropdown()

    def _show_dropdown(self):
        """Show the autocomplete dropdown."""
        if self.dropdown_window:
            # Update existing dropdown
            self._update_listbox()
            return

        # Create toplevel window for dropdown
        self.dropdown_window = ctk.CTkToplevel(self)
        self.dropdown_window.withdraw()
        self.dropdown_window.overrideredirect(True)
        self.dropdown_window.attributes("-topmost", True)

        # Create listbox frame with dark background
        self.listbox_frame = ctk.CTkFrame(self.dropdown_window, fg_color=("gray95", "gray20"))
        self.listbox_frame.pack(fill="both", expand=True, padx=1, pady=1)

        # Create item buttons
        self.item_buttons = []
        self._update_listbox()

        # Position and show
        self._position_dropdown()
        self.dropdown_window.deiconify()
        self.dropdown_visible = True
        self.selected_index = -1

    def _update_listbox(self):
        """Update the listbox with current matches."""
        # Clear existing buttons
        for btn in getattr(self, 'item_buttons', []):
            btn.destroy()
        self.item_buttons = []

        # Create new buttons
        for match in self.current_matches:
            btn = ctk.CTkButton(
                self.listbox_frame,
                text=match,
                anchor="w",
                height=28,
                corner_radius=0,
                fg_color="transparent",
                hover_color=("gray80", "gray35"),
                text_color=("gray10", "gray90"),
                command=lambda m=match: self._select_item(m)
            )
            btn.pack(fill="x")
            self.item_buttons.append(btn)

        # Update geometry
        self._position_dropdown()

    def _position_dropdown(self):
        """Position the dropdown window below the entry."""
        if not self.dropdown_window:
            return

        # Get entry position
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()

        # Calculate size
        width = max(self.entry.winfo_width(), 300)
        height = min(len(self.current_matches) * 30 + 4, 300)

        # Check screen bounds
        screen_height = self.winfo_screenheight()
        if y + height > screen_height - 50:
            # Show above the entry instead
            y = self.entry.winfo_rooty() - height

        self.dropdown_window.geometry(f"{width}x{height}+{x}+{y}")

    def _highlight_selection(self):
        """Highlight the currently selected item."""
        for i, btn in enumerate(self.item_buttons):
            if i == self.selected_index:
                btn.configure(fg_color=("gray75", "gray40"))
            else:
                btn.configure(fg_color="transparent")

    def _on_down_arrow(self, event):
        """Move selection down in dropdown."""
        if not self.dropdown_visible or not self.current_matches:
            return "break"

        self.selected_index = min(self.selected_index + 1, len(self.current_matches) - 1)
        self._highlight_selection()
        return "break"

    def _on_up_arrow(self, event):
        """Move selection up in dropdown."""
        if not self.dropdown_visible or not self.current_matches:
            return

        self.selected_index = max(self.selected_index - 1, 0)
        self._highlight_selection()
        return "break"

    def _on_enter(self, event):
        """Select the highlighted item on Enter."""
        if self.dropdown_visible and 0 <= self.selected_index < len(self.current_matches):
            self._select_item(self.current_matches[self.selected_index])
            return "break"

    def _hide_dropdown(self, event=None):
        """Hide the autocomplete dropdown."""
        if self.dropdown_window:
            self.dropdown_window.destroy()
            self.dropdown_window = None
            self.listbox_frame = None
            self.item_buttons = []
        self.dropdown_visible = False
        self.selected_index = -1

    def _on_focus_out(self, event):
        """Handle focus out - delay hide to allow click on dropdown."""
        self.after(250, self._check_focus_and_hide)

    def _check_focus_and_hide(self):
        """Check if focus is still relevant before hiding."""
        try:
            focused = self.focus_get()
            # Don't hide if focus is on dropdown
            if self.dropdown_window and focused:
                return
        except (AttributeError, KeyError):
            pass
        self._hide_dropdown()

    def _select_item(self, item: str):
        """Select an item from the dropdown."""
        text = self.textvariable.get()
        _, start, end = self._get_current_word()

        # Rebuild the text with the selected item
        prefix = text[:start].rstrip()
        suffix = text[end:].lstrip()

        if prefix and not prefix.endswith(","):
            prefix += ", "
        elif prefix:
            prefix += " "

        new_text = prefix + item
        if suffix:
            new_text += ", " + suffix.lstrip(", ")

        self.textvariable.set(new_text)
        self._hide_dropdown()

        # Move cursor to end of inserted item
        self.entry.focus_set()


# =============================================================================
# MAIN BUILDINGS VIEW
# =============================================================================
# The primary UI component for creating and editing building/construction
# .def files. Provides a split-pane interface with a file list on the left
# and a form editor on the right.
# =============================================================================


class BuildingsView(ctk.CTkFrame):
    """
    Main view for managing building/construction objects from .def files.

    This view provides a comprehensive interface for:
    - Browsing and selecting .def files from the Buildings directory
    - Editing recipe and construction JSON data within .def files
    - Creating new building definitions with sensible defaults
    - Importing constructions from game data (DT_ConstructionRecipes.json)
    - Bulk operations via checkbox selection

    The UI is organized as a split pane:
    - Left pane (1/4 width): Scrollable list of .def files with checkboxes
    - Right pane (3/4 width): Dynamic form for editing selected building

    Attributes:
        on_status_message: Callback for status bar updates
        on_back: Callback for navigation back to main menu
        current_def_path: Path to currently loaded .def file
        current_def_data: Parsed JSON data from current .def file
        cached_options: Dropdown options populated from file scans
        form_vars: Dictionary of tkinter variables for form fields
    """

    def __init__(self, parent, on_status_message: Optional[Callable] = None, on_back: Optional[Callable] = None):
        """
        Initialize the BuildingsView.

        Args:
            parent: Parent widget (typically the main window's content frame)
            on_status_message: Callback function for status messages
            on_back: Callback function for back navigation
        """
        super().__init__(parent, fg_color="transparent")

        # Callback references for parent communication
        self.on_status_message = on_status_message
        self.on_back = on_back

        # Current file state
        self.current_def_path: Optional[Path] = None
        self.current_def_data: Optional[dict] = None
        self.def_files: list[Path] = []
        self.material_rows: list[dict] = []
        self.sandbox_material_rows: list[dict] = []

        # Cached dropdown options (populated from file scans)
        self.cached_options: dict = {}

        # Form field tkinter variables for data binding
        self.form_vars = {}

        # Widget references for form manipulation
        self.building_list = None
        self.form_scroll = None
        self.placeholder_label = None
        self.form_content = None
        self.buttons_frame = None
        self.materials_frame = None
        self.sandbox_materials_frame = None

        # Building list item references for selection highlighting
        self.building_list_items = {}  # {file_path: (row_frame, file_label)}

        # Checkbox tracking for bulk construction operations
        self.construction_checkboxes: dict[Path, ctk.CTkCheckBox] = {}
        self.construction_check_vars: dict[Path, ctk.BooleanVar] = {}
        self.select_all_var = None
        self.select_all_checkbox = None

        # Search filter for construction definitions
        self.def_search_var = None

        # Current construction pack name and tracking
        self.current_construction_pack = None

        # Construction name entry for bulk build operations
        self.construction_name_var = None
        self.construction_name_entry = None

        # View mode: 'definitions' (default .def files), 'buildings', 'weapons', 'armor'
        self.view_mode = 'definitions'

        # Secrets data holders (loaded from Secrets Source jsondata)
        self.secrets_recipes = {}  # {recipe_name: recipe_data}
        self.secrets_constructions = {}  # {construction_name: construction_data}
        self.game_recipe_names = set()  # Recipe names from game files (to filter out)
        self.current_secrets_recipe_name = None  # Currently selected secrets recipe

        # String table for game name lookups {internal_name: display_name}
        self.string_table = {}

        # Widget references created in _create_widgets helper methods
        self.buildings_btn = None
        self.weapons_btn = None
        self.armor_btn = None
        self.def_search_entry = None
        self.count_label = None
        self.form_container = None
        self.form_header = None
        self.header_title = None
        self.header_author = None
        self.header_description = None
        self.form_footer = None
        self.footer_save_btn = None
        self.footer_revert_btn = None

        self._create_widgets()
        # Defer scan until after main window is fully initialized
        self.after(100, self._scan_and_refresh)

    # -------------------------------------------------------------------------
    # INITIALIZATION AND SCANNING
    # -------------------------------------------------------------------------

    def _scan_and_refresh(self):
        """
        Scan .def files and DT_ConstructionRecipes.json for dropdown options.

        This method populates the cached_options dictionary with unique values
        found in existing .def files and the game's construction recipes JSON.
        These values are used to populate autocomplete dropdowns in the form.
        """
        buildings_dir = get_buildings_dir()
        cache_path = buildings_dir / CACHE_FILENAME

        # Scan .def files for all unique values (categories, materials, etc.)
        self._set_status("Scanning building definitions...")
        self.cached_options = _scan_def_files_for_options(buildings_dir)

        # Scan DT_ConstructionRecipes.json for official game values
        self._set_status("Scanning game construction recipes...")
        game_options = _scan_construction_recipes_json()

        # Merge game options into cached options, deduplicating values
        for key, values in game_options.items():
            if key in self.cached_options:
                existing = set(self.cached_options[key])
                for v in values:
                    existing.add(v)
                self.cached_options[key] = sorted(existing)
            else:
                self.cached_options[key] = values

        # Build combined "AllValues" key for unrestricted autocomplete fields
        all_values = set()
        for values in self.cached_options.values():
            all_values.update(values)
        self.cached_options["AllValues"] = sorted(all_values)

        # Persist to INI cache for faster startup
        _save_cached_options(cache_path, self.cached_options)

        # Load string tables for display name resolution
        self.string_table = self._load_string_table()

        # Refresh the building list to show scanned files
        self._refresh_building_list()

        # Report scan results to status bar
        total_items = sum(len(v) for v in self.cached_options.values())
        self._set_status(f"Scanned {len(self.def_files)} definitions, found {total_items} unique values")

    def _get_options(self, key: str, defaults: list[str] | None = None) -> list[str]:
        """
        Get dropdown options for a field, merging cached values with defaults.

        Args:
            key: The option category key (e.g., 'categories', 'materials')
            defaults: Default values to include if not already present

        Returns:
            List of unique option strings for the dropdown
        """
        cached = self.cached_options.get(key, [])
        if defaults:
            # Merge cached and defaults, preserving order and deduplicating
            merged = list(cached)
            for d in defaults:
                if d not in merged:
                    merged.append(d)
            return merged
        return cached if cached else ["(none)"]

    # -------------------------------------------------------------------------
    # WIDGET CREATION
    # -------------------------------------------------------------------------

    def _create_widgets(self):
        """
        Create the main buildings view layout.

        Sets up a two-column grid with the building list on the left
        and the form editor on the right.
        """
        # Configure grid: left list (1/4) and right form (3/4)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # Left pane: Building list
        self._create_building_list_pane()

        # Right pane: Building form
        self._create_building_form_pane()

    def _create_building_list_pane(self):
        """
        Create the left pane with .def file list and action buttons.

        The pane includes:
        - Category buttons (Buildings, Weapons, Armor)
        - Refresh button
        - Scrollable list of items with individual checkboxes
        - Search bar below the list
        - Action buttons: My Construction, Name, Build
        """
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Button row for category filters (BUILDINGS, WEAPONS, ARMOR) + refresh
        btn_row = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(10, 5))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)
        btn_row.grid_columnconfigure(2, weight=1)
        btn_row.grid_columnconfigure(3, weight=0)  # Refresh icon, fixed width

        # Buildings button
        self.buildings_btn = ctk.CTkButton(
            btn_row,
            text="Buildings",
            height=32,
            fg_color="#2196F3",
            hover_color="#1976D2",
            font=ctk.CTkFont(weight="bold"),
            command=self._load_secrets_buildings
        )
        self.buildings_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        # Weapons button
        self.weapons_btn = ctk.CTkButton(
            btn_row,
            text="Weapons",
            height=32,
            fg_color="#9C27B0",
            hover_color="#7B1FA2",
            font=ctk.CTkFont(weight="bold"),
            command=self._load_secrets_weapons
        )
        self.weapons_btn.grid(row=0, column=1, sticky="ew", padx=2)

        # Armor button
        self.armor_btn = ctk.CTkButton(
            btn_row,
            text="Armor",
            height=32,
            fg_color="#FF9800",
            hover_color="#F57C00",
            font=ctk.CTkFont(weight="bold"),
            command=self._load_secrets_armor
        )
        self.armor_btn.grid(row=0, column=2, sticky="ew", padx=2)

        # Refresh button (symbol only) - deletes cache and re-copies from Secrets Source
        refresh_btn = ctk.CTkButton(
            btn_row,
            text="↻",
            width=32,
            height=32,
            font=ctk.CTkFont(size=16),
            fg_color="transparent",
            hover_color=("gray75", "gray25"),
            command=self._on_refresh_cache_click
        )
        refresh_btn.grid(row=0, column=3, padx=(2, 0))

        # Scrollable file list
        self.building_list = ctk.CTkScrollableFrame(list_frame, fg_color="transparent")
        self.building_list.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        # === SEARCH BAR (below scrollable list) ===
        search_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(5, 5))

        ctk.CTkLabel(
            search_frame,
            text="🔍",
            font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=(0, 5))

        self.def_search_var = ctk.StringVar()
        self.def_search_var.trace_add("write", lambda *args: self._filter_definitions_list())
        self.def_search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.def_search_var,
            height=28,
            placeholder_text="Search definitions...",
            font=ctk.CTkFont(size=12)
        )
        self.def_search_entry.pack(side="left", fill="x", expand=True)

        # Clear search button
        clear_btn = ctk.CTkButton(
            search_frame,
            text="✕",
            width=28,
            height=28,
            fg_color="#757575",
            hover_color="#616161",
            command=lambda: self.def_search_var.set("")
        )
        clear_btn.pack(side="left", padx=(5, 0))

        # Count label (at bottom of list)
        self.count_label = ctk.CTkLabel(
            list_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.count_label.pack(padx=10, anchor="w", pady=(0, 5))

        # Bottom section with construction name and build button
        bottom_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=10, pady=(5, 10))

        # Left side: "My Construction Name" button and text field
        left_bottom = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        left_bottom.pack(side="left", fill="x", expand=True)

        construction_name_btn = ctk.CTkButton(
            left_bottom,
            text="My Construction",
            fg_color="#9C27B0",  # Purple
            hover_color="#7B1FA2",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=120,
            command=self._on_construction_name_click
        )
        construction_name_btn.pack(side="left")

        # Text field for construction name
        self.construction_name_var = ctk.StringVar(value="")
        self.construction_name_entry = ctk.CTkEntry(
            left_bottom,
            textvariable=self.construction_name_var,
            width=100,
            placeholder_text="Name..."
        )
        self.construction_name_entry.pack(side="left", padx=(10, 0), fill="x", expand=True)

        # Right side: "Build" button
        build_btn = ctk.CTkButton(
            bottom_frame,
            text="Build",
            fg_color="#4CAF50",  # Green
            hover_color="#388E3C",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=80,
            command=self._on_construction_build_click
        )
        build_btn.pack(side="right", padx=(10, 0))

    def _create_building_form_pane(self):
        """Create the right pane with the building form (fixed header, scrollable content, fixed footer)."""
        self.form_container = ctk.CTkFrame(self)
        self.form_container.grid(row=0, column=1, sticky="nsew")

        # Configure grid for header (row 0), content (row 1), footer (row 2)
        self.form_container.grid_rowconfigure(0, weight=0)  # Header - fixed
        self.form_container.grid_rowconfigure(1, weight=1)  # Content - expandable
        self.form_container.grid_rowconfigure(2, weight=0)  # Footer - fixed
        self.form_container.grid_columnconfigure(0, weight=1)

        # === FIXED HEADER ===
        self.form_header = ctk.CTkFrame(self.form_container, fg_color=("gray90", "gray17"))
        self.form_header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.form_header.grid_remove()  # Hidden initially

        self.header_title = ctk.CTkLabel(
            self.form_header,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w"
        )
        self.header_title.pack(fill="x", padx=10, pady=(10, 2))

        self.header_author = ctk.CTkLabel(
            self.form_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w"
        )
        self.header_author.pack(fill="x", padx=10)

        self.header_description = ctk.CTkLabel(
            self.form_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            anchor="w",
            wraplength=500
        )
        self.header_description.pack(fill="x", padx=10, pady=(0, 10))

        # === SCROLLABLE CONTENT ===
        self.form_scroll = ctk.CTkScrollableFrame(self.form_container, fg_color="transparent")
        self.form_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        # Placeholder message
        self.placeholder_label = ctk.CTkLabel(
            self.form_scroll,
            text="Select a building definition from the list\nto view and edit its properties",
            text_color="gray",
            font=ctk.CTkFont(size=14)
        )
        self.placeholder_label.pack(pady=50)

        # Form content (hidden initially)
        self.form_content = ctk.CTkFrame(self.form_scroll, fg_color="transparent")

        # === FIXED FOOTER ===
        self.form_footer = ctk.CTkFrame(self.form_container, fg_color=("gray90", "gray17"))
        self.form_footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.form_footer.grid_remove()  # Hidden initially

        # Footer buttons
        self.footer_revert_btn = ctk.CTkButton(
            self.form_footer,
            text="↩ Revert",
            width=100,
            height=36,
            fg_color="gray50",
            hover_color="gray40",
            command=self._revert_changes
        )
        self.footer_revert_btn.pack(side="left", padx=10, pady=10)

        self.footer_save_btn = ctk.CTkButton(
            self.form_footer,
            text="💾 Save Changes",
            width=150,
            height=36,
            fg_color="#4CAF50",
            hover_color="#45a049",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._save_changes
        )
        self.footer_save_btn.pack(side="right", padx=10, pady=10)

    # -------------------------------------------------------------------------
    # FILE OPERATIONS
    # -------------------------------------------------------------------------

    def _revert_changes(self):
        """Revert form to the original version by reloading from source files.

        For secrets items, this reads from the original Secrets Source files
        (not cache), writes those original rows back to cache, and unchecks
        the item in the left pane list.
        """
        if self.current_def_path:
            self._load_def_file(self.current_def_path)
        elif self.current_secrets_recipe_name:
            recipe_name = self.current_secrets_recipe_name

            # Read original rows from Secrets Source (not cache)
            original_recipe = self._get_row_by_name(
                self._get_secrets_recipes_path(), recipe_name)
            original_construction = self._get_row_by_name(
                self._get_secrets_constructions_path(), recipe_name)

            # Overwrite cache with original rows
            if original_recipe:
                self._update_row_in_json(
                    self._get_cache_recipes_path(), recipe_name, original_recipe)
            if original_construction:
                self._update_row_in_json(
                    self._get_cache_constructions_path(), recipe_name, original_construction)

            # Uncheck the item in the left pane and persist to INI
            check_var = self.construction_check_vars.get(recipe_name)
            if check_var:
                check_var.set(False)
            self._save_checked_states_to_ini()

            # Reload the form from the now-reverted cache
            self._load_secrets_recipe(recipe_name)
            self._set_status(f"Reverted {recipe_name} to original")

    def _refresh_building_list(self):
        """
        Refresh the list of .def files from the Buildings directory.

        Clears and rebuilds the file list, creating a row for each .def file
        with a checkbox and clickable label.
        """
        # Clear existing items
        for widget in self.building_list.winfo_children():
            widget.destroy()

        # Get buildings directory (where .def files are stored)
        buildings_dir = get_buildings_dir()

        # Find all .def files
        self.def_files = sorted(buildings_dir.glob("*.def"))

        # Update count
        self.count_label.configure(text=f"{len(self.def_files)} definitions")

        if not self.def_files:
            no_files_label = ctk.CTkLabel(
                self.building_list,
                text="No .def files found\n\nRun helpers/generate_building_defs.py\nto generate from source JSON",
                text_color="gray"
            )
            no_files_label.pack(pady=20)
            return

        # Clear previous item references and checkbox tracking
        self.building_list_items.clear()
        self.construction_checkboxes.clear()
        self.construction_check_vars.clear()

        # Create entry for each file with checkbox
        for file_path in self.def_files:
            row_frame = ctk.CTkFrame(self.building_list, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)

            # Checkbox for selection
            check_var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(
                row_frame,
                text="",
                variable=check_var,
                width=20,
                command=lambda p=file_path: self._on_construction_checkbox_toggle(p)
            )
            checkbox.pack(side="left")

            # Store checkbox references
            self.construction_checkboxes[file_path] = checkbox
            self.construction_check_vars[file_path] = check_var

            internal_name = file_path.stem
            display_name = self._lookup_game_name(internal_name)
            label_text = (f"{display_name} ({internal_name})"
                          if display_name != internal_name else internal_name)

            file_label = ctk.CTkLabel(
                row_frame,
                text=label_text,
                anchor="w",
                cursor="hand2",
                text_color=("gray10", "#E8E8E8")
            )
            file_label.pack(side="left", fill="x", expand=True, padx=5)
            file_label.bind("<Button-1>", lambda e, p=file_path: self._load_def_file(p))
            row_frame.bind("<Button-1>", lambda e, p=file_path: self._load_def_file(p))

            # Store reference for highlighting (3-tuple with label text for filtering)
            self.building_list_items[file_path] = (row_frame, file_label, label_text)

            # Hover effect (only if not selected)
            file_label.bind("<Enter>", lambda e, p=file_path, lbl=file_label: self._on_item_hover(p, lbl, True))
            file_label.bind("<Leave>", lambda e, p=file_path, lbl=file_label: self._on_item_hover(p, lbl, False))

        # Apply any active filter
        self._filter_definitions_list()

    def _filter_definitions_list(self):
        """Filter the definitions list based on search text."""
        if not self.def_search_var:
            return

        # If in secrets mode, use the secrets filter
        if self.view_mode in ('buildings', 'weapons', 'armor'):
            self._filter_secrets_list()
            return

        filter_text = self.def_search_var.get().lower().strip()

        visible_count = 0
        for file_path, item_data in self.building_list_items.items():
            row_frame = item_data[0]
            label_text = item_data[2] if len(item_data) == 3 else ""

            # Handle both Path objects and string keys
            if isinstance(file_path, Path):
                name_str = file_path.stem.lower()
            else:
                name_str = str(file_path).lower()

            # Search against both internal name and display text
            search_str = f"{name_str} {label_text.lower()}"
            if not filter_text or filter_text in search_str:
                row_frame.pack(fill="x", pady=1)
                visible_count += 1
            else:
                row_frame.pack_forget()

        # Update count label with filter info
        total = len(self.def_files)
        if filter_text:
            self.count_label.configure(text=f"{visible_count} of {total} definitions")
        else:
            self.count_label.configure(text=f"{total} definitions")

    def _load_def_file(self, file_path: Path):
        """Load a .def file and display it in the form."""
        try:
            self.current_def_data = parse_def_file(file_path)
            self.current_def_path = file_path
            self._highlight_selected_item(file_path)
            self._show_form()
            self._set_status(f"Loaded: {file_path.name}")
        except (ET.ParseError, OSError, KeyError, json.JSONDecodeError) as e:
            logger.error("Error loading def file: %s", e)
            self._set_status(f"Error loading file: {e}", is_error=True)

    def _highlight_selected_item(self, selected_path: Path):
        """Highlight the selected building in the list."""
        for file_path, item_data in self.building_list_items.items():
            row_frame, file_label = item_data[0], item_data[1]
            if file_path == selected_path:
                # Selected state - highlight with accent color
                row_frame.configure(fg_color=("#d0e8ff", "#1a4a6e"))
                file_label.configure(text_color=("#0066cc", "#66b3ff"))
            else:
                # Unselected state - reset to default
                row_frame.configure(fg_color="transparent")
                file_label.configure(text_color=("gray10", "#E8E8E8"))

    def _on_item_hover(self, file_path: Path, label: ctk.CTkLabel, entering: bool):
        """Handle hover effect on list items, respecting selection state."""
        # Don't change hover color if this is the selected item
        if file_path == self.current_def_path:
            return

        if entering:
            label.configure(text_color="#4CAF50")
        else:
            label.configure(text_color=("gray10", "#E8E8E8"))

    def _on_select_all_toggle(self):
        """Toggle all construction checkboxes based on select-all state."""
        if self.select_all_var is None:
            return

        select_all = self.select_all_var.get()
        for _, check_var in self.construction_check_vars.items():
            check_var.set(select_all)

        # Save to INI file immediately if we have a construction pack selected
        if self.current_construction_pack:
            self._save_construction_pack_to_ini()

    def _on_refresh_cache_click(self):
        """Handle Refresh button - delete cache and re-copy from Secrets Source."""
        self._refresh_cache()
        self._set_status("Cache refreshed from Secrets Source")

        # Reload the current view if one is active
        if self.view_mode == 'buildings':
            self._load_secrets_buildings()
        elif self.view_mode == 'weapons':
            self._load_secrets_weapons()
        elif self.view_mode == 'armor':
            self._load_secrets_armor()

    def _on_secrets_checkbox_toggle(self, recipe_name: str):
        """Handle secrets item checkbox toggle - saves to INI in real-time."""
        self._save_checked_states_to_ini()

    def _on_construction_checkbox_toggle(self, file_path: Path):
        """Handle individual construction checkbox toggle - saves to INI in real-time."""
        # Save to INI file immediately if we have a construction pack selected
        if self.current_construction_pack:
            self._save_construction_pack_to_ini()

    def _save_construction_pack_to_ini(self):
        """Save current checkbox states to the construction pack INI file."""
        if not self.current_construction_pack:
            return

        pack_name = self.current_construction_pack
        pack_dir = get_constructions_dir() / pack_name
        pack_dir.mkdir(parents=True, exist_ok=True)
        ini_path = pack_dir / f"{pack_name}.ini"

        # Get selected construction names
        selected_names = [
            fp.stem for fp, check_var in self.construction_check_vars.items()
            if check_var.get()
        ]

        # Write to INI
        config = configparser.ConfigParser()
        config['Constructions'] = {name: '1' for name in selected_names}

        with open(ini_path, 'w', encoding='utf-8') as f:
            config.write(f)

    def _on_construction_name_click(self):
        """Handle click on 'My Construction' button - open dialog to select .def filename."""
        from src.ui.construction_name_dialog import show_construction_name_dialog  # pylint: disable=import-outside-toplevel

        # Get current name from the text field
        current_name = self.construction_name_var.get().strip() if self.construction_name_var else ""

        # Show dialog - returns filename (without .def) or None
        result = show_construction_name_dialog(self.winfo_toplevel(), current_name)

        if result:
            # Update the name entry with the selected filename
            if self.construction_name_var:
                self.construction_name_var.set(result)
            self._set_status(f"Selected definition: {result}.def")

    def _on_construction_build_click(self):
        """Build a .def file with only the changes between original and cached rows."""
        from tkinter import messagebox  # pylint: disable=import-outside-toplevel

        # Get selected construction names (checked items in the list)
        selected_names = [
            name for name, check_var in self.construction_check_vars.items()
            if check_var.get()
        ]

        if not selected_names:
            messagebox.showwarning("No Selection", "Please select at least one construction to build.")
            return

        # Get .def filename from the text field
        pack_name = self.construction_name_var.get().strip() if self.construction_name_var else ""
        if not pack_name:
            messagebox.showwarning("No Name", "Please enter a filename for the definition.")
            if hasattr(self, 'construction_name_entry') and self.construction_name_entry:
                self.construction_name_entry.focus_set()
            return

        # Sanitize name for use as filename
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', pack_name)

        # Define output directory and file
        output_dir = get_appdata_dir() / "Definitions" / "Building"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{safe_name}.def"

        self._set_status("Building definition file from changes...")

        # Load both original and cached data
        try:
            orig_recipes = self._load_table_data(self._get_secrets_recipes_path())
            orig_constructions = self._load_table_data(self._get_secrets_constructions_path())
            cache_recipes = self._load_table_data(self._get_cache_recipes_path())
            cache_constructions = self._load_table_data(self._get_cache_constructions_path())
        except (OSError, json.JSONDecodeError, KeyError) as e:
            self._set_status(f"Build failed: Could not read files - {e}", is_error=True)
            return

        # Diff each selected item: compare original vs cached row properties
        recipe_changes = []  # list of (row_name, property_name, new_value_str)
        construction_changes = []

        for name in sorted(selected_names):
            # Diff recipe rows
            orig_row = orig_recipes.get(name, {})
            cache_row = cache_recipes.get(name, {})
            recipe_changes.extend(self._diff_row_properties(name, orig_row, cache_row))

            # Diff construction rows
            orig_row = orig_constructions.get(name, {})
            cache_row = cache_constructions.get(name, {})
            construction_changes.extend(self._diff_row_properties(name, orig_row, cache_row))

        if not recipe_changes and not construction_changes:
            self._set_status("No changes found between original and cached data")
            return

        # Write the .def file with <change> elements
        try:
            self._write_changes_def_file(
                output_file, safe_name, recipe_changes, construction_changes
            )
        except OSError as e:
            logger.error("Error writing .def file: %s", e)
            self._set_status(f"Build failed: Could not write .def file - {e}", is_error=True)
            return

        total_changes = len(recipe_changes) + len(construction_changes)
        self._set_status(
            f"Build complete: '{pack_name}' - {total_changes} change(s) → {output_file.name}"
        )

    def _load_table_data(self, json_path: Path) -> dict:
        """Load Table.Data rows from a JSON file, keyed by row Name.

        Args:
            json_path: Path to the JSON file

        Returns:
            Dict mapping row name to row dict
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        rows_by_name = {}
        exports = data.get('Exports', [])
        if exports:
            table = exports[0].get('Table', {})
            for row in table.get('Data', []):
                row_name = row.get('Name')
                if row_name:
                    rows_by_name[row_name] = row
        return rows_by_name

    def _diff_row_properties(
        self, row_name: str, orig_row: dict, cache_row: dict
    ) -> list[tuple[str, str, str]]:
        """Compare original and cached row, returning changes as (item, property, value) tuples.

        Walks the Value arrays of both rows and compares each property.
        For scalar types (bool, int, float, enum, text), emits a simple change.
        For complex types (arrays, structs), compares serialized JSON and emits
        dot-path changes where possible.

        Args:
            row_name: The row Name (used as the item in <change>)
            orig_row: Original row dict from Secrets Source
            cache_row: Modified row dict from cache

        Returns:
            List of (item_name, property_path, new_value_str) tuples
        """
        changes = []
        orig_props = {p.get('Name'): p for p in orig_row.get('Value', []) if p.get('Name')}
        cache_props = {p.get('Name'): p for p in cache_row.get('Value', []) if p.get('Name')}

        for prop_name, cache_prop in cache_props.items():
            orig_prop = orig_props.get(prop_name)
            if orig_prop is None:
                continue  # New property, skip

            # Quick check: if JSON is identical, no change
            if json.dumps(orig_prop, sort_keys=True) == json.dumps(cache_prop, sort_keys=True):
                continue

            prop_type = cache_prop.get('$type', '')
            cache_val = cache_prop.get('Value')
            orig_val = orig_prop.get('Value')

            # Simple scalar types
            if any(t in prop_type for t in ('BoolPropertyData', 'IntPropertyData',
                                             'FloatPropertyData', 'EnumPropertyData',
                                             'NamePropertyData')):
                if cache_val != orig_val:
                    changes.append((row_name, prop_name, str(cache_val)))

            # Text property - compare CultureInvariantString
            elif 'TextPropertyData' in prop_type:
                orig_text = orig_prop.get('CultureInvariantString', '')
                cache_text = cache_prop.get('CultureInvariantString', '')
                if orig_text != cache_text:
                    changes.append((row_name, f"{prop_name}.CultureInvariantString", cache_text))

            # SoftObject property (Actor paths)
            elif 'SoftObjectPropertyData' in prop_type:
                orig_path = (orig_prop.get('Value', {}).get('AssetPath', {})
                             .get('AssetName', ''))
                cache_path = (cache_prop.get('Value', {}).get('AssetPath', {})
                              .get('AssetName', ''))
                if orig_path != cache_path:
                    changes.append((row_name, f"{prop_name}.AssetPath.AssetName", cache_path))

            # Struct property (e.g. ResultConstructionHandle) - diff inner properties
            elif 'StructPropertyData' in prop_type:
                if isinstance(orig_val, list) and isinstance(cache_val, list):
                    inner_changes = self._diff_struct_properties(
                        row_name, prop_name, orig_val, cache_val)
                    changes.extend(inner_changes)

            # Array property (materials, name arrays) - compare serialized
            elif 'ArrayPropertyData' in prop_type:
                if json.dumps(orig_val, sort_keys=True) != json.dumps(cache_val, sort_keys=True):
                    # For arrays of simple values, try element-level diff
                    inner = self._diff_array_properties(
                        row_name, prop_name, orig_val, cache_val)
                    changes.extend(inner)

            # Fallback: any other type where Value changed
            elif cache_val != orig_val:
                changes.append((row_name, prop_name, str(cache_val)))

        return changes

    def _diff_struct_properties(
        self, row_name: str, parent_path: str,
        orig_props: list, cache_props: list
    ) -> list[tuple[str, str, str]]:
        """Diff inner properties of a struct, returning dot-path changes."""
        changes = []
        orig_map = {p.get('Name'): p for p in orig_props if p.get('Name')}
        cache_map = {p.get('Name'): p for p in cache_props if p.get('Name')}

        for inner_name, cache_inner in cache_map.items():
            orig_inner = orig_map.get(inner_name)
            if orig_inner is None:
                continue
            if json.dumps(orig_inner, sort_keys=True) == json.dumps(cache_inner, sort_keys=True):
                continue

            inner_val = cache_inner.get('Value')
            orig_inner_val = orig_inner.get('Value')

            # Simple scalar inner value
            if not isinstance(inner_val, (list, dict)):
                if inner_val != orig_inner_val:
                    changes.append((row_name, f"{parent_path}.{inner_name}", str(inner_val)))
            # Nested struct
            elif isinstance(inner_val, list) and isinstance(orig_inner_val, list):
                changes.extend(self._diff_struct_properties(
                    row_name, f"{parent_path}.{inner_name}", orig_inner_val, inner_val))

        return changes

    def _diff_array_properties(
        self, row_name: str, prop_name: str,
        orig_arr: list, cache_arr: list
    ) -> list[tuple[str, str, str]]:
        """Diff array elements, returning indexed changes where possible."""
        changes = []

        # Compare element by element for matching indices
        for i in range(min(len(orig_arr), len(cache_arr))):
            orig_elem = orig_arr[i]
            cache_elem = cache_arr[i]

            if json.dumps(orig_elem, sort_keys=True) == json.dumps(cache_elem, sort_keys=True):
                continue

            # If elements are structs with Value arrays, diff their inner properties
            if (isinstance(orig_elem, dict) and isinstance(cache_elem, dict)
                    and 'Value' in orig_elem and 'Value' in cache_elem
                    and isinstance(orig_elem['Value'], list)):
                inner = self._diff_struct_properties(
                    row_name, f"{prop_name}[{i}]",
                    orig_elem['Value'], cache_elem['Value'])
                changes.extend(inner)
            elif isinstance(orig_elem, dict) and isinstance(cache_elem, dict):
                # Simple dict element - compare Value field
                orig_v = orig_elem.get('Value', '')
                cache_v = cache_elem.get('Value', '')
                if orig_v != cache_v:
                    changes.append((row_name, f"{prop_name}[{i}]", str(cache_v)))
            else:
                changes.append((row_name, f"{prop_name}[{i}]", str(cache_elem)))

        return changes

    def _write_changes_def_file(
        self, output_file: Path, def_name: str,
        recipe_changes: list[tuple[str, str, str]],
        construction_changes: list[tuple[str, str, str]]
    ):
        """Write a .def file containing only <change> elements for modified properties.

        Args:
            output_file: Path to write the .def file
            def_name: Name for the definition title
            recipe_changes: List of (item, property, value) for DT_ConstructionRecipes
            construction_changes: List of (item, property, value) for DT_Constructions
        """
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<definition>',
            f'  <title>{self._escape_xml(def_name)}</title>',
            '  <author>Moria MOD Creator</author>',
            f'  <description>Building modifications: {len(recipe_changes)} recipe changes, '
            f'{len(construction_changes)} construction changes</description>',
        ]

        if recipe_changes:
            lines.append('  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_ConstructionRecipes.json">')
            for item, prop, value in recipe_changes:
                lines.append(
                    f'    <change item="{self._escape_xml(item)}" '
                    f'property="{self._escape_xml(prop)}" '
                    f'value="{self._escape_xml(str(value))}" />'
                )
            lines.append('  </mod>')

        if construction_changes:
            lines.append('  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_Constructions.json">')
            for item, prop, value in construction_changes:
                lines.append(
                    f'    <change item="{self._escape_xml(item)}" '
                    f'property="{self._escape_xml(prop)}" '
                    f'value="{self._escape_xml(str(value))}" />'
                )
            lines.append('  </mod>')

        lines.append('</definition>')

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info("Wrote changes .def file: %s (%d recipe, %d construction changes)",
                     output_file, len(recipe_changes), len(construction_changes))

    def _get_imports_for_constructions(
        self, constructions_path: Path, construction_names: list[str]
    ) -> list[str]:
        """Extract icon Import entries needed by the specified constructions.

        Reads the Imports array from the JSON file and finds entries referenced
        by the Icon property of each selected construction row.

        Args:
            constructions_path: Path to DT_Constructions.json
            construction_names: List of construction row names to check

        Returns:
            List of import JSON text strings (each is a JSON array)
        """
        try:
            with open(constructions_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []

        all_imports = data.get('Imports', [])
        if not all_imports:
            return []

        exports = data.get('Exports', [])
        if not exports:
            return []

        table = exports[0].get('Table', {})
        rows = table.get('Data', [])

        # Collect needed import entries
        needed_imports = []
        seen = set()

        for row in rows:
            if row.get('Name') not in construction_names:
                continue

            # Find Icon property with negative import index
            for prop in row.get('Value', []):
                if prop.get('Name') == 'Icon':
                    icon_idx = prop.get('Value')
                    if isinstance(icon_idx, int) and icon_idx < 0:
                        # Negative index: -2 means Imports[1], also need Imports[0]
                        texture_idx = abs(icon_idx) - 1
                        package_idx = texture_idx - 1
                        for idx in (package_idx, texture_idx):
                            if 0 <= idx < len(all_imports):
                                obj_name = all_imports[idx].get('ObjectName', '')
                                if obj_name and obj_name not in seen:
                                    seen.add(obj_name)
                                    needed_imports.append(all_imports[idx])

        if needed_imports:
            return [json.dumps(needed_imports, separators=(',', ':'))]
        return []

    def _write_combined_def_file(
        self,
        output_file: Path,
        pack_name: str,
        recipe_rows: list,
        construction_rows: list,
        all_imports: list
    ):
        """Write the combined .def file with all recipes and constructions.

        Args:
            output_file: Path to write the .def file
            pack_name: Name of the construction pack
            recipe_rows: List of (name, json_text) tuples for recipes
            construction_rows: List of (name, json_text) tuples for constructions
            all_imports: List of imports JSON texts
        """
        # Merge all imports into one array (deduplicated)
        merged_imports = []
        seen_imports = set()
        for imports_text in all_imports:
            try:
                imports_list = json.loads(imports_text)
                for imp in imports_list:
                    obj_name = imp.get('ObjectName', '')
                    if obj_name and obj_name not in seen_imports:
                        seen_imports.add(obj_name)
                        merged_imports.append(imp)
            except json.JSONDecodeError:
                pass

        # Build the XML structure
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<definition>',
            f'  <title>{self._escape_xml(pack_name)}</title>',
            '  <author>Moria MOD Creator</author>',
            f'  <description>Combined construction pack with {len(recipe_rows)} recipes and {len(construction_rows)} constructions</description>',
            '',  # Empty line after header
        ]

        # DT_ConstructionRecipes mod section
        if recipe_rows:
            lines.append('  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_ConstructionRecipes.json">')
            lines.append('')  # Empty line after opening tag
            for row_name, row_json in recipe_rows:
                lines.append(f'    <add_row name="{self._escape_xml(row_name)}">')
                lines.append(f'      <![CDATA[{row_json}]]>')
                lines.append('    </add_row>')
                lines.append('')  # Empty line between rows
            lines.append('  </mod>')
            lines.append('')  # Empty line after section

        # DT_Constructions mod section
        if construction_rows or merged_imports:
            lines.append('  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_Constructions.json">')
            lines.append('')  # Empty line after opening tag

            # Add merged imports if any
            if merged_imports:
                imports_json = json.dumps(merged_imports, separators=(',', ':'))
                lines.append(f'    <add_imports><![CDATA[{imports_json}]]></add_imports>')
                lines.append('')  # Empty line after imports

            for row_name, row_json in construction_rows:
                lines.append(f'    <add_row name="{self._escape_xml(row_name)}">')
                lines.append(f'      <![CDATA[{row_json}]]>')
                lines.append('    </add_row>')
                lines.append('')  # Empty line between rows
            lines.append('  </mod>')

        lines.append('</definition>')

        # Write the file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        logger.info("Wrote combined .def file: %s", output_file)

    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters in text."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&apos;'))

    # -------------------------------------------------------------------------
    # FORM DISPLAY AND LAYOUT
    # -------------------------------------------------------------------------

    def _show_form(self):
        """Render the complete editable form with Recipe and Construction sections."""
        # Hide placeholder and show form widgets
        self.placeholder_label.pack_forget()

        # Clear existing form content
        for widget in self.form_content.winfo_children():
            widget.destroy()
        self.form_content.pack(fill="both", expand=True)

        # Update header with def file metadata
        title = self.current_def_data.get("title", "")
        author = self.current_def_data.get("author", "")
        description = self.current_def_data.get("description", "")
        if title or author:
            header_text = title or "(Untitled)"
            # Show StringTable display name alongside title if available
            construction_json = self.current_def_data.get("construction_json")
            construction_name = (construction_json.get("Name", "")
                                 if construction_json else "")
            game_display = (self._lookup_game_name(construction_name)
                            if construction_name else "")
            if game_display and game_display != construction_name and game_display != title:
                header_text = f"{header_text}  \u2014  {game_display}"
            self.header_title.configure(text=header_text)
            self.header_author.configure(text=f"by {author}" if author else "")
            self.header_description.configure(text=description or "")
            self.form_header.grid()
        else:
            self.form_header.grid_remove()

        # Show footer with save/revert/delete buttons
        self.form_footer.grid()

        self.form_vars.clear()
        self.material_rows.clear()
        self.sandbox_material_rows.clear()

        recipe_json = self.current_def_data.get("recipe_json")
        construction_json = self.current_def_data.get("construction_json")

        has_data = False

        # ===== SECTION 1: RECIPE DATA =====
        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            recipe = extract_recipe_fields(recipe_json)

            self._create_section_header("Construction Recipe", "#FF9800")

            # Row name and result construction
            self._create_text_field("Name", recipe["Name"], label="Row Name")
            self._create_text_field(
                "ResultConstructionHandle", recipe["ResultConstructionHandle"],
                label="Result Construction", autocomplete_key="ResultConstructions"
            )

            # Enum dropdowns - row 1
            row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row1.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row1, "BuildProcess", recipe["BuildProcess"],
                self._get_options("Enum_BuildProcess", DEFAULT_BUILD_PROCESS)
            )
            self._create_dropdown_field_inline(
                row1, "PlacementType", recipe["PlacementType"],
                self._get_options("Enum_PlacementType", DEFAULT_PLACEMENT)
            )

            # Enum dropdowns - row 2
            row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row2.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row2, "LocationRequirement", recipe["LocationRequirement"],
                self._get_options("Enum_LocationRequirement", DEFAULT_LOCATION)
            )
            self._create_dropdown_field_inline(
                row2, "FoundationRule", recipe["FoundationRule"],
                self._get_options("Enum_FoundationRule", DEFAULT_FOUNDATION_RULE)
            )

            # Enum dropdown - row 3
            row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row3.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row3, "MonumentType", recipe["MonumentType"],
                self._get_options("Enum_MonumentType", DEFAULT_MONUMENT_TYPE)
            )

            # Boolean checkboxes - row 1 (placement)
            self._create_subsection_header("Placement Options")
            bool_row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row1.pack(fill="x", pady=4)
            for bf in ["bOnWall", "bOnFloor", "bPlaceOnWater", "bOverrideRotation"]:
                self._create_checkbox_field(bool_row1, bf, recipe[bf])

            # Boolean checkboxes - row 2 (building rules)
            bool_row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row2.pack(fill="x", pady=4)
            for bf in ["bAllowRefunds", "bAutoFoundation", "bInheritAutoFoundationStability", "bOnlyOnVoxel"]:
                self._create_checkbox_field(bool_row2, bf, recipe[bf])

            # Boolean checkboxes - row 3 (restrictions)
            bool_row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row3.pack(fill="x", pady=4)
            for bf in ["bIsBlockedByNearbySettlementStones", "bIsBlockedByNearbyRavenConstructions"]:
                self._create_checkbox_field(bool_row3, bf, recipe[bf])

            # Numeric fields
            self._create_subsection_header("Numeric Properties")
            self._create_text_field(
                "MaxAllowedPenetrationDepth", str(recipe["MaxAllowedPenetrationDepth"]),
                label="Max Penetration Depth", width=200
            )
            self._create_text_field(
                "RequireNearbyRadius", str(recipe["RequireNearbyRadius"]),
                label="Require Nearby Radius", width=200
            )
            self._create_text_field(
                "CameraStateOverridePriority", str(recipe["CameraStateOverridePriority"]),
                label="Camera Priority", width=200
            )

            # Materials section
            self._create_subsection_header("Required Materials")
            add_mat_btn = ctk.CTkButton(
                self.form_content, text="+ Add Material", width=120, height=28,
                fg_color="#4CAF50", hover_color="#45a049",
                command=self._add_new_material_row
            )
            add_mat_btn.pack(anchor="w", pady=(0, 5))

            self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
            self.materials_frame.pack(fill="x", pady=5)
            for mat in recipe["Materials"]:
                self._add_material_row(mat["Material"], mat["Amount"])

            # Required constructions
            self._create_text_field(
                "DefaultRequiredConstructions",
                ", ".join(recipe["DefaultRequiredConstructions"]),
                label="Required Constructions", autocomplete_key="Constructions"
            )

            # Default Unlocks subsection
            self._create_subsection_header("Default Unlocks")
            self._create_dropdown_field(
                "DefaultUnlocks_UnlockType", recipe["DefaultUnlocks_UnlockType"],
                self._get_options("Enum_EMorRecipeUnlockType", DEFAULT_UNLOCK_TYPE),
                label="Unlock Type"
            )
            self._create_text_field(
                "DefaultUnlocks_NumFragments", str(recipe["DefaultUnlocks_NumFragments"]),
                label="Num Fragments", width=200
            )
            self._create_text_field(
                "DefaultUnlocks_RequiredItems",
                ", ".join(recipe["DefaultUnlocks_RequiredItems"]),
                label="Required Items", autocomplete_key="AllValues"
            )
            self._create_text_field(
                "DefaultUnlocks_RequiredConstructions",
                ", ".join(recipe["DefaultUnlocks_RequiredConstructions"]),
                label="Required Constructions", autocomplete_key="AllValues"
            )
            self._create_text_field(
                "DefaultUnlocks_RequiredFragments",
                ", ".join(recipe["DefaultUnlocks_RequiredFragments"]),
                label="Required Fragments", autocomplete_key="AllValues"
            )

            # Sandbox overrides
            self._create_subsection_header("Sandbox Overrides")
            sandbox_bool_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
            sandbox_bool_frame.pack(fill="x", pady=4)
            self._create_checkbox_field(sandbox_bool_frame, "bHasSandboxRequirementsOverride",
                                        recipe["bHasSandboxRequirementsOverride"])
            self._create_checkbox_field(sandbox_bool_frame, "bHasSandboxUnlockOverride",
                                        recipe["bHasSandboxUnlockOverride"])

            self._create_dropdown_field(
                "SandboxUnlocks_UnlockType", recipe["SandboxUnlocks_UnlockType"],
                self._get_options("Enum_EMorRecipeUnlockType", DEFAULT_UNLOCK_TYPE),
                label="Sandbox Unlock Type"
            )
            self._create_text_field(
                "SandboxUnlocks_NumFragments", str(recipe["SandboxUnlocks_NumFragments"]),
                label="Sandbox Num Fragments", width=200
            )
            self._create_text_field(
                "SandboxUnlocks_RequiredItems",
                ", ".join(recipe["SandboxUnlocks_RequiredItems"]),
                label="Sandbox Required Items", autocomplete_key="AllValues"
            )
            self._create_text_field(
                "SandboxUnlocks_RequiredConstructions",
                ", ".join(recipe.get("SandboxUnlocks_RequiredConstructions", [])),
                label="Sandbox Unlock Req. Constructions", autocomplete_key="AllValues"
            )
            self._create_text_field(
                "SandboxUnlocks_RequiredFragments",
                ", ".join(recipe.get("SandboxUnlocks_RequiredFragments", [])),
                label="Sandbox Unlock Req. Fragments", autocomplete_key="AllValues"
            )

            # Sandbox materials
            self._create_subsection_header("Sandbox Required Materials")
            add_sandbox_mat_btn = ctk.CTkButton(
                self.form_content, text="+ Add Sandbox Material", width=160, height=28,
                fg_color="#4CAF50", hover_color="#45a049",
                command=self._add_new_sandbox_material_row
            )
            add_sandbox_mat_btn.pack(anchor="w", pady=(0, 5))

            self.sandbox_materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
            sandbox_mats = recipe.get("SandboxRequiredMaterials", [])
            if sandbox_mats:
                self.sandbox_materials_frame.pack(fill="x", pady=(0, 5))
                for mat in sandbox_mats:
                    self._add_sandbox_material_row(mat["Material"], mat["Amount"])

            # Sandbox required constructions
            self._create_text_field(
                "SandboxRequiredConstructions",
                ", ".join(recipe.get("SandboxRequiredConstructions", [])),
                label="Sandbox Required Constructions", autocomplete_key="Constructions"
            )

            # Recipe EnabledState
            self._create_dropdown_field(
                "Recipe_EnabledState", recipe["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Recipe Enabled State"
            )

        # ===== SECTION 2: CONSTRUCTION DATA =====
        if construction_json and isinstance(construction_json, dict):
            has_data = True
            construction = extract_construction_fields(construction_json)

            self._create_section_header("Construction Definition", "#4CAF50")

            self._create_text_field("Construction_Name", construction["Name"], label="Row Name")
            self._create_text_field("DisplayName", construction["DisplayName"], label="Display Name")
            self._create_text_field("Description", construction["Description"])
            self._create_text_field("Actor", construction["Actor"],
                                    label="Actor Path", autocomplete_key="Actors")
            # Icon import index (read-only reference)
            icon_val = construction.get("Icon")
            self._create_text_field(
                "Icon", str(icon_val) if icon_val is not None else "",
                label="Icon (Import Index)", readonly=True
            )
            self._create_dropdown_field(
                "Tags",
                construction["Tags"][0] if construction["Tags"] else "",
                self._get_options("Tags", []),
                label="Category Tag"
            )
            self._create_text_field(
                "BackwardCompatibilityActors",
                ", ".join(construction["BackwardCompatibilityActors"]),
                label="Backward Compat Actors", autocomplete_key="Actors"
            )
            self._create_dropdown_field(
                "Construction_EnabledState", construction["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Construction Enabled State"
            )

        if not has_data:
            ctk.CTkLabel(
                self.form_content, text="No construction/building data found.",
                text_color="gray"
            ).pack(anchor="center", pady=40)

    def _create_action_buttons(self):
        """Create Save and other action buttons at the bottom of the form."""
        # Separator
        sep = ctk.CTkFrame(self.form_content, height=2, fg_color="gray50")
        sep.pack(fill="x", pady=(20, 10))


    def _create_section_header(self, text: str, color: str = "#4CAF50"):
        """Create a section header in the form."""
        header_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        header_frame.pack(fill="x", pady=(20, 5), anchor="w")

        header = ctk.CTkLabel(
            header_frame,
            text=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color
        )
        header.pack(side="left")

        # Separator line
        sep = ctk.CTkFrame(self.form_content, height=2, fg_color=color)
        sep.pack(fill="x", pady=(0, 10))

    def _create_subsection_header(self, text: str):
        """Create a subsection header."""
        header = ctk.CTkLabel(
            self.form_content,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray"
        )
        header.pack(fill="x", pady=(10, 5), anchor="w")

    def _create_text_field(self, name: str, value: str, width: int = 600, label: str | None = None,
                           autocomplete_key: str | None = None, readonly: bool = False):
        """Create a text input field with optional autocomplete.

        Args:
            name: Field name for form_vars
            value: Initial value
            width: Width of the entry (default 600 for full width)
            label: Display label (defaults to name)
            autocomplete_key: Key to look up autocomplete suggestions from cached_options
            readonly: If True, field is displayed but not editable
        """
        frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        frame.pack(fill="x", pady=3)

        field_label = ctk.CTkLabel(
            frame,
            text=f"{label or name}:",
            width=140,
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        # Add tooltip if description exists
        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)

        # Use autocomplete entry if suggestions are available (skip for readonly)
        if autocomplete_key and not readonly:
            # Get suggestions directly from cached options (avoid _get_options "(none)" fallback)
            suggestions = self.cached_options.get(autocomplete_key, [])
            if suggestions:
                entry = AutocompleteEntry(
                    frame,
                    textvariable=self.form_vars[name],
                    suggestions=suggestions,
                    width=width
                )
                entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
                return

        # Regular entry (or readonly)
        ctk.CTkEntry(
            frame,
            textvariable=self.form_vars[name],
            width=width,
            state="disabled" if readonly else "normal",
            text_color=("gray50", "gray60") if readonly else ("gray10", "gray90")
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _create_dropdown_field(self, name: str, value: str, options: list[str], label: str | None = None):
        """Create a dropdown field with manual input support (ComboBox)."""
        frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        frame.pack(fill="x", pady=3)

        field_label = ctk.CTkLabel(
            frame,
            text=f"{label or name}:",
            width=120,
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        # Add tooltip if description exists
        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)
        combo = ctk.CTkComboBox(
            frame,
            variable=self.form_vars[name],
            values=options if options else ["(none)"],
            width=350
        )
        combo.pack(side="left", padx=(10, 0))

    def _create_dropdown_field_inline(
        self, parent, name: str, value: str, options: list[str], label: str | None = None
    ):
        """Create an inline dropdown field with manual input support (ComboBox)."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=(0, 20))

        display_label = label if label else name
        field_label = ctk.CTkLabel(
            frame,
            text=f"{display_label}:",
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        # Add tooltip if description exists
        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)
        combo = ctk.CTkComboBox(
            frame,
            variable=self.form_vars[name],
            values=options if options else ["(none)"],
            width=280
        )
        combo.pack(side="left", padx=(5, 0))

    def _create_checkbox_field(self, parent, name: str, value: bool):
        """Create a checkbox field with tooltip."""
        self.form_vars[name] = ctk.BooleanVar(value=value)

        # Get display text (strip leading 'b' from boolean field names)
        display_text = name.replace("b", "", 1) if name.startswith("b") else name

        cb = ctk.CTkCheckBox(
            parent,
            text=display_text,
            variable=self.form_vars[name],
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        cb.pack(side="left", padx=(0, 15))

        # Add tooltip if description exists
        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(cb, FIELD_DESCRIPTIONS[name])

    def _add_material_row(self, material: str = "Item.Wood", amount: int = 1):
        """Add an editable material row with combobox (supports manual input) and amount entry."""
        row_id = len(self.material_rows)
        row_frame = ctk.CTkFrame(self.materials_frame, fg_color=("gray85", "gray20"))
        row_frame.pack(fill="x", pady=2)

        # Material combobox with display names
        raw_options = self._get_options("Materials", ["Item.Wood"])
        if material and material not in raw_options:
            raw_options.insert(0, material)
        material_options = [self._format_material_display(m) for m in raw_options]

        mat_var = ctk.StringVar(value=self._format_material_display(material))
        mat_combo = ctk.CTkComboBox(
            row_frame,
            variable=mat_var,
            values=material_options,
            width=350
        )
        mat_combo.pack(side="left", padx=5, pady=5)

        # Amount label
        ctk.CTkLabel(row_frame, text="x", width=20).pack(side="left")

        # Amount entry (editable)
        amount_var = ctk.StringVar(value=str(amount))
        amount_entry = ctk.CTkEntry(
            row_frame,
            textvariable=amount_var,
            width=60,
            placeholder_text="qty"
        )
        amount_entry.pack(side="left", padx=5)

        # Remove button
        remove_btn = ctk.CTkButton(
            row_frame,
            text="✕",
            width=28,
            height=28,
            fg_color="#f44336",
            hover_color="#d32f2f",
            command=lambda rf=row_frame, rid=row_id: self._remove_material_row(rf, rid)
        )
        remove_btn.pack(side="right", padx=5, pady=5)

        self.material_rows.append({
            "frame": row_frame,
            "material_var": mat_var,
            "amount_var": amount_var
        })

    def _add_new_material_row(self):
        """Add a new empty material row."""
        self._add_material_row("Item.Wood", 1)

    def _remove_material_row(self, row_frame, row_id):  # noqa: ARG002
        """Remove a material row."""
        row_frame.destroy()
        # Mark as removed (don't reindex to avoid issues)
        for row in self.material_rows:
            if row.get("frame") == row_frame:
                row["removed"] = True
                break

    def _add_sandbox_material_row(self, material: str = "Item.Wood", amount: int = 1):
        """Add an editable sandbox material row."""
        row_id = len(self.sandbox_material_rows)
        row_frame = ctk.CTkFrame(self.sandbox_materials_frame, fg_color=("gray85", "gray20"))
        row_frame.pack(fill="x", pady=2)

        raw_options = self._get_options("Materials", ["Item.Wood"])
        if material and material not in raw_options:
            raw_options.insert(0, material)
        material_options = [self._format_material_display(m) for m in raw_options]

        mat_var = ctk.StringVar(value=self._format_material_display(material))
        mat_combo = ctk.CTkComboBox(
            row_frame, variable=mat_var, values=material_options, width=350
        )
        mat_combo.pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(row_frame, text="x", width=20).pack(side="left")

        amount_var = ctk.StringVar(value=str(amount))
        ctk.CTkEntry(
            row_frame, textvariable=amount_var, width=60, placeholder_text="qty"
        ).pack(side="left", padx=5)

        remove_btn = ctk.CTkButton(
            row_frame, text="✕", width=28, height=28,
            fg_color="#f44336", hover_color="#d32f2f",
            command=lambda rf=row_frame, rid=row_id: self._remove_sandbox_material_row(rf, rid)
        )
        remove_btn.pack(side="right", padx=5, pady=5)

        self.sandbox_material_rows.append({
            "frame": row_frame, "material_var": mat_var, "amount_var": amount_var
        })

    def _add_new_sandbox_material_row(self):
        """Add a new empty sandbox material row."""
        if self.sandbox_materials_frame and not self.sandbox_materials_frame.winfo_ismapped():
            self.sandbox_materials_frame.pack(fill="x", pady=(0, 5))
        self._add_sandbox_material_row("Item.Wood", 1)

    def _remove_sandbox_material_row(self, row_frame, row_id):  # noqa: ARG002
        """Remove a sandbox material row."""
        row_frame.destroy()
        for row in self.sandbox_material_rows:
            if row.get("frame") == row_frame:
                row["removed"] = True
                break

    def _save_changes(self):
        """Save form changes back to the cached JSON files."""
        if not self.current_def_data:
            self._set_status("No data loaded to save", is_error=True)
            return

        recipe_json = self.current_def_data.get("recipe_json")
        construction_json = self.current_def_data.get("construction_json")

        if not recipe_json and not construction_json:
            self._set_status("No recipe or construction data to save", is_error=True)
            return

        # Apply form values to in-memory JSON dicts
        if recipe_json:
            self._update_recipe_json(recipe_json)
        if construction_json:
            self._update_construction_json(construction_json)

        # Always save to cache files
        recipes_path = self._get_cache_recipes_path()
        constructions_path = self._get_cache_constructions_path()

        try:
            saved_files = []

            # Update recipe row in cached JSON
            if recipe_json:
                recipe_name = recipe_json.get("Name", "")
                if recipe_name and recipes_path.exists():
                    self._update_row_in_json(recipes_path, recipe_name, recipe_json)
                    saved_files.append("recipes")

            # Update construction row in cached JSON
            if construction_json:
                construction_name = construction_json.get("Name", "")
                if construction_name and constructions_path.exists():
                    self._update_row_in_json(constructions_path, construction_name,
                                             construction_json)
                    saved_files.append("constructions")

            if saved_files:
                self._set_status(f"Saved changes to {', '.join(saved_files)}")
                # Mark the checkbox for this item in the left pane
                self._mark_item_checked_on_save()
                # Add any new field values to the autocomplete index
                self._update_autocomplete_index()
            else:
                self._set_status("No matching rows found in JSON files", is_error=True)

        except (OSError, json.JSONDecodeError) as e:
            logger.error("Error saving changes: %s", e)
            self._set_status(f"Error saving: {e}", is_error=True)

    def _mark_item_checked_on_save(self):
        """Mark the currently selected item's checkbox as checked after a save."""
        # For secrets items, use the recipe name
        if self.current_secrets_recipe_name:
            check_var = self.construction_check_vars.get(self.current_secrets_recipe_name)
            if check_var:
                check_var.set(True)
                self._save_checked_states_to_ini()

    def _update_autocomplete_index(self):
        """Extract new values from the current form and add them to the autocomplete index.

        Maps form fields to their autocomplete keys and adds any new values
        found. Persists the updated index to the cache INI file.
        """
        # Field name -> autocomplete key mapping for comma-separated text fields
        field_to_key = {
            "ResultConstructionHandle": "ResultConstructions",
            "DefaultRequiredConstructions": "Constructions",
            "SandboxRequiredConstructions": "Constructions",
            "Actor": "Actors",
            "BackwardCompatibilityActors": "Actors",
        }

        changed = False
        for field_name, ac_key in field_to_key.items():
            if field_name not in self.form_vars:
                continue
            raw = self.form_vars[field_name].get().strip()
            if not raw:
                continue

            # Split comma-separated values and clean
            values = [v.strip() for v in raw.split(",") if v.strip()]

            if ac_key not in self.cached_options:
                self.cached_options[ac_key] = []

            existing = set(self.cached_options[ac_key])
            for val in values:
                if val not in existing:
                    existing.add(val)
                    changed = True
            self.cached_options[ac_key] = sorted(existing)

        # Add material names from material rows
        for row in getattr(self, 'material_rows', []):
            if row.get("removed"):
                continue
            mat_name = row["material_var"].get().strip()
            if mat_name:
                if "Materials" not in self.cached_options:
                    self.cached_options["Materials"] = []
                existing = set(self.cached_options["Materials"])
                if mat_name not in existing:
                    existing.add(mat_name)
                    self.cached_options["Materials"] = sorted(existing)
                    changed = True

        # Add Tags value
        if "Tags" in self.form_vars:
            tag = self.form_vars["Tags"].get().strip()
            if tag:
                if "Tags" not in self.cached_options:
                    self.cached_options["Tags"] = []
                existing = set(self.cached_options["Tags"])
                if tag not in existing:
                    existing.add(tag)
                    self.cached_options["Tags"] = sorted(existing)
                    changed = True

        if changed:
            # Rebuild AllValues
            all_values = set()
            for values in self.cached_options.values():
                all_values.update(values)
            self.cached_options["AllValues"] = sorted(all_values)

            # Persist to cache file
            buildings_dir = get_buildings_dir()
            cache_path = buildings_dir / CACHE_FILENAME
            _save_cached_options(cache_path, self.cached_options)
            logger.info("Updated autocomplete index with new values")

    def _update_row_in_json(self, json_path: Path, row_name: str, updated_row: dict):
        """Replace a row in a JSON file's Table.Data by matching Name.

        Args:
            json_path: Path to the JSON file
            row_name: Name of the row to replace
            updated_row: The updated row dict
        """
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        exports = data.get('Exports', [])
        if not exports:
            return

        table = exports[0].get('Table', {})
        rows = table.get('Data', [])

        for i, row in enumerate(rows):
            if row.get('Name') == row_name:
                rows[i] = updated_row
                break

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # -------------------------------------------------------------------------
    # JSON DATA UPDATE METHODS
    # -------------------------------------------------------------------------
    # These methods update the in-memory JSON structures with values from
    # the form fields before saving back to the source JSON files.
    # -------------------------------------------------------------------------

    def _update_recipe_json(self, recipe_json: dict):
        """Update recipe JSON structure with current form values."""
        for prop in recipe_json.get("Value", []):
            prop_name = prop.get("Name", "")
            prop_type = prop.get("$type", "")

            # Update enum fields (dropdowns)
            if "EnumPropertyData" in prop_type:
                if prop_name in self.form_vars:
                    prop["Value"] = self.form_vars[prop_name].get()
                elif prop_name == "EnabledState" and "Recipe_EnabledState" in self.form_vars:
                    prop["Value"] = self.form_vars["Recipe_EnabledState"].get()

            # Update boolean fields (checkboxes)
            elif "BoolPropertyData" in prop_type:
                if prop_name in self.form_vars:
                    prop["Value"] = self.form_vars[prop_name].get()

            # Update float fields
            elif "FloatPropertyData" in prop_type:
                if prop_name in self.form_vars:
                    try:
                        prop["Value"] = float(self.form_vars[prop_name].get())
                    except ValueError:
                        pass

            # Update int fields
            elif "IntPropertyData" in prop_type:
                if prop_name in self.form_vars:
                    try:
                        prop["Value"] = int(self.form_vars[prop_name].get())
                    except ValueError:
                        pass

            # Update ResultConstructionHandle
            elif prop_name == "ResultConstructionHandle":
                if "ResultConstructionHandle" in self.form_vars:
                    for handle_prop in prop.get("Value", []):
                        if handle_prop.get("Name") == "RowName":
                            handle_prop["Value"] = self.form_vars["ResultConstructionHandle"].get()

            # Update materials array
            elif prop_name == "DefaultRequiredMaterials":
                new_materials = []
                for row in self.material_rows:
                    if row.get("removed"):
                        continue
                    mat_name = self._parse_material_name(row["material_var"].get())
                    try:
                        mat_amount = int(row["amount_var"].get())
                    except ValueError:
                        mat_amount = 1
                    new_materials.append(self._build_material_entry(mat_name, mat_amount))
                prop["Value"] = new_materials

            # Update DefaultRequiredConstructions
            elif prop_name == "DefaultRequiredConstructions":
                if "DefaultRequiredConstructions" in self.form_vars:
                    const_str = self.form_vars["DefaultRequiredConstructions"].get().strip()
                    if const_str:
                        constructions = [c.strip() for c in const_str.split(",") if c.strip()]
                        prop["Value"] = self._build_unlock_required_constructions(constructions)
                    else:
                        prop["Value"] = []

            # Update DefaultUnlocks
            elif prop_name == "DefaultUnlocks":
                self._update_unlock_struct(prop, "DefaultUnlocks")

            # Update SandboxUnlocks
            elif prop_name == "SandboxUnlocks":
                self._update_unlock_struct(prop, "SandboxUnlocks")

            # Update SandboxRequiredMaterials
            elif prop_name == "SandboxRequiredMaterials":
                new_materials = []
                for row in self.sandbox_material_rows:
                    if row.get("removed"):
                        continue
                    mat_name = self._parse_material_name(row["material_var"].get())
                    try:
                        mat_amount = int(row["amount_var"].get())
                    except ValueError:
                        mat_amount = 1
                    entry = self._build_material_entry(mat_name, mat_amount)
                    entry["Name"] = "SandboxRequiredMaterials"
                    new_materials.append(entry)
                prop["Value"] = new_materials

            # Update SandboxRequiredConstructions
            elif prop_name == "SandboxRequiredConstructions":
                if "SandboxRequiredConstructions" in self.form_vars:
                    const_str = self.form_vars["SandboxRequiredConstructions"].get().strip()
                    if const_str:
                        constructions = [c.strip() for c in const_str.split(",") if c.strip()]
                        prop["Value"] = self._build_unlock_required_constructions(constructions)
                    else:
                        prop["Value"] = []

    def _update_unlock_struct(self, prop: dict, prefix: str):
        """Update an unlock struct (DefaultUnlocks or SandboxUnlocks) from form_vars."""
        for unlock_prop in prop.get("Value", []):
            unlock_name = unlock_prop.get("Name", "")
            unlock_type = unlock_prop.get("$type", "")

            if unlock_name == "UnlockType" and "EnumPropertyData" in unlock_type:
                key = f"{prefix}_UnlockType"
                if key in self.form_vars:
                    unlock_prop["Value"] = self.form_vars[key].get()

            elif unlock_name == "NumFragments":
                key = f"{prefix}_NumFragments"
                if key in self.form_vars:
                    try:
                        unlock_prop["Value"] = int(self.form_vars[key].get())
                    except ValueError:
                        unlock_prop["Value"] = 1

            elif unlock_name == "UnlockRequiredItems":
                key = f"{prefix}_RequiredItems"
                if key in self.form_vars:
                    items_str = self.form_vars[key].get().strip()
                    if items_str:
                        items = [i.strip() for i in items_str.split(",") if i.strip()]
                        unlock_prop["Value"] = self._build_unlock_required_items(items)
                    else:
                        unlock_prop["Value"] = []

            elif unlock_name == "UnlockRequiredConstructions":
                key = f"{prefix}_RequiredConstructions"
                if key in self.form_vars:
                    const_str = self.form_vars[key].get().strip()
                    if const_str:
                        constructions = [c.strip() for c in const_str.split(",") if c.strip()]
                        unlock_prop["Value"] = self._build_unlock_required_constructions(constructions)
                    else:
                        unlock_prop["Value"] = []

            elif unlock_name == "UnlockRequiredFragments":
                key = f"{prefix}_RequiredFragments"
                if key in self.form_vars:
                    frag_str = self.form_vars[key].get().strip()
                    if frag_str:
                        fragments = [f.strip() for f in frag_str.split(",") if f.strip()]
                        unlock_prop["Value"] = self._build_unlock_required_items(fragments)
                    else:
                        unlock_prop["Value"] = []

    def _update_construction_json(self, construction_json: dict):
        """Update construction JSON with form values."""
        for prop in construction_json.get("Value", []):
            prop_name = prop.get("Name", "")
            prop_type = prop.get("$type", "")

            if prop_name == "DisplayName" and "TextPropertyData" in prop_type:
                if "DisplayName" in self.form_vars:
                    prop["Value"] = self.form_vars["DisplayName"].get()

            elif prop_name == "Description" and "TextPropertyData" in prop_type:
                if "Description" in self.form_vars:
                    prop["Value"] = self.form_vars["Description"].get()

            elif prop_name == "Tags":
                if "Tags" in self.form_vars:
                    tag_val = self.form_vars["Tags"].get()
                    for tag_prop in prop.get("Value", []):
                        if tag_prop.get("Name") == "Tags":
                            tag_prop["Value"] = [tag_val] if tag_val else []

            elif prop_name == "EnabledState" and "EnumPropertyData" in prop_type:
                if "Construction_EnabledState" in self.form_vars:
                    prop["Value"] = self.form_vars["Construction_EnabledState"].get()

    def _build_material_entry(self, material_name: str, amount: int) -> dict:
        """Build a material entry structure for the recipe JSON."""
        return {
            "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
            "Name": "DefaultRequiredMaterials",
            "StructType": "FConstructionMaterial",
            "Value": [
                {
                    "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                    "Name": "MaterialHandle",
                    "StructType": "FDataTableRowHandle",
                    "Value": [
                        {
                            "$type": "UAssetAPI.PropertyTypes.Objects.ObjectPropertyData, UAssetAPI",
                            "Name": "DataTable",
                            "Value": 0
                        },
                        {
                            "$type": "UAssetAPI.PropertyTypes.Structs.NamePropertyData, UAssetAPI",
                            "Name": "RowName",
                            "Value": material_name
                        }
                    ]
                },
                {
                    "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI",
                    "Name": "Count",
                    "Value": amount
                }
            ]
        }

    def _build_unlock_required_items(self, items: list[str]) -> list[dict]:
        """Build unlock required items structure for the recipe JSON."""
        result = []
        for item in items:
            result.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "MorAnyItemRowHandle",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "UnlockRequiredItems",
                "ArrayIndex": 0,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTagExtensions": "NoExtension",
                "Value": [{
                    "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                    "Name": "RowName",
                    "ArrayIndex": 0,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTagExtensions": "NoExtension",
                    "Value": item
                }]
            })
        return result

    def _build_unlock_required_constructions(self, constructions: list[str]) -> list[dict]:
        """Build unlock required constructions structure for the recipe JSON."""
        result = []
        for construction in constructions:
            result.append({
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "StructType": "MorConstructionRowHandle",
                "SerializeNone": True,
                "StructGUID": "{00000000-0000-0000-0000-000000000000}",
                "SerializationControl": "NoExtension",
                "Operation": "None",
                "Name": "UnlockRequiredConstructions",
                "ArrayIndex": 0,
                "IsZero": False,
                "PropertyTagFlags": "None",
                "PropertyTagExtensions": "NoExtension",
                "Value": [{
                    "$type": "UAssetAPI.PropertyTypes.Objects.NamePropertyData, UAssetAPI",
                    "Name": "RowName",
                    "ArrayIndex": 0,
                    "IsZero": False,
                    "PropertyTagFlags": "None",
                    "PropertyTagExtensions": "NoExtension",
                    "Value": construction
                }]
            })
        return result

    def _set_status(self, message: str, is_error: bool = False):
        """Set status message via callback."""
        if self.on_status_message:
            self.on_status_message(message, is_error)

    def _go_back(self):
        """Go back to the main mod builder view."""
        if self.on_back:
            self.on_back()

    def _import_construction(self):
        """Import constructions from game JSON files.

        Opens a dialog that allows users to:
        1. Select a directory containing DT_Constructions.json and DT_ConstructionRecipes.json
        2. Browse and select constructions to import
        3. Generate .def files for the selected constructions
        """
        from src.ui.import_construction_dialog import show_import_construction_dialog  # pylint: disable=import-outside-toplevel

        # Show the import dialog, passing a callback to refresh the list when done
        show_import_construction_dialog(
            self.winfo_toplevel(),
            on_complete=self._refresh_building_list
        )

    # -------------------------------------------------------------------------
    # SECRETS SOURCE LOADING FUNCTIONS
    # -------------------------------------------------------------------------

    @staticmethod
    def _get_cache_dir() -> Path:
        """Get path to the buildings cache directory."""
        return get_appdata_dir() / 'cache' / 'buildings'

    def _get_cache_recipes_path(self) -> Path:
        """Get path to cached DT_ConstructionRecipes.json."""
        return self._get_cache_dir() / 'DT_ConstructionRecipes.json'

    def _get_cache_constructions_path(self) -> Path:
        """Get path to cached DT_Constructions.json."""
        return self._get_cache_dir() / 'DT_Constructions.json'

    def _ensure_cache_files(self):
        """Copy Secrets Source building JSONs to cache if not already cached.

        Copies from Secrets Source to %APPDATA%/MoriaMODCreator/cache/buildings/.
        Only copies if cache files don't exist yet (use _refresh_cache to force).
        """
        cache_dir = self._get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        src_recipes = self._get_secrets_recipes_path()
        src_constructions = self._get_secrets_constructions_path()
        cache_recipes = self._get_cache_recipes_path()
        cache_constructions = self._get_cache_constructions_path()

        if src_recipes.exists() and not cache_recipes.exists():
            shutil.copy2(src_recipes, cache_recipes)
            logger.info("Cached %s", cache_recipes.name)

        if src_constructions.exists() and not cache_constructions.exists():
            shutil.copy2(src_constructions, cache_constructions)
            logger.info("Cached %s", cache_constructions.name)

    def _refresh_cache(self):
        """Force-refresh cache by deleting old cache and re-copying from Secrets Source."""
        cache_dir = self._get_cache_dir()

        # Delete the entire cache directory to start fresh
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            logger.info("Deleted cache directory: %s", cache_dir)

        cache_dir.mkdir(parents=True, exist_ok=True)

        src_recipes = self._get_secrets_recipes_path()
        src_constructions = self._get_secrets_constructions_path()

        if src_recipes.exists():
            shutil.copy2(src_recipes, self._get_cache_recipes_path())
            logger.info("Refreshed cache: %s", src_recipes.name)

        if src_constructions.exists():
            shutil.copy2(src_constructions, self._get_cache_constructions_path())
            logger.info("Refreshed cache: %s", src_constructions.name)

    def _get_checked_ini_path(self) -> Path:
        """Get path to checked_items.ini in the cache directory."""
        return self._get_cache_dir() / 'checked_items.ini'

    def _save_checked_states_to_ini(self):
        """Save current checkbox states to INI file in the cache folder."""
        ini_path = self._get_checked_ini_path()
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case

        checked_names = [
            name for name, check_var in self.construction_check_vars.items()
            if check_var.get()
        ]
        config['CheckedItems'] = {name: 'true' for name in checked_names}

        ini_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ini_path, 'w', encoding='utf-8') as f:
            config.write(f)

    def _load_checked_states_from_ini(self) -> set:
        """Load checked item names from INI file in the cache folder.

        Returns:
            Set of recipe names that were previously checked.
        """
        ini_path = self._get_checked_ini_path()
        if not ini_path.exists():
            return set()

        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case

        try:
            config.read(ini_path, encoding='utf-8')
            if 'CheckedItems' in config:
                return {name for name, val in config['CheckedItems'].items()
                        if val.lower() == 'true'}
        except (OSError, configparser.Error) as e:
            logger.error("Error loading checked states: %s", e)

        return set()

    def _get_secrets_recipes_path(self) -> Path:
        """Get path to DT_ConstructionRecipes.json in Secrets Source (original)."""
        return (get_appdata_dir() / 'Secrets Source' / 'jsondata' / 'Moria'
                / 'Content' / 'Tech' / 'Data' / 'Building' / 'DT_ConstructionRecipes.json')

    def _get_secrets_constructions_path(self) -> Path:
        """Get path to DT_Constructions.json in Secrets Source (original)."""
        return (get_appdata_dir() / 'Secrets Source' / 'jsondata' / 'Moria'
                / 'Content' / 'Tech' / 'Data' / 'Building' / 'DT_Constructions.json')

    def _get_game_recipes_path(self) -> Path:
        """Get path to DT_ConstructionRecipes.json in game output."""
        return (get_appdata_dir() / 'output' / 'jsondata' / 'Moria' / 'Content'
                / 'Tech' / 'Data' / 'Building' / 'DT_ConstructionRecipes.json')

    def _get_game_constructions_path(self) -> Path:
        """Get path to DT_Constructions.json in game output."""
        return (get_appdata_dir() / 'output' / 'jsondata' / 'Moria' / 'Content'
                / 'Tech' / 'Data' / 'Building' / 'DT_Constructions.json')

    def _get_string_tables_dir(self) -> Path:
        """Get path to the StringTables directory in Secrets Source."""
        return (get_appdata_dir() / 'Secrets Source' / 'jsondata' / 'Moria'
                / 'Content' / 'Mods' / 'Tech' / 'Data' / 'StringTables')

    def _load_string_table(self) -> dict:
        """Load string tables from all ST_*.json files.

        The string table files use the KeysToEntries format:
        [{"StringTable": {"KeysToEntries": {"GameName.Name": "Display Name", ...}}}]

        Returns:
            Dict mapping internal names to {"name": display_name, "description": desc}
        """
        string_table = {}
        st_dir = self._get_string_tables_dir()

        if not st_dir.exists():
            logger.debug("StringTables directory not found: %s", st_dir)
            return string_table

        st_files = list(st_dir.glob("ST_*.json"))
        if not st_files:
            logger.debug("No ST_*.json files found in %s", st_dir)
            return string_table

        for st_path in st_files:
            try:
                with open(st_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Handle array format [{"StringTable": {...}}]
                if isinstance(data, list) and data:
                    entries_obj = data[0]
                elif isinstance(data, dict):
                    entries_obj = data
                else:
                    continue

                keys_to_entries = (entries_obj
                                   .get("StringTable", {})
                                   .get("KeysToEntries", {}))

                if not keys_to_entries:
                    continue

                # Parse "GameName.Name" and "GameName.Description" entries
                for key, value in keys_to_entries.items():
                    if "." not in key:
                        continue
                    # Split on last dot: "GameName.Name" or "GameName.Description"
                    game_name, field_type = key.rsplit(".", 1)

                    if game_name not in string_table:
                        string_table[game_name] = {"name": "", "description": ""}

                    if field_type == "Name":
                        string_table[game_name]["name"] = value
                    elif field_type == "Description":
                        string_table[game_name]["description"] = value

            except (json.JSONDecodeError, OSError, KeyError, TypeError) as e:
                logger.error("Error loading string table %s: %s", st_path.name, e)

        logger.info("Loaded %s display names from %s string table files",
                     len(string_table), len(st_files))
        return string_table

    def _lookup_game_name(self, internal_name: str) -> str:
        """Look up the game display name for an internal recipe name.

        Args:
            internal_name: The internal recipe/construction name

        Returns:
            The display name if found, otherwise the internal name
        """
        entry = self.string_table.get(internal_name)
        if entry and entry.get("name"):
            return entry["name"]
        return internal_name

    def _lookup_game_description(self, internal_name: str) -> str:
        """Look up the game description for an internal recipe name.

        Args:
            internal_name: The internal recipe/construction name

        Returns:
            The description if found, otherwise empty string
        """
        entry = self.string_table.get(internal_name)
        if entry and entry.get("description"):
            return entry["description"]
        return ""

    def _get_material_display_name(self, internal_name: str) -> str:
        """Get a display name for a material.

        Checks string table first, then strips prefix (e.g., Item.Wood → Wood).
        """
        # Check string table
        entry = self.string_table.get(internal_name)
        if entry and entry.get("name"):
            return entry["name"]
        # Strip prefix (Item.Wood → Wood, Ore.Iron → Iron)
        if "." in internal_name:
            return internal_name.split(".", 1)[1]
        return internal_name

    def _format_material_display(self, internal_name: str) -> str:
        """Format material as 'Display Name (InternalName)'."""
        display = self._get_material_display_name(internal_name)
        if display != internal_name:
            return f"{display} ({internal_name})"
        return internal_name

    @staticmethod
    def _parse_material_name(display_text: str) -> str:
        """Extract internal name from 'Display Name (InternalName)' format."""
        if "(" in display_text and display_text.endswith(")"):
            return display_text[display_text.rindex("(") + 1:-1].strip()
        return display_text.strip()

    def _load_recipes_from_json(self, json_path: Path) -> dict:
        """Load recipe data from a DT_ConstructionRecipes.json file.

        Args:
            json_path: Path to the JSON file

        Returns:
            Dict mapping recipe names to their full row data (with Name and Value)
        """
        recipes = {}
        if not json_path.exists():
            logger.warning("Recipes file not found: %s", json_path)
            return recipes

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Get the exports - typically there's one export with all the rows
            exports = data.get('Exports', [])
            if not exports:
                return recipes

            # The first export should be the DataTable
            export = exports[0]

            # Check for Table.Data property first (game output format from UAssetGUI)
            table = export.get('Table', {})
            if isinstance(table, dict):
                table_data = table.get('Data', [])
                if table_data:
                    for row in table_data:
                        row_name = row.get('Name', '')
                        if row_name and not row_name.startswith('$'):
                            recipes[row_name] = row
                    logger.info("Loaded %s recipes from %s (Table.Data)", len(recipes), json_path.name)
                    return recipes

            # Fallback to Table as array (older format)
            if isinstance(table, list) and table:
                for row in table:
                    row_name = row.get('Name', '')
                    if row_name and not row_name.startswith('$'):
                        recipes[row_name] = row
                logger.info("Loaded %s recipes from %s (Table)", len(recipes), json_path.name)
                return recipes

            # Fallback to Data property for older format
            export_data = export.get('Data', [])
            for item in export_data:
                if item.get('Name') == 'RowStruct':
                    continue
                row_name = item.get('Name', '')
                if row_name and not row_name.startswith('$'):
                    recipes[row_name] = item

            # If still no rows found, use NameMap for recipe names (minimal data)
            if not recipes:
                name_map = data.get('NameMap', [])
                for name in name_map:
                    if name.startswith('/') or name.startswith('$'):
                        continue
                    if name in ('ArrayProperty', 'BoolProperty', 'IntProperty',
                               'FloatProperty', 'StructProperty', 'ObjectProperty',
                               'EnumProperty', 'NameProperty', 'None', 'Object',
                               'RowStruct', 'RowName', 'DataTable'):
                        continue
                    if '::' in name:
                        continue
                    if 'Blueprint' in name or 'Actor' in name:
                        continue
                    if name and name[0].isupper():
                        recipes[name] = {'Name': name, 'Value': []}

            logger.info("Loaded %s recipes from %s", len(recipes), json_path.name)

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error loading recipes from %s: %s", json_path, e)

        return recipes

    def _load_constructions_from_json(self, json_path: Path) -> dict:
        """Load construction data from a DT_Constructions.json file.

        Args:
            json_path: Path to the JSON file

        Returns:
            Dict mapping construction names to their full row data
        """
        constructions = {}
        if not json_path.exists():
            logger.warning("Constructions file not found: %s", json_path)
            return constructions

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Same structure as recipes
            exports = data.get('Exports', [])
            if not exports:
                return constructions

            export = exports[0]

            # Check for Table.Data property first (game output format from UAssetGUI)
            table = export.get('Table', {})
            if isinstance(table, dict):
                table_data = table.get('Data', [])
                if table_data:
                    for row in table_data:
                        row_name = row.get('Name', '')
                        if row_name and not row_name.startswith('$'):
                            constructions[row_name] = row
                    logger.info("Loaded %s constructions from %s (Table.Data)", len(constructions), json_path.name)
                    return constructions

            # Fallback to Table as array
            if isinstance(table, list) and table:
                for row in table:
                    row_name = row.get('Name', '')
                    if row_name and not row_name.startswith('$'):
                        constructions[row_name] = row
                logger.info("Loaded %s constructions from %s (Table)", len(constructions), json_path.name)
                return constructions

            # Fallback to Data property
            export_data = export.get('Data', [])
            for item in export_data:
                if item.get('Name') == 'RowStruct':
                    continue
                row_name = item.get('Name', '')
                if row_name and not row_name.startswith('$'):
                    constructions[row_name] = item

            # Fallback to NameMap
            if not constructions:
                name_map = data.get('NameMap', [])
                for name in name_map:
                    if name.startswith('/') or name.startswith('$'):
                        continue
                    if name in ('ArrayProperty', 'BoolProperty', 'IntProperty',
                               'FloatProperty', 'StructProperty', 'ObjectProperty',
                               'EnumProperty', 'NameProperty', 'None', 'Object',
                               'RowStruct', 'RowName', 'DataTable'):
                        continue
                    if '::' in name:
                        continue
                    if 'Blueprint' in name or 'Actor' in name:
                        continue
                    if name and name[0].isupper():
                        constructions[name] = {'Name': name, 'Value': []}

            logger.info("Loaded %s constructions from %s", len(constructions), json_path.name)

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error loading constructions from %s: %s", json_path, e)

        return constructions

    def _load_secrets_buildings(self):
        """Load building recipes from Secrets mod, showing only mod-added items.

        Shows items that exist in BOTH:
        - New recipes (in Secret Recipe but not in Game Recipe)
        - New constructions (in Secret Constructions but not in Game Constructions)

        This ensures we only show complete building definitions with both
        a recipe and a construction entry. All operations use cached copies.
        """
        self.view_mode = 'buildings'
        self._set_status("Loading Secrets buildings...")

        # Ensure cache files exist (copies from Secrets Source if needed)
        self._ensure_cache_files()

        # Get names from cache and game JSON files using Table.Data structure
        secret_recipe_names = self._get_names_from_table_data(self._get_cache_recipes_path())
        game_recipe_names = self._get_names_from_table_data(self._get_game_recipes_path())
        secret_construction_names = self._get_names_from_table_data(self._get_cache_constructions_path())
        game_construction_names = self._get_names_from_table_data(self._get_game_constructions_path())

        # Find NEW items (in Secret but not in Game)
        new_recipes = secret_recipe_names - game_recipe_names
        new_constructions = secret_construction_names - game_construction_names

        # Find MATCHING items (in both new recipes AND new constructions)
        matching_items = new_recipes & new_constructions

        logger.info("New recipes: %s, New constructions: %s, Matching: %s", len(new_recipes), len(new_constructions), len(matching_items))

        # Build secrets_recipes dict for the matching items
        self.secrets_recipes = {}
        for name in matching_items:
            self.secrets_recipes[name] = {'Name': name}

        # Store for reference
        self.game_recipe_names = game_recipe_names
        self.secrets_constructions = {name: {'Name': name} for name in matching_items}

        if not self.secrets_recipes:
            self._set_status("No mod-unique buildings found in Secrets Source")
        else:
            self._set_status(f"Found {len(self.secrets_recipes)} mod buildings")

        # Update the list with matching items
        self._populate_secrets_list(self.secrets_recipes)

    def _get_names_from_table_data(self, json_path: Path) -> set:
        """Extract names from Exports[0].Table.Data[*].Name in a JSON file.

        Args:
            json_path: Path to the JSON file

        Returns:
            Set of names found in the table data
        """
        names = set()
        if not json_path.exists():
            logger.warning("File not found: %s", json_path)
            return names

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            exports = data.get('Exports', [])
            if exports:
                table = exports[0].get('Table', {})
                rows = table.get('Data', [])
                for row in rows:
                    row_name = row.get('Name')
                    if row_name:
                        names.add(row_name)

            logger.info("Found %s names in %s", len(names), json_path.name)

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error reading names from %s: %s", json_path, e)

        return names

    def _get_row_by_name(self, json_path: Path, name: str) -> dict:
        """Get a specific row from a JSON file by name.

        Args:
            json_path: Path to the JSON file
            name: Name of the row to find

        Returns:
            The row dict if found, empty dict otherwise
        """
        if not json_path.exists():
            return {}

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            exports = data.get('Exports', [])
            if exports:
                table = exports[0].get('Table', {})
                rows = table.get('Data', [])
                for row in rows:
                    if row.get('Name') == name:
                        return row

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error reading row %s from %s: %s", name, json_path, e)

        return {}

    def _get_recipe_names_from_namemap(self, json_path: Path) -> set:
        """Extract recipe/construction names from a JSON file's NameMap.

        This is useful for Secrets Source files which have names in NameMap
        but no full row data (data is in binary Extras field).

        Args:
            json_path: Path to the JSON file

        Returns:
            Set of recipe/construction names
        """
        names = set()
        if not json_path.exists():
            return names

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            name_map = data.get('NameMap', [])
            for name in name_map:
                # Skip system names and property types
                if name.startswith('/') or name.startswith('$'):
                    continue
                if name in ('ArrayProperty', 'BoolProperty', 'IntProperty',
                           'FloatProperty', 'StructProperty', 'ObjectProperty',
                           'EnumProperty', 'NameProperty', 'None', 'Object',
                           'RowStruct', 'RowName', 'DataTable', 'MorConstructionRecipeDefinition',
                           'MorConstructionDefinition', 'MorConstructionRowHandle',
                           'MorRequiredRecipeMaterial', 'MorRecipeUnlock', 'MorItemRowHandle'):
                    continue
                # Skip enum values
                if '::' in name:
                    continue
                # Skip paths
                if '/' in name:
                    continue
                # Likely a recipe/construction name if it starts with uppercase
                if name and name[0].isupper() and '_' in name:
                    names.add(name)

            logger.info("Found %s names in NameMap from %s", len(names), json_path.name)

        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.error("Error reading NameMap from %s: %s", json_path, e)

        return names

    def _load_secrets_weapons(self):
        """Placeholder for loading weapons from Secrets Source."""
        self.view_mode = 'weapons'
        self._set_status("Weapons loading not yet implemented")
        # Clear the list
        for widget in self.building_list.winfo_children():
            widget.destroy()
        self.building_list_items.clear()
        self.count_label.configure(text="0 items")

    def _load_secrets_armor(self):
        """Placeholder for loading armor from Secrets Source."""
        self.view_mode = 'armor'
        self._set_status("Armor loading not yet implemented")
        # Clear the list
        for widget in self.building_list.winfo_children():
            widget.destroy()
        self.building_list_items.clear()
        self.count_label.configure(text="0 items")

    def _populate_secrets_list(self, recipes: dict):
        """Populate the left pane with secrets recipes.

        Args:
            recipes: Dict mapping recipe names to their data
        """
        # Clear existing list
        for widget in self.building_list.winfo_children():
            widget.destroy()
        self.building_list_items.clear()
        self.construction_checkboxes.clear()
        self.construction_check_vars.clear()

        # Update count
        self.count_label.configure(text=f"{len(recipes)} Secrets items")

        if not recipes:
            no_files_label = ctk.CTkLabel(
                self.building_list,
                text="No Secrets buildings found\n\nRun Import Secrets first\nto load mod source files",
                text_color="gray"
            )
            no_files_label.pack(pady=20)
            return

        # Sort recipe names alphabetically by game name
        sorted_names = sorted(recipes.keys(), key=lambda n: self._lookup_game_name(n).lower())

        # Create entry for each recipe
        for recipe_name in sorted_names:
            row_frame = ctk.CTkFrame(self.building_list, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)

            # Checkbox for selection
            check_var = ctk.BooleanVar(value=False)
            checkbox = ctk.CTkCheckBox(
                row_frame,
                text="",
                variable=check_var,
                width=20,
                command=lambda n=recipe_name: self._on_secrets_checkbox_toggle(n)
            )
            checkbox.pack(side="left")

            # Store checkbox references using recipe name as key
            self.construction_checkboxes[recipe_name] = checkbox
            self.construction_check_vars[recipe_name] = check_var

            # Display game name with internal name in parentheses
            display_name = self._lookup_game_name(recipe_name)
            label_text = (f"{display_name} ({recipe_name})"
                          if display_name != recipe_name else recipe_name)

            file_label = ctk.CTkLabel(
                row_frame,
                text=label_text,
                anchor="w",
                cursor="hand2",
                text_color=("gray10", "#E8E8E8")
            )
            file_label.pack(side="left", fill="x", expand=True, padx=5)
            file_label.bind("<Button-1>", lambda e, n=recipe_name: self._load_secrets_recipe(n))
            row_frame.bind("<Button-1>", lambda e, n=recipe_name: self._load_secrets_recipe(n))

            # Store reference for highlighting (using recipe_name as key)
            # Also store label_text for filtering
            self.building_list_items[recipe_name] = (row_frame, file_label, label_text)

            # Hover effect
            file_label.bind("<Enter>", lambda e, n=recipe_name, lbl=file_label: self._on_secrets_item_hover(n, lbl, True))
            file_label.bind("<Leave>", lambda e, n=recipe_name, lbl=file_label: self._on_secrets_item_hover(n, lbl, False))

        # Restore checked states from INI
        checked_names = self._load_checked_states_from_ini()
        for name in checked_names:
            check_var = self.construction_check_vars.get(name)
            if check_var:
                check_var.set(True)

        # Apply any active filter
        self._filter_secrets_list()

    def _filter_secrets_list(self):
        """Filter the secrets list based on search text."""
        if not self.def_search_var:
            return

        filter_text = self.def_search_var.get().lower().strip()

        visible_count = 0
        for name, item_data in self.building_list_items.items():
            # Handle both old format (2-tuple) and new format (3-tuple with display name)
            if len(item_data) == 3:
                row_frame, _, display_name = item_data
                # Search both internal name and display name
                searchable = f"{str(name).lower()} {display_name.lower()}"
            else:
                row_frame, _ = item_data
                searchable = str(name).lower() if not isinstance(name, Path) else name.stem.lower()

            if not filter_text or filter_text in searchable:
                row_frame.pack(fill="x", pady=1)
                visible_count += 1
            else:
                row_frame.pack_forget()

        # Update count label
        total = len(self.building_list_items)
        if filter_text:
            self.count_label.configure(text=f"{visible_count} of {total} items")
        else:
            mode_label = "Secrets items" if self.view_mode in ('buildings', 'weapons', 'armor') else "definitions"
            self.count_label.configure(text=f"{total} {mode_label}")

    def _on_secrets_item_hover(self, recipe_name: str, label: ctk.CTkLabel, entering: bool):
        """Handle hover effect on secrets list items."""
        if recipe_name == self.current_secrets_recipe_name:
            return

        if entering:
            label.configure(text_color="#4CAF50")
        else:
            label.configure(text_color=("gray10", "#E8E8E8"))

    def _load_secrets_recipe(self, recipe_name: str):
        """Load a secrets recipe and display it in the form.

        Args:
            recipe_name: Name of the recipe to load
        """
        self.current_secrets_recipe_name = recipe_name
        self._highlight_secrets_item(recipe_name)

        # Load full row data from the cached JSON files
        recipe_row = self._get_row_by_name(self._get_cache_recipes_path(), recipe_name)
        construction_row = self._get_row_by_name(self._get_cache_constructions_path(), recipe_name)

        # Extract fields from the row data
        recipe_fields = self._extract_secrets_recipe_fields(recipe_row) if recipe_row else {}
        construction_fields = self._extract_secrets_construction_fields(construction_row) if construction_row else {}

        # Build a combined data structure
        display_name = self._lookup_game_name(recipe_name)
        self.current_def_data = {
            'recipe_json': recipe_row,
            'construction_json': construction_row,
            'recipe_fields': recipe_fields,
            'construction_fields': construction_fields,
            'is_secrets_item': True,
            'title': display_name,
            'author': 'Secrets of Khazad-dum',
            'description': f'Internal name: {recipe_name}',
        }
        self.current_def_path = None  # No file path for secrets items

        self._show_form()
        self._set_status(f"Loaded Secrets: {recipe_name}")

    def _highlight_secrets_item(self, selected_name: str):
        """Highlight the selected item in the secrets list."""
        for name, item_data in self.building_list_items.items():
            # Handle both old format (2-tuple) and new format (3-tuple)
            if len(item_data) == 3:
                row_frame, file_label, _ = item_data
            else:
                row_frame, file_label = item_data

            if name == selected_name:
                row_frame.configure(fg_color=("#d0e8ff", "#1a4a6e"))
                file_label.configure(text_color=("#0066cc", "#66b3ff"))
            else:
                row_frame.configure(fg_color="transparent")
                file_label.configure(text_color=("gray10", "#E8E8E8"))

    def _extract_secrets_recipe_fields(self, recipe_data: dict) -> dict:
        """Extract editable fields from secrets recipe data.

        This converts the UAssetAPI JSON format to a simpler dict for form display.
        """
        fields = {}

        # If recipe_data is minimal (just has Name), return basic fields
        if not recipe_data or recipe_data.get('Name') == recipe_data.get('$type', recipe_data.get('Name')):
            fields['Name'] = recipe_data.get('Name', '')
            return fields

        # Extract from Value if present (row data structure)
        value = recipe_data.get('Value', [])
        if isinstance(value, list):
            for prop in value:
                prop_name = prop.get('Name', '')
                if prop_name:
                    # Extract the actual value based on type
                    fields[prop_name] = self._extract_property_value(prop)

        return fields

    def _extract_secrets_construction_fields(self, construction_data: dict) -> dict:
        """Extract editable fields from secrets construction data."""
        fields = {}

        if not construction_data or construction_data.get('Name') == construction_data.get('$type', construction_data.get('Name')):
            fields['Name'] = construction_data.get('Name', '')
            return fields

        value = construction_data.get('Value', [])
        if isinstance(value, list):
            for prop in value:
                prop_name = prop.get('Name', '')
                if prop_name:
                    fields[prop_name] = self._extract_property_value(prop)

        return fields

    def _extract_property_value(self, prop: dict):  # pylint: disable=too-many-return-statements
        """Extract the value from a UAssetAPI property."""
        prop_type = prop.get('$type', '')

        if 'BoolPropertyData' in prop_type:
            return prop.get('Value', False)
        elif 'IntPropertyData' in prop_type:
            return prop.get('Value', 0)
        elif 'FloatPropertyData' in prop_type:
            return prop.get('Value', 0.0)
        elif 'EnumPropertyData' in prop_type:
            return prop.get('Value', '')
        elif 'TextPropertyData' in prop_type:
            return prop.get('CultureInvariantString', '') or prop.get('Value', '')
        elif 'NamePropertyData' in prop_type:
            return prop.get('Value', '')
        elif 'ArrayPropertyData' in prop_type:
            arr = prop.get('Value', [])
            # Deep extraction for arrays of structs
            result = []
            for item in arr:
                item_type = item.get('$type', '')
                if 'StructPropertyData' in item_type:
                    # Recursively extract struct fields
                    struct_val = item.get('Value', [])
                    struct_dict = {}
                    for struct_prop in struct_val:
                        struct_prop_name = struct_prop.get('Name', '')
                        if struct_prop_name:
                            struct_dict[struct_prop_name] = self._extract_property_value(struct_prop)
                    result.append(struct_dict)
                else:
                    result.append(self._extract_property_value(item))
            return result
        elif 'StructPropertyData' in prop_type:
            struct_val = prop.get('Value', [])
            struct_dict = {}
            for struct_prop in struct_val:
                struct_prop_name = struct_prop.get('Name', '')
                if struct_prop_name:
                    struct_dict[struct_prop_name] = self._extract_property_value(struct_prop)
            return struct_dict
        elif 'SoftObjectPropertyData' in prop_type:
            return prop.get('Value', {}).get('AssetPath', {}).get('AssetName', '')
        else:
            return prop.get('Value', '')

    def _show_new_building_form(self):
        """Show form for creating a new building definition."""
        # Clear current selection
        self.current_def_path = None
        self.current_def_data = None

        # Hide placeholder and fixed header/footer (new form has its own)
        self.placeholder_label.pack_forget()
        self.form_header.grid_remove()  # Hide fixed header for new building form
        self.form_footer.grid_remove()  # Hide fixed footer for new building form
        self.form_content.pack(fill="both", expand=True)

        # Clear existing form content
        for widget in self.form_content.winfo_children():
            widget.destroy()

        self.form_vars.clear()
        self.material_rows.clear()
        self.sandbox_material_rows.clear()

        # === NEW BUILDING HEADER ===
        header_frame = ctk.CTkFrame(self.form_content, fg_color=("#2196F3", "#1565C0"))
        header_frame.pack(fill="x", pady=(0, 15), padx=5)

        ctk.CTkLabel(
            header_frame,
            text="✨ Create New Building",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="white"
        ).pack(anchor="w", padx=10, pady=10)

        # === BASIC INFO ===
        self._create_section_header("Basic Information", "#2196F3")

        self._create_text_field("BuildingName", "", label="Building Name *")
        self._create_text_field("Title", "", label="Title")
        self._create_text_field("Author", "Moria MOD Creator", label="Author")
        self._create_text_field("DefDescription", "", label="Description")

        # === CONSTRUCTION RECIPE SECTION ===
        self._create_section_header("Construction Recipe", "#2196F3")

        # Two-column layout for dropdowns
        row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        row1.pack(fill="x", pady=3)

        self._create_dropdown_field_inline(row1, "BuildProcess", "EBuildProcess::DualMode",
                                           self._get_options("Enum_BuildProcess", DEFAULT_BUILD_PROCESS))
        self._create_dropdown_field_inline(row1, "PlacementType", "EPlacementType::SnapGrid",
                                           self._get_options("Enum_PlacementType", DEFAULT_PLACEMENT))

        row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        row2.pack(fill="x", pady=3)

        self._create_dropdown_field_inline(row2, "LocationRequirement", "EConstructionLocation::Base",
                                           self._get_options("Enum_LocationRequirement", DEFAULT_LOCATION))
        self._create_dropdown_field_inline(row2, "FoundationRule", "EFoundationRule::Never",
                                           self._get_options("Enum_FoundationRule", DEFAULT_FOUNDATION_RULE))

        # Boolean fields
        bool_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_frame.pack(fill="x", pady=8)

        bool_defaults = {"bOnWall": False, "bOnFloor": True, "bPlaceOnWater": False,
                        "bAllowRefunds": True, "bAutoFoundation": False, "bOnlyOnVoxel": False}
        for bf, default_val in bool_defaults.items():
            self._create_checkbox_field(bool_frame, bf, default_val)

        # Materials section
        self._create_subsection_header("Required Materials")

        add_mat_btn = ctk.CTkButton(
            self.form_content,
            text="+ Add Material",
            width=120,
            height=28,
            fg_color="#4CAF50",
            hover_color="#45a049",
            command=self._add_new_material_row
        )
        add_mat_btn.pack(anchor="w", pady=(0, 5))

        self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        self.materials_frame.pack(fill="x", pady=5)

        self._add_material_row("Ore.Stone", 5)

        # === CONSTRUCTION SECTION ===
        self._create_section_header("Construction Definition", "#4CAF50")

        self._create_text_field("DisplayName", "", label="Display Name *")
        self._create_text_field("Description", "")
        self._create_text_field("Actor", "", label="Actor Path *", autocomplete_key="Actors")

        # Tags
        self._create_dropdown_field("Tags", "UI.Construction.Category.Advanced.Walls",
                                    self._get_options("Tags", []))

        # === CREATE BUTTON ===
        sep = ctk.CTkFrame(self.form_content, height=2, fg_color="gray50")
        sep.pack(fill="x", pady=(20, 10))

        btn_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)

        create_btn = ctk.CTkButton(
            btn_frame,
            text="✨ Create Building",
            width=180,
            height=40,
            fg_color="#2196F3",
            hover_color="#1976D2",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._create_new_building
        )
        create_btn.pack(side="left", padx=(0, 10))

        cancel_btn = ctk.CTkButton(
            btn_frame,
            text="Cancel",
            width=100,
            height=40,
            fg_color="gray50",
            hover_color="gray40",
            command=self._cancel_new_building
        )
        cancel_btn.pack(side="left")

    def _cancel_new_building(self):
        """Cancel new building creation and show placeholder."""
        for widget in self.form_content.winfo_children():
            widget.destroy()
        self.form_content.pack_forget()
        self.form_header.grid_remove()  # Hide fixed header
        self.form_footer.grid_remove()  # Hide fixed footer
        self.placeholder_label.pack(pady=50)
        self.form_vars.clear()
        self.material_rows.clear()
        self.sandbox_material_rows.clear()

    def _create_new_building(self):
        """Create a new .def file from the form data."""
        # Validate required fields
        building_name = self.form_vars.get("BuildingName", ctk.StringVar()).get().strip()
        display_name = self.form_vars.get("DisplayName", ctk.StringVar()).get().strip()
        actor_path = self.form_vars.get("Actor", ctk.StringVar()).get().strip()

        if not building_name:
            self._set_status("Building Name is required", is_error=True)
            return
        if not display_name:
            self._set_status("Display Name is required", is_error=True)
            return
        if not actor_path:
            self._set_status("Actor Path is required", is_error=True)
            return

        # Sanitize building name for filename
        safe_name = "".join(c for c in building_name if c.isalnum() or c in "._- ")
        safe_name = safe_name.replace(" ", "_")

        # Check if file already exists
        buildings_dir = get_buildings_dir()
        new_file_path = buildings_dir / f"{safe_name}.def"

        if new_file_path.exists():
            self._set_status(f"File already exists: {safe_name}.def", is_error=True)
            return

        try:
            # Build the .def file content
            def_content = self._generate_def_file_content(safe_name)

            # Write the file
            with open(new_file_path, "w", encoding="utf-8") as f:
                f.write(def_content)

            self._set_status(f"Created: {safe_name}.def")

            # Refresh list and load the new file
            self._refresh_building_list()
            self._load_def_file(new_file_path)

        except (OSError, json.JSONDecodeError, ET.ParseError) as e:
            logger.error("Error creating def file: %s", e)
            self._set_status(f"Error creating file: {e}", is_error=True)

    # -------------------------------------------------------------------------
    # NEW BUILDING JSON GENERATION
    # -------------------------------------------------------------------------
    # These methods generate the JSON structures for new building definitions.
    # The structures match the format expected by the game's data tables.
    # -------------------------------------------------------------------------

    def _generate_def_file_content(self, building_name: str) -> str:
        """
        Generate the complete XML content for a new .def file.

        Args:
            building_name: Sanitized name for the building (used as RowName)

        Returns:
            Complete XML string with recipe and construction JSON embedded
        """
        title = self.form_vars.get("Title", ctk.StringVar()).get() or building_name
        author = self.form_vars.get("Author", ctk.StringVar()).get() or "Moria MOD Creator"
        description = self.form_vars.get("DefDescription", ctk.StringVar()).get() or ""

        # Build recipe JSON (DT_ConstructionRecipes entry)
        recipe_json = self._build_new_recipe_json(building_name)
        recipe_json_str = json.dumps(recipe_json, indent=2)

        # Build construction JSON (DT_Constructions entry)
        construction_json = self._build_new_construction_json(building_name)
        construction_json_str = json.dumps(construction_json, indent=2)

        # Build XML structure with embedded JSON
        xml_content = f'''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <title>{title}</title>
    <author>{author}</author>
    <description>{description}</description>

    <mod file="Moria/Content/Data/DT_ConstructionRecipes.uasset">
        <add_row><![CDATA[
{recipe_json_str}
]]></add_row>
    </mod>

    <mod file="Moria/Content/Data/DT_Constructions.uasset">
        <add_row><![CDATA[
{construction_json_str}
]]></add_row>
    </mod>
</definition>
'''
        return xml_content

    def _build_new_recipe_json(self, name: str) -> dict:
        """
        Build a new recipe JSON structure for DT_ConstructionRecipes.

        Creates a complete recipe entry with all required properties including
        build process, placement rules, materials, and unlock requirements.

        Args:
            name: The RowName for the recipe (typically sanitized building name)

        Returns:
            Complete recipe dict matching the game's expected format
        """
        # Collect materials from form rows (excluding removed entries)
        materials = []
        for row in self.material_rows:
            if row.get("removed"):
                continue
            mat_name = row["material_var"].get()
            try:
                mat_amount = int(row["amount_var"].get())
            except ValueError:
                mat_amount = 1
            materials.append(self._build_material_entry(mat_name, mat_amount))

        return {
            "Name": name,
            "Value": [
                {"$type": ENUM_TYPE, "Name": "BuildProcess",
                 "Value": self.form_vars.get("BuildProcess", ctk.StringVar()).get()},
                {"$type": ENUM_TYPE, "Name": "LocationRequirement",
                 "Value": self.form_vars.get("LocationRequirement", ctk.StringVar()).get()},
                {"$type": ENUM_TYPE, "Name": "PlacementType",
                 "Value": self.form_vars.get("PlacementType", ctk.StringVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bOnWall",
                 "Value": self.form_vars.get("bOnWall", ctk.BooleanVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bOnFloor",
                 "Value": self.form_vars.get("bOnFloor", ctk.BooleanVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bPlaceOnWater",
                 "Value": self.form_vars.get("bPlaceOnWater", ctk.BooleanVar()).get()},
                {"$type": ENUM_TYPE, "Name": "FoundationRule",
                 "Value": self.form_vars.get("FoundationRule", ctk.StringVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bAutoFoundation",
                 "Value": self.form_vars.get("bAutoFoundation", ctk.BooleanVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bAllowRefunds",
                 "Value": self.form_vars.get("bAllowRefunds", ctk.BooleanVar()).get()},
                {"$type": BOOL_TYPE, "Name": "bOnlyOnVoxel",
                 "Value": self.form_vars.get("bOnlyOnVoxel", ctk.BooleanVar()).get()},
                {"$type": ENUM_TYPE, "Name": "EnabledState",
                 "Value": "ERowEnabledState::Live"},
                {"$type": ARRAY_TYPE, "Name": "DefaultRequiredMaterials",
                 "Value": materials},
            ]
        }

    def _build_new_construction_json(self, name: str) -> dict:
        """
        Build a new construction JSON structure for DT_Constructions.

        Creates a complete construction entry with display info, actor reference,
        and gameplay tags.

        Args:
            name: The RowName for the construction (typically sanitized building name)

        Returns:
            Complete construction dict matching the game's expected format
        """
        display_name = self.form_vars.get("DisplayName", ctk.StringVar()).get()
        description = self.form_vars.get("Description", ctk.StringVar()).get()
        actor_path = self.form_vars.get("Actor", ctk.StringVar()).get()
        tag = self.form_vars.get("Tags", ctk.StringVar()).get()

        return {
            "Name": name,
            "Value": [
                {"$type": TEXT_TYPE, "Name": "DisplayName", "Value": display_name},
                {"$type": TEXT_TYPE, "Name": "Description", "Value": description},
                {
                    "$type": SOFT_OBJ_TYPE,
                    "Name": "Actor",
                    "Value": {
                        "AssetPath": {
                            # Split actor path to get package name (path without extension)
                            "PackageName": (actor_path.rsplit(".", 1)[0]
                                            if "." in actor_path else actor_path),
                            "AssetName": actor_path
                        }
                    }
                },
                {
                    "$type": STRUCT_TYPE,
                    "Name": "Tags",
                    "StructType": "GameplayTagContainer",
                    "Value": [
                        {"$type": ARRAY_TYPE, "Name": "Tags",
                         "Value": [tag] if tag else []}
                    ]
                },
                {"$type": ENUM_TYPE, "Name": "EnabledState",
                 "Value": "ERowEnabledState::Live"},
            ]
        }


