"""Object template utilities for creating and editing DataTable rows.

Ported from TobiIchiro/RtoM-Moding-Tool (modUtils.py, armorModUtils.py).
Provides functions to create new construction, armor, weapon, and item rows
by deep-copying JSON templates and modifying properties.

All functions operate on UAssetGUI-exported JSON data structures.
Templates are loaded from docs/templates/.
"""

import copy
import json
import logging
from pathlib import Path
from string import ascii_uppercase

logger = logging.getLogger(__name__)

# Resolve templates directory relative to this file
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "docs" / "templates"


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def _load_template(name: str) -> dict:
    """Load a JSON template file from docs/templates/."""
    path = _TEMPLATES_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    """Save data to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Unique tag generation
# ---------------------------------------------------------------------------

def gen_unique_tag(base_tag: str, existing_names: set[str]) -> str:
    """Generate a unique tag suffix (A-Z) for a base tag.

    Args:
        base_tag: The base row name (e.g. "MyWall")
        existing_names: Set of existing row Name values in the DataTable

    Returns:
        The unique tag with suffix, e.g. "MyWall_A"

    Raises:
        ValueError: If all A-Z suffixes are taken
    """
    for letter in ascii_uppercase:
        candidate = f"{base_tag}_{letter}"
        if candidate not in existing_names:
            return candidate
    raise ValueError(
        f"Could not generate a unique name for '{base_tag}' (A-Z exhausted)"
    )


def get_existing_row_names(data: dict) -> set[str]:
    """Extract all row Name values from a DataTable JSON.

    Args:
        data: Loaded DataTable JSON (UAssetGUI format)

    Returns:
        Set of row Name strings
    """
    names = set()
    for export in data.get("Exports", []):
        table = export.get("Table")
        if not table:
            continue
        for row in table.get("Data", []):
            if isinstance(row, dict) and "Name" in row:
                names.add(row["Name"])
    return names


# ---------------------------------------------------------------------------
# String table (Architecture.json) handling
# ---------------------------------------------------------------------------

def add_string_table_entry(
    string_table_data: dict,
    unique_tag: str,
    display_name: str,
    description: str,
) -> None:
    """Add name and description entries to a string table JSON.

    Modifies string_table_data in-place by appending [tag.Name, value]
    and [tag.Description, value] pairs to Exports[0].Table.Value.

    Args:
        string_table_data: Loaded string table JSON (e.g. Architecture.json)
        unique_tag: The unique row tag (e.g. "MyWall_A")
        display_name: Human-readable display name
        description: Human-readable description
    """
    exports_value = string_table_data["Exports"][0]["Table"]["Value"]
    exports_value.append([f"{unique_tag}.Name", display_name])
    exports_value.append([f"{unique_tag}.Description", description])


# ---------------------------------------------------------------------------
# Required materials builder
# ---------------------------------------------------------------------------

def build_required_materials(
    materials: list[tuple[str, int]],
) -> list[dict]:
    """Build a list of MorRequiredRecipeMaterial structs.

    Args:
        materials: List of (item_tag, count) tuples,
                   e.g. [("Item.Stone", 5), ("Item.Iron", 2)]

    Returns:
        List of deep-copied RequiredMaterialTemplate structs with values set
    """
    template = _load_template("RequiredMaterialTemplate.json")
    result = []
    for item_tag, count in materials:
        item = copy.deepcopy(template)
        # Set material handle RowName
        item["Value"][0]["Value"][0]["Value"] = item_tag
        # Set count
        item["Value"][2]["Value"] = count
        result.append(item)
    return result


# ---------------------------------------------------------------------------
# Crafting stations builder
# ---------------------------------------------------------------------------

def build_crafting_stations(
    stations: list[str],
) -> list[dict]:
    """Build a list of crafting station structs.

    Args:
        stations: List of crafting station row names,
                  e.g. ["CraftingStation_BasicForge"]

    Returns:
        List of deep-copied CraftingStationTemplate structs with values set
    """
    template = _load_template("CraftingStationTemplate.json")
    result = []
    for station in stations:
        entry = copy.deepcopy(template)
        entry["Value"][0]["Value"] = station
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Unlock conditions
# ---------------------------------------------------------------------------

def build_unlock_condition(
    unlock_option: str,
    unlock_requirement: str,
) -> tuple[dict, dict]:
    """Build unlock requirement structs for a recipe.

    Args:
        unlock_option: Either "UnlockRequiredItems" or "UnlockRequiredConstructions"
        unlock_requirement: The item or construction tag to require,
                           e.g. "Item.Hide" or "CraftingStation_BasicForge"

    Returns:
        Tuple of (unlock_items_struct, unlock_constructions_struct).
        One will have the requirement set, the other will be empty.
    """
    unlock_structs = _load_template("UnlockStructs.json")

    if unlock_option == "UnlockRequiredItems":
        items = copy.deepcopy(unlock_structs["UnlockRequiredItems"])
        items["Value"][0]["Value"][0]["Value"] = unlock_requirement
        constructions = copy.deepcopy(unlock_structs["EmptyConstructions"])
    else:
        items = copy.deepcopy(unlock_structs["EmptyItems"])
        constructions = copy.deepcopy(unlock_structs["UnlockRequiredConstructions"])
        constructions["Value"][0]["Value"][0]["Value"] = unlock_requirement

    return items, constructions


# ---------------------------------------------------------------------------
# Construction creation
# ---------------------------------------------------------------------------

def create_construction_row(
    unique_tag: str,
    asset_path: str,
    category_tag: str,
    icon_path: str,
    dt_constructions_data: dict,
) -> None:
    """Create a new DT_Constructions row and append it to the data.

    Modifies dt_constructions_data in-place: appends the row to
    Exports[0].Table.Data, adds Import entries for the icon, and
    extends NameMap.

    Args:
        unique_tag: Unique row name (e.g. "MyWall_A")
        asset_path: Blueprint asset path (e.g. "/Game/Mods/...")
        category_tag: Gameplay tag for the category
        icon_path: Full icon asset path (e.g. "/Game/Mods/UserPack/Icons/T_UI_...")
        dt_constructions_data: Loaded DT_Constructions.json
    """
    template = _load_template("ConstructionTemplate.json")
    import_templates = _load_template("ImportTemplates.json")

    blueprint_name = asset_path.rsplit("/", 1)[-1]
    texture_name = f"T_UI_BuildIcon_{unique_tag}"

    # Set row Name
    template["Name"] = unique_tag
    # Set string table references
    template["Value"][0]["Value"] = f"{unique_tag}.Name"
    template["Value"][1]["Value"] = f"{unique_tag}.Description"
    # Set Actor path
    template["Value"][3]["Value"]["AssetPath"]["AssetName"] = (
        f"{asset_path}.{blueprint_name}_C"
    )
    # Set BackwardCompatibilityActors
    template["Value"][4]["Value"][0]["Value"][0]["Value"]["AssetPath"]["AssetName"] = (
        f"{asset_path}.{blueprint_name}_C"
    )
    # Add category tag
    template["Value"][5]["Value"][0]["Value"].append(category_tag)

    # Icon import index (negative, referencing Imports array)
    num_imports = len(dt_constructions_data["Imports"])
    package_import_idx = -1 - num_imports
    template["Value"][2]["Value"] = package_import_idx - 1

    # Extend NameMap
    dt_constructions_data["NameMap"].extend([
        unique_tag,
        asset_path,
        f"{asset_path}.{blueprint_name}_C",
        texture_name,
        icon_path,
    ])

    # Append row
    dt_constructions_data["Exports"][0]["Table"]["Data"].append(template)

    # Add icon imports
    package_import = import_templates["Package"].copy()
    package_import["ObjectName"] = icon_path

    texture_import = import_templates["Texture2D"].copy()
    texture_import["ObjectName"] = texture_name
    texture_import["OuterIndex"] = package_import_idx

    dt_constructions_data["Imports"].append(package_import)
    dt_constructions_data["Imports"].append(texture_import)


# ---------------------------------------------------------------------------
# Construction recipe creation
# ---------------------------------------------------------------------------

def create_construction_recipe_row(
    unique_tag: str,
    category_tag: str,
    materials: list[tuple[str, int]],
    unlock_option: str,
    unlock_requirement: str,
    dt_recipes_data: dict,
) -> None:
    """Create a new DT_ConstructionRecipes row and append it.

    Modifies dt_recipes_data in-place.

    Args:
        unique_tag: Unique row name matching the construction
        category_tag: Category for placement flags lookup
        materials: List of (item_tag, count) tuples
        unlock_option: "UnlockRequiredItems" or "UnlockRequiredConstructions"
        unlock_requirement: Tag of the unlock dependency
        dt_recipes_data: Loaded DT_ConstructionRecipes.json
    """
    template = _load_template("ConstructionRecipeTemplate.json")
    category_flags = _load_template("CategoryFlags.json")

    # Extend NameMap
    dt_recipes_data["NameMap"].append(unique_tag)
    for item_tag, _ in materials:
        dt_recipes_data["NameMap"].append(item_tag)

    # Look up placement flags for category
    flags = category_flags.get(category_tag)
    if not flags and "." in category_tag:
        _, sub = category_tag.split(".", 1)
        flags = category_flags.get(sub)
    if not flags:
        # Default to Furniture placement if category not found
        flags = category_flags.get("Furniture", [
            "EConstructionLocation::Base",
            "EPlacementType::FreePlacement",
            False, True, False, False, True,
        ])

    # Set template values
    template["Name"] = unique_tag
    template["Value"][0]["Value"][0]["Value"] = unique_tag  # ResultConstructionHandle
    template["Value"][2]["Value"] = flags[0]   # LocationRequirement
    template["Value"][3]["Value"] = flags[1]   # PlacementType
    template["Value"][4]["Value"] = flags[2]   # bOnWall
    template["Value"][5]["Value"] = flags[3]   # bOnFloor
    template["Value"][9]["Value"] = flags[4]   # bAutoFoundation
    template["Value"][10]["Value"] = flags[5]  # bInheritAutoFoundationStability
    template["Value"][11]["Value"] = flags[6]  # bAllowRefunds

    # Set required materials
    template["Value"][16]["Value"] = build_required_materials(materials)

    # Set unlock conditions
    unlock_items, unlock_constructions = build_unlock_condition(
        unlock_option, unlock_requirement
    )
    template["Value"][20]["Value"][3] = unlock_items
    template["Value"][20]["Value"][4] = unlock_constructions

    # Append row
    dt_recipes_data["Exports"][0]["Table"]["Data"].append(template)


# ---------------------------------------------------------------------------
# Item recipe creation (armor, weapons, tools)
# ---------------------------------------------------------------------------

def create_item_recipe_row(
    item_tag: str,
    item_handle_prefix: str,
    crafting_stations: list[str],
    materials: list[tuple[str, int]],
    unlock_option: str,
    unlock_requirement: str,
    dt_item_recipes_data: dict,
) -> None:
    """Create a new DT_ItemRecipes row and append it.

    Modifies dt_item_recipes_data in-place.

    Args:
        item_tag: Row name for the recipe (e.g. "MyArmor_Helmet")
        item_handle_prefix: Prefix for ResultItemHandle RowName
                           (e.g. "Armor" -> "Armor.MyArmor_Helmet")
        crafting_stations: List of crafting station tags
        materials: List of (item_tag, count) tuples
        unlock_option: "UnlockRequiredItems" or "UnlockRequiredConstructions"
        unlock_requirement: Tag of the unlock dependency
        dt_item_recipes_data: Loaded DT_ItemRecipes.json
    """
    template = _load_template("ItemRecipeTemplate.json")

    result_handle = f"{item_handle_prefix}.{item_tag}"

    # Set template values
    template["Name"] = item_tag
    template["Value"][0]["Value"][0]["Value"] = result_handle  # ResultItemHandle

    # Set crafting stations
    template["Value"][3]["Value"] = build_crafting_stations(crafting_stations)

    # Set required materials
    template["Value"][8]["Value"] = build_required_materials(materials)

    # Set unlock conditions
    unlock_items, unlock_constructions = build_unlock_condition(
        unlock_option, unlock_requirement
    )
    template["Value"][12]["Value"][3] = unlock_items
    template["Value"][12]["Value"][4] = unlock_constructions

    # Extend NameMap
    dt_item_recipes_data["NameMap"].append(item_tag)
    dt_item_recipes_data["NameMap"].append(result_handle)

    # Append row
    dt_item_recipes_data["Exports"][0]["Table"]["Data"].append(template)


# ---------------------------------------------------------------------------
# Generic row operations
# ---------------------------------------------------------------------------

def add_row_to_datatable(
    data: dict,
    row: dict,
    namemap_entries: list[str] | None = None,
) -> None:
    """Append a row to a DataTable's Exports[0].Table.Data.

    Args:
        data: Loaded DataTable JSON
        row: The row dict to append
        namemap_entries: Optional list of strings to add to NameMap
    """
    data["Exports"][0]["Table"]["Data"].append(row)
    if namemap_entries:
        data["NameMap"].extend(namemap_entries)


def remove_row_from_datatable(data: dict, row_name: str) -> bool:
    """Remove a row by Name from a DataTable's Exports[0].Table.Data.

    Args:
        data: Loaded DataTable JSON
        row_name: The Name field value of the row to remove

    Returns:
        True if a row was removed, False if not found
    """
    table_data = data["Exports"][0]["Table"]["Data"]
    for i, row in enumerate(table_data):
        if isinstance(row, dict) and row.get("Name") == row_name:
            table_data.pop(i)
            return True
    return False


def clone_existing_row(data: dict, source_name: str, new_name: str) -> dict | None:
    """Deep-copy an existing row and change its Name.

    Args:
        data: Loaded DataTable JSON
        source_name: Name of the row to clone
        new_name: Name for the cloned row

    Returns:
        The cloned row dict, or None if source not found.
        The clone is NOT automatically appended — call add_row_to_datatable.
    """
    table_data = data["Exports"][0]["Table"]["Data"]
    for row in table_data:
        if isinstance(row, dict) and row.get("Name") == source_name:
            cloned = copy.deepcopy(row)
            cloned["Name"] = new_name
            return cloned
    return None


def get_row_by_name(data: dict, row_name: str) -> dict | None:
    """Find and return a row by its Name field.

    Args:
        data: Loaded DataTable JSON
        row_name: The Name field to search for

    Returns:
        The row dict, or None if not found
    """
    table_data = data["Exports"][0]["Table"]["Data"]
    for row in table_data:
        if isinstance(row, dict) and row.get("Name") == row_name:
            return row
    return None


def set_row_property(row: dict, property_name: str, value) -> bool:
    """Set a named property value within a row's Value array.

    Searches row["Value"] for a dict with matching "Name" field and
    sets its "Value" key.

    Args:
        row: A DataTable row dict
        property_name: The property Name to find (e.g. "EnabledState")
        value: The value to set

    Returns:
        True if the property was found and set, False otherwise
    """
    for prop in row.get("Value", []):
        if isinstance(prop, dict) and prop.get("Name") == property_name:
            prop["Value"] = value
            return True
    return False


def get_row_property(row: dict, property_name: str):
    """Get a named property value from a row's Value array.

    Args:
        row: A DataTable row dict
        property_name: The property Name to find

    Returns:
        The property's Value, or None if not found
    """
    for prop in row.get("Value", []):
        if isinstance(prop, dict) and prop.get("Name") == property_name:
            return prop.get("Value")
    return None


# ---------------------------------------------------------------------------
# Sandbox-exclusive items (from RtoM-Moding-Tool)
# ---------------------------------------------------------------------------

SANDBOX_EXCLUSIVE_ITEMS = [
    {"Tag": "Spear_1h_t1_TU2", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_BasicForge"},
    {"Tag": "WarAxe_1h_t2", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_FurnaceUpgrade"},
    {"Tag": "WarAxe_1h_t3", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_FloodedForge"},
    {"Tag": "Battleaxe_2h_t2", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_ForgeUpgrade_GemCutter"},
    {"Tag": "Halberd_2h_t2", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_AdvancedForge"},
    {"Tag": "Sword_2h_t2", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_AdvancedForge"},
    {"Tag": "Battleaxe_2h_t4", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_MithrilForge"},
    {"Tag": "FamousElvenSword", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_LegendayElvishForge"},
    {"Tag": "Amazing_Set_HelmetArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "Wonderful_Set_HelmetArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "SouthernmostFireProof_Set_HelmetArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "BlueMountainsHunter_Set_TorsoArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "BlueMountainsHunter_Set_BootsArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "RangeBonus_Set_GlovesArmor", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "BowmansGloves", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.Hide"},
    {"Tag": "AntiColdTorso", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.BoltsOfCloth"},
    {"Tag": "AntiColdBoots", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.BoltsOfCloth"},
    {"Tag": "AntiColdGloves", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.BoltsOfCloth"},
    {"Tag": "AntiColdHelm", "UnlockOption": "UnlockRequiredItems", "UnlockRequirement": "Item.BoltsOfCloth"},
    {"Tag": "Nogrod_Set_TorsoArmor", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_NogrodForge"},
    {"Tag": "Nogrod_Set_GlovesArmor", "UnlockOption": "UnlockRequiredConstructions", "UnlockRequirement": "CraftingStation_NogrodForge"},
]
