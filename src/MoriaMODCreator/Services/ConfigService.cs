using System.IO;

namespace MoriaMODCreator.Services;

/// <summary>
/// Manages application configuration and AppData directory paths.
/// Mirrors the Python config.py functionality.
/// </summary>
public class ConfigService
{
    private const string AppDataFolderName = "MoriaMODCreator";
    private const string ConfigFileName = "config.ini";

    public string AppDataDir { get; }
    public string ConfigFilePath { get; }

    public ConfigService()
    {
        AppDataDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            AppDataFolderName);
        ConfigFilePath = Path.Combine(AppDataDir, ConfigFileName);
        Directory.CreateDirectory(AppDataDir);
    }

    // --- Directory paths (mirrors Python config.py) ---

    public string DefinitionsDir => GetValue("Directories", "definitions") ?? Path.Combine(AppDataDir, "Definitions");
    public string PrebuiltModfilesDir => Path.Combine(AppDataDir, "prebuilt modfiles");
    public string SecretsSourceDir => Path.Combine(AppDataDir, "Secrets Source");
    /// <summary>Raw extracted repo contents (full tree including /json, /StringTables, /scripts, etc.).</summary>
    public string SecretsGitHubRawDir => Path.Combine(SecretsSourceDir, "github");
    /// <summary>Post-processed DataTable JSON copied out of /github/json/Moria/Content/.</summary>
    public string SecretsJsonDataGitHubDir => Path.Combine(SecretsSourceDir, "jsondata_github");
    public string SecretsJsonDataDir => Path.Combine(SecretsSourceDir, "jsondata");
    public string OutputDir => GetValue("Directories", "output") ?? Path.Combine(AppDataDir, "output");
    public string OutputJsonDataDir => Path.Combine(OutputDir, "jsondata");
    public string OutputRetocDir => Path.Combine(OutputDir, "retoc");
    public string MyModFilesDir => GetValue("Directories", "mymodfiles") ?? Path.Combine(AppDataDir, "mymodfiles");
    public string UtilitiesDir => GetValue("Directories", "utilities") ?? Path.Combine(AppDataDir, "utilities");
    public string CacheDir => Path.Combine(AppDataDir, "cache");
    public string NewSecretsDir => Path.Combine(AppDataDir, "New Secrets");
    public string NewSecretsJsonDataDir => Path.Combine(NewSecretsDir, "jsondata");
    public string ChangeSecretsDir => Path.Combine(AppDataDir, "changesecrets");
    public string ChangeConstructionsDir => Path.Combine(AppDataDir, "changeconstructions");
    public string NewObjectsDir => Path.Combine(AppDataDir, "New Objects");

    public string RetocExePath => Path.Combine(UtilitiesDir, "retoc.exe");
    public string UAssetGuiExePath => Path.Combine(UtilitiesDir, "UAssetGUI.exe");

    /// <summary>Get the mod build directory for a named mod.</summary>
    public string GetModDir(string modName) => Path.Combine(MyModFilesDir, modName);
    public string GetModJsonFilesDir(string modName) => Path.Combine(GetModDir(modName), "jsonfiles");
    public string GetModUAssetDir(string modName) => Path.Combine(GetModDir(modName), "uasset");
    public string GetModFinalDir(string modName) => Path.Combine(GetModDir(modName), "finalmod");

    // --- Config.ini read/write ---

    private Dictionary<string, Dictionary<string, string>>? _config;

    public string? GetValue(string section, string key)
    {
        EnsureConfigLoaded();
        if (_config!.TryGetValue(section, out var sec) && sec.TryGetValue(key, out var val))
            return val;
        return null;
    }

    public void SetValue(string section, string key, string value)
    {
        EnsureConfigLoaded();
        if (!_config!.ContainsKey(section))
            _config[section] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        _config[section][key] = value;
    }

    public void Save()
    {
        if (_config == null) return;
        using var writer = new StreamWriter(ConfigFilePath);
        foreach (var (section, entries) in _config)
        {
            writer.WriteLine($"[{section}]");
            foreach (var (key, value) in entries)
                writer.WriteLine($"{key} = {value}");
            writer.WriteLine();
        }
    }

    public string? GetGameInstallPath()
    {
        return GetValue("Game", "game_path") ?? GetValue("Settings", "game_path");
    }

    public string GetColorScheme() => GetValue("Settings", "color_scheme") ?? "Blue (Default)";
    public int GetMaxWorkers()
    {
        var val = GetValue("Performance", "max_workers") ?? GetValue("Settings", "max_workers");
        return int.TryParse(val, out var w) ? w : 4;
    }
    public bool GetDebugMode()
    {
        var val = GetValue("Debug", "debug") ?? GetValue("Debug", "debug_mode");
        return val?.Equals("true", StringComparison.OrdinalIgnoreCase) ?? false;
    }
    public string GetFinalDestinationDir() => GetValue("Directories", "final_destination")
        ?? GetValue("Settings", "final_destination")
        ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
    public string NewSecretsRawJsonDir => Path.Combine(NewSecretsDir, "Raw JSON");

    public bool GetGenerateBuildersPackEnabled() =>
        GetValue("Settings", "generate_builders_pack")?.Equals("true", StringComparison.OrdinalIgnoreCase) ?? false;

    public string GetConstructionsJsonDir() =>
        GetValue("Settings", "constructions_json_dir") ?? Path.Combine(OutputJsonDataDir, "Moria", "Content", "Tech", "Data", "Building");

    public void SetConstructionsJsonDir(string path) =>
        SetValue("Settings", "constructions_json_dir", path);

    /// <summary>
    /// Find a source JSON file by checking Secrets Source/jsondata_github/modified-json/Moria/Content/ first
    /// (for secrets mode), then game output jsondata.
    /// Shared utility for CategoryDataService and BuildingsDataService.
    /// </summary>
    public string? FindSourceJson(string mode, string relativePath)
    {
        // Secrets mode: use New Secrets (filtered, secrets-only rows)
        if (mode == "secrets")
        {
            var newSecretsPath = Path.Combine(NewSecretsJsonDataDir, "Moria", "Content", relativePath);
            if (File.Exists(newSecretsPath)) return newSecretsPath;

            // Fallback to jsondata_github full data
            var githubPath = Path.Combine(
                SecretsJsonDataGitHubDir, "modified-json", "Moria", "Content", relativePath);
            if (File.Exists(githubPath)) return githubPath;
        }

        // Constructions mode + default: use game output ONLY (no secrets data)
        var gamePath = Path.Combine(OutputJsonDataDir, "Moria", "Content", relativePath);
        if (File.Exists(gamePath)) return gamePath;

        return null;
    }

    /// <summary>Color palette definition for a theme.</summary>
    private record ColorPalette(
        string Background, string Surface, string Primary, string Accent,
        string Button, string ButtonHover, string ButtonInactive, string ButtonInactiveHover,
        string Import, string ListItemHover, string ListItemSelected);

    private static readonly Dictionary<string, ColorPalette> Palettes = new()
    {
        ["Blue (Default)"] = new("#1a1a2e", "#2d2d44", "#1f6aa5", "#3b8ed0",
            "#1f6aa5", "#3b8ed0", "#4d4d4d", "#666666",
            "#2E7D32", "#3a3a55", "#2a4a6b"),
        ["Dark Blue"] = new("#0d1b2a", "#1b2838", "#1565C0", "#42A5F5",
            "#1565C0", "#42A5F5", "#37474F", "#546E7A",
            "#0D47A1", "#263850", "#1a3a5c"),
        ["Green"] = new("#1a2e1a", "#2d442d", "#2E7D32", "#4CAF50",
            "#2E7D32", "#4CAF50", "#4d4d4d", "#666666",
            "#1B5E20", "#3a553a", "#2a6b2a"),
    };

    /// <summary>
    /// Apply a color scheme by updating existing SolidColorBrush.Color properties.
    /// This works with StaticResource because the brush objects stay the same — only their Color changes.
    /// </summary>
    public static void ApplyColorScheme(string scheme)
    {
        var app = System.Windows.Application.Current;
        if (app == null) return;

        if (!Palettes.TryGetValue(scheme, out var palette))
            palette = Palettes["Blue (Default)"];

        static System.Windows.Media.Color Parse(string hex) =>
            (System.Windows.Media.Color)System.Windows.Media.ColorConverter.ConvertFromString(hex);

        static void SetBrush(System.Windows.Application a, string key, string hex)
        {
            if (a.Resources[key] is System.Windows.Media.SolidColorBrush brush)
                brush.Color = Parse(hex);
        }

        try
        {
            SetBrush(app, "BackgroundBrush", palette.Background);
            SetBrush(app, "SurfaceBrush", palette.Surface);
            SetBrush(app, "PrimaryBrush", palette.Primary);
            SetBrush(app, "AccentBrush", palette.Accent);
            SetBrush(app, "ButtonBrush", palette.Button);
            SetBrush(app, "ButtonHoverBrush", palette.ButtonHover);
            SetBrush(app, "ButtonInactiveBrush", palette.ButtonInactive);
            SetBrush(app, "ButtonInactiveHoverBrush", palette.ButtonInactiveHover);
            SetBrush(app, "ImportBrush", palette.Import);
            SetBrush(app, "ListItemHoverBrush", palette.ListItemHover);
            SetBrush(app, "ListItemSelectedBrush", palette.ListItemSelected);
        }
        catch (Exception ex)
        {
            System.Diagnostics.Debug.WriteLine($"Failed to apply color scheme '{scheme}': {ex.Message}");
        }
    }

    public bool IsConfigValid()
    {
        var gamePath = GetGameInstallPath();
        return !string.IsNullOrEmpty(gamePath) && Directory.Exists(gamePath);
    }

    /// <summary>Validate all config paths exist.</summary>
    public List<string> ValidateConfig()
    {
        var errors = new List<string>();
        var gamePath = GetGameInstallPath();
        if (string.IsNullOrEmpty(gamePath) || !Directory.Exists(gamePath))
            errors.Add("Game install path is not configured or does not exist");
        if (!File.Exists(RetocExePath))
            errors.Add("retoc.exe not found in utilities directory");
        if (!File.Exists(UAssetGuiExePath))
            errors.Add("UAssetGUI.exe not found in utilities directory");
        return errors;
    }

    /// <summary>Check if a Steam install exists.</summary>
    public static string? CheckSteamPath()
    {
        var paths = new[]
        {
            @"C:\Program Files (x86)\Steam\steamapps\common\Return to Moria",
            @"C:\Program Files\Steam\steamapps\common\Return to Moria",
        };
        return paths.FirstOrDefault(Directory.Exists);
    }

    /// <summary>Check if an Epic Games install exists.</summary>
    public static string? CheckEpicPath()
    {
        var path = @"C:\Program Files\Epic Games\ReturnToMoria";
        return Directory.Exists(path) ? path : null;
    }

    /// <summary>Get all available game install options.</summary>
    public static List<(string Name, string Path)> GetAvailableInstallOptions()
    {
        var options = new List<(string, string)>();
        var epic = CheckEpicPath();
        if (epic != null) options.Add(("Epic Games", epic));
        var steam = CheckSteamPath();
        if (steam != null) options.Add(("Steam", steam));
        options.Add(("Custom", ""));
        return options;
    }

    public string? GetGamePaksPath()
    {
        var gamePath = GetGameInstallPath();
        if (gamePath == null) return null;
        return Path.Combine(gamePath, "Moria", "Content", "Paks");
    }

    private void EnsureConfigLoaded()
    {
        if (_config != null) return;
        _config = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
        if (!File.Exists(ConfigFilePath)) return;

        string? currentSection = null;
        foreach (var line in File.ReadAllLines(ConfigFilePath))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                currentSection = trimmed[1..^1];
                if (!_config.ContainsKey(currentSection))
                    _config[currentSection] = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            }
            else if (currentSection != null && trimmed.Contains('='))
            {
                var eqIdx = trimmed.IndexOf('=');
                var key = trimmed[..eqIdx].Trim();
                var value = trimmed[(eqIdx + 1)..].Trim();
                _config[currentSection][key] = value;
            }
        }
    }
}
