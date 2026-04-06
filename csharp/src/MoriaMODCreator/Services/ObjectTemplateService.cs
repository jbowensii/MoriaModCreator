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
        return BitConverter.ToString(bytes).Replace("-", "").ToUpperInvariant()[..32];
    }

    /// <summary>Extract ores fields from a row (same structure as items).</summary>
    public Dictionary<string, object?> ExtractOresFields(JsonNode row)
        => ExtractItemFields(row);

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
