using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Loads and caches JSON DataTable data for category-based views
/// (Change Secrets / Change Constructions).
/// Handles scanning JSON files, extracting row data, resolving display names,
/// and managing the edits.json manifest.
/// </summary>
public class CategoryDataService
{
    private readonly ConfigService _config;
    private readonly ObjectTemplateService _templates;
    private readonly ILogger<CategoryDataService> _logger;

    // Category → (definition JSON path, recipe JSON path)
    public static readonly Dictionary<string, CategoryPaths> SecretsPaths = new()
    {
        ["Buildings"] = new("Tech/Data/Building/DT_Constructions.json", "Tech/Data/Building/DT_ConstructionRecipes.json"),
        ["Weapons"] = new("Tech/Data/Items/DT_Weapons.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Armor"] = new("Tech/Data/Items/DT_Armor.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Tools"] = new("Tech/Data/Items/DT_Tools.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Flora"] = new("Tech/Data/GameWorld/DT_Moria_Flora.json", null),
        ["Loot"] = new("Character/AI/DT_Loot.json", null),
        ["Items"] = new("Tech/Data/Items/DT_Items.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Ores"] = new("Tech/Data/Items/DT_Ores.json", null),
    };

    public static readonly Dictionary<string, CategoryPaths> ConstructionsPaths = new()
    {
        ["Buildings"] = new("Tech/Data/Building/DT_Constructions.json", "Tech/Data/Building/DT_ConstructionRecipes.json"),
        ["Weapons"] = new("Tech/Data/Items/DT_Weapons.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Armor"] = new("Tech/Data/Items/DT_Armor.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Tools"] = new("Tech/Data/Items/DT_Tools.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Flora"] = new("Tech/Data/GameWorld/DT_Moria_Flora.json", null),
        ["Loot"] = new("Character/AI/DT_Loot.json", null),
        ["Items"] = new("Tech/Data/Items/DT_Items.json", "Tech/Data/Items/DT_ItemRecipes.json"),
        ["Ores"] = new("Tech/Data/Items/DT_Ores.json", null),
    };

    // Row cache: file path → (row name → row node). Invalidated on save.
    private readonly Dictionary<string, Dictionary<string, System.Text.Json.Nodes.JsonNode>> _rowCache = [];

    public CategoryDataService(ConfigService config, ObjectTemplateService templates, ILogger<CategoryDataService> logger)
    {
        _config = config;
        _templates = templates;
        _logger = logger;
    }

    /// <summary>Clear the row cache (call after save or cache refresh).</summary>
    public void InvalidateCache() => _rowCache.Clear();

    /// <summary>Invalidate cache for a specific file.</summary>
    public void InvalidateCache(string filePath) => _rowCache.Remove(filePath);

    /// <summary>
    /// Load all items for a category from the cached JSON files.
    /// Returns a list of (rowName, displayName, fields) tuples.
    /// </summary>
    public List<CategoryItem> LoadCategoryItems(string mode, string category, string prefix)
    {
        var pathMap = mode == "secrets" ? SecretsPaths : ConstructionsPaths;
        if (!pathMap.TryGetValue(category, out var paths))
        {
            _logger.LogWarning("LoadCategoryItems: unknown category {Category}", category);
            return [];
        }

        var baseDir = mode == "secrets"
            ? Path.Combine(_config.ChangeSecretsDir, prefix)
            : Path.Combine(_config.ChangeConstructionsDir, prefix);

        var cacheDir = Path.Combine(baseDir, category.ToLowerInvariant());
        var defJsonPath = Path.Combine(cacheDir, Path.GetFileName(paths.DefinitionPath));

        _logger.LogInformation("LoadCategoryItems: mode={Mode} category={Category} prefix={Prefix}", mode, category, prefix);
        _logger.LogInformation("  CacheDir: {CacheDir}", cacheDir);
        _logger.LogInformation("  DefJsonPath: {DefJsonPath}", defJsonPath);

        // Try loading from cache first, then from source
        if (!File.Exists(defJsonPath))
        {
            // Copy from source
            var sourcePath = _config.FindSourceJson(mode, paths.DefinitionPath);
            _logger.LogInformation("  Source JSON: {SourcePath} (exists={Exists})",
                sourcePath ?? "(null)", sourcePath != null && File.Exists(sourcePath));
            if (sourcePath != null && File.Exists(sourcePath))
            {
                Directory.CreateDirectory(cacheDir);
                File.Copy(sourcePath, defJsonPath, true);
                _logger.LogInformation("  Copied source to cache");
            }
        }
        else
        {
            _logger.LogInformation("  Using cached file");
        }

        if (!File.Exists(defJsonPath))
        {
            _logger.LogWarning("Definition JSON not found: {Path}", defJsonPath);
            return [];
        }

        var root = _templates.LoadJson(defJsonPath);
        if (root == null) return [];

        var items = new List<CategoryItem>();
        var rowNames = new HashSet<string>(_templates.GetRowNames(root));

        // For secrets mode: subtract game rows by name — only show mod-ADDED items
        // (matching Python _populate_secrets_list which does secrets_names - game_names)
        // For constructions mode: show ALL game items (no subtraction)
        if (mode == ImportService.ModeSecrets)
        {
            var gameJsonPath = Path.Combine(_config.OutputJsonDataDir, "Moria", "Content", paths.DefinitionPath);
            if (File.Exists(gameJsonPath))
            {
                var gameRoot = _templates.LoadJson(gameJsonPath);
                if (gameRoot != null)
                {
                    var gameRowNames = new HashSet<string>(_templates.GetRowNames(gameRoot));
                    var before = rowNames.Count;
                    rowNames.ExceptWith(gameRowNames);
                    _logger.LogInformation("Secrets filter {Category}: {Before} total - {Game} game = {After} mod-only",
                        category, before, gameRowNames.Count, rowNames.Count);
                }
            }
            else
            {
                _logger.LogWarning("Game JSON not found for subtraction: {Path}. Run Import to extract game data.",
                    paths.DefinitionPath);
            }
        }

        // For categories with both recipe + definition files, load the recipe JSON too
        System.Text.Json.Nodes.JsonNode? recipeRoot = null;
        if (paths.RecipePath != null)
        {
            var recipeJsonPath = Path.Combine(cacheDir, Path.GetFileName(paths.RecipePath));
            if (!File.Exists(recipeJsonPath))
            {
                var recipeSourcePath = _config.FindSourceJson(mode, paths.RecipePath);
                if (recipeSourcePath != null && File.Exists(recipeSourcePath))
                {
                    Directory.CreateDirectory(cacheDir);
                    File.Copy(recipeSourcePath, recipeJsonPath, true);
                }
            }
            if (File.Exists(recipeJsonPath))
                recipeRoot = _templates.LoadJson(recipeJsonPath);

            _logger.LogInformation("  Recipe JSON loaded: {Loaded} ({Path})",
                recipeRoot != null, paths.RecipePath);
        }

        foreach (var rowName in rowNames)
        {
            // Extract fields from the DEFINITION file (DT_Constructions, DT_Weapons, etc.)
            var row = _templates.GetRowByName(root, rowName);
            if (row == null) continue;

            var fields = category switch
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

            // Merge recipe fields if recipe file exists (Buildings, Weapons, Armor, Tools, Items)
            if (recipeRoot != null)
            {
                var recipeRow = _templates.GetRowByName(recipeRoot, rowName);
                if (recipeRow != null)
                {
                    var recipeFields = _templates.ExtractRecipeFields(recipeRow);
                    // Prefix recipe fields to avoid collision, or merge directly
                    foreach (var (key, value) in recipeFields)
                    {
                        if (!fields.ContainsKey(key))
                            fields[key] = value;
                    }
                }
            }

            if (items.Count == 0)
            {
                // Log the first item's field details for debugging
                _logger.LogInformation("  First item '{Row}': {FieldCount} fields extracted: {Fields}",
                    rowName, fields.Count,
                    string.Join(", ", fields.Keys.Take(8)));
            }

            // Try to get display name — format as "DisplayName (RowName)" when different
            var displayName = ResolveDisplayName(fields, rowName);
            var formattedName = displayName != rowName
                ? $"{displayName} ({rowName})"
                : rowName;
            items.Add(new CategoryItem(rowName, formattedName, fields, defJsonPath));
        }

        _logger.LogInformation("Loaded {Count} items for {Category} in {Mode}/{Prefix}",
            items.Count, category, mode, prefix);
        return items;
    }

    /// <summary>Save edits for an item to the JSON file and edits manifest.</summary>
    public void SaveItemEdits(CategoryItem item, Dictionary<string, object?> editedFields)
    {
        InvalidateCache(item.JsonFilePath);
        if (!File.Exists(item.JsonFilePath)) return;

        var root = _templates.LoadJson(item.JsonFilePath);
        if (root == null) return;

        var row = _templates.GetRowByName(root, item.RowName);
        if (row == null) return;

        foreach (var (fieldName, value) in editedFields)
        {
            if (value is string strVal)
            {
                var valueArray = row["Value"] as JsonArray;
                if (valueArray == null) continue;

                foreach (var prop in valueArray)
                {
                    if (prop?["Name"]?.GetValue<string>() == fieldName)
                    {
                        var existing = prop!["Value"];
                        prop["Value"] = existing?.GetValueKind() switch
                        {
                            JsonValueKind.Number when int.TryParse(strVal, out var i) => JsonValue.Create(i),
                            JsonValueKind.Number when double.TryParse(strVal, out var d) => JsonValue.Create(d),
                            JsonValueKind.True or JsonValueKind.False when bool.TryParse(strVal, out var b) => JsonValue.Create(b),
                            _ => JsonValue.Create(strVal)!,
                        };
                        break;
                    }
                }
            }
        }

        _templates.SaveJson(item.JsonFilePath, root);

        // Save to edits manifest
        SaveEditManifest(item);
    }

    /// <summary>Load the edits.json manifest for a category cache directory.</summary>
    public Dictionary<string, JsonNode> LoadEditManifest(string cacheDir)
    {
        var manifestPath = Path.Combine(cacheDir, "edits.json");
        if (!File.Exists(manifestPath))
            return new Dictionary<string, JsonNode>();

        var root = JsonNode.Parse(File.ReadAllText(manifestPath));
        if (root is not JsonObject obj)
            return new Dictionary<string, JsonNode>();

        return obj.ToDictionary(kv => kv.Key, kv => kv.Value!);
    }

    // --- Display name resolution ---

    private string ResolveDisplayName(Dictionary<string, object?> fields, string rowName)
    {
        // Check DisplayName and common variants — ExtractPropertyValue returns string
        // for TextPropertyData (CultureInvariantString), so accept string directly.
        foreach (var key in new[] { "DisplayName", "RowDisplayName", "Name_DisplayName" })
        {
            if (!fields.TryGetValue(key, out var val) || val == null) continue;
            var text = val switch
            {
                string s => s,
                JsonNode n => n.GetValue<string>(),
                _ => val.ToString() ?? "",
            };
            if (!string.IsNullOrEmpty(text) && text != "None")
                return text;
        }

        return rowName;
    }

    // =========================================================================
    // DROPDOWN OPTIONS FROM NAMEMAP (Gap #3-4)
    // =========================================================================

    /// <summary>
    /// Scan NameMap from a JSON DataTable and extract categorized dropdown options.
    /// Mirrors Python _scan_construction_recipes_json() / update_buildings_ini_from_json().
    /// </summary>
    public Dictionary<string, List<string>> ScanDropdownOptions(string mode)
    {
        var options = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase)
        {
            ["Materials"] = [],
            ["Actors"] = [],
            ["Constructions"] = [],
            ["Tags"] = [],
            ["AllValues"] = [],
        };

        // Scan all category JSON files for NameMap values
        var pathMap = mode == "secrets" ? SecretsPaths : ConstructionsPaths;
        foreach (var (_, paths) in pathMap)
        {
            var sourcePath = _config.FindSourceJson(mode, paths.DefinitionPath);
            if (sourcePath == null || !File.Exists(sourcePath)) continue;

            try
            {
                var root = _templates.LoadJson(sourcePath);
                if (root == null) continue;

                // Extract from NameMap
                var nameMap = root["NameMap"] as JsonArray;
                if (nameMap != null)
                {
                    foreach (var entry in nameMap)
                    {
                        var name = entry?.GetValue<string>();
                        if (name == null) continue;

                        // Categorize by prefix/pattern
                        if (name.StartsWith("Item.") || name.StartsWith("Ore.") ||
                            name.StartsWith("Consumable.") || name.StartsWith("Tool."))
                            options["Materials"].Add(name);
                        else if (name.StartsWith("/Game/") || name.Contains("BP_"))
                            options["Actors"].Add(name);
                        else if (name.StartsWith("Construction.") || name.StartsWith("Building."))
                            options["Constructions"].Add(name);
                        else if (name.StartsWith("UI.") || name.StartsWith("Tag.") ||
                                 name.Contains(".Category."))
                            options["Tags"].Add(name);

                        options["AllValues"].Add(name);
                    }
                }

                // Also extract from row names
                var rowNames = _templates.GetRowNames(root);
                foreach (var rn in rowNames)
                {
                    if (!options["AllValues"].Contains(rn))
                        options["AllValues"].Add(rn);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to scan NameMap from {Path}", sourcePath);
            }
        }

        // Deduplicate
        foreach (var key in options.Keys.ToList())
            options[key] = options[key].Distinct().OrderBy(v => v).ToList();

        return options;
    }

    // FindSourceJson and ConvertValue are shared via ConfigService and JsonDataService

    private void SaveEditManifest(CategoryItem item)
    {
        var dir = Path.GetDirectoryName(item.JsonFilePath)!;
        var manifestPath = Path.Combine(dir, "edits.json");

        JsonObject manifest;
        if (File.Exists(manifestPath))
        {
            manifest = JsonNode.Parse(File.ReadAllText(manifestPath)) as JsonObject ?? new JsonObject();
        }
        else
        {
            manifest = new JsonObject();
        }

        var fileName = Path.GetFileName(item.JsonFilePath);
        if (!manifest.ContainsKey(fileName))
            manifest[fileName] = new JsonObject();

        var fileEntry = manifest[fileName] as JsonObject ?? new JsonObject();

        // Load the full row for the manifest
        var root = _templates.LoadJson(item.JsonFilePath);
        var row = root != null ? _templates.GetRowByName(root, item.RowName) : null;
        if (row != null)
            fileEntry[item.RowName] = JsonNode.Parse(row.ToJsonString());

        manifest[fileName] = fileEntry;
        File.WriteAllText(manifestPath, manifest.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
    }
}

public record CategoryPaths(string DefinitionPath, string? RecipePath);

public partial class CategoryItem : CommunityToolkit.Mvvm.ComponentModel.ObservableObject
{
    public string RowName { get; init; } = "";
    public string DisplayName { get; init; } = "";
    public Dictionary<string, object?> Fields { get; init; } = [];
    public string JsonFilePath { get; init; } = "";

    [CommunityToolkit.Mvvm.ComponentModel.ObservableProperty]
    private bool _isChecked;

    [CommunityToolkit.Mvvm.ComponentModel.ObservableProperty]
    private bool _isVisible = true;

    /// <summary>Eye icon: open eye for visible, closed for hidden.</summary>
    public string EyeIcon => IsVisible ? "\U0001F441" : "\u2014"; // 👁 vs —

    /// <summary>Eye icon color: green for visible, red for hidden.</summary>
    public string EyeColor => IsVisible ? "#4CAF50" : "#F44336";

    partial void OnIsVisibleChanged(bool value)
    {
        OnPropertyChanged(nameof(EyeIcon));
        OnPropertyChanged(nameof(EyeColor));
    }

    public CategoryItem() { }

    public CategoryItem(string rowName, string displayName, Dictionary<string, object?> fields, string jsonFilePath)
    {
        RowName = rowName;
        DisplayName = displayName;
        Fields = fields;
        JsonFilePath = jsonFilePath;
    }
}
