using Microsoft.Extensions.Logging.Abstractions;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;
using Xunit;

namespace MoriaMODCreator.Tests;

public class BuildServiceTests
{
    // =========================================================================
    // BuildProgress / BuildResult records
    // =========================================================================

    [Fact]
    public void BuildProgress_HasStatusAndProgress()
    {
        var p = new BuildProgress("Building...", 0.5);
        Assert.Equal("Building...", p.Status);
        Assert.Equal(0.5, p.Progress);
    }

    [Fact]
    public void BuildResult_Success()
    {
        var r = new BuildResult(true, "/path/to/mod.zip");
        Assert.True(r.Success);
        Assert.Contains("mod.zip", r.Message);
    }

    [Fact]
    public void BuildResult_Failure()
    {
        var r = new BuildResult(false, "retoc packaging failed");
        Assert.False(r.Success);
        Assert.Contains("retoc", r.Message);
    }

    // =========================================================================
    // DefinitionService.NormalizePath (used by build pipeline)
    // =========================================================================

    [Fact]
    public void NormalizePath_StripsSecretsSourceJsondata()
    {
        var result = DefinitionService.NormalizePath("Secrets Source/jsondata/Moria/Content/Items/DT_Weapons.json");
        Assert.Equal("Moria/Content/Items/DT_Weapons.json", result);
    }

    [Fact]
    public void NormalizePath_PreservesNonSecretsPath()
    {
        var result = DefinitionService.NormalizePath("Moria/Content/Items/DT_Weapons.json");
        Assert.Equal("Moria/Content/Items/DT_Weapons.json", result);
    }

    // =========================================================================
    // Constants validation
    // =========================================================================

    [Fact]
    public void Constants_SecretsCompanionFiles_HasExpectedFiles()
    {
        Assert.Contains("SecretsOfKhazadDum_LocTags_P.pak", Constants.SecretsCompanionFiles);
        Assert.Contains("TobiModsAddons_P.pak", Constants.SecretsCompanionFiles);
        Assert.Contains("TobiModsAddons_P.ucas", Constants.SecretsCompanionFiles);
        Assert.Contains("TobiModsAddons_P.utoc", Constants.SecretsCompanionFiles);
    }

    [Fact]
    public void Constants_SkipSecretsPakStems_SkipsExpected()
    {
        Assert.Contains("SecretsOfKhazadDum_Localization_P", Constants.SkipSecretsPakStems);
        Assert.Contains("TobiModsAddons_P", Constants.SkipSecretsPakStems);
    }

    [Fact]
    public void Constants_AppVersion_IsSet()
    {
        Assert.False(string.IsNullOrEmpty(Constants.AppVersion));
        Assert.Contains(".", Constants.AppVersion);
    }
}
