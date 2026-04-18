using System.Text.Json.Nodes;
using MoriaMODCreator.Services;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ObjectTemplateServiceTests
{
    private readonly ObjectTemplateService _service = new(
        new ConfigService(), NullLogger<ObjectTemplateService>.Instance);

    private static JsonNode CreateRow(string name, params (string PropName, object Value)[] props)
    {
        var valueArray = new JsonArray();
        foreach (var (propName, value) in props)
        {
            var prop = new JsonObject
            {
                ["Name"] = propName,
                ["Value"] = value is int i ? JsonValue.Create(i) : JsonValue.Create(value.ToString()!),
            };
            valueArray.Add(prop);
        }

        return new JsonObject
        {
            ["Name"] = name,
            ["Value"] = valueArray,
        };
    }

    private static JsonNode CreateDataTable(params JsonNode[] rows)
    {
        var dataArray = new JsonArray();
        foreach (var row in rows)
            dataArray.Add(row);

        return new JsonObject
        {
            ["NameMap"] = new JsonArray(),
            ["Exports"] = new JsonArray
            {
                new JsonObject
                {
                    ["Table"] = new JsonObject
                    {
                        ["Data"] = dataArray,
                    },
                },
            },
        };
    }

    [Fact]
    public void GetRowNames_ReturnsAllNames()
    {
        var dt = CreateDataTable(
            CreateRow("Sword", ("Damage", 100)),
            CreateRow("Axe", ("Damage", 80)),
            CreateRow("Bow", ("Damage", 50)));

        var names = _service.GetRowNames(dt);
        Assert.Equal(3, names.Count);
        Assert.Contains("Sword", names);
        Assert.Contains("Axe", names);
        Assert.Contains("Bow", names);
    }

    [Fact]
    public void GetRowByName_FindsRow()
    {
        var dt = CreateDataTable(
            CreateRow("Sword", ("Damage", 100)),
            CreateRow("Axe", ("Damage", 80)));

        var row = _service.GetRowByName(dt, "Axe");
        Assert.NotNull(row);
        Assert.Equal("Axe", row!["Name"]!.GetValue<string>());
    }

    [Fact]
    public void GetRowByName_ReturnsNullForMissing()
    {
        var dt = CreateDataTable(CreateRow("Sword", ("Damage", 100)));
        Assert.Null(_service.GetRowByName(dt, "NonExistent"));
    }

    [Fact]
    public void GetRowProperty_ReturnsValue()
    {
        var row = CreateRow("Sword", ("Damage", 100));
        var value = _service.GetRowProperty(row, "Damage");
        Assert.NotNull(value);
        Assert.Equal(100, value!.GetValue<int>());
    }

    [Fact]
    public void GetRowProperty_ReturnsNullForMissing()
    {
        var row = CreateRow("Sword", ("Damage", 100));
        Assert.Null(_service.GetRowProperty(row, "NonExistent"));
    }

    [Fact]
    public void SetRowProperty_UpdatesValue()
    {
        var row = CreateRow("Sword", ("Damage", 100));
        var result = _service.SetRowProperty(row, "Damage", JsonValue.Create(200));
        Assert.True(result);

        var newValue = _service.GetRowProperty(row, "Damage");
        Assert.Equal(200, newValue!.GetValue<int>());
    }

    [Fact]
    public void AddRow_InsertsRow()
    {
        var dt = CreateDataTable(CreateRow("Sword", ("Damage", 100)));
        var newRow = CreateRow("Bow", ("Damage", 50));

        var result = _service.AddRow(dt, newRow);
        Assert.True(result);
        Assert.Equal(2, _service.GetRowNames(dt).Count);
    }

    [Fact]
    public void RemoveRow_DeletesRow()
    {
        var dt = CreateDataTable(
            CreateRow("Sword", ("Damage", 100)),
            CreateRow("Axe", ("Damage", 80)));

        var result = _service.RemoveRow(dt, "Sword");
        Assert.True(result);
        Assert.Single(_service.GetRowNames(dt));
        Assert.Equal("Axe", _service.GetRowNames(dt)[0]);
    }

    [Fact]
    public void RemoveRow_ReturnsFalseForMissing()
    {
        var dt = CreateDataTable(CreateRow("Sword", ("Damage", 100)));
        Assert.False(_service.RemoveRow(dt, "NonExistent"));
    }

    [Fact]
    public void CloneRow_CreatesDeepCopy()
    {
        var dt = CreateDataTable(CreateRow("Sword", ("Damage", 100)));
        var clone = _service.CloneRow(dt, "Sword", "Sword_Copy");

        Assert.NotNull(clone);
        Assert.Equal("Sword_Copy", clone!["Name"]!.GetValue<string>());
    }

    [Fact]
    public void CloneRow_ReturnsNullForMissing()
    {
        var dt = CreateDataTable(CreateRow("Sword", ("Damage", 100)));
        Assert.Null(_service.CloneRow(dt, "NonExistent", "Copy"));
    }

    [Fact]
    public void GenUniqueTag_Returns32CharHex()
    {
        var tag = ObjectTemplateService.GenUniqueTag();
        Assert.Equal(32, tag.Length);
        Assert.True(tag.All(c => "0123456789ABCDEF".Contains(c)));
    }

    [Fact]
    public void GenUniqueTag_IsUnique()
    {
        var tags = Enumerable.Range(0, 100).Select(_ => ObjectTemplateService.GenUniqueTag()).ToHashSet();
        Assert.Equal(100, tags.Count);
    }

    [Fact]
    public void ExtractRecipeFields_ReturnsAllProperties()
    {
        var row = CreateRow("Recipe1", ("Material", "Iron"), ("Amount", 5));
        var fields = _service.ExtractRecipeFields(row);
        Assert.Equal(3, fields.Count); // Name + Material + Amount
        Assert.True(fields.ContainsKey("Name"));
        Assert.True(fields.ContainsKey("Material"));
        Assert.True(fields.ContainsKey("Amount"));
    }

    [Fact]
    public void ExtractTagNames_HandlesPlainStringTags()
    {
        var container = JsonNode.Parse("""
            {
              "Name": "Tags",
              "StructType": "GameplayTagContainer",
              "Value": [
                { "Name": "GameplayTags", "Value": [ "Tag.One", "Tag.Two" ] }
              ]
            }
            """)!;
        var tags = _service.ExtractTagNames(container);
        Assert.Equal(2, tags.Count);
        Assert.Contains("Tag.One", tags);
        Assert.Contains("Tag.Two", tags);
    }

    [Fact]
    public void ExtractTagNames_HandlesWrappedNamePropertyData()
    {
        // Some UAssetAPI dumps wrap tags in NamePropertyData objects instead of bare strings.
        // Previously this crashed with GetValue<string>(). Must no longer crash.
        var container = JsonNode.Parse("""
            {
              "Name": "Tags",
              "StructType": "GameplayTagContainer",
              "Value": [
                { "Name": "GameplayTags", "Value": [
                  { "$type": "NamePropertyData", "Name": "Tag", "Value": "Tag.Wrapped" }
                ] }
              ]
            }
            """)!;
        var tags = _service.ExtractTagNames(container);
        Assert.Single(tags);
        Assert.Equal("Tag.Wrapped", tags[0]);
    }

    [Fact]
    public void ExtractPropertyValue_FloatWithStringNoneValue_DoesNotThrow()
    {
        // UAssetAPI sometimes emits "None" as a string for a nulled-out Float slot.
        // This used to crash Tools/Weapons forms.
        var prop = JsonNode.Parse("""
            { "$type": "FloatPropertyData", "Name": "Speed", "Value": "None" }
            """)!;
        var result = _service.ExtractPropertyValue(prop);
        Assert.NotNull(result);
    }

    [Fact]
    public void ExtractPropertyValue_IntWithStringValue_DoesNotThrow()
    {
        var prop = JsonNode.Parse("""
            { "$type": "IntPropertyData", "Name": "Count", "Value": "None" }
            """)!;
        var result = _service.ExtractPropertyValue(prop);
        Assert.NotNull(result);
    }
}
