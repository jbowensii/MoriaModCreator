using MoriaMODCreator.Services;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ConfigServiceTests
{
    [Fact]
    public void AppDataDir_IsNotEmpty()
    {
        var config = new ConfigService();
        Assert.False(string.IsNullOrEmpty(config.AppDataDir));
        Assert.Contains("MoriaMODCreator", config.AppDataDir);
    }

    [Fact]
    public void DirectoryPaths_AreUnderAppData()
    {
        var config = new ConfigService();
        Assert.StartsWith(config.AppDataDir, config.DefinitionsDir);
        Assert.StartsWith(config.AppDataDir, config.SecretsSourceDir);
        Assert.StartsWith(config.AppDataDir, config.SecretsJsonDataFullDir);
        Assert.StartsWith(config.AppDataDir, config.OutputJsonDataDir);
        Assert.StartsWith(config.AppDataDir, config.UtilitiesDir);
    }

    [Fact]
    public void GetModDir_IncludesModName()
    {
        var config = new ConfigService();
        var modDir = config.GetModDir("TestMod");
        Assert.Contains("TestMod", modDir);
        Assert.Contains("mymodfiles", modDir);
    }

    [Fact]
    public void SetAndGetValue_RoundTrips()
    {
        var config = new ConfigService();
        config.SetValue("TestSection", "TestKey", "TestValue");
        var result = config.GetValue("TestSection", "TestKey");
        Assert.Equal("TestValue", result);
    }

    [Fact]
    public void GetValue_ReturnsNull_ForMissingKey()
    {
        var config = new ConfigService();
        var result = config.GetValue("NonExistent", "NoKey");
        Assert.Null(result);
    }
}
