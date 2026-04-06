using System.IO;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.Services;

/// <summary>
/// Reads and manages prebuilt mod .ini files for Novice mode.
/// </summary>
public class PrebuiltModService
{
    private readonly ConfigService _config;
    private readonly ILogger<PrebuiltModService> _logger;

    public PrebuiltModService(ConfigService config, ILogger<PrebuiltModService> logger)
    {
        _config = config;
        _logger = logger;
    }

    /// <summary>Load all prebuilt mods from the prebuilt modfiles directory.</summary>
    public List<PrebuiltMod> LoadAll()
    {
        var dir = _config.PrebuiltModfilesDir;
        if (!Directory.Exists(dir))
            return [];

        var mods = new List<PrebuiltMod>();
        foreach (var iniFile in Directory.GetFiles(dir, "*.ini"))
        {
            try
            {
                mods.Add(ParseIni(iniFile));
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Failed to parse prebuilt mod: {File}", iniFile);
            }
        }

        _logger.LogInformation("Loaded {Count} prebuilt mod(s)", mods.Count);
        return mods;
    }

    /// <summary>
    /// Resolve .def file paths from a prebuilt mod's [Paths] section.
    /// Returns absolute paths to .def files.
    /// </summary>
    public List<string> ResolveDefPaths(PrebuiltMod mod)
    {
        var defDir = _config.DefinitionsDir;
        var resolved = new List<string>();

        foreach (var pathEntry in mod.DefPaths)
        {
            // Convert "items|dt_weapons" to "items\dt_weapons"
            var relPath = pathEntry.Replace('|', Path.DirectorySeparatorChar)
                                   .Replace('~', ':');

            // Try to find the .def file
            var candidates = new[]
            {
                Path.Combine(defDir, relPath + ".def"),
                Path.Combine(defDir, relPath),
            };

            var found = candidates.FirstOrDefault(File.Exists);
            if (found != null)
            {
                resolved.Add(found);
            }
            else
            {
                // Search recursively
                var fileName = Path.GetFileName(relPath) + ".def";
                var matches = Directory.GetFiles(defDir, fileName, SearchOption.AllDirectories);
                if (matches.Length > 0)
                    resolved.Add(matches[0]);
                else
                    _logger.LogWarning("Could not resolve def path: {Path}", pathEntry);
            }
        }

        return resolved;
    }

    private PrebuiltMod ParseIni(string iniPath)
    {
        var lines = File.ReadAllLines(iniPath);
        string? currentSection = null;
        var title = "";
        var author = "";
        var description = "";
        var includeSecrets = false;
        var defPaths = new List<string>();

        foreach (var line in lines)
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                currentSection = trimmed[1..^1];
                continue;
            }

            if (!trimmed.Contains('=')) continue;
            var eqIdx = trimmed.IndexOf('=');
            var key = trimmed[..eqIdx].Trim();
            var value = trimmed[(eqIdx + 1)..].Trim();

            switch (currentSection?.ToLowerInvariant())
            {
                case "modinfo":
                    if (key.Equals("Title", StringComparison.OrdinalIgnoreCase)) title = value;
                    else if (key.Equals("Authors", StringComparison.OrdinalIgnoreCase)) author = value;
                    else if (key.Equals("Description", StringComparison.OrdinalIgnoreCase)) description = value;
                    break;
                case "paths":
                    if (value.Equals("true", StringComparison.OrdinalIgnoreCase))
                        defPaths.Add(key);
                    break;
                case "settings":
                    if (key.Equals("include_secrets", StringComparison.OrdinalIgnoreCase))
                        includeSecrets = value.Equals("true", StringComparison.OrdinalIgnoreCase);
                    break;
            }
        }

        return new PrebuiltMod
        {
            FilePath = iniPath,
            Name = Path.GetFileNameWithoutExtension(iniPath),
            Title = string.IsNullOrEmpty(title) ? Path.GetFileNameWithoutExtension(iniPath) : title,
            Author = author,
            Description = description,
            IncludeSecrets = includeSecrets,
            DefPaths = defPaths,
        };
    }
}
