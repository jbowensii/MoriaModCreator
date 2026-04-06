using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Manages DataTable row operations: extract fields, create rows, modify properties.
/// Mirrors Python object_templates.py.
/// </summary>
public class ObjectTemplateService
{
    private readonly ConfigService _config;
    private readonly ILogger<ObjectTemplateService> _logger;

    public ObjectTemplateService(ConfigService config, ILogger<ObjectTemplateService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>Load a JSON file and return the root JsonNode.</summary>
    public JsonNode? LoadJson(string path)
    {
        if (!File.Exists(path)) return null;
        return JsonNode.Parse(File.ReadAllText(path));
    }

    /// <summary>Save a JsonNode to a file with indentation.</summary>
    public void SaveJson(string path, JsonNode root)
    {
        var options = new JsonSerializerOptions { WriteIndented = true };
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(path, root.ToJsonString(options));
    }

    /// <summary>Get all row names from a DataTable JSON.</summary>
    public List<string> GetRowNames(JsonNode root)
    {
        var names = new List<string>();
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (data == null) return names;
        foreach (var row in data)
        {
            var name = row?["Name"]?.GetValue<string>();
            if (name != null) names.Add(name);
        }
        return names;
    }

    /// <summary>Find a row by name in a DataTable.</summary>
    public JsonNode? GetRowByName(JsonNode root, string rowName)
    {
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        return data?.FirstOrDefault(r => r?["Name"]?.GetValue<string>() == rowName);
    }

    /// <summary>Get a property value from a row's Value array.</summary>
    public JsonNode? GetRowProperty(JsonNode row, string propertyName)
    {
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return null;

        foreach (var prop in valueArray)
        {
            if (prop?["Name"]?.GetValue<string>() == propertyName)
                return prop["Value"];
        }
        return null;
    }

    /// <summary>Set a property value in a row's Value array.</summary>
    public bool SetRowProperty(JsonNode row, string propertyName, JsonNode value)
    {
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return false;

        foreach (var prop in valueArray)
        {
            if (prop?["Name"]?.GetValue<string>() == propertyName)
            {
                prop!["Value"] = value;
                return true;
            }
        }
        return false;
    }

    /// <summary>Extract recipe fields from a DataTable row.</summary>
    public Dictionary<string, object?> ExtractRecipeFields(JsonNode row)
    {
        var fields = new Dictionary<string, object?>();
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return fields;

        foreach (var prop in valueArray)
        {
            var name = prop?["Name"]?.GetValue<string>();
            if (name == null) continue;
            fields[name] = prop!["Value"];
        }
        return fields;
    }

    /// <summary>Extract construction/building fields from a row.</summary>
    public Dictionary<string, object?> ExtractConstructionFields(JsonNode row)
        => ExtractRecipeFields(row);

    /// <summary>Extract weapon fields from a row.</summary>
    public Dictionary<string, object?> ExtractWeaponFields(JsonNode row)
        => ExtractRecipeFields(row);

    /// <summary>Extract armor fields from a row.</summary>
    public Dictionary<string, object?> ExtractArmorFields(JsonNode row)
        => ExtractRecipeFields(row);

    /// <summary>Extract tool fields from a row.</summary>
    public Dictionary<string, object?> ExtractToolFields(JsonNode row)
        => ExtractRecipeFields(row);

    /// <summary>Extract item fields (includes Tags extraction).</summary>
    public Dictionary<string, object?> ExtractItemFields(JsonNode row)
    {
        var fields = ExtractRecipeFields(row);
        // Extract Tags specifically
        var valueArray = row["Value"] as JsonArray;
        if (valueArray != null)
        {
            foreach (var prop in valueArray)
            {
                if (prop?["Name"]?.GetValue<string>() == "Tags" &&
                    prop["StructType"]?.GetValue<string>() == "GameplayTagContainer")
                {
                    fields["Tags"] = ExtractTagNames(prop);
                }
            }
        }
        return fields;
    }

    /// <summary>Extract flora fields from a row.</summary>
    public Dictionary<string, object?> ExtractFloraFields(JsonNode row)
        => ExtractItemFields(row);

    /// <summary>Extract loot fields from a row.</summary>
    public Dictionary<string, object?> ExtractLootFields(JsonNode row)
        => ExtractRecipeFields(row);

    /// <summary>Extract tag names from a GameplayTagContainer property.</summary>
    public List<string> ExtractTagNames(JsonNode tagContainer)
    {
        var tags = new List<string>();
        var inner = tagContainer["Value"] as JsonArray;
        if (inner == null || inner.Count == 0) return tags;

        var tagsNode = inner[0]?["Value"];
        if (tagsNode is JsonArray tagArray)
        {
            foreach (var tag in tagArray)
            {
                var val = tag?.GetValue<string>();
                if (val != null) tags.Add(val);
            }
        }
        return tags;
    }

    /// <summary>Add a new row to a DataTable's Data array.</summary>
    public bool AddRow(JsonNode root, JsonNode newRow)
    {
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (data == null) return false;
        data.Add(newRow);
        return true;
    }

    /// <summary>Remove a row by name from a DataTable.</summary>
    public bool RemoveRow(JsonNode root, string rowName)
    {
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (data == null) return false;

        for (int i = data.Count - 1; i >= 0; i--)
        {
            if (data[i]?["Name"]?.GetValue<string>() == rowName)
            {
                data.RemoveAt(i);
                return true;
            }
        }
        return false;
    }

    /// <summary>Generate a unique tag string (hex-based).</summary>
    public static string GenUniqueTag()
    {
        var bytes = Guid.NewGuid().ToByteArray();
        return Convert.ToHexString(bytes);
    }

    /// <summary>Extract ores fields from a row (same structure as items).</summary>
    public Dictionary<string, object?> ExtractOresFields(JsonNode row)
        => ExtractItemFields(row);

    /// <summary>Load a template JSON from the docs/templates directory.</summary>
    public JsonNode? LoadTemplate(string templateName)
    {
        var templatePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "docs", "templates", templateName);
        if (!File.Exists(templatePath))
        {
            // Also check relative to config AppData
            templatePath = Path.Combine(_config.AppDataDir, "..", "templates", templateName);
        }
        return File.Exists(templatePath) ? LoadJson(templatePath) : null;
    }

    /// <summary>Create a new construction row from a template, with a unique name.</summary>
    public JsonNode? CreateConstructionRow(JsonNode templateRow, string newName)
    {
        var clone = JsonNode.Parse(templateRow.ToJsonString());
        if (clone == null) return null;
        clone["Name"] = JsonValue.Create(newName);
        return clone;
    }

    /// <summary>Create a new construction recipe row.</summary>
    public JsonNode? CreateConstructionRecipeRow(JsonNode templateRow, string newName)
        => CreateConstructionRow(templateRow, newName);

    /// <summary>Create a new item recipe row.</summary>
    public JsonNode? CreateItemRecipeRow(JsonNode templateRow, string newName)
        => CreateConstructionRow(templateRow, newName);

    /// <summary>Add a string table entry to a string table JSON.</summary>
    public bool AddStringTableEntry(JsonNode root, string key, string value)
    {
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (data == null) return false;

        // Check if key already exists
        if (data.Any(r => r?["Name"]?.GetValue<string>() == key))
            return false;

        var entry = new JsonObject
        {
            ["Name"] = key,
            ["Value"] = new JsonArray
            {
                new JsonObject
                {
                    ["Name"] = "SourceString",
                    ["Value"] = value,
                },
            },
        };
        data.Add(entry);
        return true;
    }

    /// <summary>Build a required materials array for a recipe.</summary>
    public JsonArray BuildRequiredMaterials(IEnumerable<(string Material, int Amount)> materials)
    {
        var arr = new JsonArray();
        foreach (var (material, amount) in materials)
        {
            arr.Add(new JsonObject
            {
                ["Name"] = material,
                ["Value"] = new JsonArray
                {
                    new JsonObject { ["Name"] = "ItemDefinition", ["Value"] = material },
                    new JsonObject { ["Name"] = "Amount", ["Value"] = amount },
                },
            });
        }
        return arr;
    }

    /// <summary>Build a crafting stations array.</summary>
    public JsonArray BuildCraftingStations(IEnumerable<string> stations)
    {
        var arr = new JsonArray();
        foreach (var station in stations)
            arr.Add(JsonValue.Create(station));
        return arr;
    }

    /// <summary>Build an unlock condition struct.</summary>
    public JsonObject BuildUnlockCondition(string unlockType, string? requiredItem = null)
    {
        return new JsonObject
        {
            ["Name"] = "UnlockCondition",
            ["Value"] = new JsonArray
            {
                new JsonObject { ["Name"] = "UnlockType", ["Value"] = unlockType },
                new JsonObject { ["Name"] = "RequiredItem", ["Value"] = requiredItem ?? "" },
            },
        };
    }

    /// <summary>Clone an existing row with a new name.</summary>
    public JsonNode? CloneRow(JsonNode root, string sourceRowName, string newRowName)
    {
        var sourceRow = GetRowByName(root, sourceRowName);
        if (sourceRow == null) return null;

        var clone = JsonNode.Parse(sourceRow.ToJsonString());
        if (clone == null) return null;
        clone["Name"] = JsonValue.Create(newRowName);
        return clone;
    }
}
