using System.Text.Json.Nodes;
using MoriaMODCreator.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace MoriaMODCreator.Tests;

public class BuildingsDataServiceTests
{
    private readonly BuildingsDataService _service;
    private readonly ObjectTemplateService _templates;

    public BuildingsDataServiceTests()
    {
        var config = new ConfigService();
        _templates = new ObjectTemplateService(config, NullLogger<ObjectTemplateService>.Instance);
        _service = new BuildingsDataService(config, _templates, NullLogger<BuildingsDataService>.Instance);
    }

    private static JsonNode CreateRow(string name, int damage)
    {
        return JsonNode.Parse($$"""
        {
            "Name": "{{name}}",
            "Value": [
                {
                    "Name": "Damage",
                    "Value": {{damage}},
                    "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"
                },
                {
                    "Name": "Weight",
                    "Value": 10,
                    "$type": "UAssetAPI.PropertyTypes.Structs.FloatPropertyData, UAssetAPI"
                }
            ]
        }
        """)!;
    }

    [Fact]
    public void DiffRowProperties_DetectsScalarChange()
    {
        var orig = CreateRow("Sword", 100);
        var cache = CreateRow("Sword", 200);

        var diffs = _service.DiffRowProperties("Sword", orig, cache);
        Assert.Single(diffs);
        Assert.Equal("Sword", diffs[0].Item);
        Assert.Equal("Damage", diffs[0].Property);
        Assert.Equal("200", diffs[0].Value);
    }

    [Fact]
    public void DiffRowProperties_NoChangeReturnsEmpty()
    {
        var orig = CreateRow("Sword", 100);
        var cache = CreateRow("Sword", 100);

        var diffs = _service.DiffRowProperties("Sword", orig, cache);
        Assert.Empty(diffs);
    }

    [Fact]
    public void DiffRowProperties_MultipleChanges()
    {
        var orig = JsonNode.Parse("""
        {
            "Name": "Sword",
            "Value": [
                {"Name": "Damage", "Value": 100, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"},
                {"Name": "Weight", "Value": 10, "$type": "UAssetAPI.PropertyTypes.Structs.FloatPropertyData, UAssetAPI"}
            ]
        }
        """)!;

        var cache = JsonNode.Parse("""
        {
            "Name": "Sword",
            "Value": [
                {"Name": "Damage", "Value": 200, "$type": "UAssetAPI.PropertyTypes.Structs.IntPropertyData, UAssetAPI"},
                {"Name": "Weight", "Value": 20, "$type": "UAssetAPI.PropertyTypes.Structs.FloatPropertyData, UAssetAPI"}
            ]
        }
        """)!;

        var diffs = _service.DiffRowProperties("Sword", orig, cache);
        Assert.Equal(2, diffs.Count);
    }

    [Fact]
    public void DiffRowProperties_DetectsEnumChange()
    {
        var orig = JsonNode.Parse("""
        {
            "Name": "Item",
            "Value": [{"Name": "EnabledState", "Value": "ERowEnabledState::Live", "$type": "UAssetAPI.PropertyTypes.Structs.EnumPropertyData, UAssetAPI"}]
        }
        """)!;

        var cache = JsonNode.Parse("""
        {
            "Name": "Item",
            "Value": [{"Name": "EnabledState", "Value": "ERowEnabledState::Testing", "$type": "UAssetAPI.PropertyTypes.Structs.EnumPropertyData, UAssetAPI"}]
        }
        """)!;

        var diffs = _service.DiffRowProperties("Item", orig, cache);
        Assert.Single(diffs);
        Assert.Equal("EnabledState", diffs[0].Property);
        Assert.Equal("ERowEnabledState::Testing", diffs[0].Value);
    }

    [Fact]
    public void DiffRowProperties_DetectsGameplayTagChange()
    {
        var orig = JsonNode.Parse("""
        {
            "Name": "Stone",
            "Value": [{
                "Name": "Tags",
                "StructType": "GameplayTagContainer",
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "Value": [{
                    "Name": "Tags",
                    "Value": ["Item.Mineral.Stone", "Item.BasicGather"]
                }]
            }]
        }
        """)!;

        var cache = JsonNode.Parse("""
        {
            "Name": "Stone",
            "Value": [{
                "Name": "Tags",
                "StructType": "GameplayTagContainer",
                "$type": "UAssetAPI.PropertyTypes.Structs.StructPropertyData, UAssetAPI",
                "Value": [{
                    "Name": "Tags",
                    "Value": ["Item.Mineral.Stone", "Item.BasicGather", "Item.NewTag"]
                }]
            }]
        }
        """)!;

        var diffs = _service.DiffRowProperties("Stone", orig, cache);
        Assert.Single(diffs);
        Assert.Equal("Tags", diffs[0].Property);
        Assert.Contains("Item.NewTag", diffs[0].Value);
    }
}
