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

    public CategoryDataService(ConfigService config, ObjectTemplateService templates, ILogger<CategoryDataService> logger)
    {
        _config = config;
        _templates = templates;
        _logger = logger;
    }

    /// <summary>
    /// Load all items for a category from the cached JSON files.
    /// Returns a list of (rowName, displayName, fields) tuples.
    /// </summary>
    public List<CategoryItem> LoadCategoryItems(string mode, string category, string prefix)
    {
        var pathMap = mode == "secrets" ? SecretsPaths : ConstructionsPaths;
        if (!pathMap.TryGetValue(category, out var paths))
            return [];

        var baseDir = mode == "secrets"
            ? Path.Combine(_config.ChangeSecretsDir, prefix)
            : Path.Combine(_config.ChangeConstructionsDir, prefix);

        var cacheDir = Path.Combine(baseDir, category.ToLowerInvariant());
        var defJsonPath = Path.Combine(cacheDir, Path.GetFileName(paths.DefinitionPath));

        // Try loading from cache first, then from source
        if (!File.Exists(defJsonPath))
        {
            // Copy from source
            var sourcePath = FindSourceJson(mode, paths.DefinitionPath);
            if (sourcePath != null && File.Exists(sourcePath))
            {
                Directory.CreateDirectory(cacheDir);
                File.Copy(sourcePath, defJsonPath, true);
            }
        }

        if (!File.Exists(defJsonPath))
        {
            _logger.LogWarning("Definition JSON not found: {Path}", defJsonPath);
            return [];
        }

        var root = _templates.LoadJson(defJsonPath);
        if (root == null) return [];

        var items = new List<CategoryItem>();
        var rowNames = _templates.GetRowNames(root);

        foreach (var rowName in rowNames)
        {
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

            // Try to get display name
            var displayName = ResolveDisplayName(fields, rowName);
            items.Add(new CategoryItem(rowName, displayName, fields, defJsonPath));
        }

        _logger.LogInformation("Loaded {Count} items for {Category} in {Mode}/{Prefix}",
            items.Count, category, mode, prefix);
        return items;
    }

    /// <summary>Save edits for an item to the JSON file and edits manifest.</summary>
    public void SaveItemEdits(CategoryItem item, Dictionary<string, object?> editedFields)
    {
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
                        prop["Value"] = ConvertValue(strVal, existing);
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
        // Check for DisplayName field
        if (fields.TryGetValue("DisplayName", out var dn) && dn is JsonNode dnNode)
        {
            var text = dnNode.GetValue<string>();
            if (!string.IsNullOrEmpty(text) && text != "None")
                return text;
        }

        // Check NameMap-style display name keys
        if (fields.TryGetValue("RowDisplayName", out var rdn) && rdn is string rdnStr)
            return rdnStr;

        return rowName;
    }

    private string? FindSourceJson(string mode, string relativePath)
    {
        // Check game output jsondata
        var gamePath = Path.Combine(_config.OutputJsonDataDir, "Moria", "Content", relativePath);
        if (File.Exists(gamePath)) return gamePath;

        // Check secrets jsondata_full
        if (mode == "secrets")
        {
            var secretsPath = Path.Combine(_config.SecretsJsonDataFullDir, "Moria", "Content", relativePath);
            if (File.Exists(secretsPath)) return secretsPath;
        }

        return null;
    }

    private static JsonNode ConvertValue(string value, JsonNode? existing)
    {
        if (existing == null) return JsonValue.Create(value)!;

        var kind = existing.GetValueKind();
        if (kind == JsonValueKind.Number)
        {
            if (int.TryParse(value, out var intVal)) return JsonValue.Create(intVal);
            if (double.TryParse(value, out var dblVal)) return JsonValue.Create(dblVal);
        }
        else if (kind is JsonValueKind.True or JsonValueKind.False)
        {
            if (bool.TryParse(value, out var boolVal)) return JsonValue.Create(boolVal);
        }

        return JsonValue.Create(value)!;
    }

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

public record CategoryItem(
    string RowName,
    string DisplayName,
    Dictionary<string, object?> Fields,
    string JsonFilePath);
