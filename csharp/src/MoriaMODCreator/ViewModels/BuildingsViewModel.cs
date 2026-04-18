using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Shared view model for Change Secrets and Change Constructions tabs.
/// Manages category buttons, item list, right-pane form editing, and build.
/// Mirrors Python buildings_view.py / constructions_view.py.
/// </summary>
public partial class BuildingsViewModel : ObservableObject
{
    private readonly ConfigService _config;
    private readonly CategoryDataService _categoryData;
    private readonly BuildingsDataService _buildingsData;
    private readonly BuildService _buildService;
    private readonly DiffService _diffService;
    private readonly ObjectTemplateService _templates;
    private readonly string _mode;

    [ObservableProperty] private string _prefix = "";
    [ObservableProperty] private string _selectedCategory = "";
    [ObservableProperty] private CategoryItem? _selectedItem;
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private string _buildStatus = "";
    [ObservableProperty] private double _buildProgress;
    [ObservableProperty] private string _modName = "";
    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private string _formSearchText = "";
    [ObservableProperty] private string _formReplaceText = "";
    [ObservableProperty] private bool _showPlaceholder = true;
    [ObservableProperty] private bool _includeSecrets = true;
    [ObservableProperty] private string _bulkEyeIcon = "\U0001F441"; // 👁 eye

    public ObservableCollection<string> Categories { get; } = [];
    public ObservableCollection<CategoryItem> Items { get; } = [];
    public ObservableCollection<CategoryItem> FilteredItems { get; } = [];
    public ObservableCollection<FormField> FormFields { get; } = [];
    public ObservableCollection<MaterialSection> MaterialSections { get; } = [];

    public string ModeLabel { get; }

    // Cached dropdown options
    private List<string> _materialOptions = [];
    private List<string> _actorOptions = [];
    private List<string> _constructionOptions = [];
    private readonly Dictionary<string, List<string>> _enumOptions = [];

    public BuildingsViewModel(
        ConfigService config,
        CategoryDataService categoryData,
        BuildingsDataService buildingsData,
        BuildService buildService,
        DiffService diffService,
        ObjectTemplateService templates,
        string mode)
    {
        _config = config;
        _categoryData = categoryData;
        _buildingsData = buildingsData;
        _buildService = buildService;
        _diffService = diffService;
        _templates = templates;
        _mode = mode;
        ModeLabel = mode == "secrets" ? "Change Secrets" : "Change Constructions";

        foreach (var cat in new[] { "Buildings", "Weapons", "Armor", "Tools", "Flora", "Loot", "Items", "Ores" })
            Categories.Add(cat);

        // Load cached dropdown options from NameMap (Gap #3-4)
        LoadDropdownOptions();

        // Gap #34: Restore saved prefix
        LoadSavedPrefix();
    }

    private void LoadSavedPrefix()
    {
        var baseDir = _mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        var iniPath = System.IO.Path.Combine(baseDir, "current_prefix.ini");
        if (!System.IO.File.Exists(iniPath)) return;

        // Parse INI format: may be plain text "MyPrefix" or Python-style "[Section]\nkey = value"
        foreach (var line in System.IO.File.ReadAllLines(iniPath))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') || string.IsNullOrEmpty(trimmed)) continue;
            if (trimmed.Contains('='))
            {
                // "current_prefix = Secrets" → extract "Secrets"
                var val = trimmed[(trimmed.IndexOf('=') + 1)..].Trim();
                if (!string.IsNullOrEmpty(val))
                {
                    Prefix = val;
                    return;
                }
            }
            else
            {
                // Plain text format
                Prefix = trimmed;
                return;
            }
        }
    }

    private void LoadDropdownOptions()
    {
        try
        {
            var opts = _categoryData.ScanDropdownOptions(_mode);
            _materialOptions = opts.GetValueOrDefault("Materials") ?? [];
            _actorOptions = opts.GetValueOrDefault("Actors") ?? [];
            _constructionOptions = opts.GetValueOrDefault("Constructions") ?? [];
            _enumOptions["AllValues"] = opts.GetValueOrDefault("AllValues") ?? [];
            _enumOptions["Tags"] = opts.GetValueOrDefault("Tags") ?? [];
        }
        catch { /* ignore scan failures on startup */ }
    }

    // =========================================================================
    // CATEGORY SELECTION
    // =========================================================================

    [RelayCommand]
    private void SelectCategory(string category)
    {
        SelectedCategory = category;
        Items.Clear();
        FilteredItems.Clear();
        FormFields.Clear();
        MaterialSections.Clear();
        SelectedItem = null;
        ShowPlaceholder = true;

        // Sanitize prefix — trim whitespace and normalize
        Prefix = Prefix.Trim();
        if (string.IsNullOrWhiteSpace(Prefix))
        {
            BuildStatus = "Enter a prefix/change set name first, then select a category.";
            return;
        }

        try
        {
            var items = _categoryData.LoadCategoryItems(_mode, category, Prefix);
            foreach (var item in items)
                Items.Add(item);
            ComputeVisibility();
            RestoreCheckedStates();
            ApplyFilter();

            var checkedCount = items.Count(i => i.IsChecked);
            BuildStatus = items.Count > 0
                ? $"{category}: {items.Count} items loaded ({checkedCount} checked)"
                : $"{category}: No items found. Ensure Import has been run.";
        }
        catch (Exception ex)
        {
            // Log the full exception to file for diagnostics
            try
            {
                var logPath = System.IO.Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                    "MoriaMODCreator", "MoriaMODCreator.log");
                System.IO.File.AppendAllText(logPath,
                    $"  ERROR loading {category}: {ex.GetType().Name}: {ex.Message}\n  {ex.StackTrace}\n");
            }
            catch { }
            BuildStatus = $"Error loading {category}: {ex.Message}";
        }
    }

    /// <summary>Compute visibility for all loaded items based on EnabledState.</summary>
    private void ComputeVisibility()
    {
        foreach (var item in Items)
        {
            item.IsVisible = IsItemVisible(item.Fields);
        }
        UpdateBulkEyeState();
    }

    /// <summary>Determine if an item is visible based on EnabledState fields.</summary>
    private static bool IsItemVisible(Dictionary<string, object?> fields)
    {
        // Check EnabledState variants
        foreach (var key in new[] { "EnabledState" })
        {
            if (fields.TryGetValue(key, out var val) && val != null)
            {
                var str = val.ToString() ?? "";
                if (str.Contains("Disabled", StringComparison.OrdinalIgnoreCase) ||
                    str.Contains("Testing", StringComparison.OrdinalIgnoreCase))
                    return false;
            }
        }
        return true;
    }

    [ObservableProperty] private string _bulkEyeColor = "#4CAF50";

    private void UpdateBulkEyeState()
    {
        if (Items.Count == 0) { BulkEyeIcon = "\U0001F441"; BulkEyeColor = "#4CAF50"; return; }
        var allVisible = Items.All(i => i.IsVisible);
        var allHidden = Items.All(i => !i.IsVisible);
        BulkEyeIcon = allVisible ? "\U0001F441" : allHidden ? "\u2014" : "\U0001F441"; // 👁 or —
        BulkEyeColor = allVisible ? "#4CAF50" : allHidden ? "#F44336" : "#2196F3"; // green/red/blue
    }

    [RelayCommand]
    private void ToggleItemVisibility(CategoryItem? item)
    {
        if (item == null) return;
        item.IsVisible = !item.IsVisible;
        UpdateBulkEyeState();
    }

    [RelayCommand]
    private void ToggleBulkVisibility()
    {
        var anyHidden = Items.Any(i => !i.IsVisible);
        foreach (var item in Items)
            item.IsVisible = anyHidden; // if any hidden, make all visible; otherwise hide all
        UpdateBulkEyeState();
    }

    // =========================================================================
    // ITEM SELECTION & FORM BUILDING
    // =========================================================================

    [RelayCommand]
    private void SelectItem(CategoryItem? item)
    {
        SelectedItem = item;
        FormFields.Clear();
        MaterialSections.Clear();

        if (item == null)
        {
            ShowPlaceholder = true;
            return;
        }

        // Build form on dispatcher to prevent flicker
        ShowPlaceholder = true;
        System.Windows.Application.Current.Dispatcher.BeginInvoke(
            System.Windows.Threading.DispatcherPriority.Background, () =>
        {
            try
            {
                // Dump all field keys + value types for diagnostics
                foreach (var (key, val) in item.Fields.Take(15))
                {
                    var valStr = FieldValueToString(val);
                    var valType = val?.GetType().Name ?? "null";
                    System.IO.File.AppendAllText(
                        System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                            "MoriaMODCreator", "MoriaMODCreator.log"),
                        $"  FIELD: {key} = [{valType}] '{valStr}'\n");
                }

                BuildFormForCategory(item);
                System.IO.File.AppendAllText(
                    System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                        "MoriaMODCreator", "MoriaMODCreator.log"),
                    $"  FORM: {FormFields.Count} fields, {MaterialSections.Count} material sections\n");
            }
            catch (Exception ex)
            {
                BuildStatus = $"Error loading form: {ex.Message}";
                System.Diagnostics.Debug.WriteLine($"[BuildingsVM] FORM BUILD ERROR: {ex}");
            }
            ShowPlaceholder = false;
        });
    }

    private void BuildFormForCategory(CategoryItem item)
    {
        var fields = item.Fields;
        switch (SelectedCategory)
        {
            case "Buildings": BuildBuildingsForm(fields); break;
            case "Weapons": BuildWeaponForm(fields); break;
            case "Armor": BuildArmorForm(fields); break;
            case "Tools": BuildToolForm(fields); break;
            case "Flora": BuildFloraForm(fields); break;
            case "Loot": BuildLootForm(fields); break;
            case "Items": BuildItemsForm(fields); break;
            case "Ores": BuildOresForm(fields); break;
            default: BuildGenericForm(fields); break;
        }
    }

    // =========================================================================
    // BUILDINGS FORM (recipe + construction definition)
    // =========================================================================

    private void BuildBuildingsForm(Dictionary<string, object?> fields)
    {
        // --- Construction Recipe Section ---
        AddSection("Construction Recipe", "#795548");
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextFieldWithOptions(fields, "ResultConstructionHandle", _constructionOptions, label: "Result Construction");
        AddDropdown(fields, "BuildProcess", ["Hammer", "Place", "Auto"]);
        AddDropdown(fields, "PlacementType", ["Floor", "Wall", "Ceiling", "Any", "Freeform"]);
        AddDropdown(fields, "LocationRequirement", ["None", "Indoors", "Outdoors", "Underground"]);
        AddDropdown(fields, "FoundationRule", ["None", "RequiresFoundation", "IsFoundation"]);
        AddDropdown(fields, "MonumentType", ["None", "Small", "Medium", "Large"]);

        // Placement options (checkboxes)
        AddSection("Placement Options", "#5D4037");
        AddCheckbox(fields, "bOnWall");
        AddCheckbox(fields, "bOnFloor");
        AddCheckbox(fields, "bPlaceOnWater");
        AddCheckbox(fields, "bOverrideRotation");
        AddCheckbox(fields, "bAllowRefunds");
        AddCheckbox(fields, "bAutoFoundation");
        AddCheckbox(fields, "bInheritAutoFoundationStability");
        AddCheckbox(fields, "bOnlyOnVoxel");

        // Blocking options
        AddCheckbox(fields, "bIsBlockedByNearbySettlementStones");
        AddCheckbox(fields, "bIsBlockedByNearbyRavenConstructions");

        // Numeric properties
        AddSection("Numeric Properties", "#5D4037");
        AddTextField(fields, "MaxAllowedPenetrationDepth");
        AddTextField(fields, "RequireNearbyRadius");
        AddTextField(fields, "CameraStateOverridePriority");

        // Materials
        AddMaterialSection(fields, "DefaultRequiredMaterials", "Required Materials");
        AddMaterialSection(fields, "SandboxRequiredMaterials", "Sandbox Materials");

        // Unlocks
        AddSection("Default Unlocks", "#1565C0");
        AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing", "Hidden"], label: "Enabled State");
        AddDropdown(fields, "DefaultUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);
        AddTextField(fields, "DefaultUnlocks_NumFragments");
        AddTextField(fields, "DefaultRequiredItems");
        AddTextField(fields, "DefaultRequiredConstructions");
        AddTextField(fields, "DefaultRequiredFragments");

        // Sandbox unlocks
        AddSection("Sandbox Overrides", "#1565C0");
        AddCheckbox(fields, "bHasSandboxRequirementsOverride");
        AddCheckbox(fields, "bHasSandboxUnlockOverride");
        AddDropdown(fields, "SandboxUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);

        // --- Construction Definition Section ---
        AddSection("Construction Definition", "#2E7D32");
        AddConstructionDefinitionFields(fields);
    }

    // =========================================================================
    // WEAPON FORM (item recipe + weapon definition)
    // =========================================================================

    private void BuildWeaponForm(Dictionary<string, object?> fields)
    {
        AddSection("Item Recipe", "#E65100");
        AddItemRecipeFields(fields);

        AddSection("Combat Stats", "#D84315");
        AddInlineRow(fields, "Damage", "Speed", "Durability", "Tier");

        AddSection("Advanced Stats", "#BF360C");
        AddInlineRow(fields, "ArmorPenetration", "StaminaCost", "EnergyCost", "BlockDamageReduction");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        AddSection("Display & Tags", "#E65100");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // ARMOR FORM
    // =========================================================================

    private void BuildArmorForm(Dictionary<string, object?> fields)
    {
        AddSection("Item Recipe", "#1565C0");
        AddItemRecipeFields(fields);

        AddSection("Defense Stats", "#0D47A1");
        AddInlineRow(fields, "Durability", "DamageReduction", "DamageProtection");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        AddSection("Display & Tags", "#1565C0");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // TOOL FORM
    // =========================================================================

    private void BuildToolForm(Dictionary<string, object?> fields)
    {
        AddSection("Item Recipe", "#2E7D32");
        AddItemRecipeFields(fields);

        AddSection("Tool Stats", "#1B5E20");
        AddInlineRow(fields, "Durability", "DurabilityDecayWhileEquipped", "CarveHits");

        AddSection("Advanced Stats", "#1B5E20");
        AddInlineRow(fields, "StaminaCost", "EnergyCost", "NpcMiningRate");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        AddSection("Display & Tags", "#2E7D32");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // ITEMS FORM
    // =========================================================================

    private void BuildItemsForm(Dictionary<string, object?> fields)
    {
        AddSection("Item Recipe", "#6A1B9A");
        AddItemRecipeFields(fields);

        AddSection("Item Definition", "#4A148C");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // FLORA FORM
    // =========================================================================

    private void BuildFloraForm(Dictionary<string, object?> fields)
    {
        AddSection("Flora Definition", "#388E3C");
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextField(fields, "DisplayName");

        AddSection("Item References", "#2E7D32");
        AddTextField(fields, "ItemRowHandle");
        AddTextField(fields, "OverrideItemDropHandle");

        AddSection("Drop Amounts", "#2E7D32");
        AddTextField(fields, "MinCount");
        AddTextField(fields, "MaxCount");

        AddSection("Growth Timing", "#1B5E20");
        AddTextField(fields, "NumToGrowPerCycle");
        AddTextField(fields, "RegrowthSleepCount");
        AddTextField(fields, "MinVariableGrowthTime");
        AddTextField(fields, "MaxVariableGrowthTime");

        AddSection("Growth Properties", "#1B5E20");
        AddCheckbox(fields, "bPrefersInShade");
        AddCheckbox(fields, "bCanSpoil");
        AddCheckbox(fields, "IsPlantable");
        AddCheckbox(fields, "IsFungus");
        AddTextField(fields, "MinimumFarmingLight");

        AddSection("Type & Scale", "#388E3C");
        AddDropdown(fields, "FloraType", ["Tree", "Bush", "Mushroom", "Herb", "Vine", "Flower"]);
        AddDropdown(fields, "GrowthRate", ["Slow", "Medium", "Fast"]);
        AddTextField(fields, "MinRandomScale");
        AddTextField(fields, "MaxRandomScale");
        AddTextField(fields, "ReceptacleActorToSpawn");
    }

    // =========================================================================
    // LOOT FORM
    // =========================================================================

    private void BuildLootForm(Dictionary<string, object?> fields)
    {
        AddSection("Loot Definition", "#F57F17");
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextField(fields, "RequiredTags");
        AddTextField(fields, "ItemHandle");

        AddSection("Drop Settings", "#F9A825");
        AddTextField(fields, "DropChance");
        AddTextField(fields, "MinQuantity");
        AddTextField(fields, "MaxQuantity");
        AddDropdown(fields, "EnabledState", ["Enabled", "Disabled"]);
    }

    // =========================================================================
    // ORES FORM
    // =========================================================================

    private void BuildOresForm(Dictionary<string, object?> fields)
    {
        AddSection("Ore Definition", "#795548");
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // GENERIC FORM (fallback)
    // =========================================================================

    private void BuildGenericForm(Dictionary<string, object?> fields)
    {
        AddSection("Properties", "#4d4d4d");
        foreach (var (name, value) in fields)
        {
            AddTextField(fields, name);
        }
    }

    // =========================================================================
    // SHARED FORM FIELD HELPERS
    // =========================================================================

    private void AddSection(string title, string color)
    {
        FormFields.Add(new FormField
        {
            Name = $"__section_{title}",
            Label = title,
            FieldType = FormFieldType.SectionHeader,
            SectionColor = color,
        });
    }

    /// <summary>Convert a field value (which may be a complex type) to a display string.</summary>
    private static string FieldValueToString(object? value)
    {
        if (value == null) return "";
        if (value is string s) return s;
        if (value is bool b) return b.ToString();
        if (value is int or double or float or long) return value.ToString() ?? "";

        // Dictionary (from StructPropertyData) — extract RowName if present, else flatten
        if (value is Dictionary<string, object?> dict)
        {
            if (dict.TryGetValue("RowName", out var rowName) && rowName != null)
                return rowName.ToString() ?? "";
            if (dict.TryGetValue("Value", out var val) && val != null)
                return FieldValueToString(val);
            // Flatten to "key=value, key=value"
            return string.Join(", ", dict.Where(kv => kv.Value != null)
                .Select(kv => $"{kv.Key}={FieldValueToString(kv.Value)}").Take(5));
        }

        // List (from ArrayPropertyData) — join items
        if (value is List<object?> list)
        {
            if (list.Count == 0) return "";
            var items = list.Select(FieldValueToString).Where(s => !string.IsNullOrEmpty(s)).ToList();
            return items.Count <= 5 ? string.Join(", ", items) : $"{string.Join(", ", items.Take(5))}... ({items.Count} total)";
        }

        // List<string> (from tag extraction)
        if (value is List<string> strList)
            return string.Join(", ", strList);

        return value.ToString() ?? "";
    }

    /// <summary>Strip UE4 enum prefix: "EBuildProcess::DualMode" → "DualMode"</summary>
    private static string StripEnumPrefix(string value)
    {
        var idx = value.LastIndexOf("::", StringComparison.Ordinal);
        return idx >= 0 ? value[(idx + 2)..] : value;
    }

    private void AddTextField(Dictionary<string, object?> fields, string name,
        string? label = null, bool readOnly = false)
    {
        var value = FieldValueToString(fields.GetValueOrDefault(name));
        FormFields.Add(new FormField
        {
            Name = name,
            Label = label ?? FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = readOnly ? FormFieldType.ReadOnly : FormFieldType.Text,
            Value = value,
            OriginalValue = value,
            IsReadOnly = readOnly,
        });
    }

    private void AddDropdown(Dictionary<string, object?> fields, string name, List<string> options,
        string? label = null)
    {
        var rawObj = fields.GetValueOrDefault(name);
        var rawValue = FieldValueToString(rawObj);
        var value = StripEnumPrefix(rawValue);
        System.Diagnostics.Debug.WriteLine($"[AddDropdown] {name}: rawObj={rawObj?.GetType().Name ?? "null"} rawValue='{rawValue}' stripped='{value}'");
        // Add the actual value to options if not already present
        if (!string.IsNullOrEmpty(value) && !options.Contains(value))
            options = [value, .. options];
        FormFields.Add(new FormField
        {
            Name = name,
            Label = label ?? FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = FormFieldType.Dropdown,
            Value = value,
            OriginalValue = value,
            Options = options,
        });
    }

    private void AddCheckbox(Dictionary<string, object?> fields, string name)
    {
        var rawValue = fields.GetValueOrDefault(name);
        var boolStr = rawValue switch
        {
            bool b => b.ToString(),
            _ => FieldValueToString(rawValue),
        };
        if (string.IsNullOrEmpty(boolStr) || boolStr == "0") boolStr = "False";
        if (boolStr == "1") boolStr = "True";
        FormFields.Add(new FormField
        {
            Name = name,
            Label = FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = FormFieldType.Checkbox,
            Value = boolStr,
            OriginalValue = boolStr,
        });
    }

    private void AddMaterialSection(Dictionary<string, object?> fields, string fieldName, string title)
    {
        var section = new MaterialSection
        {
            Title = title,
            FieldName = fieldName,
            MaterialOptions = _materialOptions.Count > 0 ? _materialOptions : null,
        };

        // Parse existing materials from fields
        // After ExtractPropertyValue, materials are List<object?> of Dict<string, object?>
        // Each material dict has keys like: MaterialHandle → {RowName: "Item.Wood"}, Count → 5
        var rawValue = fields.GetValueOrDefault(fieldName);
        if (rawValue is List<object?> materialList)
        {
            foreach (var entry in materialList)
            {
                if (entry is not Dictionary<string, object?> matDict) continue;
                var mat = "Item.Wood";
                var amount = "1";

                // Extract MaterialHandle.RowName
                if (matDict.TryGetValue("MaterialHandle", out var mh))
                {
                    if (mh is Dictionary<string, object?> mhDict && mhDict.TryGetValue("RowName", out var rn))
                        mat = rn?.ToString() ?? "Item.Wood";
                    else
                        mat = FieldValueToString(mh);
                }
                // Or direct Name field
                else if (matDict.TryGetValue("Name", out var nameVal))
                    mat = nameVal?.ToString() ?? "Item.Wood";

                // Extract Count
                if (matDict.TryGetValue("Count", out var countVal))
                    amount = countVal?.ToString() ?? "1";
                else if (matDict.TryGetValue("Amount", out var amtVal))
                    amount = amtVal?.ToString() ?? "1";

                section.Rows.Add(new MaterialRow { Material = mat, Amount = amount });
            }
        }
        else if (rawValue is JsonArray arr)
        {
            foreach (var entry in arr)
            {
                var mat = entry?["Name"]?.GetValue<string>() ?? "Item.Wood";
                var valueArr = entry?["Value"] as JsonArray;
                var amount = "1";
                if (valueArr != null)
                {
                    foreach (var prop in valueArr)
                    {
                        if (prop?["Name"]?.GetValue<string>() == "Amount")
                            amount = prop["Value"]?.ToString() ?? "1";
                    }
                }
                section.Rows.Add(new MaterialRow { Material = mat, Amount = amount });
            }
        }
        else if (rawValue is JsonNode node)
        {
            // Try to parse from the raw value
            try
            {
                if (node is JsonArray matArr)
                {
                    foreach (var entry in matArr)
                    {
                        section.Rows.Add(new MaterialRow
                        {
                            Material = entry?.ToString() ?? "Item.Wood",
                            Amount = "1",
                        });
                    }
                }
            }
            catch { /* ignore parse errors */ }
        }

        MaterialSections.Add(section);
    }

    private void AddItemRecipeFields(Dictionary<string, object?> fields)
    {
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextField(fields, "ResultItemHandle", label: "Result Item");
        AddTextField(fields, "CraftingStations");
        AddTextField(fields, "CraftingTime");
        AddTextField(fields, "CraftedAmount");

        AddMaterialSection(fields, "DefaultRequiredMaterials", "Required Materials");

        AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing", "Hidden"], label: "Enabled State");
        AddDropdown(fields, "DefaultUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);
        AddTextField(fields, "DefaultUnlocks_NumFragments");
        AddTextField(fields, "DefaultRequiredItems");
        AddTextField(fields, "DefaultRequiredConstructions");
    }

    private void AddCommonItemFields(Dictionary<string, object?> fields)
    {
        AddTextField(fields, "DisplayName");
        AddTextField(fields, "Description");
        AddTextFieldWithOptions(fields, "Actor", _actorOptions);
        AddDropdown(fields, "Tags", _enumOptions.GetValueOrDefault("Tags") ?? []);
        AddDropdown(fields, "Portability", ["Inventory", "CanCarry", "Stationary"]);
        AddTextField(fields, "MaxStackSize");
        AddTextField(fields, "SlotSize");
        AddTextField(fields, "BaseTradeValue");
        AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing"], label: "Enabled State");
    }

    private void AddConstructionDefinitionFields(Dictionary<string, object?> fields)
    {
        AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextField(fields, "DisplayName");
        AddTextField(fields, "Description");
        AddTextFieldWithOptions(fields, "Actor", _actorOptions);
        AddTextField(fields, "Icon", readOnly: true);
        AddDropdown(fields, "Tags", _enumOptions.GetValueOrDefault("Tags") ?? []);
        AddTextFieldWithOptions(fields, "BackwardCompatibilityActors", _actorOptions);
        AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing"], label: "Enabled State");
    }

    /// <summary>Add multiple fields in a single horizontal row.</summary>
    private void AddInlineRow(Dictionary<string, object?> fields, params string[] names)
    {
        var inlineFields = new List<FormField>();
        foreach (var name in names)
        {
            var value = fields.GetValueOrDefault(name)?.ToString() ?? "";
            inlineFields.Add(new FormField
            {
                Name = name,
                Label = FieldDescriptions.ToFriendlyLabel(name),
                Tooltip = FieldDescriptions.GetTooltip(name),
                FieldType = FormFieldType.Text,
                Value = value,
                OriginalValue = value,
            });
        }

        FormFields.Add(new FormField
        {
            Name = $"__inline_{string.Join("_", names)}",
            FieldType = FormFieldType.InlineRow,
            InlineFields = inlineFields,
        });
    }

    /// <summary>Text field that also has dropdown options for autocomplete-like behavior.</summary>
    private void AddTextFieldWithOptions(Dictionary<string, object?> fields, string name, List<string> options,
        string? label = null)
    {
        if (options.Count > 0)
            AddDropdown(fields, name, options, label);
        else
            AddTextField(fields, name, label);
    }

    // =========================================================================
    // SEARCH & FILTER
    // =========================================================================

    [RelayCommand]
    private void ClearSearch() => SearchText = "";

    partial void OnSearchTextChanged(string value) => ApplyFilter();

    [ObservableProperty] private string _itemCountText = "";

    private void ApplyFilter()
    {
        FilteredItems.Clear();
        foreach (var item in Items)
        {
            if (string.IsNullOrEmpty(SearchText) ||
                item.DisplayName.Contains(SearchText, StringComparison.OrdinalIgnoreCase) ||
                item.RowName.Contains(SearchText, StringComparison.OrdinalIgnoreCase))
            {
                FilteredItems.Add(item);
            }
        }

        // Gap #31: "X of Y items" when filtered
        ItemCountText = FilteredItems.Count == Items.Count
            ? $"{Items.Count} items"
            : $"{FilteredItems.Count} of {Items.Count} items";
    }

    [RelayCommand]
    private void FormSearch()
    {
        if (string.IsNullOrEmpty(FormSearchText)) return;
        foreach (var field in AllEditableFields())
        {
            if (field.Label.Contains(FormSearchText, StringComparison.OrdinalIgnoreCase) ||
                field.Value.Contains(FormSearchText, StringComparison.OrdinalIgnoreCase))
            {
                BuildStatus = $"Found in: {field.Label}";
                return;
            }
        }
        BuildStatus = $"'{FormSearchText}' not found";
    }

    [RelayCommand]
    private void FormReplaceAll()
    {
        if (string.IsNullOrEmpty(FormSearchText)) return;
        int count = 0;
        foreach (var field in AllEditableFields())
        {
            if (field.IsReadOnly) continue;
            if (field.Value.Contains(FormSearchText, StringComparison.OrdinalIgnoreCase))
            {
                field.Value = field.Value.Replace(FormSearchText, FormReplaceText,
                    StringComparison.OrdinalIgnoreCase);
                count++;
            }
        }
        BuildStatus = count > 0 ? $"Replaced in {count} field(s)" : "No matches found";
    }

    // =========================================================================
    // MATERIAL ROW MANAGEMENT
    // =========================================================================

    [RelayCommand]
    private void AddMaterialRow(MaterialSection section)
    {
        section.Rows.Add(new MaterialRow
        {
            Material = "Item.Wood",
            Amount = "1",
            MaterialOptions = section.MaterialOptions,
        });
    }

    [RelayCommand]
    private void RemoveMaterialRow(MaterialRow row)
    {
        row.IsRemoved = true;
        // Remove from parent section
        foreach (var section in MaterialSections)
        {
            if (section.Rows.Remove(row)) break;
        }
    }

    // =========================================================================
    // SAVE & REVERT
    // =========================================================================

    /// <summary>Enumerate all editable fields including inline sub-fields.</summary>
    private IEnumerable<FormField> AllEditableFields()
    {
        foreach (var field in FormFields)
        {
            if (field.FieldType == FormFieldType.SectionHeader) continue;
            if (field.FieldType == FormFieldType.InlineRow && field.InlineFields != null)
            {
                foreach (var sub in field.InlineFields)
                    yield return sub;
                continue;
            }
            yield return field;
        }
    }

    [RelayCommand]
    private void SaveItem()
    {
        if (SelectedItem == null) return;

        var editedFields = new Dictionary<string, object?>();
        foreach (var field in AllEditableFields())
        {
            if (field.IsReadOnly) continue;
            if (field.Value != field.OriginalValue)
                editedFields[field.Name] = field.Value;
        }

        // Include material section edits
        foreach (var section in MaterialSections)
        {
            var materials = section.Rows
                .Where(r => !r.IsRemoved)
                .Select(r => new { r.Material, r.Amount })
                .ToList();
            if (materials.Count > 0)
                editedFields[section.FieldName] = System.Text.Json.JsonSerializer.Serialize(materials);
        }

        if (editedFields.Count == 0)
        {
            BuildStatus = "No changes to save";
            return;
        }

        _categoryData.SaveItemEdits(SelectedItem, editedFields);
        SelectedItem.IsChecked = true;
        SaveCheckedStates();
        BuildStatus = $"Saved {editedFields.Count} change(s) to {SelectedItem.DisplayName}";
    }

    [RelayCommand]
    private void RevertItem()
    {
        if (SelectedItem == null) return;

        // Reload from original source (not cache) — Gap #8
        var pathMap = _mode == "secrets" ? CategoryDataService.SecretsPaths : CategoryDataService.ConstructionsPaths;
        if (pathMap.TryGetValue(SelectedCategory, out var paths))
        {
            var sourcePath = _config.FindSourceJson(_mode, paths.DefinitionPath);
            if (sourcePath != null && System.IO.File.Exists(sourcePath))
            {
                var root = _templates.LoadJson(sourcePath);
                if (root != null)
                {
                    var row = _templates.GetRowByName(root, SelectedItem.RowName);
                    if (row != null)
                    {
                        // Re-extract fields from original source
                        var freshFields = SelectedCategory switch
                        {
                            "Buildings" => _templates.ExtractConstructionFields(row),
                            "Weapons" => _templates.ExtractWeaponFields(row),
                            "Armor" => _templates.ExtractArmorFields(row),
                            "Tools" => _templates.ExtractToolFields(row),
                            "Flora" => _templates.ExtractFloraFields(row),
                            "Loot" => _templates.ExtractLootFields(row),
                            "Items" or "Ores" => _templates.ExtractItemFields(row),
                            _ => _templates.ExtractRecipeFields(row),
                        };

                        // Update the item's fields and rebuild form
                        foreach (var (k, v) in freshFields)
                            SelectedItem.Fields[k] = v;
                    }
                }
            }
        }

        // Rebuild the form from the (now-refreshed) data
        FormFields.Clear();
        MaterialSections.Clear();
        BuildFormForCategory(SelectedItem);
        BuildStatus = "Reverted to original values";
    }

    // =========================================================================
    // NEW ITEM CREATION (Gap #25)
    // =========================================================================

    [RelayCommand]
    private void NewItem()
    {
        if (string.IsNullOrWhiteSpace(Prefix) || string.IsNullOrWhiteSpace(SelectedCategory))
        {
            BuildStatus = "Select a prefix and category first";
            return;
        }

        // Prompt for name
        var dialog = new Views.Dialogs.ConstructionNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow
        };
        if (dialog.ShowDialog() != true || string.IsNullOrWhiteSpace(dialog.EnteredName))
            return;

        var newName = dialog.EnteredName;

        // Check uniqueness
        if (Items.Any(i => i.RowName.Equals(newName, StringComparison.OrdinalIgnoreCase)))
        {
            BuildStatus = $"'{newName}' already exists";
            return;
        }

        // Get the cache JSON path and clone from first existing row as template
        var pathMap = _mode == "secrets" ? CategoryDataService.SecretsPaths : CategoryDataService.ConstructionsPaths;
        if (!pathMap.TryGetValue(SelectedCategory, out var paths)) return;

        var baseDir = _mode == "secrets"
            ? System.IO.Path.Combine(_config.ChangeSecretsDir, Prefix)
            : System.IO.Path.Combine(_config.ChangeConstructionsDir, Prefix);
        var cacheDir = System.IO.Path.Combine(baseDir, SelectedCategory.ToLowerInvariant());
        var defJsonPath = System.IO.Path.Combine(cacheDir, System.IO.Path.GetFileName(paths.DefinitionPath));

        if (!System.IO.File.Exists(defJsonPath))
        {
            BuildStatus = "No JSON data for this category. Load items first.";
            return;
        }

        var root = _templates.LoadJson(defJsonPath);
        if (root == null) return;

        // Clone the first row as a template
        var firstRow = _templates.GetRowNames(root).FirstOrDefault();
        if (firstRow == null)
        {
            BuildStatus = "No template row available to clone";
            return;
        }

        var clone = _templates.CloneRow(root, firstRow, newName);
        if (clone == null) return;

        _templates.AddRow(root, clone);
        _templates.SaveJson(defJsonPath, root);

        // Reload the category
        SelectCategory(SelectedCategory);

        // Select the new item
        var newItem = Items.FirstOrDefault(i => i.RowName == newName);
        if (newItem != null) SelectItem(newItem);

        BuildStatus = $"Created new {SelectedCategory} item: {newName}";
    }

    // =========================================================================
    // CHECKED STATE PERSISTENCE (Gap #2)
    // =========================================================================

    private void RestoreCheckedStates()
    {
        if (string.IsNullOrWhiteSpace(Prefix) || string.IsNullOrWhiteSpace(SelectedCategory)) return;
        var states = _buildingsData.LoadCheckedStates(_mode, Prefix);
        foreach (var item in Items)
        {
            var key = $"{SelectedCategory}|{item.RowName}";
            if (states.TryGetValue(key, out var isChecked))
                item.IsChecked = isChecked;
        }
    }

    private void SaveCheckedStates()
    {
        if (string.IsNullOrWhiteSpace(Prefix) || string.IsNullOrWhiteSpace(SelectedCategory)) return;

        // Load existing states (other categories)
        var states = _buildingsData.LoadCheckedStates(_mode, Prefix);

        // Remove current category entries and re-add
        var keysToRemove = states.Keys.Where(k => k.StartsWith($"{SelectedCategory}|")).ToList();
        foreach (var k in keysToRemove) states.Remove(k);

        foreach (var item in Items)
        {
            if (item.IsChecked)
                states[$"{SelectedCategory}|{item.RowName}"] = true;
        }

        _buildingsData.SaveCheckedStates(_mode, Prefix, states);
    }

    // =========================================================================
    // PREFIX / CHANGE SET
    // =========================================================================

    [RelayCommand]
    private void ChoosePrefix()
    {
        System.Windows.Window dialog = _mode == "secrets"
            ? new Views.Dialogs.ChangeSecretsDialog(_mode, _config)
            : new Views.Dialogs.ChangeConstructionsDialog(_mode, _config);
        dialog.Owner = System.Windows.Application.Current.MainWindow;

        var dlgResult = dialog.ShowDialog();
        string? selected = dialog switch
        {
            Views.Dialogs.ChangeSecretsDialog s => s.SelectedPrefix,
            Views.Dialogs.ChangeConstructionsDialog c => c.SelectedPrefix,
            _ => null,
        };
        if (dlgResult == true && selected != null)
        {
            Prefix = selected;
            BuildStatus = $"Change set '{Prefix}' selected";
            if (!string.IsNullOrEmpty(SelectedCategory))
                SelectCategory(SelectedCategory);
        }
    }

    [RelayCommand]
    private void ChooseModName()
    {
        var dialog = new Views.Dialogs.ModNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow
        };
        if (dialog.ShowDialog() == true && dialog.SelectedModName != null)
        {
            ModName = dialog.SelectedModName;
            BuildStatus = $"Mod '{ModName}' selected";
        }
    }

    // =========================================================================
    // BUILD
    // =========================================================================

    [RelayCommand]
    private async Task BuildAsync()
    {
        if (string.IsNullOrWhiteSpace(Prefix))
        {
            BuildStatus = "Enter a prefix name first";
            return;
        }
        if (string.IsNullOrWhiteSpace(ModName))
        {
            BuildStatus = "Select a mod name first";
            return;
        }

        SaveCheckedStates();
        IsBuilding = true;
        BuildProgress = 0;
        BuildStatus = "Generating .def files from changes...";

        try
        {
            var pathMap = _mode == "secrets"
                ? CategoryDataService.SecretsPaths
                : CategoryDataService.ConstructionsPaths;

            var generatedDefs = new List<string>();

            await Task.Run(() =>
            {
                foreach (var (category, paths) in pathMap)
                {
                    var defContent = _buildingsData.GenerateDefFromCache(_mode, Prefix, category, paths);
                    if (string.IsNullOrEmpty(defContent)) continue;
                    var defPath = _buildingsData.SaveDefFile(_mode, Prefix, category, defContent);
                    if (!string.IsNullOrEmpty(defPath))
                        generatedDefs.Add(defPath);
                }
            });

            if (generatedDefs.Count == 0)
            {
                BuildStatus = "No changes found to build. Edit some items first.";
                IsBuilding = false;
                return;
            }

            BuildStatus = $"Generated {generatedDefs.Count} .def file(s). Building mod...";
            BuildProgress = 0.2;

            var includeSecrets = _mode == "secrets";
            var progress = new Progress<BuildProgress>(p =>
            {
                BuildStatus = p.Status;
                BuildProgress = 0.2 + 0.8 * p.Progress;
            });

            var result = await _buildService.BuildAsync(ModName, generatedDefs, includeSecrets, progress);
            BuildStatus = result.Success
                ? $"Build complete! {result.Message}"
                : $"Build failed: {result.Message}";
        }
        catch (Exception ex)
        {
            BuildStatus = $"Error: {ex.Message}";
        }
        finally
        {
            IsBuilding = false;
        }
    }

    [RelayCommand]
    private void RefreshCache()
    {
        if (string.IsNullOrWhiteSpace(Prefix))
        {
            BuildStatus = "Enter a prefix first, then refresh.";
            return;
        }

        if (string.IsNullOrWhiteSpace(SelectedCategory))
        {
            // Refresh dropdown options
            LoadDropdownOptions();
            BuildStatus = "Dropdown options refreshed. Select a category.";
            return;
        }

        // Delete cached files to force re-copy from source
        var baseDir = _mode == "secrets"
            ? System.IO.Path.Combine(_config.ChangeSecretsDir, Prefix)
            : System.IO.Path.Combine(_config.ChangeConstructionsDir, Prefix);
        var cacheDir = System.IO.Path.Combine(baseDir, SelectedCategory.ToLowerInvariant());
        if (System.IO.Directory.Exists(cacheDir))
        {
            foreach (var file in System.IO.Directory.GetFiles(cacheDir, "*.json"))
            {
                try { System.IO.File.Delete(file); } catch { }
            }
        }

        // Re-apply edits from manifest after cache refresh
        var pathMap = _mode == "secrets" ? CategoryDataService.SecretsPaths : CategoryDataService.ConstructionsPaths;
        if (pathMap.TryGetValue(SelectedCategory, out var paths))
        {
            _buildingsData.RefreshCache(_mode, Prefix, SelectedCategory, paths);
        }

        SelectCategory(SelectedCategory);
        BuildStatus = $"Cache refreshed for {SelectedCategory}";
    }
}

public partial class FieldEntry : ObservableObject
{
    [ObservableProperty] private string _value = "";
    public string Name { get; init; } = "";
    public string OriginalValue { get; init; } = "";
}
