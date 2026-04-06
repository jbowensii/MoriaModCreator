using System.IO;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;

namespace MoriaMODCreator.Services;

/// <summary>
/// Generates .def XML files by comparing edited JSON DataTables against originals.
/// Used by Change Secrets / Change Constructions to produce mod definitions.
/// </summary>
public class DiffService
{
    private readonly ObjectTemplateService _templates;
    private readonly ILogger<DiffService> _logger;

    public DiffService(ObjectTemplateService templates, ILogger<DiffService> logger)
    {
        _templates = templates;
        _logger = logger;
    }

    /// <summary>
    /// Compare two JSON DataTable files and generate a list of differences.
    /// </summary>
    public List<PropertyDiff> FindDifferences(string editedPath, string originalPath)
    {
        var diffs = new List<PropertyDiff>();

        var editedRoot = _templates.LoadJson(editedPath);
        var originalRoot = _templates.LoadJson(originalPath);
        if (editedRoot == null || originalRoot == null) return diffs;

        var editedData = editedRoot["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        var originalData = originalRoot["Exports"]?[0]?["Table"]?["Data"] as JsonArray;
        if (editedData == null || originalData == null) return diffs;

        // Build lookup for original rows
        var originalRows = new Dictionary<string, JsonNode>();
        foreach (var row in originalData)
        {
            var name = row?["Name"]?.GetValue<string>();
            if (name != null) originalRows[name] = row!;
        }

        // Compare each edited row against its original
        foreach (var editedRow in editedData)
        {
            var rowName = editedRow?["Name"]?.GetValue<string>();
            if (rowName == null) continue;

            if (!originalRows.TryGetValue(rowName, out var originalRow))
                continue; // New row — not handled as a diff

            var editedValues = editedRow!["Value"] as JsonArray;
            var originalValues = originalRow["Value"] as JsonArray;
            if (editedValues == null || originalValues == null) continue;

            // Build lookup for original properties
            var origProps = new Dictionary<string, JsonNode>();
            foreach (var prop in originalValues)
            {
                var pName = prop?["Name"]?.GetValue<string>();
                if (pName != null) origProps[pName] = prop!;
            }

            // Compare properties
            foreach (var editedProp in editedValues)
            {
                var propName = editedProp?["Name"]?.GetValue<string>();
                if (propName == null) continue;

                if (!origProps.TryGetValue(propName, out var origProp))
                    continue;

                // Check if it's a GameplayTagContainer
                var structType = editedProp!["StructType"]?.GetValue<string>();
                if (structType == "GameplayTagContainer")
                {
                    CompareTagContainers(diffs, rowName, propName, editedProp, origProp);
                    continue;
                }

                // Compare values
                var editedVal = editedProp["Value"]?.ToJsonString();
                var origVal = origProp["Value"]?.ToJsonString();

                if (editedVal != origVal)
                {
                    diffs.Add(new PropertyDiff
                    {
                        ItemName = rowName,
                        PropertyPath = propName,
                        NewValue = FormatValue(editedProp["Value"]),
                        OriginalValue = FormatValue(origProp["Value"]),
                        DiffType = DiffType.Change,
                    });
                }
            }
        }

        return diffs;
    }

    /// <summary>Generate a .def XML file from a list of diffs.</summary>
    public string GenerateDefXml(
        string title, string modFilePath, List<PropertyDiff> diffs)
    {
        var root = new XElement("definition",
            new XElement("title", title),
            new XElement("author", "Moria MOD Creator"),
            new XElement("description", $"{diffs.Count} modifications to {Path.GetFileName(modFilePath)}"));

        var modElem = new XElement("mod", new XAttribute("file", modFilePath));

        foreach (var diff in diffs)
        {
            switch (diff.DiffType)
            {
                case DiffType.Change:
                    var changeElem = new XElement("change",
                        new XAttribute("item", diff.ItemName),
                        new XAttribute("property", diff.PropertyPath),
                        new XAttribute("value", diff.NewValue));
                    if (!string.IsNullOrEmpty(diff.OriginalValue))
                        changeElem.Add(new XAttribute("original", diff.OriginalValue));
                    modElem.Add(changeElem);
                    break;

                case DiffType.Delete:
                    modElem.Add(new XElement("delete",
                        new XAttribute("item", diff.ItemName),
                        new XAttribute("property", diff.PropertyPath),
                        new XAttribute("value", diff.NewValue)));
                    break;

                case DiffType.AddTag:
                    modElem.Add(new XElement("change",
                        new XAttribute("item", diff.ItemName),
                        new XAttribute("property", diff.PropertyPath),
                        new XAttribute("value", diff.NewValue)));
                    break;
            }
        }

        root.Add(modElem);
        var doc = new XDocument(new XDeclaration("1.0", "UTF-8", null), root);
        return doc.ToString();
    }

    /// <summary>Generate a prebuilt .ini file for a set of .def files.</summary>
    public string GenerateIniContent(string title, string author, List<string> defRelPaths, bool includeSecrets)
    {
        var lines = new List<string>
        {
            "[ModInfo]",
            $"Title = {title}",
            $"Authors = {author}",
            $"Description = {defRelPaths.Count} definition file(s)",
            "",
            "[Paths]",
        };

        foreach (var defPath in defRelPaths)
        {
            var key = defPath.Replace('\\', '|').Replace('/', '|');
            if (key.EndsWith(".def", StringComparison.OrdinalIgnoreCase))
                key = key[..^4];
            lines.Add($"{key} = true");
        }

        lines.Add("");
        lines.Add("[Settings]");
        lines.Add($"include_secrets = {(includeSecrets ? "True" : "False")}");

        return string.Join(Environment.NewLine, lines);
    }

    // --- Private helpers ---

    private void CompareTagContainers(
        List<PropertyDiff> diffs, string rowName, string propName,
        JsonNode editedProp, JsonNode origProp)
    {
        var editedTags = _templates.ExtractTagNames(editedProp);
        var origTags = _templates.ExtractTagNames(origProp);

        var editedSet = new HashSet<string>(editedTags);
        var origSet = new HashSet<string>(origTags);

        // Tags added
        foreach (var tag in editedSet.Except(origSet))
        {
            diffs.Add(new PropertyDiff
            {
                ItemName = rowName,
                PropertyPath = "Tags",
                NewValue = tag,
                DiffType = DiffType.AddTag,
            });
        }

        // Tags removed
        foreach (var tag in origSet.Except(editedSet))
        {
            diffs.Add(new PropertyDiff
            {
                ItemName = rowName,
                PropertyPath = "Tags",
                NewValue = tag,
                DiffType = DiffType.Delete,
            });
        }
    }

    private static string FormatValue(JsonNode? value)
    {
        if (value == null) return "";
        return value.GetValueKind() switch
        {
            System.Text.Json.JsonValueKind.String => value.GetValue<string>(),
            System.Text.Json.JsonValueKind.Number => value.ToString(),
            System.Text.Json.JsonValueKind.True => "True",
            System.Text.Json.JsonValueKind.False => "False",
            _ => value.ToJsonString(),
        };
    }
}

public class PropertyDiff
{
    public string ItemName { get; init; } = "";
    public string PropertyPath { get; init; } = "";
    public string NewValue { get; init; } = "";
    public string? OriginalValue { get; init; }
    public DiffType DiffType { get; init; }
}

public enum DiffType
{
    Change,
    Delete,
    AddTag,
}
