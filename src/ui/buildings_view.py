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
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from src.config import get_appdata_dir, get_buildings_dir

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

    This is scanned once to populate the INI cache with official game values.
    Returns a dict with categories -> set of values.
    """
    collected = defaultdict(set)

    # Path to the DT_ConstructionRecipes.json
    recipes_path = (get_appdata_dir() / 'output' / 'jsondata' / 'Moria' / 'Content'
                     / 'Tech' / 'Data' / 'Building' / 'DT_ConstructionRecipes.json')

    if not recipes_path.exists():
        logger.debug(f"DT_ConstructionRecipes.json not found at {recipes_path}")
        return {}

    try:
        with open(recipes_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Extract from NameMap - these are all the names used in the file
        name_map = data.get('NameMap', [])

        for name in name_map:
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
            elif name.startswith('Decoration'):
                collected['Decorations'].add(name)
            elif name.endswith('_Fragment'):
                collected['Fragments'].add(name)
                collected['UnlockRequiredFragments'].add(name)
            elif name.startswith('b') and name[1].isupper():
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

        logger.info(f"Scanned DT_ConstructionRecipes.json: found {sum(len(v) for v in collected.values())} values")

    except Exception as e:
        logger.error(f"Error scanning DT_ConstructionRecipes.json: {e}")

    return {k: sorted(v) for k, v in collected.items()}


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
        except Exception as e:
            logger.debug(f"Error scanning {def_file.name}: {e}")

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
                    logger.error(f"Failed to parse recipe JSON: {e}")

        # Construction file
        elif "DT_Constructions" in file_attr:
            add_row = mod.find("add_row")
            if add_row is not None and add_row.text:
                try:
                    result["construction_json"] = json.loads(add_row.text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse construction JSON: {e}")

            add_imports = mod.find("add_imports")
            if add_imports is not None and add_imports.text:
                try:
                    result["imports_json"] = json.loads(add_imports.text)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse imports JSON: {e}")

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
        except Exception:
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
        for i, match in enumerate(self.current_matches):
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
        except Exception:
            pass
        self._hide_dropdown()

    def _select_item(self, item: str):
        """Select an item from the dropdown."""
        text = self.textvariable.get()
        current_word, start, end = self._get_current_word()

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

        # Building list item references for selection highlighting
        self.building_list_items = {}  # {file_path: (row_frame, file_label)}

        # Checkbox tracking for bulk construction operations
        self.construction_checkboxes: dict[Path, ctk.CTkCheckBox] = {}
        self.construction_check_vars: dict[Path, ctk.BooleanVar] = {}
        self.select_all_var = None
        self.select_all_checkbox = None

        # Construction name entry for bulk build operations
        self.construction_name_var = None
        self.construction_name_entry = None

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

        # Persist to INI cache for faster startup
        _save_cached_options(cache_path, self.cached_options)

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
        - Select-all checkbox and header label
        - Scrollable list of .def files with individual checkboxes
        - Action buttons: New Building, Import, Build Combined, Back
        """
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Header row with select-all checkbox
        header_frame = ctk.CTkFrame(list_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 5))

        # Select-all checkbox for bulk operations
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_checkbox = ctk.CTkCheckBox(
            header_frame,
            text="",
            variable=self.select_all_var,
            width=20,
            command=self._on_select_all_toggle
        )
        self.select_all_checkbox.pack(side="left")

        title_label = ctk.CTkLabel(
            header_frame,
            text="Construction Definitions",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(side="left", padx=(5, 0))

        # Refresh button
        refresh_btn = ctk.CTkButton(
            header_frame,
            text="↻",
            width=28,
            height=28,
            font=ctk.CTkFont(size=16),
            fg_color="transparent",
            hover_color=("gray75", "gray25"),
            command=self._scan_and_refresh
        )
        refresh_btn.pack(side="right")

        # Button row for New and Import Construction
        btn_row = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(5, 5))
        btn_row.grid_columnconfigure(0, weight=1)
        btn_row.grid_columnconfigure(1, weight=1)

        # New Construction button
        new_btn = ctk.CTkButton(
            btn_row,
            text="+ New",
            height=32,
            fg_color="#2196F3",
            hover_color="#1976D2",
            font=ctk.CTkFont(weight="bold"),
            command=self._show_new_building_form
        )
        new_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        # Import Construction button
        import_btn = ctk.CTkButton(
            btn_row,
            text="+ Import",
            height=32,
            fg_color="#9C27B0",
            hover_color="#7B1FA2",
            font=ctk.CTkFont(weight="bold"),
            command=self._import_construction
        )
        import_btn.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        # Count label
        self.count_label = ctk.CTkLabel(
            list_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.count_label.pack(padx=10, anchor="w")

        # Scrollable file list
        self.building_list = ctk.CTkScrollableFrame(list_frame, fg_color="transparent")
        self.building_list.pack(fill="both", expand=True, padx=10, pady=(0, 5))

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
        self.footer_save_btn = ctk.CTkButton(
            self.form_footer,
            text="💾 Save Changes",
            width=150,
            height=36,
            fg_color="#4CAF50",
            hover_color="#45a049",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._save_def_file
        )
        self.footer_save_btn.pack(side="left", padx=10, pady=10)

        self.footer_revert_btn = ctk.CTkButton(
            self.form_footer,
            text="↩ Revert",
            width=100,
            height=36,
            fg_color="gray50",
            hover_color="gray40",
            command=self._revert_changes
        )
        self.footer_revert_btn.pack(side="left", padx=(0, 10), pady=10)

        self.footer_delete_btn = ctk.CTkButton(
            self.form_footer,
            text="🗑 Delete",
            width=100,
            height=36,
            fg_color="#f44336",
            hover_color="#d32f2f",
            command=self._delete_def_file
        )
        self.footer_delete_btn.pack(side="right", padx=10, pady=10)

    # -------------------------------------------------------------------------
    # FILE OPERATIONS
    # -------------------------------------------------------------------------

    def _revert_changes(self):
        """Revert form to the last saved version by reloading the current file."""
        if self.current_def_path:
            self._load_def_file(self.current_def_path)

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

            file_label = ctk.CTkLabel(
                row_frame,
                text=file_path.stem,
                anchor="w",
                cursor="hand2"
            )
            file_label.pack(side="left", fill="x", expand=True, padx=5)
            file_label.bind("<Button-1>", lambda e, p=file_path: self._load_def_file(p))
            row_frame.bind("<Button-1>", lambda e, p=file_path: self._load_def_file(p))

            # Store reference for highlighting
            self.building_list_items[file_path] = (row_frame, file_label)

            # Hover effect (only if not selected)
            file_label.bind("<Enter>", lambda e, p=file_path, lbl=file_label: self._on_item_hover(p, lbl, True))
            file_label.bind("<Leave>", lambda e, p=file_path, lbl=file_label: self._on_item_hover(p, lbl, False))

    def _load_def_file(self, file_path: Path):
        """Load a .def file and display it in the form."""
        try:
            self.current_def_data = parse_def_file(file_path)
            self.current_def_path = file_path
            self._highlight_selected_item(file_path)
            self._show_form()
            self._set_status(f"Loaded: {file_path.name}")
        except Exception as e:
            logger.error(f"Error loading def file: {e}")
            self._set_status(f"Error loading file: {e}", is_error=True)

    def _highlight_selected_item(self, selected_path: Path):
        """Highlight the selected building in the list."""
        for file_path, (row_frame, file_label) in self.building_list_items.items():
            if file_path == selected_path:
                # Selected state - highlight with accent color
                row_frame.configure(fg_color=("#d0e8ff", "#1a4a6e"))
                file_label.configure(text_color=("#0066cc", "#66b3ff"))
            else:
                # Unselected state - reset to default
                row_frame.configure(fg_color="transparent")
                file_label.configure(text_color=("gray10", "gray90"))

    def _on_item_hover(self, file_path: Path, label: ctk.CTkLabel, entering: bool):
        """Handle hover effect on list items, respecting selection state."""
        # Don't change hover color if this is the selected item
        if file_path == self.current_def_path:
            return

        if entering:
            label.configure(text_color="#4CAF50")
        else:
            label.configure(text_color=("gray10", "gray90"))

    def _on_select_all_toggle(self):
        """Toggle all construction checkboxes based on select-all state."""
        if self.select_all_var is None:
            return

        select_all = self.select_all_var.get()
        for file_path, check_var in self.construction_check_vars.items():
            check_var.set(select_all)

    def _on_construction_checkbox_toggle(self, file_path: Path):
        """Handle individual construction checkbox toggle."""
        # Update select-all checkbox state based on individual checkboxes
        if self.select_all_var is None:
            return

        all_checked = all(var.get() for var in self.construction_check_vars.values())
        self.select_all_var.set(all_checked)

    def _on_construction_name_click(self):
        """Handle click on 'My Construction' button - focus the name entry."""
        if hasattr(self, 'construction_name_entry') and self.construction_name_entry:
            self.construction_name_entry.focus_set()
            self.construction_name_entry.select_range(0, 'end')

    def _on_construction_build_click(self):
        """Build selected constructions into a construction pack."""
        # Get selected constructions
        selected_files = [
            file_path for file_path, check_var in self.construction_check_vars.items()
            if check_var.get()
        ]

        if not selected_files:
            from tkinter import messagebox
            messagebox.showwarning("No Selection", "Please select at least one construction to build.")
            return

        # Get construction pack name
        pack_name = self.construction_name_var.get().strip() if self.construction_name_var else ""
        if not pack_name:
            from tkinter import messagebox
            messagebox.showwarning("No Name", "Please enter a name for your construction pack.")
            if hasattr(self, 'construction_name_entry') and self.construction_name_entry:
                self.construction_name_entry.focus_set()
            return

        # Sanitize pack name for use as folder name
        import re
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', pack_name)

        # Create constructions output directory (separate from mods)
        constructions_dir = get_appdata_dir() / "Constructions" / safe_name
        constructions_dir.mkdir(parents=True, exist_ok=True)

        # Copy selected .def files to the construction pack
        import shutil
        copied_count = 0
        for file_path in selected_files:
            if file_path.exists():
                dest_path = constructions_dir / file_path.name
                shutil.copy2(file_path, dest_path)
                copied_count += 1

        from tkinter import messagebox
        messagebox.showinfo(
            "Construction Pack Created",
            f"Created construction pack '{pack_name}' with {copied_count} construction(s).\n\n"
            f"Location: {constructions_dir}"
        )

    # -------------------------------------------------------------------------
    # FORM DISPLAY AND LAYOUT
    # -------------------------------------------------------------------------

    def _show_form(self):
        """
        Display the building form with data from the loaded .def file.

        Populates the form with recipe and construction fields from the
        current_def_data dictionary, creating appropriate input widgets
        for each field type.
        """
        if not self.current_def_data:
            return

        # Hide placeholder, show form content and fixed header/footer
        self.placeholder_label.pack_forget()
        self.form_content.pack(fill="both", expand=True)
        self.form_header.grid()  # Show fixed header
        self.form_footer.grid()  # Show fixed footer

        # Clear existing form content
        for widget in self.form_content.winfo_children():
            widget.destroy()

        self.form_vars.clear()
        self.material_rows.clear()

        data = self.current_def_data

        # === UPDATE FIXED HEADER ===
        title = data.get("title", data.get("name", "Unknown"))
        self.header_title.configure(text=title)

        author = data.get("author", "")
        if author:
            self.header_author.configure(text=f"Author: {author}")
            self.header_author.pack(fill="x", padx=10)
        else:
            self.header_author.pack_forget()

        description = data.get("description", "")
        if description:
            self.header_description.configure(text=description)
            self.header_description.pack(fill="x", padx=10, pady=(0, 10))
        else:
            self.header_description.pack_forget()

        # === CONSTRUCTION RECIPE SECTION ===
        self._create_section_header("Construction Recipe", "#2196F3")

        recipe_json = data.get("recipe_json")
        if recipe_json:
            recipe_fields = extract_recipe_fields(recipe_json)

            # ResultConstructionHandle field
            self._create_text_field("ResultConstructionHandle", recipe_fields.get("ResultConstructionHandle", ""),
                                    label="Result Construction Handle", autocomplete_key="ResultConstructions")

            # Two-column layout for dropdowns
            row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row1.pack(fill="x", pady=3)

            self._create_dropdown_field_inline(row1, "BuildProcess", recipe_fields.get("BuildProcess", ""),
                                               self._get_options("Enum_BuildProcess", DEFAULT_BUILD_PROCESS))
            self._create_dropdown_field_inline(row1, "PlacementType", recipe_fields.get("PlacementType", ""),
                                               self._get_options("Enum_PlacementType", DEFAULT_PLACEMENT))

            row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row2.pack(fill="x", pady=3)

            self._create_dropdown_field_inline(
                row2, "LocationRequirement", recipe_fields.get("LocationRequirement", ""),
                self._get_options("Enum_LocationRequirement", DEFAULT_LOCATION))
            self._create_dropdown_field_inline(
                row2, "FoundationRule", recipe_fields.get("FoundationRule", ""),
                self._get_options("Enum_FoundationRule", DEFAULT_FOUNDATION_RULE))

            # MonumentType dropdown
            row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row3.pack(fill="x", pady=3)

            self._create_dropdown_field_inline(
                row3, "MonumentType",
                recipe_fields.get("MonumentType", "EMonumentType::None"),
                self._get_options("Enum_MonumentType", DEFAULT_MONUMENT_TYPE))

            # Boolean fields - Row 1
            bool_frame1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_frame1.pack(fill="x", pady=4)

            bool_fields1 = ["bOnWall", "bOnFloor", "bPlaceOnWater", "bOverrideRotation", "bAllowRefunds"]
            for bf in bool_fields1:
                self._create_checkbox_field(bool_frame1, bf, recipe_fields.get(bf, False))

            # Boolean fields - Row 2
            bool_frame2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_frame2.pack(fill="x", pady=4)

            bool_fields2 = ["bAutoFoundation", "bInheritAutoFoundationStability", "bOnlyOnVoxel"]
            for bf in bool_fields2:
                self._create_checkbox_field(bool_frame2, bf, recipe_fields.get(bf, False))

            # Boolean fields - Row 3
            bool_frame3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_frame3.pack(fill="x", pady=4)

            bool_fields3 = [
                "bIsBlockedByNearbySettlementStones",
                "bIsBlockedByNearbyRavenConstructions",
                "bHasSandboxRequirementsOverride",
                "bHasSandboxUnlockOverride",
            ]
            for bf in bool_fields3:
                self._create_checkbox_field(bool_frame3, bf, recipe_fields.get(bf, False))

            # Numeric fields
            self._create_subsection_header("Numeric Properties")

            num_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
            num_frame.pack(fill="x", pady=3)

            # MaxAllowedPenetrationDepth
            ctk.CTkLabel(num_frame, text="MaxPenetrationDepth:", anchor="w").pack(side="left")
            pen_var = ctk.StringVar(value=str(recipe_fields.get("MaxAllowedPenetrationDepth", -1.0)))
            self.form_vars["MaxAllowedPenetrationDepth"] = pen_var
            ctk.CTkEntry(num_frame, textvariable=pen_var, width=80).pack(side="left", padx=5)

            # RequireNearbyRadius
            ctk.CTkLabel(num_frame, text="RequireNearbyRadius:", anchor="w").pack(side="left", padx=(20, 0))
            rad_var = ctk.StringVar(value=str(recipe_fields.get("RequireNearbyRadius", 300.0)))
            self.form_vars["RequireNearbyRadius"] = rad_var
            ctk.CTkEntry(num_frame, textvariable=rad_var, width=80).pack(side="left", padx=5)

            # CameraStateOverridePriority
            ctk.CTkLabel(num_frame, text="CameraPriority:", anchor="w").pack(side="left", padx=(20, 0))
            cam_var = ctk.StringVar(value=str(recipe_fields.get("CameraStateOverridePriority", 5)))
            self.form_vars["CameraStateOverridePriority"] = cam_var
            ctk.CTkEntry(num_frame, textvariable=cam_var, width=60).pack(side="left", padx=5)

            # Recipe EnabledState
            self._create_dropdown_field(
                "Recipe_EnabledState",
                recipe_fields.get("EnabledState", "ERowEnabledState::Live"),
                self._get_options("Enum_EnabledState", DEFAULT_ENABLED_STATE),
                label="EnabledState")

            # Required Constructions
            req_constructions = recipe_fields.get("DefaultRequiredConstructions", [])
            self._create_text_field(
                "DefaultRequiredConstructions", ", ".join(req_constructions),
                label="Required Constructions (comma-separated)",
                autocomplete_key="Constructions")

            # === DEFAULT UNLOCKS SECTION ===
            self._create_subsection_header("Default Unlocks")

            unlock_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            unlock_row.pack(fill="x", pady=3)

            self._create_dropdown_field_inline(
                unlock_row, "DefaultUnlocks_UnlockType",
                recipe_fields.get("DefaultUnlocks_UnlockType", "EMorRecipeUnlockType::Manual"),
                self._get_options("Enum_UnlockType", DEFAULT_UNLOCK_TYPE),
                label="Unlock Type")

            # NumFragments
            ctk.CTkLabel(unlock_row, text="Fragments:", anchor="w").pack(side="left", padx=(20, 0))
            frag_var = ctk.StringVar(value=str(recipe_fields.get("DefaultUnlocks_NumFragments", 1)))
            self.form_vars["DefaultUnlocks_NumFragments"] = frag_var
            ctk.CTkEntry(unlock_row, textvariable=frag_var, width=60).pack(side="left", padx=5)

            # Required Items for unlock (comma-separated display)
            req_items = recipe_fields.get("DefaultUnlocks_RequiredItems", [])
            self._create_text_field(
                "DefaultUnlocks_RequiredItems", ", ".join(req_items),
                label="Required Items (comma-separated)",
                autocomplete_key="UnlockRequiredItems")

            # Required Constructions for unlock (comma-separated display)
            req_const = recipe_fields.get("DefaultUnlocks_RequiredConstructions", [])
            self._create_text_field(
                "DefaultUnlocks_RequiredConstructions", ", ".join(req_const),
                label="Required Constructions (comma-separated)",
                autocomplete_key="Constructions")

            # Required Fragments for unlock
            req_frags = recipe_fields.get("DefaultUnlocks_RequiredFragments", [])
            self._create_text_field(
                "DefaultUnlocks_RequiredFragments", ", ".join(req_frags),
                label="Required Fragments (comma-separated)",
                autocomplete_key="UnlockRequiredFragments")

            # === SANDBOX UNLOCKS SECTION ===
            self._create_subsection_header("Sandbox Unlocks")

            sandbox_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            sandbox_row.pack(fill="x", pady=3)

            self._create_dropdown_field_inline(
                sandbox_row, "SandboxUnlocks_UnlockType",
                recipe_fields.get("SandboxUnlocks_UnlockType", "EMorRecipeUnlockType::Manual"),
                self._get_options("Enum_UnlockType", DEFAULT_UNLOCK_TYPE),
                label="Unlock Type")

            # Sandbox NumFragments
            ctk.CTkLabel(sandbox_row, text="Fragments:", anchor="w").pack(side="left", padx=(20, 0))
            sb_frag_var = ctk.StringVar(value=str(recipe_fields.get("SandboxUnlocks_NumFragments", 1)))
            self.form_vars["SandboxUnlocks_NumFragments"] = sb_frag_var
            ctk.CTkEntry(sandbox_row, textvariable=sb_frag_var, width=60).pack(side="left", padx=5)

            # Sandbox Required Items
            sb_req_items = recipe_fields.get("SandboxUnlocks_RequiredItems", [])
            self._create_text_field(
                "SandboxUnlocks_RequiredItems", ", ".join(sb_req_items),
                label="Sandbox Required Items (comma-separated)",
                autocomplete_key="UnlockRequiredItems")

            # Sandbox Required Constructions
            sb_req_const = recipe_fields.get("SandboxUnlocks_RequiredConstructions", [])
            self._create_text_field(
                "SandboxUnlocks_RequiredConstructions", ", ".join(sb_req_const),
                label="Sandbox Required Constructions (comma-separated)",
                autocomplete_key="Constructions")

            # Materials section
            self._create_subsection_header("Required Materials")

            # Add Material button
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

            for mat in recipe_fields.get("Materials", []):
                self._add_material_row(mat.get("Material", "Item.Wood"), mat.get("Amount", 1))

            if not recipe_fields.get("Materials"):
                self._add_material_row("Item.Wood", 1)  # Add a default row
        else:
            ctk.CTkLabel(
                self.form_content,
                text="No recipe data found in .def file",
                text_color="orange"
            ).pack(anchor="w", pady=5)

        # === CONSTRUCTION SECTION ===
        self._create_section_header("Construction Definition", "#4CAF50")

        construction_json = data.get("construction_json")
        if construction_json:
            construction_fields = extract_construction_fields(construction_json)

            # Display fields - all full width
            self._create_text_field("DisplayName", construction_fields.get("DisplayName", ""))
            self._create_text_field("Description", construction_fields.get("Description", ""))
            self._create_text_field("Actor", construction_fields.get("Actor", ""),
                                    label="Actor Path", autocomplete_key="Actors")

            # BackwardCompatibilityActors
            compat_actors = construction_fields.get("BackwardCompatibilityActors", [])
            self._create_text_field("BackwardCompatibilityActors", ", ".join(compat_actors),
                                    label="Backward Compatibility Actors (comma-separated)",
                                    autocomplete_key="BackwardCompatibilityActors")

            # Icon info
            icon_val = construction_fields.get("Icon")
            if icon_val is not None:
                icon_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
                icon_frame.pack(fill="x", pady=3)
                ctk.CTkLabel(icon_frame, text="Icon Index:", width=140, anchor="w").pack(side="left")
                ctk.CTkLabel(icon_frame, text=str(icon_val), text_color="gray").pack(side="left", padx=10)

            # Tags
            tags = construction_fields.get("Tags", [])
            current_tag = tags[0] if tags else ""
            tag_options = self._get_options("Tags", [])
            if current_tag and current_tag not in tag_options:
                tag_options.insert(0, current_tag)
            self._create_dropdown_field("Tags", current_tag, tag_options)

            # Construction EnabledState
            self._create_dropdown_field(
                "Construction_EnabledState",
                construction_fields.get("EnabledState", "ERowEnabledState::Live"),
                self._get_options("Enum_EnabledState", DEFAULT_ENABLED_STATE),
                label="EnabledState",
            )
        else:
            ctk.CTkLabel(
                self.form_content,
                text="No construction data found in .def file",
                text_color="orange"
            ).pack(anchor="w", pady=5)

        # === IMPORTS INFO ===
        imports_json = data.get("imports_json")
        if imports_json:
            self._create_section_header("Icon Imports", "#FF9800")

            for imp in imports_json:
                imp_frame = ctk.CTkFrame(self.form_content, fg_color=("gray85", "gray20"))
                imp_frame.pack(fill="x", pady=2, padx=5)

                obj_name = imp.get("ObjectName", "")
                class_name = imp.get("ClassName", "")

                ctk.CTkLabel(
                    imp_frame,
                    text=f"{class_name}: {obj_name}",
                    font=ctk.CTkFont(size=11),
                    anchor="w"
                ).pack(fill="x", padx=10, pady=5)

        # Footer buttons are now fixed in form_footer, no need to create them here

    def _create_action_buttons(self):
        """Create Save and other action buttons at the bottom of the form."""
        # Separator
        sep = ctk.CTkFrame(self.form_content, height=2, fg_color="gray50")
        sep.pack(fill="x", pady=(20, 10))

        # Button frame
        btn_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        btn_frame.pack(fill="x", pady=10)

        # Save button
        save_btn = ctk.CTkButton(
            btn_frame,
            text="💾 Save Changes",
            width=150,
            height=36,
            fg_color="#4CAF50",
            hover_color="#45a049",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._save_def_file
        )
        save_btn.pack(side="left", padx=(0, 10))

        # Revert button
        revert_btn = ctk.CTkButton(
            btn_frame,
            text="↩ Revert",
            width=100,
            height=36,
            fg_color="gray50",
            hover_color="gray40",
            command=lambda: self._load_def_file(self.current_def_path) if self.current_def_path else None
        )
        revert_btn.pack(side="left", padx=(0, 10))

        # Delete button
        delete_btn = ctk.CTkButton(
            btn_frame,
            text="🗑 Delete",
            width=100,
            height=36,
            fg_color="#f44336",
            hover_color="#d32f2f",
            command=self._delete_def_file
        )
        delete_btn.pack(side="right")

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
                           autocomplete_key: str | None = None):
        """Create a text input field with optional autocomplete.

        Args:
            name: Field name for form_vars
            value: Initial value
            width: Width of the entry (default 600 for full width)
            label: Display label (defaults to name)
            autocomplete_key: Key to look up autocomplete suggestions from cached_options
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

        # Use autocomplete entry if suggestions are available
        if autocomplete_key:
            suggestions = self._get_options(autocomplete_key, [])
            if suggestions:
                entry = AutocompleteEntry(
                    frame,
                    textvariable=self.form_vars[name],
                    suggestions=suggestions,
                    width=width
                )
                entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
                return

        # Regular entry
        ctk.CTkEntry(
            frame,
            textvariable=self.form_vars[name],
            width=width
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

        # Material combobox (allows selection OR manual typing)
        material_options = self._get_options("Materials", ["Item.Wood"])
        if material and material not in material_options:
            material_options.insert(0, material)

        mat_var = ctk.StringVar(value=material)
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

    def _save_def_file(self):
        """Save changes back to the .def file."""
        if not self.current_def_path or not self.current_def_data:
            self._set_status("No file loaded to save", is_error=True)
            return

        try:
            # Parse the existing .def file
            tree = ET.parse(self.current_def_path)
            root = tree.getroot()

            # Update recipe data
            for mod in root.findall("mod"):
                file_attr = mod.get("file", "")

                if "DT_ConstructionRecipes" in file_attr:
                    add_row = mod.find("add_row")
                    if add_row is not None and add_row.text:
                        recipe_json = json.loads(add_row.text)
                        self._update_recipe_json(recipe_json)
                        add_row.text = json.dumps(recipe_json, indent=2)

                elif "DT_Constructions" in file_attr:
                    add_row = mod.find("add_row")
                    if add_row is not None and add_row.text:
                        construction_json = json.loads(add_row.text)
                        self._update_construction_json(construction_json)
                        add_row.text = json.dumps(construction_json, indent=2)

            # Write back to file
            tree.write(self.current_def_path, encoding="utf-8", xml_declaration=True)

            self._set_status(f"Saved: {self.current_def_path.name}")

        except Exception as e:
            logger.error(f"Error saving def file: {e}")
            self._set_status(f"Error saving: {e}", is_error=True)

    # -------------------------------------------------------------------------
    # JSON DATA UPDATE METHODS
    # -------------------------------------------------------------------------
    # These methods update the in-memory JSON structures with values from
    # the form fields before saving back to the .def file.
    # -------------------------------------------------------------------------

    def _update_recipe_json(self, recipe_json: dict):
        """
        Update recipe JSON structure with current form values.

        Traverses the recipe JSON properties and updates them with values
        from self.form_vars. Handles enum fields, booleans, materials array,
        and unlock requirements.

        Args:
            recipe_json: The recipe JSON dict from DT_ConstructionRecipes
        """
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

            # Update materials array
            elif prop_name == "DefaultRequiredMaterials":
                new_materials = []
                for row in self.material_rows:
                    if row.get("removed"):
                        continue
                    mat_name = row["material_var"].get()
                    try:
                        mat_amount = int(row["amount_var"].get())
                    except ValueError:
                        mat_amount = 1

                    # Build material entry structure matching game format
                    mat_entry = self._build_material_entry(mat_name, mat_amount)
                    new_materials.append(mat_entry)

                prop["Value"] = new_materials

            # Update DefaultUnlocks (unlock requirements)
            elif prop_name == "DefaultUnlocks":
                for unlock_prop in prop.get("Value", []):
                    unlock_name = unlock_prop.get("Name", "")
                    unlock_type = unlock_prop.get("$type", "")

                    if unlock_name == "UnlockType" and "EnumPropertyData" in unlock_type:
                        if "DefaultUnlocks_UnlockType" in self.form_vars:
                            unlock_prop["Value"] = self.form_vars["DefaultUnlocks_UnlockType"].get()

                    elif unlock_name == "NumFragments":
                        if "DefaultUnlocks_NumFragments" in self.form_vars:
                            try:
                                unlock_prop["Value"] = int(self.form_vars["DefaultUnlocks_NumFragments"].get())
                            except ValueError:
                                unlock_prop["Value"] = 1

                    elif unlock_name == "UnlockRequiredItems":
                        if "DefaultUnlocks_RequiredItems" in self.form_vars:
                            items_str = self.form_vars["DefaultUnlocks_RequiredItems"].get().strip()
                            if items_str:
                                items = [i.strip() for i in items_str.split(",") if i.strip()]
                                unlock_prop["Value"] = self._build_unlock_required_items(items)
                            else:
                                unlock_prop["Value"] = []

                    elif unlock_name == "UnlockRequiredConstructions":
                        if "DefaultUnlocks_RequiredConstructions" in self.form_vars:
                            const_str = self.form_vars["DefaultUnlocks_RequiredConstructions"].get().strip()
                            if const_str:
                                constructions = [c.strip() for c in const_str.split(",") if c.strip()]
                                unlock_prop["Value"] = self._build_unlock_required_constructions(constructions)
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

    def _delete_def_file(self):
        """Delete the current .def file after confirmation."""
        if not self.current_def_path:
            return

        # Simple confirmation via dialog
        dialog = ctk.CTkInputDialog(
            text=f"Type 'DELETE' to confirm deletion of:\n{self.current_def_path.name}",
            title="Confirm Delete"
        )
        result = dialog.get_input()

        if result == "DELETE":
            try:
                self.current_def_path.unlink()
                self._set_status(f"Deleted: {self.current_def_path.name}")
                self.current_def_path = None
                self.current_def_data = None

                # Clear form and show placeholder
                for widget in self.form_content.winfo_children():
                    widget.destroy()
                self.form_content.pack_forget()
                self.form_header.grid_remove()  # Hide fixed header
                self.form_footer.grid_remove()  # Hide fixed footer
                self.placeholder_label.pack(pady=50)

                # Refresh list
                self._refresh_building_list()
            except Exception as e:
                self._set_status(f"Error deleting: {e}", is_error=True)
        else:
            self._set_status("Delete cancelled")

    def _set_status(self, message: str, is_error: bool = False):
        """Set status message via callback."""
        if self.on_status_message:
            self.on_status_message(message, is_error)

    def _go_back(self):
        """Go back to the main mod builder view."""
        if self.on_back:
            self.on_back()

    def _import_construction(self):
        """Import a construction .def file from an external location."""
        from tkinter import filedialog, messagebox
        import shutil

        # Open file dialog to select .def file(s)
        file_paths = filedialog.askopenfilenames(
            title="Import Construction Files",
            filetypes=[("Definition files", "*.def"), ("All files", "*.*")],
            initialdir=str(Path.home())
        )

        if not file_paths:
            return

        # Get destination directory
        buildings_dir = get_buildings_dir()

        imported_count = 0
        skipped_count = 0

        for file_path in file_paths:
            src_path = Path(file_path)
            dest_path = buildings_dir / src_path.name

            # Check if file already exists
            if dest_path.exists():
                result = messagebox.askyesno(
                    "File Exists",
                    f"'{src_path.name}' already exists.\n\nOverwrite?"
                )
                if not result:
                    skipped_count += 1
                    continue

            try:
                shutil.copy2(src_path, dest_path)
                imported_count += 1
            except Exception as e:
                messagebox.showerror("Import Error", f"Failed to import '{src_path.name}':\n{e}")

        # Refresh the list
        if imported_count > 0:
            self._refresh_building_list()
            messagebox.showinfo(
                "Import Complete",
                f"Imported {imported_count} construction(s)." +
                (f"\nSkipped {skipped_count} file(s)." if skipped_count > 0 else "")
            )

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

        except Exception as e:
            logger.error(f"Error creating def file: {e}")
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
