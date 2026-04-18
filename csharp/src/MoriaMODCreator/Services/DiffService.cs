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

            // Recursively compare properties to find leaf-level changes
            ComparePropertyArrays(diffs, rowName, "", editedValues, origProps);
        }

        return diffs;
    }

    /// <summary>Generate a .def XML file from a list of diffs.</summary>
    public string GenerateDefXml(
        string title, string modFilePath, List<PropertyDiff> diffs,
        string? description = null, string? changeNote = null, bool includeComments = false)
    {
        var desc = !string.IsNullOrEmpty(description)
            ? description
            : $"{diffs.Count} modifications to {Path.GetFileName(modFilePath)}";

        var root = new XElement("definition",
            new XElement("title", title),
            new XElement("author", "Moria MOD Creator"),
            new XElement("description", desc));

        var modElem = new XElement("mod", new XAttribute("file", modFilePath));

        foreach (var diff in diffs)
        {
            XElement elem = diff.DiffType switch
            {
                DiffType.Change => new XElement("change",
                    new XAttribute("item", diff.ItemName),
                    new XAttribute("property", diff.PropertyPath),
                    new XAttribute("value", diff.NewValue)),
                DiffType.Delete => new XElement("delete",
                    new XAttribute("item", diff.ItemName),
                    new XAttribute("property", diff.PropertyPath),
                    new XAttribute("value", diff.NewValue)),
                DiffType.AddTag => new XElement("change",
                    new XAttribute("item", diff.ItemName),
                    new XAttribute("property", diff.PropertyPath),
                    new XAttribute("value", diff.NewValue)),
                _ => new XElement("change"),
            };
            if (diff.DiffType == DiffType.Change && !string.IsNullOrEmpty(diff.OriginalValue))
                elem.Add(new XAttribute("original", diff.OriginalValue));
            if (!string.IsNullOrEmpty(changeNote))
                elem.Add(new XAttribute("note", changeNote));
            if (includeComments)
                modElem.Add(new XComment($" {diff.ItemName} → {diff.PropertyPath} "));
            modElem.Add(elem);
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

    // --- Recursive deep comparison (matches Python find_differences) ---

    /// <summary>
    /// Recursively compare two property arrays, drilling into structs and arrays
    /// to find specific leaf-level scalar changes with dot-path property names.
    /// e.g., "DefaultRequiredMaterials[0].Count" with value "20" → "0"
    /// </summary>
    private void ComparePropertyArrays(
        List<PropertyDiff> diffs, string itemName, string pathPrefix,
        JsonArray editedProps, Dictionary<string, JsonNode> origProps)
    {
        foreach (var editedProp in editedProps)
        {
            var propName = editedProp?["Name"]?.GetValue<string>();
            if (propName == null) continue;

            if (!origProps.TryGetValue(propName, out var origProp))
                continue;

            var fullPath = string.IsNullOrEmpty(pathPrefix) ? propName : $"{pathPrefix}.{propName}";
            var typeStr = editedProp!["$type"]?.GetValue<string>() ?? "";

            // GameplayTagContainer — special handling
            var structType = editedProp["StructType"]?.GetValue<string>();
            if (structType == "GameplayTagContainer")
            {
                CompareTagContainers(diffs, itemName, fullPath, editedProp, origProp);
                continue;
            }

            // Quick equality check — skip if identical
            var editedJson = editedProp.ToJsonString();
            var origJson = origProp.ToJsonString();
            if (editedJson == origJson) continue;

            var editedValue = editedProp["Value"];
            var origValue = origProp["Value"];

            // ArrayPropertyData — compare element by element
            if (typeStr.Contains("ArrayPropertyData") &&
                editedValue is JsonArray editedArr && origValue is JsonArray origArr)
            {
                var maxLen = Math.Max(editedArr.Count, origArr.Count);
                for (int i = 0; i < maxLen; i++)
                {
                    if (i >= editedArr.Count || i >= origArr.Count)
                    {
                        // Array length changed
                        diffs.Add(new PropertyDiff
                        {
                            ItemName = itemName,
                            PropertyPath = $"{fullPath}[{i}]",
                            NewValue = i < editedArr.Count ? FormatValue(editedArr[i]) : "(removed)",
                            OriginalValue = i < origArr.Count ? FormatValue(origArr[i]) : "(added)",
                            DiffType = DiffType.Change,
                        });
                        continue;
                    }

                    var editedElem = editedArr[i];
                    var origElem = origArr[i];
                    if (editedElem?.ToJsonString() == origElem?.ToJsonString()) continue;

                    // If elements are struct-like (have Value array), recurse
                    if (editedElem?["Value"] is JsonArray innerEdited && origElem?["Value"] is JsonArray innerOrig)
                    {
                        var innerOrigProps = new Dictionary<string, JsonNode>();
                        foreach (var p in innerOrig)
                        {
                            var n = p?["Name"]?.GetValue<string>();
                            if (n != null) innerOrigProps[n] = p!;
                        }
                        ComparePropertyArrays(diffs, itemName, $"{fullPath}[{i}]", innerEdited, innerOrigProps);
                    }
                    else
                    {
                        // Leaf-level array element change
                        diffs.Add(new PropertyDiff
                        {
                            ItemName = itemName,
                            PropertyPath = $"{fullPath}[{i}]",
                            NewValue = FormatValue(editedElem),
                            OriginalValue = FormatValue(origElem),
                            DiffType = DiffType.Change,
                        });
                    }
                }
                continue;
            }

            // StructPropertyData — recurse into nested properties
            if (typeStr.Contains("StructPropertyData") &&
                editedValue is JsonArray editedStructProps && origValue is JsonArray origStructProps)
            {
                var innerOrigProps = new Dictionary<string, JsonNode>();
                foreach (var p in origStructProps)
                {
                    var n = p?["Name"]?.GetValue<string>();
                    if (n != null) innerOrigProps[n] = p!;
                }
                ComparePropertyArrays(diffs, itemName, fullPath, editedStructProps, innerOrigProps);
                continue;
            }

            // Scalar change — leaf level
            diffs.Add(new PropertyDiff
            {
                ItemName = itemName,
                PropertyPath = fullPath,
                NewValue = FormatValue(editedValue),
                OriginalValue = FormatValue(origValue),
                DiffType = DiffType.Change,
            });
        }
    }

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

    internal static string FormatValue(JsonNode? value)
    {
        if (value == null) return "";
        var kind = value.GetValueKind();

        // Scalar types — return directly
        if (kind is System.Text.Json.JsonValueKind.String) return value.GetValue<string>();
        if (kind is System.Text.Json.JsonValueKind.Number) return value.ToString();
        if (kind is System.Text.Json.JsonValueKind.True) return "True";
        if (kind is System.Text.Json.JsonValueKind.False) return "False";

        // UAssetAPI property object — extract the scalar Value inside
        if (value is JsonObject obj)
        {
            // SoftObjectPath: { "AssetPath": { "AssetName": "X", ... }, ... }
            var assetName = obj["AssetPath"]?["AssetName"];
            if (assetName != null && assetName.GetValueKind() == System.Text.Json.JsonValueKind.String)
                return assetName.GetValue<string>();

            // DataTableRowHandle-style: has RowName directly at top level
            if (obj["RowName"] is JsonNode rn)
                return rn.GetValueKind() == System.Text.Json.JsonValueKind.String
                    ? rn.GetValue<string>() : rn.ToString();

            var inner = obj["Value"];
            if (inner != null)
            {
                var innerKind = inner.GetValueKind();

                // Scalar Value — extract
                if (innerKind is System.Text.Json.JsonValueKind.String
                    or System.Text.Json.JsonValueKind.Number
                    or System.Text.Json.JsonValueKind.True
                    or System.Text.Json.JsonValueKind.False)
                {
                    return inner.ToString();
                }

                // Struct Value (array of inner props) — extract RowName, AssetName, or key scalars
                if (inner is JsonArray innerArr)
                {
                    // Try to find RowName first (DataTableRowHandle/ItemHandle pattern)
                    foreach (var p in innerArr)
                    {
                        var pName = p?["Name"]?.GetValue<string>();
                        if (pName == "RowName")
                            return FormatValue(p!["Value"]);
                    }

                    // Otherwise summarize scalar props as "k=v, k=v"
                    var parts = new List<string>();
                    foreach (var p in innerArr)
                    {
                        var pName = p?["Name"]?.GetValue<string>();
                        if (pName == null) continue;
                        var pVal = FormatValue(p!["Value"]);
                        if (!string.IsNullOrEmpty(pVal) && pVal.Length < 40)
                            parts.Add($"{pName}={pVal}");
                        if (parts.Count >= 4) break;
                    }
                    if (parts.Count > 0)
                        return string.Join(", ", parts);
                }

                // Nested SoftObjectPath inside Value
                if (inner is JsonObject innerObj)
                {
                    var an = innerObj["AssetPath"]?["AssetName"];
                    if (an != null && an.GetValueKind() == System.Text.Json.JsonValueKind.String)
                        return an.GetValue<string>();
                }
            }

            // CultureInvariantString (TextPropertyData)
            var cis = obj["CultureInvariantString"];
            if (cis != null && cis.GetValueKind() == System.Text.Json.JsonValueKind.String)
                return cis.GetValue<string>();
        }

        // Array — try to summarize briefly
        if (value is JsonArray arr)
        {
            if (arr.Count == 0) return "";
            if (arr.Count == 1) return FormatValue(arr[0]);
            // For small arrays of simple values, join them
            var simpleItems = new List<string>();
            foreach (var item in arr)
            {
                var s = FormatValue(item);
                if (!string.IsNullOrEmpty(s) && s.Length < 40)
                    simpleItems.Add(s);
            }
            if (simpleItems.Count > 0)
                return string.Join(", ", simpleItems.Take(10));
        }

        // Fallback — truncated JSON
        var json = value.ToJsonString();
        return json.Length > 120 ? json[..120] + "..." : json;
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
