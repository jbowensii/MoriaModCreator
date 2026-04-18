using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;

namespace MoriaMODCreator.Models;

/// <summary>
/// Types of form fields in the property editor.
/// Maps to Python buildings_view.py field rendering methods.
/// </summary>
public enum FormFieldType
{
    SectionHeader,
    Text,
    Dropdown,
    Checkbox,
    ReadOnly,
    InlineRow,    // Multiple fields rendered horizontally in one row
}

/// <summary>
/// A single editable field in the right-pane form editor.
/// Backed by ObservableObject for two-way binding.
/// </summary>
public partial class FormField : ObservableObject
{
    public string Name { get; init; } = "";
    public string Label { get; init; } = "";
    public string? Tooltip { get; init; }
    public FormFieldType FieldType { get; init; }

    [ObservableProperty] private string _value = "";
    public string OriginalValue { get; init; } = "";
    public List<string>? Options { get; init; }
    public bool IsReadOnly { get; init; }

    // For section headers
    public string? SectionColor { get; init; }

    // For inline grouping — InlineRow type holds sub-fields
    public List<FormField>? InlineFields { get; init; }

    public bool IsModified => Value != OriginalValue;
}

/// <summary>
/// A dynamic material row in the materials editor.
/// Mirrors Python's material_rows list entries.
/// </summary>
public partial class MaterialRow : ObservableObject
{
    [ObservableProperty] private string _material = "Item.Wood";
    [ObservableProperty] private string _amount = "1";
    [ObservableProperty] private bool _isRemoved;
    public List<string>? MaterialOptions { get; init; }
}

/// <summary>
/// Container for the materials/repair cost editor section.
/// </summary>
public partial class MaterialSection : ObservableObject
{
    public string Title { get; init; } = "Required Materials";
    public string FieldName { get; init; } = "DefaultRequiredMaterials";
    public ObservableCollection<MaterialRow> Rows { get; } = [];
    public List<string>? MaterialOptions { get; init; }
}

/// <summary>
/// Field descriptions matching Python FIELD_DESCRIPTIONS dict.
/// Used for tooltip display on form field labels.
/// </summary>
public static class FieldDescriptions
{
    public static readonly Dictionary<string, string> Descriptions = new(StringComparer.OrdinalIgnoreCase)
    {
        // === Construction Recipe Fields ===
        ["BuildingName"] = "Internal row name of this construction/building recipe",
        ["ResultConstructionHandle"] = "The construction definition this recipe builds (RowName from DT_Constructions)",
        ["BuildProcess"] = "How the construction is built (Hammer, Place, etc.)",
        ["PlacementType"] = "Where this construction can be placed (Floor, Wall, Ceiling, etc.)",
        ["LocationRequirement"] = "Required location type for placement (None, Indoors, Outdoors, etc.)",
        ["FoundationRule"] = "Foundation requirement (None, RequiresFoundation, IsFoundation, etc.)",
        ["MonumentType"] = "Monument category if this is a monument piece",

        // === Boolean placement flags ===
        ["bOnWall"] = "Can be placed on walls",
        ["bOnFloor"] = "Can be placed on floors",
        ["bPlaceOnWater"] = "Can be placed on water surfaces",
        ["bOverrideRotation"] = "Override default rotation behavior during placement",
        ["bAllowRefunds"] = "Allow material refund when deconstructed",
        ["bAutoFoundation"] = "Automatically creates foundation underneath",
        ["bInheritAutoFoundationStability"] = "Inherit stability from auto-generated foundation",
        ["bOnlyOnVoxel"] = "Can only be placed on voxel terrain",
        ["bIsBlockedByNearbySettlementStones"] = "Cannot be placed near settlement stones",
        ["bIsBlockedByNearbyRavenConstructions"] = "Cannot be placed near raven constructions",
        ["bHasSandboxRequirementsOverride"] = "Override material requirements in Sandbox mode",
        ["bHasSandboxUnlockOverride"] = "Override unlock conditions in Sandbox mode",

        // === Numeric fields ===
        ["MaxAllowedPenetrationDepth"] = "How far this can penetrate into terrain during placement",
        ["RequireNearbyRadius"] = "Radius within which a required construction must exist",
        ["CameraStateOverridePriority"] = "Camera behavior priority when interacting",

        // === Unlock fields ===
        ["Recipe_EnabledState"] = "Whether this recipe is enabled by default",
        ["DefaultUnlocks_UnlockType"] = "How this recipe is unlocked (None, Fragments, Construction, etc.)",
        ["DefaultUnlocks_NumFragments"] = "Number of fragments needed to unlock",
        ["DefaultRequiredItems"] = "Items required before this recipe can be used",
        ["DefaultRequiredConstructions"] = "Constructions that must exist before this can be built",
        ["DefaultRequiredFragments"] = "Fragment types needed to unlock this recipe",
        ["SandboxUnlocks_UnlockType"] = "Unlock type override for Sandbox mode",

        // === Construction Definition Fields ===
        ["DisplayName"] = "Name shown to the player in-game",
        ["Description"] = "Description shown in the construction UI",
        ["Actor"] = "Blueprint actor path for the construction's visual mesh",
        ["Tags"] = "Gameplay tags controlling categories, visibility, and behavior",
        ["Construction_EnabledState"] = "Whether this construction is enabled by default",
        ["BackwardCompatibilityActors"] = "Legacy actor paths for backward compatibility",
        ["IconIndex"] = "Index into the construction icon atlas (read-only)",

        // === Weapon Fields ===
        ["Damage"] = "Base damage per hit",
        ["Speed"] = "Attack speed multiplier",
        ["Durability"] = "Total durability before breaking",
        ["Tier"] = "Weapon tier (affects which enemies can be damaged)",
        ["ArmorPenetration"] = "Percentage of armor ignored on hit",
        ["StaminaCost"] = "Stamina consumed per attack",
        ["EnergyCost"] = "Energy consumed per attack",
        ["BlockDamageReduction"] = "Damage reduction percentage when blocking",

        // === Armor Fields ===
        ["DamageReduction"] = "Flat damage reduction per hit",
        ["DamageProtection"] = "Percentage damage reduction",

        // === Tool Fields ===
        ["DurabilityDecayWhileEquipped"] = "Durability lost per second while equipped",
        ["CarveHits"] = "Number of hits to carve a resource node",
        ["NpcMiningRate"] = "Mining speed multiplier for NPC workers",

        // === Item Fields ===
        ["Portability"] = "Item portability type (Inventory, CanCarry, Stationary)",
        ["MaxStackSize"] = "Maximum items per inventory stack",
        ["SlotSize"] = "Inventory slot size (Small, Medium, Large)",
        ["BaseTradeValue"] = "Base value when trading with merchants",
        ["Definition_EnabledState"] = "Whether this item definition is enabled",

        // === Flora Fields ===
        ["ItemRowHandle"] = "The item this plant drops when harvested",
        ["OverrideItemDropHandle"] = "Override item drop (if different from default)",
        ["MinCount"] = "Minimum items dropped when harvested",
        ["MaxCount"] = "Maximum items dropped when harvested",
        ["NumToGrowPerCycle"] = "Plants that grow per cycle",
        ["RegrowthSleepCount"] = "Cycles to wait before regrowth starts",
        ["FloraType"] = "Type of flora (Tree, Bush, Mushroom, etc.)",
        ["GrowthRate"] = "How fast this flora grows",
        ["MinRandomScale"] = "Minimum random scale variation",
        ["MaxRandomScale"] = "Maximum random scale variation",
        ["bPrefersInShade"] = "Grows better in shaded areas",
        ["bCanSpoil"] = "Can spoil/rot over time",
        ["IsPlantable"] = "Can be planted by the player",
        ["IsFungus"] = "Is a fungus (affects growth rules)",
        ["MinimumFarmingLight"] = "Minimum light level needed to grow",

        // === Loot Fields ===
        ["RequiredTags"] = "Tags required on the loot source",
        ["ItemHandle"] = "The item this loot entry drops",
        ["DropChance"] = "Probability of this item dropping (0.0 to 1.0)",
        ["MinQuantity"] = "Minimum quantity dropped",
        ["MaxQuantity"] = "Maximum quantity dropped",
        ["EnabledState"] = "Whether this loot entry is active",

        // === Recipe Fields ===
        ["ResultItemHandle"] = "The item this recipe produces",
        ["CraftingStations"] = "Stations where this recipe can be crafted",
        ["RequiredRecipes"] = "Recipes that must be unlocked first",
        ["CraftingTime"] = "Time in seconds to craft this item",
        ["CraftedAmount"] = "Number of items produced per craft",
    };

    /// <summary>Get tooltip for a field name, or null if none.</summary>
    public static string? GetTooltip(string fieldName)
    {
        return Descriptions.GetValueOrDefault(fieldName);
    }

    /// <summary>Format a material internal name for display. Item.Wood → "Wood (Item.Wood)"</summary>
    public static string FormatMaterialName(string internalName)
    {
        if (string.IsNullOrEmpty(internalName)) return internalName;

        // Strip common prefixes for the display portion
        var display = internalName;
        foreach (var prefix in new[] { "Item.", "Ore.", "Consumable.", "Tool.", "Fragment.", "Decoration." })
        {
            if (display.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            {
                display = display[prefix.Length..];
                break;
            }
        }

        // Insert spaces before capitals
        display = ToFriendlyLabel(display);

        return display == internalName ? internalName : $"{display} ({internalName})";
    }

    /// <summary>Convert a raw field name to a friendly label.</summary>
    public static string ToFriendlyLabel(string fieldName)
    {
        if (string.IsNullOrEmpty(fieldName)) return fieldName;

        // Strip leading 'b' from boolean fields
        if (fieldName.StartsWith('b') && fieldName.Length > 1 && char.IsUpper(fieldName[1]))
            fieldName = fieldName[1..];

        // Insert spaces before capitals: "ResultConstructionHandle" -> "Result Construction Handle"
        var result = new System.Text.StringBuilder();
        for (int i = 0; i < fieldName.Length; i++)
        {
            if (i > 0 && char.IsUpper(fieldName[i]) && !char.IsUpper(fieldName[i - 1]))
                result.Append(' ');
            result.Append(fieldName[i]);
        }

        return result.ToString();
    }
}
