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

    private readonly FormBuilder _form;

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
        _form = new FormBuilder(FormFields);

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
                    var valStr = FormBuilder.FieldValueToString(val);
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
        _form.AddSection("Construction Recipe", "#795548");
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddTextFieldWithOptions(fields, "ResultConstructionHandle", _constructionOptions, label: "Result Construction");
        _form.AddDropdown(fields, "BuildProcess", ["Hammer", "Place", "Auto"]);
        _form.AddDropdown(fields, "PlacementType", ["Floor", "Wall", "Ceiling", "Any", "Freeform"]);
        _form.AddDropdown(fields, "LocationRequirement", ["None", "Indoors", "Outdoors", "Underground"]);
        _form.AddDropdown(fields, "FoundationRule", ["None", "RequiresFoundation", "IsFoundation"]);
        _form.AddDropdown(fields, "MonumentType", ["None", "Small", "Medium", "Large"]);

        // Placement options (checkboxes)
        _form.AddSection("Placement Options", "#5D4037");
        _form.AddCheckbox(fields, "bOnWall");
        _form.AddCheckbox(fields, "bOnFloor");
        _form.AddCheckbox(fields, "bPlaceOnWater");
        _form.AddCheckbox(fields, "bOverrideRotation");
        _form.AddCheckbox(fields, "bAllowRefunds");
        _form.AddCheckbox(fields, "bAutoFoundation");
        _form.AddCheckbox(fields, "bInheritAutoFoundationStability");
        _form.AddCheckbox(fields, "bOnlyOnVoxel");

        // Blocking options
        _form.AddCheckbox(fields, "bIsBlockedByNearbySettlementStones");
        _form.AddCheckbox(fields, "bIsBlockedByNearbyRavenConstructions");

        // Numeric properties
        _form.AddSection("Numeric Properties", "#5D4037");
        _form.AddTextField(fields, "MaxAllowedPenetrationDepth");
        _form.AddTextField(fields, "RequireNearbyRadius");
        _form.AddTextField(fields, "CameraStateOverridePriority");

        // Materials
        AddMaterialSection(fields, "DefaultRequiredMaterials", "Required Materials");
        AddMaterialSection(fields, "SandboxRequiredMaterials", "Sandbox Materials");

        // Unlocks
        _form.AddSection("Default Unlocks", "#1565C0");
        _form.AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing", "Hidden"], label: "Enabled State");
        _form.AddDropdown(fields, "DefaultUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);
        _form.AddTextField(fields, "DefaultUnlocks_NumFragments");
        _form.AddTextField(fields, "DefaultRequiredItems");
        _form.AddTextField(fields, "DefaultRequiredConstructions");
        _form.AddTextField(fields, "DefaultRequiredFragments");

        // Sandbox unlocks
        _form.AddSection("Sandbox Overrides", "#1565C0");
        _form.AddCheckbox(fields, "bHasSandboxRequirementsOverride");
        _form.AddCheckbox(fields, "bHasSandboxUnlockOverride");
        _form.AddDropdown(fields, "SandboxUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);

        // --- Construction Definition Section ---
        _form.AddSection("Construction Definition", "#2E7D32");
        AddConstructionDefinitionFields(fields);
    }

    // =========================================================================
    // WEAPON FORM (item recipe + weapon definition)
    // =========================================================================

    private void BuildWeaponForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Item Recipe", "#E65100");
        AddItemRecipeFields(fields);

        _form.AddSection("Combat Stats", "#D84315");
        _form.AddInlineRow(fields, "Damage", "Speed", "Durability", "Tier");

        _form.AddSection("Advanced Stats", "#BF360C");
        _form.AddInlineRow(fields, "ArmorPenetration", "StaminaCost", "EnergyCost", "BlockDamageReduction");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        _form.AddSection("Display & Tags", "#E65100");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // ARMOR FORM
    // =========================================================================

    private void BuildArmorForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Item Recipe", "#1565C0");
        AddItemRecipeFields(fields);

        _form.AddSection("Defense Stats", "#0D47A1");
        _form.AddInlineRow(fields, "Durability", "DamageReduction", "DamageProtection");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        _form.AddSection("Display & Tags", "#1565C0");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // TOOL FORM
    // =========================================================================

    private void BuildToolForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Item Recipe", "#2E7D32");
        AddItemRecipeFields(fields);

        _form.AddSection("Tool Stats", "#1B5E20");
        _form.AddInlineRow(fields, "Durability", "DurabilityDecayWhileEquipped", "CarveHits");

        _form.AddSection("Advanced Stats", "#1B5E20");
        _form.AddInlineRow(fields, "StaminaCost", "EnergyCost", "NpcMiningRate");

        AddMaterialSection(fields, "InitialRepairCost", "Repair Cost");

        _form.AddSection("Display & Tags", "#2E7D32");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // ITEMS FORM
    // =========================================================================

    private void BuildItemsForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Item Recipe", "#6A1B9A");
        AddItemRecipeFields(fields);

        _form.AddSection("Item Definition", "#4A148C");
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // FLORA FORM
    // =========================================================================

    private void BuildFloraForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Flora Definition", "#388E3C");
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        _form.AddTextField(fields, "DisplayName");

        _form.AddSection("Item References", "#2E7D32");
        _form.AddTextField(fields, "ItemRowHandle");
        _form.AddTextField(fields, "OverrideItemDropHandle");

        _form.AddSection("Drop Amounts", "#2E7D32");
        _form.AddTextField(fields, "MinCount");
        _form.AddTextField(fields, "MaxCount");

        _form.AddSection("Growth Timing", "#1B5E20");
        _form.AddTextField(fields, "NumToGrowPerCycle");
        _form.AddTextField(fields, "RegrowthSleepCount");
        _form.AddTextField(fields, "MinVariableGrowthTime");
        _form.AddTextField(fields, "MaxVariableGrowthTime");

        _form.AddSection("Growth Properties", "#1B5E20");
        _form.AddCheckbox(fields, "bPrefersInShade");
        _form.AddCheckbox(fields, "bCanSpoil");
        _form.AddCheckbox(fields, "IsPlantable");
        _form.AddCheckbox(fields, "IsFungus");
        _form.AddTextField(fields, "MinimumFarmingLight");

        _form.AddSection("Type & Scale", "#388E3C");
        _form.AddDropdown(fields, "FloraType", ["Tree", "Bush", "Mushroom", "Herb", "Vine", "Flower"]);
        _form.AddDropdown(fields, "GrowthRate", ["Slow", "Medium", "Fast"]);
        _form.AddTextField(fields, "MinRandomScale");
        _form.AddTextField(fields, "MaxRandomScale");
        _form.AddTextField(fields, "ReceptacleActorToSpawn");
    }

    // =========================================================================
    // LOOT FORM
    // =========================================================================

    private void BuildLootForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Loot Definition", "#F57F17");
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        _form.AddTextField(fields, "RequiredTags");
        _form.AddTextField(fields, "ItemHandle");

        _form.AddSection("Drop Settings", "#F9A825");
        _form.AddTextField(fields, "DropChance");
        _form.AddTextField(fields, "MinQuantity");
        _form.AddTextField(fields, "MaxQuantity");
        _form.AddDropdown(fields, "EnabledState", ["Enabled", "Disabled"]);
    }

    // =========================================================================
    // ORES FORM
    // =========================================================================

    private void BuildOresForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Ore Definition", "#795548");
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        AddCommonItemFields(fields);
    }

    // =========================================================================
    // GENERIC FORM (fallback)
    // =========================================================================

    private void BuildGenericForm(Dictionary<string, object?> fields)
    {
        _form.AddSection("Properties", "#4d4d4d");
        foreach (var (name, value) in fields)
        {
            _form.AddTextField(fields, name);
        }
    }

    // =========================================================================
    // DATA-DEPENDENT FORM FIELD HELPERS (keep in BuildingsViewModel — need _materialOptions, _actorOptions, etc.)
    // =========================================================================

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
                        mat = FormBuilder.FieldValueToString(mh);
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
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        _form.AddTextField(fields, "ResultItemHandle", label: "Result Item");
        _form.AddTextField(fields, "CraftingStations");
        _form.AddTextField(fields, "CraftingTime");
        _form.AddTextField(fields, "CraftedAmount");

        AddMaterialSection(fields, "DefaultRequiredMaterials", "Required Materials");

        _form.AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing", "Hidden"], label: "Enabled State");
        _form.AddDropdown(fields, "DefaultUnlocks_UnlockType", ["None", "Fragments", "Construction", "Item"]);
        _form.AddTextField(fields, "DefaultUnlocks_NumFragments");
        _form.AddTextField(fields, "DefaultRequiredItems");
        _form.AddTextField(fields, "DefaultRequiredConstructions");
    }

    private void AddCommonItemFields(Dictionary<string, object?> fields)
    {
        _form.AddTextField(fields, "DisplayName");
        _form.AddTextField(fields, "Description");
        AddTextFieldWithOptions(fields, "Actor", _actorOptions);
        _form.AddDropdown(fields, "Tags", _enumOptions.GetValueOrDefault("Tags") ?? []);
        _form.AddDropdown(fields, "Portability", ["Inventory", "CanCarry", "Stationary"]);
        _form.AddTextField(fields, "MaxStackSize");
        _form.AddTextField(fields, "SlotSize");
        _form.AddTextField(fields, "BaseTradeValue");
        _form.AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing"], label: "Enabled State");
    }

    private void AddConstructionDefinitionFields(Dictionary<string, object?> fields)
    {
        _form.AddTextField(fields, "Name", label: "Row Name", readOnly: true);
        _form.AddTextField(fields, "DisplayName");
        _form.AddTextField(fields, "Description");
        AddTextFieldWithOptions(fields, "Actor", _actorOptions);
        _form.AddTextField(fields, "Icon", readOnly: true);
        _form.AddDropdown(fields, "Tags", _enumOptions.GetValueOrDefault("Tags") ?? []);
        AddTextFieldWithOptions(fields, "BackwardCompatibilityActors", _actorOptions);
        _form.AddDropdown(fields, "EnabledState", ["Live", "Disabled", "Testing"], label: "Enabled State");
    }

    /// <summary>Text field that also has dropdown options for autocomplete-like behavior.</summary>
    private void AddTextFieldWithOptions(Dictionary<string, object?> fields, string name, List<string> options,
        string? label = null)
    {
        if (options.Count > 0)
            _form.AddDropdown(fields, name, options, label);
        else
            _form.AddTextField(fields, name, label);
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
