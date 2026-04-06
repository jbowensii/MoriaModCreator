using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Handles all data operations for the Change Secrets / Change Constructions views.
/// Combines cache management, secrets loading, display name resolution, diff generation,
/// and edit manifest persistence.
/// Mirrors the private methods from Python's buildings_view.py and constructions_view.py.
/// </summary>
public class BuildingsDataService
{
    private readonly ConfigService _config;
    private readonly ObjectTemplateService _templates;
    private readonly ILogger<BuildingsDataService> _logger;

    public BuildingsDataService(ConfigService config, ObjectTemplateService templates, ILogger<BuildingsDataService> logger)
    {
        _config = config;
        _templates = templates;
        _logger = logger;
    }

    // =========================================================================
    // CACHE MANAGEMENT
    // =========================================================================

    /// <summary>Get the cache directory for a mode/prefix/category.</summary>
    public string GetCacheDir(string mode, string prefix, string category)
    {
        var baseDir = mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        return Path.Combine(baseDir, prefix, category.ToLowerInvariant());
    }

    /// <summary>
    /// Refresh the cache by copying source JSON files into the cache directory.
    /// Source is either output/jsondata (game) or Secrets Source/jsondata_full (secrets).
    /// </summary>
    public void RefreshCache(string mode, string prefix, string category, CategoryPaths paths)
    {
        var cacheDir = GetCacheDir(mode, prefix, category);
        Directory.CreateDirectory(cacheDir);

        // Copy definition JSON
        CopySourceToCache(mode, paths.DefinitionPath, cacheDir);

        // Copy recipe JSON if applicable
        if (paths.RecipePath != null)
            CopySourceToCache(mode, paths.RecipePath, cacheDir);

        // Reapply edits from manifest
        ReapplyEditsFromManifest(cacheDir);

        _logger.LogInformation("Refreshed cache for {Mode}/{Prefix}/{Category}", mode, prefix, category);
    }

    private void CopySourceToCache(string mode, string relativePath, string cacheDir)
    {
        var sourcePath = _config.FindSourceJson(mode, relativePath);
        if (sourcePath == null || !File.Exists(sourcePath)) return;

        var destPath = Path.Combine(cacheDir, Path.GetFileName(relativePath));
        File.Copy(sourcePath, destPath, true);
    }

    // FindSourceJson is shared via ConfigService.FindSourceJson

    // =========================================================================
    // EDIT MANIFEST (edits.json)
    // =========================================================================

    /// <summary>Save an edit entry to the edits.json manifest.</summary>
    public void SaveEditManifestEntry(string cacheDir, string jsonFilename, string rowName, JsonNode rowData)
    {
        var manifestPath = Path.Combine(cacheDir, "edits.json");
        var manifest = LoadManifestFile(manifestPath);

        if (!manifest.ContainsKey(jsonFilename))
            manifest[jsonFilename] = new JsonObject();

        var fileEntry = manifest[jsonFilename] as JsonObject ?? new JsonObject();
        fileEntry[rowName] = JsonNode.Parse(rowData.ToJsonString());
        manifest[jsonFilename] = fileEntry;

        SaveManifestFile(manifestPath, manifest);
    }

    /// <summary>Load the edits.json manifest.</summary>
    public JsonObject LoadEditManifest(string cacheDir)
    {
        var manifestPath = Path.Combine(cacheDir, "edits.json");
        return LoadManifestFile(manifestPath);
    }

    /// <summary>Remove an edit entry from the manifest.</summary>
    public void RemoveEditManifestEntry(string cacheDir, string jsonFilename, string rowName)
    {
        var manifestPath = Path.Combine(cacheDir, "edits.json");
        var manifest = LoadManifestFile(manifestPath);

        if (manifest[jsonFilename] is JsonObject fileEntry)
        {
            fileEntry.Remove(rowName);
            if (fileEntry.Count == 0)
                manifest.Remove(jsonFilename);
        }

        SaveManifestFile(manifestPath, manifest);
    }

    /// <summary>Reapply all edits from the manifest after a cache refresh.</summary>
    public void ReapplyEditsFromManifest(string cacheDir)
    {
        var manifest = LoadEditManifest(cacheDir);
        if (manifest.Count == 0) return;

        foreach (var (filename, fileEntryNode) in manifest)
        {
            if (fileEntryNode is not JsonObject fileEntry) continue;

            var jsonPath = Path.Combine(cacheDir, filename);
            if (!File.Exists(jsonPath)) continue;

            var root = _templates.LoadJson(jsonPath);
            if (root == null) continue;

            var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
            if (data == null) continue;

            foreach (var (rowName, savedRowNode) in fileEntry)
            {
                if (savedRowNode == null) continue;

                // Find and replace the row in the data array
                for (int i = 0; i < data.Count; i++)
                {
                    if (data[i]?["Name"]?.GetValue<string>() == rowName)
                    {
                        data[i] = JsonNode.Parse(savedRowNode.ToJsonString());
                        break;
                    }
                }
            }

            _templates.SaveJson(jsonPath, root);
        }

        _logger.LogDebug("Reapplied edits from manifest in {Dir}", cacheDir);
    }

    private static JsonObject LoadManifestFile(string path)
    {
        if (!File.Exists(path)) return new JsonObject();
        return JsonNode.Parse(File.ReadAllText(path)) as JsonObject ?? new JsonObject();
    }

    private static void SaveManifestFile(string path, JsonObject manifest)
    {
        var options = new JsonSerializerOptions { WriteIndented = true };
        File.WriteAllText(path, manifest.ToJsonString(options));
    }

    // =========================================================================
    // CHECKED ITEMS STATE (checked_items.ini)
    // =========================================================================

    /// <summary>Get the checked items INI path for a mode/prefix.</summary>
    public string GetCheckedIniPath(string mode, string prefix)
    {
        var baseDir = mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        return Path.Combine(baseDir, prefix, "checked_items.ini");
    }

    /// <summary>Load checked item states from INI.</summary>
    public Dictionary<string, bool> LoadCheckedStates(string mode, string prefix)
    {
        var iniPath = GetCheckedIniPath(mode, prefix);
        var states = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
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
            if (currentSection != null && trimmed.Contains('='))
            {
                var eqIdx = trimmed.IndexOf('=');
                var key = trimmed[..eqIdx].Trim();
                var value = trimmed[(eqIdx + 1)..].Trim();
                states[$"{currentSection}|{key}"] = value.Equals("true", StringComparison.OrdinalIgnoreCase);
            }
        }
        return states;
    }

    /// <summary>Save checked item states to INI.</summary>
    public void SaveCheckedStates(string mode, string prefix, Dictionary<string, bool> states)
    {
        var iniPath = GetCheckedIniPath(mode, prefix);
        Directory.CreateDirectory(Path.GetDirectoryName(iniPath)!);

        // Group by category (section)
        var sections = new Dictionary<string, Dictionary<string, bool>>();
        foreach (var (key, value) in states)
        {
            var parts = key.Split('|', 2);
            var section = parts.Length > 1 ? parts[0] : "General";
            var itemName = parts.Length > 1 ? parts[1] : parts[0];

            if (!sections.ContainsKey(section))
                sections[section] = new Dictionary<string, bool>();
            sections[section][itemName] = value;
        }

        using var writer = new StreamWriter(iniPath);
        foreach (var (section, items) in sections.OrderBy(kv => kv.Key))
        {
            writer.WriteLine($"[{section}]");
            foreach (var (item, isChecked) in items.OrderBy(kv => kv.Key))
                writer.WriteLine($"{item} = {(isChecked ? "true" : "false")}");
            writer.WriteLine();
        }
    }

    // =========================================================================
    // ROW DIFF COMPARISON
    // =========================================================================

    /// <summary>
    /// Compare original and cached row properties, returning changes.
    /// Handles scalar types, text, soft objects, structs, arrays, and gameplay tags.
    /// </summary>
    public List<(string Item, string Property, string Value)> DiffRowProperties(
        string rowName, JsonNode origRow, JsonNode cacheRow)
    {
        var changes = new List<(string, string, string)>();

        var origProps = BuildPropertyMap(origRow);
        var cacheProps = BuildPropertyMap(cacheRow);

        foreach (var (propName, cacheProp) in cacheProps)
        {
            if (!origProps.TryGetValue(propName, out var origProp))
                continue;

            // Quick equality check
            if (cacheProp.ToJsonString() == origProp.ToJsonString())
                continue;

            var propType = cacheProp["$type"]?.GetValue<string>() ?? "";
            var cacheVal = cacheProp["Value"];
            var origVal = origProp["Value"];

            // Scalar types
            if (propType.Contains("BoolPropertyData") || propType.Contains("IntPropertyData") ||
                propType.Contains("FloatPropertyData") || propType.Contains("EnumPropertyData") ||
                propType.Contains("NamePropertyData"))
            {
                if (cacheVal?.ToJsonString() != origVal?.ToJsonString())
                    changes.Add((rowName, propName, cacheVal?.ToString() ?? ""));
            }
            // Text property
            else if (propType.Contains("TextPropertyData"))
            {
                var origStr = origProp["Value"]?.ToString() ?? "";
                var cacheStr = cacheProp["Value"]?.ToString() ?? "";
                if (origStr != cacheStr)
                    changes.Add((rowName, propName, cacheStr));

                var origCulture = origProp["CultureInvariantString"]?.ToString() ?? "";
                var cacheCulture = cacheProp["CultureInvariantString"]?.ToString() ?? "";
                if (origCulture != cacheCulture)
                    changes.Add((rowName, $"{propName}.CultureInvariantString", cacheCulture));
            }
            // Soft object (Actor paths)
            else if (propType.Contains("SoftObjectPropertyData"))
            {
                var origPath = origProp["Value"]?["AssetPath"]?["AssetName"]?.ToString() ?? "";
                var cachePath = cacheProp["Value"]?["AssetPath"]?["AssetName"]?.ToString() ?? "";
                if (origPath != cachePath)
                    changes.Add((rowName, $"{propName}.AssetPath.AssetName", cachePath));
            }
            // Struct property
            else if (propType.Contains("StructPropertyData"))
            {
                var structType = cacheProp["StructType"]?.GetValue<string>() ?? "";
                if (structType == "GameplayTagContainer")
                {
                    var cacheTags = ExtractTagStrings(cacheProp);
                    var origTags = ExtractTagStrings(origProp);
                    if (!cacheTags.SequenceEqual(origTags))
                        changes.Add((rowName, propName, string.Join(",", cacheTags)));
                }
                else if (cacheVal is JsonArray cacheArr && origVal is JsonArray origArr)
                {
                    var inner = DiffStructProperties(rowName, propName, origArr, cacheArr);
                    changes.AddRange(inner);
                }
            }
            // Array property
            else if (propType.Contains("ArrayPropertyData"))
            {
                if (cacheVal?.ToJsonString() != origVal?.ToJsonString())
                {
                    // Simple fallback: emit the whole value
                    changes.Add((rowName, propName, cacheVal?.ToJsonString() ?? ""));
                }
            }
            // Fallback
            else if (cacheVal?.ToJsonString() != origVal?.ToJsonString())
            {
                changes.Add((rowName, propName, cacheVal?.ToString() ?? ""));
            }
        }

        return changes;
    }

    /// <summary>Diff inner struct properties with dot-path changes.</summary>
    public List<(string Item, string Property, string Value)> DiffStructProperties(
        string rowName, string parentPath, JsonArray origProps, JsonArray cacheProps)
    {
        var changes = new List<(string, string, string)>();

        var origMap = new Dictionary<string, JsonNode>();
        foreach (var p in origProps)
            if (p?["Name"]?.GetValue<string>() is string n) origMap[n] = p;

        foreach (var cacheProp in cacheProps)
        {
            var propName = cacheProp?["Name"]?.GetValue<string>();
            if (propName == null || !origMap.TryGetValue(propName, out var origProp))
                continue;

            if (cacheProp!.ToJsonString() != origProp.ToJsonString())
            {
                var cacheVal = cacheProp["Value"];
                var origVal = origProp["Value"];

                if (cacheVal is JsonArray cArr && origVal is JsonArray oArr)
                {
                    var inner = DiffStructProperties(rowName, $"{parentPath}.{propName}", oArr, cArr);
                    changes.AddRange(inner);
                }
                else
                {
                    changes.Add((rowName, $"{parentPath}.{propName}", cacheVal?.ToString() ?? ""));
                }
            }
        }

        return changes;
    }

    // =========================================================================
    // DEF FILE GENERATION
    // =========================================================================

    /// <summary>
    /// Generate a .def file from all changes in a cache directory.
    /// Compares cached JSON against source JSON and produces diff changes.
    /// </summary>
    public string GenerateDefFromCache(string mode, string prefix, string category, CategoryPaths paths)
    {
        var cacheDir = GetCacheDir(mode, prefix, category);
        var defFileName = Path.GetFileName(paths.DefinitionPath);
        var cachePath = Path.Combine(cacheDir, defFileName);
        var sourcePath = _config.FindSourceJson(mode, paths.DefinitionPath);

        if (!File.Exists(cachePath) || sourcePath == null || !File.Exists(sourcePath))
            return "";

        var cacheRoot = _templates.LoadJson(cachePath);
        var sourceRoot = _templates.LoadJson(sourcePath);
        if (cacheRoot == null || sourceRoot == null) return "";

        var allChanges = new List<(string Item, string Property, string Value)>();

        var sourceRows = BuildRowMap(sourceRoot);
        var cacheData = cacheRoot["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (cacheData == null) return "";

        foreach (var cacheRow in cacheData)
        {
            var rowName = cacheRow?["Name"]?.GetValue<string>();
            if (rowName == null) continue;

            if (sourceRows.TryGetValue(rowName, out var sourceRow))
            {
                var rowChanges = DiffRowProperties(rowName, sourceRow, cacheRow!);
                allChanges.AddRange(rowChanges);
            }
        }

        if (allChanges.Count == 0) return "";

        // Build .def XML
        var modFilePath = $"Moria/Content/{paths.DefinitionPath}";
        var root = new XElement("definition",
            new XElement("title", $"{prefix}_MODIFY {Path.GetFileNameWithoutExtension(defFileName)}"),
            new XElement("author", "Moria MOD Creator"),
            new XElement("description", $"{allChanges.Count} modifications to {defFileName}"));

        var modElem = new XElement("mod", new XAttribute("file", modFilePath));
        foreach (var (item, prop, value) in allChanges)
        {
            modElem.Add(new XElement("change",
                new XAttribute("item", item),
                new XAttribute("property", prop),
                new XAttribute("value", value)));
        }

        root.Add(modElem);
        return new XDocument(new XDeclaration("1.0", "UTF-8", null), root).ToString();
    }

    /// <summary>Save a generated .def file to the definitions directory.</summary>
    public string SaveDefFile(string mode, string prefix, string category, string defContent)
    {
        if (string.IsNullOrEmpty(defContent)) return "";

        // Determine output category dir
        var outputCategory = category switch
        {
            "Buildings" => "Building",
            "Weapons" or "Armor" or "Tools" or "Items" or "Ores" => "Items",
            "Flora" => "GameWorld",
            "Loot" => "Loot",
            _ => category,
        };

        var defDir = Path.Combine(_config.DefinitionsDir, outputCategory);
        Directory.CreateDirectory(defDir);

        var defFileName = $"{prefix}_MODIFY DT_{category}.def";
        var defPath = Path.Combine(defDir, defFileName);
        File.WriteAllText(defPath, defContent);

        _logger.LogInformation("Saved .def file: {Path}", defPath);
        return defPath;
    }

    // =========================================================================
    // DISPLAY NAME RESOLUTION
    // =========================================================================

    /// <summary>
    /// Resolve display names for items by reading string table JSON files
    /// and definition table display name properties.
    /// </summary>
    public Dictionary<string, string> ResolveDisplayNames(string mode)
    {
        var names = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);

        // Load from string tables (cache/secrets/string_tables/)
        var stringTablesDir = Path.Combine(_config.CacheDir, "secrets", "string_tables");
        if (Directory.Exists(stringTablesDir))
        {
            foreach (var tableFile in Directory.GetFiles(stringTablesDir, "*.json"))
            {
                LoadStringTableEntries(tableFile, names);
            }
        }

        // Load from game string tables
        var gameStringTablesDir = Path.Combine(_config.CacheDir, "game", "string_tables");
        if (Directory.Exists(gameStringTablesDir))
        {
            foreach (var tableFile in Directory.GetFiles(gameStringTablesDir, "*.json"))
            {
                LoadStringTableEntries(tableFile, names);
            }
        }

        // Resolve from definition tables
        ResolveFromDefinitionTables(mode, names);

        return names;
    }

    private void LoadStringTableEntries(string tablePath, Dictionary<string, string> names)
    {
        try
        {
            var root = _templates.LoadJson(tablePath);
            if (root == null) return;

            var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
            if (data == null) return;

            foreach (var row in data)
            {
                var key = row?["Name"]?.GetValue<string>();
                var valueArr = row?["Value"] as JsonArray;
                if (key == null || valueArr == null) continue;

                foreach (var prop in valueArr)
                {
                    if (prop?["Name"]?.GetValue<string>() == "SourceString")
                    {
                        var displayName = prop["Value"]?.GetValue<string>();
                        if (!string.IsNullOrEmpty(displayName))
                            names.TryAdd(key, displayName);
                    }
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to load string table: {Path}", tablePath);
        }
    }

    private void ResolveFromDefinitionTables(string mode, Dictionary<string, string> names)
    {
        // Check common definition tables for DisplayName properties
        var tablePaths = new[]
        {
            "Tech/Data/Building/DT_Constructions.json",
            "Tech/Data/Items/DT_Weapons.json",
            "Tech/Data/Items/DT_Armor.json",
            "Tech/Data/Items/DT_Tools.json",
            "Tech/Data/Items/DT_Items.json",
            "Tech/Data/Items/DT_Ores.json",
            "Tech/Data/GameWorld/DT_Moria_Flora.json",
        };

        foreach (var relPath in tablePaths)
        {
            var fullPath = _config.FindSourceJson(mode, relPath);
            if (fullPath == null || !File.Exists(fullPath)) continue;

            var root = _templates.LoadJson(fullPath);
            if (root == null) continue;

            var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
            if (data == null) continue;

            foreach (var row in data)
            {
                var rowName = row?["Name"]?.GetValue<string>();
                if (rowName == null || names.ContainsKey(rowName)) continue;

                var valueArr = row?["Value"] as JsonArray;
                if (valueArr == null) continue;

                foreach (var prop in valueArr)
                {
                    var propName = prop?["Name"]?.GetValue<string>();
                    if (propName == "DisplayName" || propName == "RowDisplayName")
                    {
                        var val = prop?["Value"]?.ToString();
                        if (!string.IsNullOrEmpty(val) && val != "None")
                        {
                            names.TryAdd(rowName, val);
                            break;
                        }
                    }
                }
            }
        }
    }

    // =========================================================================
    // HELPERS
    // =========================================================================

    private static Dictionary<string, JsonNode> BuildPropertyMap(JsonNode row)
    {
        var map = new Dictionary<string, JsonNode>();
        if (row["Value"] is JsonArray arr)
        {
            foreach (var prop in arr)
            {
                var name = prop?["Name"]?.GetValue<string>();
                if (name != null) map[name] = prop!;
            }
        }
        return map;
    }

    private static Dictionary<string, JsonNode> BuildRowMap(JsonNode root)
    {
        var map = new Dictionary<string, JsonNode>();
        var data = root["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (data == null) return map;
        foreach (var row in data)
        {
            var name = row?["Name"]?.GetValue<string>();
            if (name != null) map[name] = row!;
        }
        return map;
    }

    private static List<string> ExtractTagStrings(JsonNode tagContainer)
    {
        var tags = new List<string>();
        var inner = tagContainer["Value"] as JsonArray;
        if (inner == null) return tags;
        foreach (var item in inner)
        {
            if (item?["Value"] is JsonArray tagArr)
            {
                foreach (var tag in tagArr)
                {
                    var val = tag?.GetValue<string>();
                    if (val != null) tags.Add(val);
                }
            }
        }
        return tags;
    }
}
