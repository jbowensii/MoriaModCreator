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
            $$"""{"Name": "{{name}}", "Value": [{"Name": "MaxStackSize", "Value": 100, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"}]}"""));

        return $$"""
        {
            "NameMap": ["MaxStackSize"],
            "Exports": [{
                "Table": {
                    "Data": [{{rows}}]
                }
            }]
        }
        """;
    }

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

            // Verify the remaining row
            var result = JsonNode.Parse(File.ReadAllText(secretsPath));
            var data = result!["Exports"]![0]!["Table"]!["Data"] as JsonArray;
            Assert.Single(data!);
            Assert.Equal("SecretDagger", data[0]!["Name"]!.GetValue<string>());
        }
        finally
        {
            File.Delete(secretsPath);
            File.Delete(gamePath);
        }
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
        finally
        {
            File.Delete(secretsPath);
            File.Delete(gamePath);
        }
    }

    [Fact]
    public void ApplyChange_ModifiesPropertyValue()
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
    public void ApplyChange_ReturnsFalseForMissingRow()
    {
        var json = CreateDataTableJson("Sword");
        var root = JsonNode.Parse(json)!;

        var result = _service.ApplyChange(root, "NonExistent", "MaxStackSize", "999");
        Assert.False(result);
    }

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
        finally
        {
            File.Delete(path);
        }
    }
}
