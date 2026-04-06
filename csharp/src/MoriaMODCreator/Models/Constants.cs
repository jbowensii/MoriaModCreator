namespace MoriaMODCreator.Models;

/// <summary>
/// Application-wide constants matching Python constants.py.
/// </summary>
public static class Constants
{
    // UE4 version strings
    public const string UeVersion = "VER_UE4_27";
    public const string RetocUeVersion = "UE4_27";

    // File extensions
    public const string DefExtension = ".def";
    public const string JsonExtension = ".json";
    public const string UassetExtension = ".uasset";
    public const string UmapExtension = ".umap";

    // Directory names
    public const string JsonFilesDir = "jsonfiles";
    public const string UassetDir = "uasset";
    public const string FinalModDir = "finalmod";
    public const string JsonDataDir = "jsondata";
    public const string RetocDir = "retoc";

    // Executable names
    public const string UAssetGuiExe = "UAssetGUI.exe";
    public const string RetocExe = "retoc.exe";
    public const string FModelExe = "FModel.exe";

    // UI constants
    public static readonly int[] ToolbarIconSize = [24, 24];
    public static readonly int[] TitleIconSize = [40, 40];

    // Colors
    public const string ColorCheckboxDefault = "#1f6aa5";
    public const string ColorCheckboxMixed = "#FFA500";
    public const string ColorStatusText = "#a0a0a0";
    public const string ColorSaveButton = "#4caf50";
    public const string ColorSaveButtonHover = "#388E3C";

    // Build
    public const int BuildTimeoutSeconds = 60;

    // Secrets pak stems
    public const string SecretsPakStem = "RtoMSecretsOfKhazaddum_NoFatStacks_P";
    public static readonly string[] SecretsCompanionFiles =
    [
        "SecretsOfKhazadDum_Localization_P.pak",
        "TobiModsAddons_P.pak",
        "TobiModsAddons_P.ucas",
        "TobiModsAddons_P.utoc",
    ];

    public static readonly string[] SkipSecretsPakStems =
    [
        "SecretsOfKhazadDum_Localization_P",
        "TobiModsAddons_P",
    ];

    // Search modes
    public const string SearchBoth = "Both";
    public const string SearchProperties = "Properties";
    public const string SearchValues = "Values";

    // Application info
    public const string AppName = "Moria MOD Creator";
    public const string AppVersion = "2.10.0";
    public const string AppDate = "April 2026";
    public const string AppAuthor = "John B Owens II";
    public const string GitHubUrl = "https://github.com/jbowensii/MoriaModCreator";
    public const string LicenseUrl = "https://github.com/jbowensii/MoriaModCreator?tab=MIT-1-ov-file#";
}
