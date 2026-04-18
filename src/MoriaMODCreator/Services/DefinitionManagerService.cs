using System.IO;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Manages mod definition selection state (checkbox persistence).
/// Mirrors Python definition_manager.py.
/// </summary>
public class DefinitionManagerService
{
    private readonly ConfigService _config;
    private readonly ILogger<DefinitionManagerService> _logger;

    public DefinitionManagerService(ConfigService config, ILogger<DefinitionManagerService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>Get the checkbox state INI path for a mod.</summary>
    public string GetCheckboxIniPath(string modName)
    {
        return Path.Combine(_config.GetModDir(modName), "checked_items.ini");
    }

    /// <summary>Load checkbox states from the INI file.</summary>
    public Dictionary<string, bool> LoadCheckboxStates(string modName)
    {
        var states = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
        var iniPath = GetCheckboxIniPath(modName);
        if (!File.Exists(iniPath)) return states;

        string? currentSection = null;
        foreach (var line in File.ReadAllLines(iniPath))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                currentSection = trimmed[1..^1];
                continue;
            }
            if (currentSection == "CheckedItems" && trimmed.Contains('='))
            {
                var eqIdx = trimmed.IndexOf('=');
                var key = trimmed[..eqIdx].Trim();
                var value = trimmed[(eqIdx + 1)..].Trim();
                states[key] = value.Equals("true", StringComparison.OrdinalIgnoreCase);
            }
        }
        return states;
    }

    /// <summary>Save checkbox states to the INI file.</summary>
    public void SaveCheckboxStates(string modName, Dictionary<string, bool> states)
    {
        var iniPath = GetCheckboxIniPath(modName);
        Directory.CreateDirectory(Path.GetDirectoryName(iniPath)!);

        using var writer = new StreamWriter(iniPath);
        writer.WriteLine("[CheckedItems]");
        foreach (var (key, value) in states.OrderBy(kv => kv.Key))
        {
            writer.WriteLine($"{key} = {(value ? "true" : "false")}");
        }
    }

    /// <summary>Get all selected (checked) .def file paths for a mod.</summary>
    public List<string> GetAllSelectedDefinitions(string modName)
    {
        var states = LoadCheckboxStates(modName);
        return states.Where(kv => kv.Value)
                     .Select(kv => kv.Key)
                     .Where(File.Exists)
                     .ToList();
    }
}
