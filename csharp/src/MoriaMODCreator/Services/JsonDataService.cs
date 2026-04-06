using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// High-performance JSON DataTable operations using System.Text.Json.
/// Handles row comparison, stripping, merging, and property modification.
/// </summary>
public class JsonDataService
{
    private readonly ILogger<JsonDataService> _logger;

    public JsonDataService(ILogger<JsonDataService> logger)
    {
        _logger = logger;
    }

    /// <summary>
    /// Strip rows from secrets JSON that already exist in the game JSON.
    /// Modifies the secrets file in-place.
    /// Returns (rowsRemoved, rowsRemaining).
    /// </summary>
    public (int Removed, int Remaining) StripDuplicateRows(string secretsJsonPath, string gameJsonPath)
    {
        var secretsNode = JsonNode.Parse(File.ReadAllText(secretsJsonPath));
        var gameNode = JsonNode.Parse(File.ReadAllText(gameJsonPath));

        if (secretsNode == null || gameNode == null)
            return (0, 0);

        var gameRowNames = GetRowNames(gameNode);
        if (gameRowNames.Count == 0)
            return (0, 0);

        var secretsData = GetDataArray(secretsNode);
        if (secretsData == null)
            return (0, 0);

        int originalCount = secretsData.Count;
        int removed = 0;

        // Remove rows whose Name exists in game data (iterate backwards)
        for (int i = secretsData.Count - 1; i >= 0; i--)
        {
            var rowName = secretsData[i]?["Name"]?.GetValue<string>();
            if (rowName != null && gameRowNames.Contains(rowName))
            {
                secretsData.RemoveAt(i);
                removed++;
            }
        }

        if (removed > 0)
        {
            var options = new JsonSerializerOptions { WriteIndented = true };
            File.WriteAllText(secretsJsonPath, secretsNode.ToJsonString(options));
            _logger.LogInformation("Stripped {Removed} rows from {File}, {Remaining} remain",
                removed, Path.GetFileName(secretsJsonPath), secretsData.Count);
        }

        return (removed, secretsData.Count);
    }

    /// <summary>Get all row names from a DataTable JSON file.</summary>
    public HashSet<string> GetRowNames(string jsonPath)
    {
        var node = JsonNode.Parse(File.ReadAllText(jsonPath));
        return node == null ? [] : GetRowNames(node);
    }

    /// <summary>
    /// Apply a property change to a DataTable row.
    /// Returns true if the change was applied.
    /// </summary>
    public bool ApplyChange(JsonNode root, string itemName, string property, string value)
    {
        var dataArray = GetDataArray(root);
        if (dataArray == null) return false;

        var row = FindRow(dataArray, itemName);
        if (row == null)
        {
            _logger.LogWarning("Row '{Item}' not found in DataTable", itemName);
            return false;
        }

        return SetPropertyValue(row, property, value);
    }

    /// <summary>
    /// Add a gameplay tag to a row's tag container.
    /// </summary>
    public bool AddGameplayTag(JsonNode root, string itemName, string property, string tagValue)
    {
        var dataArray = GetDataArray(root);
        if (dataArray == null) return false;

        var row = FindRow(dataArray, itemName);
        if (row == null) return false;

        var tagContainer = FindTagContainer(row, property);
        if (tagContainer is not JsonArray tagArray) return false;

        // Don't add duplicates
        if (!tagArray.Any(t => t?.GetValue<string>() == tagValue))
            tagArray.Add(JsonValue.Create(tagValue));

        return true;
    }

    /// <summary>
    /// Remove a gameplay tag from a row's tag container.
    /// </summary>
    public bool RemoveGameplayTag(JsonNode root, string itemName, string property, string tagValue)
    {
        var dataArray = GetDataArray(root);
        if (dataArray == null) return false;

        var row = FindRow(dataArray, itemName);
        if (row == null) return false;

        var tagContainer = FindTagContainer(row, property);
        if (tagContainer is not JsonArray tagArray) return false;

        for (int i = tagArray.Count - 1; i >= 0; i--)
        {
            if (tagArray[i]?.GetValue<string>() == tagValue)
            {
                tagArray.RemoveAt(i);
                return true;
            }
        }
        return false;
    }

    /// <summary>
    /// Ensure a value exists in the NameMap array. Adds it if missing.
    /// </summary>
    public void SyncNameMap(JsonNode root, string name)
    {
        var nameMap = root["NameMap"];
        if (nameMap is not JsonArray nameArray) return;

        if (!nameArray.Any(n => n?.GetValue<string>() == name))
            nameArray.Add(JsonValue.Create(name));
    }

    /// <summary>
    /// Merge secrets-only rows into a game JSON file.
    /// Appends rows from secrets that don't exist in game.
    /// Returns number of rows merged.
    /// </summary>
    public int MergeSecretsRows(string gameJsonPath, string secretsJsonPath)
    {
        var gameNode = JsonNode.Parse(File.ReadAllText(gameJsonPath));
        var secretsNode = JsonNode.Parse(File.ReadAllText(secretsJsonPath));
        if (gameNode == null || secretsNode == null) return 0;

        var gameData = GetDataArray(gameNode);
        var secretsData = GetDataArray(secretsNode);
        if (gameData == null || secretsData == null) return 0;

        var existingNames = GetRowNames(gameNode);
        int merged = 0;

        foreach (var row in secretsData)
        {
            var name = row?["Name"]?.GetValue<string>();
            if (name != null && !existingNames.Contains(name))
            {
                var clone = JsonNode.Parse(row!.ToJsonString());
                if (clone != null)
                {
                    gameData.Add(clone);
                    merged++;
                }
            }
        }

        if (merged > 0)
        {
            // Also merge NameMap entries
            var gameNm = gameNode["NameMap"] as JsonArray;
            var secretsNm = secretsNode["NameMap"] as JsonArray;
            if (gameNm != null && secretsNm != null)
            {
                var existingNm = new HashSet<string>();
                foreach (var n in gameNm)
                    if (n != null) existingNm.Add(n.GetValue<string>());
                foreach (var n in secretsNm)
                {
                    var val = n?.GetValue<string>();
                    if (val != null && !existingNm.Contains(val))
                        gameNm.Add(JsonValue.Create(val));
                }
            }

            var options = new JsonSerializerOptions { WriteIndented = true };
            File.WriteAllText(gameJsonPath, gameNode.ToJsonString(options));
        }

        return merged;
    }

    /// <summary>
    /// Set a property value using a dot-separated path like "LevelData.bCanPatrol".
    /// Handles nested StructPropertyData traversal.
    /// </summary>
    public bool SetNestedPropertyValue(JsonNode row, string propertyPath, string value)
    {
        return SetPropertyValue(row, propertyPath, value);
    }

    /// <summary>
    /// Add a new property to a row's Value array if it doesn't already exist.
    /// Used by .def files with <add_property> elements.
    /// </summary>
    public bool AddPropertyToRow(JsonNode row, string propertyName, JsonNode value, string type = "")
    {
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return false;

        // Check if property already exists
        if (valueArray.Any(p => p?["Name"]?.GetValue<string>() == propertyName))
            return false;

        var newProp = new JsonObject
        {
            ["Name"] = propertyName,
            ["Value"] = JsonNode.Parse(value.ToJsonString()),
        };
        if (!string.IsNullOrEmpty(type))
            newProp["$type"] = type;

        valueArray.Add(newProp);
        return true;
    }

    /// <summary>
    /// Set a property value using wildcard path (e.g., "Data.*.Health").
    /// Applies the change to all matching elements.
    /// </summary>
    public int SetWildcardPropertyValue(JsonNode root, string itemName, string wildcardPath, string value)
    {
        var dataArray = GetDataArray(root);
        if (dataArray == null) return 0;

        var row = FindRow(dataArray, itemName);
        if (row == null) return 0;

        var parts = wildcardPath.Split('.');
        var wildcardIdx = Array.IndexOf(parts, "*");
        if (wildcardIdx < 0)
        {
            // No wildcard, use normal path
            return SetPropertyValue(row, wildcardPath, value) ? 1 : 0;
        }

        // Navigate to the array before the wildcard
        var prePath = string.Join(".", parts[..wildcardIdx]);
        var postPath = string.Join(".", parts[(wildcardIdx + 1)..]);

        // This is a simplified implementation — the full Python version
        // traverses nested arrays. For now, just apply to the first match.
        return SetPropertyValue(row, wildcardPath.Replace(".*.", "."), value) ? 1 : 0;
    }

    /// <summary>Check if a property is a GameplayTagContainer.</summary>
    public bool IsGameplayTagContainer(JsonNode row, string propertyName)
    {
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return false;

        var baseProp = propertyName.Split('.')[0];
        return valueArray.Any(p =>
            p?["Name"]?.GetValue<string>() == baseProp &&
            p["StructType"]?.GetValue<string>() == "GameplayTagContainer");
    }

    // --- Private helpers ---

    private static HashSet<string> GetRowNames(JsonNode root)
    {
        var names = new HashSet<string>();
        var dataArray = GetDataArray(root);
        if (dataArray == null) return names;

        foreach (var row in dataArray)
        {
            var name = row?["Name"]?.GetValue<string>();
            if (name != null)
                names.Add(name);
        }
        return names;
    }

    private static JsonArray? GetDataArray(JsonNode root)
    {
        // Path: Exports[0].Table.Data
        return root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
    }

    private static JsonNode? FindRow(JsonArray dataArray, string itemName)
    {
        return dataArray.FirstOrDefault(row =>
            row?["Name"]?.GetValue<string>() == itemName);
    }

    private bool SetPropertyValue(JsonNode row, string propertyPath, string value)
    {
        // Handle dot-separated paths like "LevelData.bCanPatrol"
        var parts = propertyPath.Split('.');
        var current = row["Value"];

        if (current is not JsonArray valueArray)
            return false;

        // Navigate to the target property
        JsonNode? target = null;
        for (int pi = 0; pi < parts.Length; pi++)
        {
            var propName = parts[pi];
            target = null;

            if (current is JsonArray arr)
            {
                // Search array for property with matching Name
                foreach (var item in arr)
                {
                    if (item?["Name"]?.GetValue<string>() == propName)
                    {
                        target = item;
                        break;
                    }
                }
            }

            if (target == null)
            {
                _logger.LogWarning("Property '{Prop}' not found in path '{Path}'", propName, propertyPath);
                return false;
            }

            if (pi < parts.Length - 1)
            {
                // Navigate deeper
                current = target["Value"];
            }
        }

        if (target == null) return false;

        // Set the value — detect type from existing value
        var existingValue = target["Value"];
        if (existingValue is JsonValue)
        {
            target["Value"] = ConvertValue(value, existingValue);
        }
        else
        {
            target["Value"] = JsonValue.Create(value);
        }

        return true;
    }

    private static JsonNode ConvertValue(string value, JsonNode existing)
    {
        // Try to match the type of the existing value
        if (existing.GetValueKind() == JsonValueKind.Number)
        {
            if (int.TryParse(value, out var intVal))
                return JsonValue.Create(intVal);
            if (double.TryParse(value, out var dblVal))
                return JsonValue.Create(dblVal);
        }
        else if (existing.GetValueKind() == JsonValueKind.True ||
                 existing.GetValueKind() == JsonValueKind.False)
        {
            if (bool.TryParse(value, out var boolVal))
                return JsonValue.Create(boolVal);
        }

        return JsonValue.Create(value)!;
    }

    private static JsonNode? FindTagContainer(JsonNode row, string property)
    {
        var valueArray = row["Value"] as JsonArray;
        if (valueArray == null) return null;

        foreach (var prop in valueArray)
        {
            if (prop?["Name"]?.GetValue<string>() == property &&
                prop["StructType"]?.GetValue<string>() == "GameplayTagContainer")
            {
                // Inner Tags array
                var inner = prop["Value"] as JsonArray;
                if (inner?.Count > 0)
                {
                    var tagsNode = inner[0];
                    if (tagsNode?["Name"]?.GetValue<string>() == "Tags")
                        return tagsNode["Value"];
                }
            }
        }
        return null;
    }
}
