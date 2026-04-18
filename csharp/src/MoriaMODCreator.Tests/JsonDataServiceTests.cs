using System.IO;
using System.Text.Json.Nodes;
using MoriaMODCreator.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace MoriaMODCreator.Tests;

public class JsonDataServiceTests
{
    private readonly JsonDataService _service = new(NullLogger<JsonDataService>.Instance);

    private static string CreateDataTableJson(params string[] rowNames)
    {
        var rows = string.Join(",\n", rowNames.Select(name =>
            $$"""{"Name": "{{name}}", "Value": [{"Name": "MaxStackSize", "Value": 100, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"}, {"Name": "EnabledState", "Value": "ERowEnabledState::Live", "$type": "UAssetAPI.PropertyTypes.Structs.EnumPropertyData, UAssetAPI"}]}"""));

        return $$"""
        {
            "NameMap": ["MaxStackSize", "EnabledState"],
            "Exports": [{
                "Table": {
                    "Data": [{{rows}}]
                }
            }]
        }
        """;
    }

    private static string CreateTagDataTableJson(string rowName, params string[] tags)
    {
        var tagList = string.Join(", ", tags.Select(t => $"\"{t}\""));
        return $$"""
        {
            "NameMap": ["Tags"],
            "Exports": [{
                "Table": {
                    "Data": [{
                        "Name": "{{rowName}}",
                        "Value": [{
                            "Name": "Tags",
                            "StructType": "GameplayTagContainer",
                            "Value": [{
                                "Name": "Tags",
                                "Value": [{{tagList}}]
                            }]
                        }]
                    }]
                }
            }]
        }
        """;
    }

    // --- StripDuplicateRows tests ---

    [Fact]
    public void StripDuplicateRows_RemovesMatchingRows()
    {
        var secretsJson = CreateDataTableJson("GameSword", "GameAxe", "SecretDagger");
        var gameJson = CreateDataTableJson("GameSword", "GameAxe");

        var secretsPath = Path.GetTempFileName();
        var gamePath = Path.GetTempFileName();
        File.WriteAllText(secretsPath, secretsJson);
        File.WriteAllText(gamePath, gameJson);

        try
        {
            var (removed, remaining) = _service.StripDuplicateRows(secretsPath, gamePath);
            Assert.Equal(2, removed);
            Assert.Equal(1, remaining);

            var result = JsonNode.Parse(File.ReadAllText(secretsPath));
            var data = result!["Exports"]![0]!["Table"]!["Data"] as JsonArray;
            Assert.Single(data!);
            Assert.Equal("SecretDagger", data![0]!["Name"]!.GetValue<string>());
        }
        finally { File.Delete(secretsPath); File.Delete(gamePath); }
    }

    [Fact]
    public void StripDuplicateRows_KeepsAllWhenNoOverlap()
    {
        var secretsJson = CreateDataTableJson("SecretA", "SecretB");
        var gameJson = CreateDataTableJson("GameX", "GameY");

        var secretsPath = Path.GetTempFileName();
        var gamePath = Path.GetTempFileName();
        File.WriteAllText(secretsPath, secretsJson);
        File.WriteAllText(gamePath, gameJson);

        try
        {
            var (removed, remaining) = _service.StripDuplicateRows(secretsPath, gamePath);
            Assert.Equal(0, removed);
            Assert.Equal(2, remaining);
        }
        finally { File.Delete(secretsPath); File.Delete(gamePath); }
    }

    [Fact]
    public void StripDuplicateRows_RemovesAllWhenFullOverlap()
    {
        var secretsJson = CreateDataTableJson("A", "B");
        var gameJson = CreateDataTableJson("A", "B", "C");

        var secretsPath = Path.GetTempFileName();
        var gamePath = Path.GetTempFileName();
        File.WriteAllText(secretsPath, secretsJson);
        File.WriteAllText(gamePath, gameJson);

        try
        {
            var (removed, remaining) = _service.StripDuplicateRows(secretsPath, gamePath);
            Assert.Equal(2, removed);
            Assert.Equal(0, remaining);
        }
        finally { File.Delete(secretsPath); File.Delete(gamePath); }
    }

    [Fact]
    public void StripDuplicateRows_KeepsModifiedRowsWithSameName()
    {
        // Game row: MaxStackSize=100. Secrets row: same name but MaxStackSize=999 (Tobi's mod).
        var gameJson = CreateDataTableJson("SharedSword");
        var secretsJson = $$"""
        {
            "NameMap": ["MaxStackSize", "EnabledState"],
            "Exports": [{
                "Table": {
                    "Data": [
                        {"Name": "SharedSword", "Value": [{"Name": "MaxStackSize", "Value": 999, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"}]},
                        {"Name": "NewDagger", "Value": [{"Name": "MaxStackSize", "Value": 50, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"}]}
                    ]
                }
            }]
        }
        """;

        var secretsPath = Path.GetTempFileName();
        var gamePath = Path.GetTempFileName();
        File.WriteAllText(secretsPath, secretsJson);
        File.WriteAllText(gamePath, gameJson);

        try
        {
            var (removed, remaining) = _service.StripDuplicateRows(secretsPath, gamePath);
            // SharedSword has different content (999 vs 100), so it should NOT be stripped
            Assert.Equal(0, removed);
            Assert.Equal(2, remaining);

            var result = JsonNode.Parse(File.ReadAllText(secretsPath));
            var data = result!["Exports"]![0]!["Table"]!["Data"] as JsonArray;
            Assert.Equal(2, data!.Count);
        }
        finally { File.Delete(secretsPath); File.Delete(gamePath); }
    }

    // --- MergeSecretsRows tests ---

    [Fact]
    public void MergeSecretsRows_AppendsNewRows()
    {
        var gameJson = CreateDataTableJson("GameSword", "GameAxe");
        var secretsJson = CreateDataTableJson("SecretDagger", "SecretBow");

        var gamePath = Path.GetTempFileName();
        var secretsPath = Path.GetTempFileName();
        File.WriteAllText(gamePath, gameJson);
        File.WriteAllText(secretsPath, secretsJson);

        try
        {
            var merged = _service.MergeSecretsRows(gamePath, secretsPath);
            Assert.Equal(2, merged);

            var names = _service.GetRowNames(gamePath);
            Assert.Equal(4, names.Count);
            Assert.Contains("GameSword", names);
            Assert.Contains("SecretDagger", names);
        }
        finally { File.Delete(gamePath); File.Delete(secretsPath); }
    }

    [Fact]
    public void MergeSecretsRows_SkipsDuplicates()
    {
        var gameJson = CreateDataTableJson("A", "B");
        var secretsJson = CreateDataTableJson("B", "C");

        var gamePath = Path.GetTempFileName();
        var secretsPath = Path.GetTempFileName();
        File.WriteAllText(gamePath, gameJson);
        File.WriteAllText(secretsPath, secretsJson);

        try
        {
            var merged = _service.MergeSecretsRows(gamePath, secretsPath);
            Assert.Equal(1, merged); // Only C is new
            Assert.Equal(3, _service.GetRowNames(gamePath).Count);
        }
        finally { File.Delete(gamePath); File.Delete(secretsPath); }
    }

    // --- ApplyChange tests ---

    [Fact]
    public void ApplyChange_ModifiesIntProperty()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;

        var result = _service.ApplyChange(root, "Sword", "MaxStackSize", "999");
        Assert.True(result);

        var data = root["Exports"]![0]!["Table"]!["Data"] as JsonArray;
        var value = data![0]!["Value"]![0]!["Value"]!.GetValue<int>();
        Assert.Equal(999, value);
    }

    [Fact]
    public void ApplyChange_ModifiesStringProperty()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;

        var result = _service.ApplyChange(root, "Sword", "EnabledState", "ERowEnabledState::Testing");
        Assert.True(result);
    }

    [Fact]
    public void ApplyChange_ReturnsFalseForMissingRow()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;
        Assert.False(_service.ApplyChange(root, "NonExistent", "MaxStackSize", "999"));
    }

    [Fact]
    public void ApplyChange_ReturnsFalseForMissingProperty()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;
        Assert.False(_service.ApplyChange(root, "Sword", "NonExistentProp", "999"));
    }

    // --- GameplayTag tests ---

    [Fact]
    public void AddGameplayTag_AddsNewTag()
    {
        var json = CreateTagDataTableJson("Stone", "Item.Mineral.Stone");
        var root = JsonNode.Parse(json)!;

        var result = _service.AddGameplayTag(root, "Stone", "Tags", "Item.NewTag");
        Assert.True(result);
    }

    [Fact]
    public void AddGameplayTag_DoesNotDuplicate()
    {
        var json = CreateTagDataTableJson("Stone", "Item.Mineral.Stone");
        var root = JsonNode.Parse(json)!;

        _service.AddGameplayTag(root, "Stone", "Tags", "Item.Mineral.Stone");
        // Should still have only 1 tag with that name
    }

    [Fact]
    public void RemoveGameplayTag_RemovesExistingTag()
    {
        var json = CreateTagDataTableJson("Stone", "Item.Mineral.Stone", "Item.BasicGather");
        var root = JsonNode.Parse(json)!;

        var result = _service.RemoveGameplayTag(root, "Stone", "Tags", "Item.Mineral.Stone");
        Assert.True(result);
    }

    [Fact]
    public void RemoveGameplayTag_ReturnsFalseForMissingTag()
    {
        var json = CreateTagDataTableJson("Stone", "Item.Mineral.Stone");
        var root = JsonNode.Parse(json)!;

        var result = _service.RemoveGameplayTag(root, "Stone", "Tags", "NonExistent");
        Assert.False(result);
    }

    // --- NameMap tests ---

    [Fact]
    public void SyncNameMap_AddsNewEntry()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;

        _service.SyncNameMap(root, "NewName");
        var nameMap = root["NameMap"] as JsonArray;
        Assert.Contains(nameMap!, n => n!.GetValue<string>() == "NewName");
    }

    [Fact]
    public void SyncNameMap_DoesNotDuplicate()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;

        _service.SyncNameMap(root, "MaxStackSize");
        var nameMap = root["NameMap"] as JsonArray;
        Assert.Equal(1, nameMap!.Count(n => n!.GetValue<string>() == "MaxStackSize"));
    }

    // --- GetRowNames tests ---

    [Fact]
    public void GetRowNames_ReturnsAllNames()
    {
        var json = CreateDataTableJson("Alpha", "Beta", "Gamma");
        var path = Path.GetTempFileName();
        File.WriteAllText(path, json);

        try
        {
            var names = _service.GetRowNames(path);
            Assert.Equal(3, names.Count);
            Assert.Contains("Alpha", names);
            Assert.Contains("Beta", names);
            Assert.Contains("Gamma", names);
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void GetRowNames_ReturnsEmptyForEmptyDataTable()
    {
        var json = """{"Exports": [{"Table": {"Data": []}}]}""";
        var path = Path.GetTempFileName();
        File.WriteAllText(path, json);

        try
        {
            var names = _service.GetRowNames(path);
            Assert.Empty(names);
        }
        finally { File.Delete(path); }
    }

    // --- IsGameplayTagContainer tests ---

    [Fact]
    public void IsGameplayTagContainer_DetectsTagProperty()
    {
        var json = CreateTagDataTableJson("Stone", "Item.Mineral.Stone");
        var root = JsonNode.Parse(json)!;
        var data = root["Exports"]![0]!["Table"]!["Data"] as JsonArray;

        Assert.True(_service.IsGameplayTagContainer(data![0]!, "Tags"));
    }

    [Fact]
    public void IsGameplayTagContainer_ReturnsFalseForRegularProperty()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;
        var data = root["Exports"]![0]!["Table"]!["Data"] as JsonArray;

        Assert.False(_service.IsGameplayTagContainer(data![0]!, "MaxStackSize"));
    }
}
