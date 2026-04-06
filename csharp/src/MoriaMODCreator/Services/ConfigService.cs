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

    public string DefinitionsDir => Path.Combine(AppDataDir, "Definitions");
    public string PrebuiltModfilesDir => Path.Combine(AppDataDir, "prebuilt modfiles");
    public string SecretsSourceDir => Path.Combine(AppDataDir, "Secrets Source");
    public string SecretsJsonDataFullDir => Path.Combine(SecretsSourceDir, "jsondata_full");
    public string SecretsJsonDataDir => Path.Combine(SecretsSourceDir, "jsondata");
    public string OutputDir => Path.Combine(AppDataDir, "output");
    public string OutputJsonDataDir => Path.Combine(OutputDir, "jsondata");
    public string OutputRetocDir => Path.Combine(OutputDir, "retoc");
    public string MyModFilesDir => Path.Combine(AppDataDir, "mymodfiles");
    public string UtilitiesDir => Path.Combine(AppDataDir, "utilities");
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
    public int GetMaxWorkers() => int.TryParse(GetValue("Settings", "max_workers"), out var w) ? w : 4;
    public bool GetDebugMode() => GetValue("Debug", "debug_mode")?.Equals("true", StringComparison.OrdinalIgnoreCase) ?? false;
    public string GetFinalDestinationDir() => GetValue("Settings", "final_destination")
        ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");
    public string NewSecretsRawJsonDir => Path.Combine(NewSecretsDir, "Raw JSON");

    public bool IsConfigValid()
    {
        var gamePath = GetGameInstallPath();
        return !string.IsNullOrEmpty(gamePath) && Directory.Exists(gamePath);
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
