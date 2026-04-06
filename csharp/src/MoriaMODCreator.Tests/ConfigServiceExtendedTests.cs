using MoriaMODCreator.Services;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ConfigServiceExtendedTests
{
    [Fact]
    public void GetColorScheme_ReturnsDefault()
    {
        var config = new ConfigService();
        Assert.Equal("Blue (Default)", config.GetColorScheme());
    }

    [Fact]
    public void GetMaxWorkers_ReturnsDefault4()
    {
        var config = new ConfigService();
        Assert.Equal(4, config.GetMaxWorkers());
    }

    [Fact]
    public void GetDebugMode_ReturnsBool()
    {
        var config = new ConfigService();
        // May be true or false depending on config.ini state — just verify it returns without error
        _ = config.GetDebugMode();
    }

    [Fact]
    public void GetFinalDestinationDir_ReturnsDownloads()
    {
        var config = new ConfigService();
        var dir = config.GetFinalDestinationDir();
        Assert.Contains("Downloads", dir);
    }

    [Fact]
    public void GetGenerateBuildersPackEnabled_ReturnsFalseByDefault()
    {
        var config = new ConfigService();
        Assert.False(config.GetGenerateBuildersPackEnabled());
    }

    [Fact]
    public void GetConstructionsJsonDir_ReturnsPath()
    {
        var config = new ConfigService();
        var dir = config.GetConstructionsJsonDir();
        Assert.Contains("Building", dir);
    }

    [Fact]
    public void SetAndGetConstructionsJsonDir_RoundTrips()
    {
        var config = new ConfigService();
        config.SetConstructionsJsonDir(@"C:\Test\Path");
        Assert.Equal(@"C:\Test\Path", config.GetConstructionsJsonDir());
    }

    [Fact]
    public void ValidateConfig_ReturnsErrors_WhenNotConfigured()
    {
        var config = new ConfigService();
        var errors = config.ValidateConfig();
        Assert.NotEmpty(errors); // Game path won't be set in test environment
    }

    [Fact]
    public void GetAvailableInstallOptions_AlwaysIncludesCustom()
    {
        var options = ConfigService.GetAvailableInstallOptions();
        Assert.Contains(options, o => o.Name == "Custom");
    }

    [Fact]
    public void NewSecretsRawJsonDir_ContainsRawJson()
    {
        var config = new ConfigService();
        Assert.Contains("Raw JSON", config.NewSecretsRawJsonDir);
    }
}
