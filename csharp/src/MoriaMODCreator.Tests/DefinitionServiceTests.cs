using System.IO;
using MoriaMODCreator.Services;
using MoriaMODCreator.Models;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace MoriaMODCreator.Tests;

public class DefinitionServiceTests
{
    private readonly DefinitionService _service = new(NullLogger<DefinitionService>.Instance);

    [Fact]
    public void Parse_ValidDefFile_ReturnsCorrectModel()
    {
        var defContent = """
            <?xml version="1.0" encoding="UTF-8"?>
            <definition>
              <title>Test Mod</title>
              <author>Test Author</author>
              <description>Test description</description>
              <mod file="Moria\Content\Tech\Data\Items\DT_Weapons.json">
                <change item="Sword" property="Damage" value="150" original="100" />
                <change item="Axe" property="Weight" value="50" />
                <delete item="Shield" property="Tags" value="Item.Removed" />
              </mod>
            </definition>
            """;

        var tempFile = Path.GetTempFileName();
        File.WriteAllText(tempFile, defContent);
        try
        {
            var result = _service.Parse(tempFile);
            Assert.Equal("Test Mod", result.Title);
            Assert.Equal("Test Author", result.Author);
            Assert.Single(result.ModFiles);
            Assert.Equal(2, result.ModFiles[0].Changes.Count);
            Assert.Single(result.ModFiles[0].Deletes);
            Assert.Equal("Sword", result.ModFiles[0].Changes[0].Item);
            Assert.Equal("150", result.ModFiles[0].Changes[0].Value);
            Assert.Equal("100", result.ModFiles[0].Changes[0].Original);
        }
        finally { File.Delete(tempFile); }
    }

    [Fact]
    public void Parse_MultipleModBlocks_ParsesAll()
    {
        var defContent = """
            <?xml version="1.0" encoding="UTF-8"?>
            <definition>
              <title>Multi Mod</title>
              <mod file="DT_Weapons.json">
                <change item="Sword" property="Damage" value="100" />
              </mod>
              <mod file="DT_Armor.json">
                <change item="Shield" property="Defense" value="50" />
              </mod>
            </definition>
            """;

        var tempFile = Path.GetTempFileName();
        File.WriteAllText(tempFile, defContent);
        try
        {
            var result = _service.Parse(tempFile);
            Assert.Equal(2, result.ModFiles.Count);
            Assert.Equal("DT_Weapons.json", result.ModFiles[0].FilePath);
            Assert.Equal("DT_Armor.json", result.ModFiles[1].FilePath);
        }
        finally { File.Delete(tempFile); }
    }

    [Fact]
    public void NormalizePath_StripsSecretsSourcePrefix()
    {
        Assert.Equal("Building/DT_X.json",
            DefinitionService.NormalizePath("Secrets Source/jsondata/Building/DT_X.json"));
    }

    [Fact]
    public void NormalizePath_HandlesRegularPath()
    {
        Assert.Equal("Moria/Content/Items/DT_Weapons.json",
            DefinitionService.NormalizePath("Moria/Content/Items/DT_Weapons.json"));
    }

    [Fact]
    public void NormalizePath_HandlesBackslashes()
    {
        Assert.Equal("Building/DT_X.json",
            DefinitionService.NormalizePath("Secrets Source\\jsondata\\Building\\DT_X.json"));
    }

    [Fact]
    public void NormalizePath_StripsLeadingSlash()
    {
        Assert.Equal("Items/DT_Weapons.json",
            DefinitionService.NormalizePath("/Items/DT_Weapons.json"));
    }

    [Fact]
    public void ReferencesSecrets_DetectsSecretsPath()
    {
        var def = new ModDefinition
        {
            ModFiles = [new() { FilePath = "Secrets Source/jsondata/Items/DT_Items.json" }]
        };
        Assert.True(_service.ReferencesSecrets(def));
    }

    [Fact]
    public void ReferencesSecrets_ReturnsFalseForGamePath()
    {
        var def = new ModDefinition
        {
            ModFiles = [new() { FilePath = "Moria/Content/Items/DT_Items.json" }]
        };
        Assert.False(_service.ReferencesSecrets(def));
    }

    [Fact]
    public void ReferencesSecrets_CaseInsensitive()
    {
        var def = new ModDefinition
        {
            ModFiles = [new() { FilePath = "SECRETS SOURCE/jsondata/DT_X.json" }]
        };
        Assert.True(_service.ReferencesSecrets(def));
    }
}
