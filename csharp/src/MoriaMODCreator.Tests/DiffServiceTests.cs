using System.Text.Json.Nodes;
using MoriaMODCreator.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace MoriaMODCreator.Tests;

public class DiffServiceTests
{
    private readonly ObjectTemplateService _templates = new(
        new ConfigService(), NullLogger<ObjectTemplateService>.Instance);
    private readonly DiffService _service;

    public DiffServiceTests()
    {
        _service = new DiffService(_templates, NullLogger<DiffService>.Instance);
    }

    [Fact]
    public void GenerateDefXml_ProducesValidXml()
    {
        var diffs = new List<PropertyDiff>
        {
            new() { ItemName = "Sword", PropertyPath = "Damage", NewValue = "150", OriginalValue = "100", DiffType = DiffType.Change },
            new() { ItemName = "Axe", PropertyPath = "Weight", NewValue = "50", DiffType = DiffType.Change },
        };

        var xml = _service.GenerateDefXml("Test Mod", "DT_Weapons.json", diffs);
        Assert.Contains("<title>Test Mod</title>", xml);
        Assert.Contains("item=\"Sword\"", xml);
        Assert.Contains("property=\"Damage\"", xml);
        Assert.Contains("value=\"150\"", xml);
        Assert.Contains("original=\"100\"", xml);
        Assert.Contains("item=\"Axe\"", xml);
    }

    [Fact]
    public void GenerateDefXml_HandlesDeleteDiffs()
    {
        var diffs = new List<PropertyDiff>
        {
            new() { ItemName = "Shield", PropertyPath = "Tags", NewValue = "Item.Removed", DiffType = DiffType.Delete },
        };

        var xml = _service.GenerateDefXml("Delete Test", "DT_Items.json", diffs);
        Assert.Contains("<delete", xml);
        Assert.Contains("item=\"Shield\"", xml);
    }

    [Fact]
    public void GenerateIniContent_ProducesValidIni()
    {
        var defPaths = new List<string> { "Items/DT_Weapons.def", "Building/DT_Buildings.def" };
        var ini = _service.GenerateIniContent("My Mod", "John", defPaths, true);

        Assert.Contains("[ModInfo]", ini);
        Assert.Contains("Title = My Mod", ini);
        Assert.Contains("Authors = John", ini);
        Assert.Contains("[Paths]", ini);
        Assert.Contains("Items|DT_Weapons = true", ini);
        Assert.Contains("[Settings]", ini);
        Assert.Contains("include_secrets = True", ini);
    }

    [Fact]
    public void GenerateIniContent_SecretsDisabled()
    {
        var ini = _service.GenerateIniContent("Test", "Author", ["x.def"], false);
        Assert.Contains("include_secrets = False", ini);
    }

    // =========================================================================
    // FormatValue — avoid JSON blobs for struct/SoftObject array elements
    // =========================================================================

    [Fact]
    public void FormatValue_ExtractsRowNameFromDataTableRowHandleStruct()
    {
        // A struct property element with an inner RowName (ItemHandle / MaterialHandle pattern)
        var node = JsonNode.Parse("""
            {
              "$type": "StructPropertyData",
              "Name": "MaterialHandle",
              "StructType": "DataTableRowHandle",
              "Value": [
                { "Name": "DataTable", "Value": "DT_Items" },
                { "Name": "RowName", "Value": "Item.Wood" }
              ]
            }
            """);

        var result = DiffService.FormatValue(node);
        Assert.Equal("Item.Wood", result);
    }

    [Fact]
    public void FormatValue_ExtractsAssetNameFromSoftObjectPath()
    {
        var node = JsonNode.Parse("""
            {
              "$type": "SoftObjectPropertyData",
              "Name": "Actor",
              "Value": { "AssetPath": { "AssetName": "BP_Sword_C", "PackageName": "..." } }
            }
            """);

        var result = DiffService.FormatValue(node);
        Assert.Equal("BP_Sword_C", result);
    }

    [Fact]
    public void FormatValue_ExtractsCultureInvariantStringFromText()
    {
        var node = JsonNode.Parse("""
            {
              "$type": "TextPropertyData",
              "Name": "DisplayName",
              "CultureInvariantString": "Iron Sword",
              "Value": { "History": {} }
            }
            """);

        var result = DiffService.FormatValue(node);
        Assert.Equal("Iron Sword", result);
    }

    [Fact]
    public void FormatValue_DoesNotEmitJsonBlobForKnownStructs()
    {
        var node = JsonNode.Parse("""
            {
              "$type": "StructPropertyData",
              "Name": "Handle",
              "Value": [ { "Name": "RowName", "Value": "Building.Stone" } ]
            }
            """);

        var result = DiffService.FormatValue(node);
        Assert.Equal("Building.Stone", result);
        Assert.DoesNotContain("\"$type\"", result);
    }

    [Fact]
    public void GenerateDefXml_EmbedsDescriptionWhenProvided()
    {
        var diffs = new List<PropertyDiff>
        {
            new() { ItemName = "Sword", PropertyPath = "Damage", NewValue = "150", DiffType = DiffType.Change },
        };
        var xml = _service.GenerateDefXml("Test Mod", "DT_Weapons.json", diffs,
            description: "Buffed sword damage", changeNote: "balance pass");
        Assert.Contains("<description>Buffed sword damage</description>", xml);
        Assert.Contains("note=\"balance pass\"", xml);
    }

    [Fact]
    public void GenerateDefXml_IncludesCommentsWhenRequested()
    {
        var diffs = new List<PropertyDiff>
        {
            new() { ItemName = "Axe", PropertyPath = "Weight", NewValue = "10", OriginalValue = "5", DiffType = DiffType.Change },
        };
        var xml = _service.GenerateDefXml("Test", "DT.json", diffs, includeComments: true);
        Assert.Matches(@"<!--\s*Axe\s*(→|->)\s*Weight\s*-->\s*<change", xml);
    }

    [Fact]
    public void GenerateDefXml_DoesNotApplyChangeNoteToDeleteDiffs()
    {
        var diffs = new List<PropertyDiff>
        {
            new() { ItemName = "Shield", PropertyPath = "Tags", NewValue = "Item.Removed", DiffType = DiffType.Delete },
        };
        var xml = _service.GenerateDefXml("Test", "DT.json", diffs, changeNote: "balance pass");
        Assert.Contains("<delete", xml);
        Assert.DoesNotContain("note=\"balance pass\"", xml);
    }
}
