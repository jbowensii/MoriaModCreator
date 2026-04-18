using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Object Editor tab: create/edit new objects with property editing.
/// Supports all 8 categories (Buildings, Weapons, Armor, Tools, Flora, Loot, Items, Ores).
/// Uses sentinel prefix "__object_editor__" under ChangeSecretsDir in "constructions" mode
/// so that NO game-row subtraction happens (all rows are new relative to vanilla).
/// </summary>
public partial class ObjectEditorViewModel : ObservableObject
{
    private const string SentinelPrefix = "__object_editor__";

    private readonly ConfigService _config;
    private readonly ObjectTemplateService _templates;
    private readonly CategoryDataService _categoryData;
    private readonly BuildService? _buildService;
    private readonly BuildingsDataService? _buildingsData;
    private readonly DiffService? _diffService;

    [ObservableProperty] private string _selectedCategory = "";
    [ObservableProperty] private CategoryItem? _selectedItem;
    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private bool _showPlaceholder = true;
    [ObservableProperty] private string _status = "";
    [ObservableProperty] private string _modName = "";
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private double _buildProgress;

    public ObservableCollection<string> Categories { get; } = [];
    public ObservableCollection<CategoryItem> Items { get; } = [];
    public ObservableCollection<CategoryItem> FilteredItems { get; } = [];
    public ObservableCollection<FormField> FormFields { get; } = [];
    public ObservableCollection<MaterialSection> MaterialSections { get; } = [];

    // Cached dropdown options
    private List<string> _materialOptions = [];
    private List<string> _actorOptions = [];
    private List<string> _constructionOptions = [];
    private readonly Dictionary<string, List<string>> _enumOptions = [];

    private readonly FormBuilder _form;

    public ObjectEditorViewModel(
        ConfigService config,
        ObjectTemplateService templates,
        CategoryDataService categoryData,
        BuildService? buildService,
        BuildingsDataService? buildingsData,
        DiffService? diffService)
    {
        _config = config;
        _templates = templates;
        _categoryData = categoryData;
        _buildService = buildService;
        _buildingsData = buildingsData;
        _diffService = diffService;

        _form = new FormBuilder(FormFields);

        foreach (var cat in new[] { "Buildings", "Weapons", "Armor", "Tools", "Flora", "Loot", "Items", "Ores" })
            Categories.Add(cat);

        // Use "constructions" mode so no game-row subtraction happens
        LoadDropdownOptions();
    }

    private void LoadDropdownOptions()
    {
        try
        {
            var opts = _categoryData.ScanDropdownOptions("constructions");
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

        try
        {
            var items = _categoryData.LoadCategoryItems("constructions", category, SentinelPrefix);
            foreach (var item in items)
                Items.Add(item);
            ApplyFilter();

            Status = items.Count > 0
                ? $"{category}: {items.Count} items loaded"
                : $"{category}: No items found. Add new items to get started.";
        }
        catch (Exception ex)
        {
            Status = $"Error loading {category}: {ex.Message}";
        }
    }

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
    }

    partial void OnSearchTextChanged(string value) => ApplyFilter();

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

        ShowPlaceholder = true;
        System.Windows.Application.Current.Dispatcher.BeginInvoke(
            System.Windows.Threading.DispatcherPriority.Background, () =>
        {
            try
            {
                BuildFormForCategory(item);
            }
            catch (Exception ex)
            {
                Status = $"Error loading form: {ex.Message}";
                System.Diagnostics.Debug.WriteLine($"[ObjectEditorVM] FORM BUILD ERROR: {ex}");
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
    // DATA-DEPENDENT FORM FIELD HELPERS
    // =========================================================================

    private void AddMaterialSection(Dictionary<string, object?> fields, string fieldName, string title)
    {
        var section = new MaterialSection
        {
            Title = title,
            FieldName = fieldName,
            MaterialOptions = _materialOptions.Count > 0 ? _materialOptions : null,
        };

        var rawValue = fields.GetValueOrDefault(fieldName);
        if (rawValue is List<object?> materialList)
        {
            foreach (var entry in materialList)
            {
                if (entry is not Dictionary<string, object?> matDict) continue;
                var mat = "Item.Wood";
                var amount = "1";

                if (matDict.TryGetValue("MaterialHandle", out var mh))
                {
                    if (mh is Dictionary<string, object?> mhDict && mhDict.TryGetValue("RowName", out var rn))
                        mat = rn?.ToString() ?? "Item.Wood";
                    else
                        mat = FormBuilder.FieldValueToString(mh);
                }
                else if (matDict.TryGetValue("Name", out var nameVal))
                    mat = nameVal?.ToString() ?? "Item.Wood";

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
    // ITEM COMMANDS: NewItem / SaveItem / RevertItem
    // =========================================================================

    [RelayCommand]
    private void NewItem()
    {
        if (string.IsNullOrWhiteSpace(SelectedCategory))
        {
            Status = "Select a category first";
            return;
        }

        var dialog = new Views.Dialogs.ConstructionNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow,
        };
        if (dialog.ShowDialog() != true || string.IsNullOrWhiteSpace(dialog.EnteredName)) return;

        var newName = dialog.EnteredName;
        if (Items.Any(i => i.RowName.Equals(newName, StringComparison.OrdinalIgnoreCase)))
        {
            Status = $"'{newName}' already exists";
            return;
        }

        var pathMap = CategoryDataService.ConstructionsPaths;
        if (!pathMap.TryGetValue(SelectedCategory, out var paths)) return;

        var baseDir = Path.Combine(_config.ChangeSecretsDir, SentinelPrefix);
        var cacheDir = Path.Combine(baseDir, SelectedCategory.ToLowerInvariant());
        Directory.CreateDirectory(cacheDir);
        var defJsonPath = Path.Combine(cacheDir, Path.GetFileName(paths.DefinitionPath));

        if (!File.Exists(defJsonPath))
        {
            var sourcePath = _config.FindSourceJson("constructions", paths.DefinitionPath);
            if (sourcePath != null && File.Exists(sourcePath))
                File.Copy(sourcePath, defJsonPath, overwrite: true);
        }

        var root = _templates.LoadJson(defJsonPath);
        if (root == null) { Status = "Failed to load template JSON"; return; }

        var firstRow = _templates.GetRowNames(root).FirstOrDefault();
        if (firstRow == null) { Status = "No template row available"; return; }

        var clone = _templates.CloneRow(root, firstRow, newName);
        if (clone == null) return;
        _templates.AddRow(root, clone);
        _templates.SaveJson(defJsonPath, root);

        SelectCategory(SelectedCategory);
        var created = Items.FirstOrDefault(i => i.RowName == newName);
        if (created != null) SelectItem(created);
        Status = $"Created new {SelectedCategory}: {newName}";
    }

    [RelayCommand]
    private void SaveItem()
    {
        if (SelectedItem == null) return;

        var edits = new Dictionary<string, object?>();
        foreach (var field in AllEditableFields())
        {
            if (field.IsReadOnly) continue;
            if (field.Value != field.OriginalValue)
                edits[field.Name] = field.Value;
        }
        foreach (var section in MaterialSections)
        {
            var mats = section.Rows.Where(r => !r.IsRemoved)
                .Select(r => new { r.Material, r.Amount }).ToList();
            if (mats.Count > 0)
                edits[section.FieldName] = System.Text.Json.JsonSerializer.Serialize(mats);
        }

        if (edits.Count == 0) { Status = "No changes"; return; }
        _categoryData.SaveItemEdits(SelectedItem, edits);
        Status = $"Saved {edits.Count} change(s)";
    }

    [RelayCommand]
    private void RevertItem()
    {
        if (SelectedItem == null) return;
        var rowName = SelectedItem.RowName;
        SelectCategory(SelectedCategory);
        var item = Items.FirstOrDefault(i => i.RowName == rowName);
        if (item != null) SelectItem(item);
        Status = "Reverted";
    }

    private IEnumerable<FormField> AllEditableFields()
    {
        foreach (var f in FormFields)
        {
            if (f.FieldType == FormFieldType.SectionHeader) continue;
            if (f.FieldType == FormFieldType.InlineRow && f.InlineFields != null)
            {
                foreach (var sub in f.InlineFields) yield return sub;
                continue;
            }
            yield return f;
        }
    }

    // =========================================================================
    // BUILD COMMANDS: BuildAsync / ChooseModName
    // =========================================================================

    [RelayCommand]
    private async Task BuildAsync()
    {
        if (string.IsNullOrWhiteSpace(ModName)) { Status = "Select a mod name first"; return; }

        IsBuilding = true;
        BuildProgress = 0;
        Status = "Generating .def files...";

        try
        {
            var baseDir = Path.Combine(_config.ChangeSecretsDir, SentinelPrefix);
            var pathMap = CategoryDataService.ConstructionsPaths;
            var generatedDefs = new List<string>();

            await Task.Run(() =>
            {
                foreach (var (category, paths) in pathMap)
                {
                    var categoryDir = Path.Combine(baseDir, category.ToLowerInvariant());
                    if (!Directory.Exists(categoryDir)) continue;

                    var defContent = _buildingsData!.GenerateDefFromCache("constructions", SentinelPrefix, category, paths);
                    if (string.IsNullOrEmpty(defContent)) continue;
                    var defPath = _buildingsData.SaveDefFile("constructions", SentinelPrefix, category, defContent);
                    if (!string.IsNullOrEmpty(defPath))
                        generatedDefs.Add(defPath);
                }
            });

            if (generatedDefs.Count == 0)
            {
                Status = "No changes to build. Create items first.";
                IsBuilding = false;
                return;
            }

            Status = $"Generated {generatedDefs.Count} .def file(s). Building mod...";
            BuildProgress = 0.2;

            var progress = new Progress<Services.BuildProgress>(p =>
            {
                Status = p.Status;
                BuildProgress = 0.2 + 0.8 * p.Progress;
            });

            var result = await _buildService!.BuildAsync(ModName, generatedDefs, includeSecrets: true, progress);
            Status = result.Success
                ? $"Build complete! {result.Message}"
                : $"Build failed: {result.Message}";
        }
        catch (Exception ex)
        {
            Status = $"Error: {ex.Message}";
        }
        finally
        {
            IsBuilding = false;
        }
    }

    [RelayCommand]
    private void ChooseModName()
    {
        var dialog = new Views.Dialogs.ModNameDialog { Owner = System.Windows.Application.Current.MainWindow };
        if (dialog.ShowDialog() == true && dialog.SelectedModName != null)
        {
            ModName = dialog.SelectedModName;
            Status = $"Mod '{ModName}' selected";
        }
    }
}
