using System.IO;
using System.Xml.Linq;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.Services;

/// <summary>
/// Parses .def XML files into ModDefinition models.
/// Mirrors the Python definition_manager.py and build_manager.py XML parsing.
/// </summary>
public class DefinitionService
{
    private readonly ILogger<DefinitionService> _logger;

    public DefinitionService(ILogger<DefinitionService> logger)
    {
        _logger = logger;
    }

    /// <summary>Parse a .def XML file into a ModDefinition.</summary>
    public ModDefinition Parse(string defFilePath)
    {
        var doc = XDocument.Load(defFilePath);
        var root = doc.Root;
        if (root == null)
            throw new InvalidDataException($"Empty .def file: {defFilePath}");

        var definition = new ModDefinition
        {
            FilePath = defFilePath,
            Title = root.Element("title")?.Value ?? Path.GetFileNameWithoutExtension(defFilePath),
            Author = root.Element("author")?.Value ?? "",
            Description = root.Element("description")?.Value ?? "",
            ModFiles = ParseModFiles(root).ToList(),
        };

        _logger.LogDebug("Parsed {Path}: {Title} with {Count} mod file(s)",
            defFilePath, definition.Title, definition.ModFiles.Count);
        return definition;
    }

    /// <summary>Check if a .def file references Secrets Source paths.</summary>
    public bool ReferencesSecrets(ModDefinition def)
    {
        return def.ModFiles.Any(mf =>
            mf.FilePath.Contains("Secrets Source", StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Normalize a file path from a .def's <mod file="..."> attribute.
    /// Strips "Secrets Source/" and "jsondata/" prefixes.
    /// </summary>
    public static string NormalizePath(string modFilePath)
    {
        var path = modFilePath.Replace('\\', '/');

        // Strip Secrets Source prefix
        var ssIdx = path.IndexOf("Secrets Source/", StringComparison.OrdinalIgnoreCase);
        if (ssIdx >= 0)
        {
            path = path[(ssIdx + "Secrets Source/".Length)..];
            // Also strip jsondata/ if present
            if (path.StartsWith("jsondata/", StringComparison.OrdinalIgnoreCase))
                path = path["jsondata/".Length..];
        }

        // Strip leading slashes
        return path.TrimStart('/');
    }

    private static IEnumerable<ModFile> ParseModFiles(XElement root)
    {
        foreach (var modElem in root.Elements("mod"))
        {
            var filePath = modElem.Attribute("file")?.Value ?? "";
            var changes = new List<ModChange>();
            var deletes = new List<ModDelete>();
            var addProps = new List<ModAddProperty>();

            foreach (var changeElem in modElem.Elements("change"))
            {
                // Python schema: <add_property> is a child of <change>, not a sibling of it.
                // The JSON text content has keys: Name, DefaultValue, Type.
                ModAddProperty? addProp = null;
                var addPropElem = changeElem.Element("add_property");
                if (addPropElem != null)
                {
                    var jsonText = addPropElem.Value.Trim();
                    var item = addPropElem.Attribute("item")?.Value
                               ?? changeElem.Attribute("item")?.Value
                               ?? "";

                    // Parse the JSON to extract Name, DefaultValue, Type fields.
                    string propName = "", propDefaultValue = "", propType = "";
                    try
                    {
                        var parsed = System.Text.Json.JsonDocument.Parse(jsonText);
                        propName = parsed.RootElement.TryGetProperty("Name", out var n) ? n.GetString() ?? "" : "";
                        propType = parsed.RootElement.TryGetProperty("Type", out var t) ? t.GetString() ?? "" : "";
                        // DefaultValue may be any JSON type (number, string, bool)
                        propDefaultValue = parsed.RootElement.TryGetProperty("DefaultValue", out var dv)
                            ? dv.ToString()
                            : "";
                    }
                    catch
                    {
                        // Malformed JSON — fall back to empty fields; raw JSON stored in JsonContent.
                    }

                    addProp = new ModAddProperty
                    {
                        Item = item,
                        PropertyName = propName,
                        PropertyType = propType,
                        DefaultValue = propDefaultValue,
                        JsonContent = jsonText,
                    };
                    addProps.Add(addProp);
                }

                changes.Add(new ModChange
                {
                    Item = changeElem.Attribute("item")?.Value ?? "",
                    Property = changeElem.Attribute("property")?.Value ?? "",
                    Value = changeElem.Attribute("value")?.Value ?? "",
                    Original = changeElem.Attribute("original")?.Value,
                    AddProperty = addProp,
                });
            }

            foreach (var deleteElem in modElem.Elements("delete"))
            {
                deletes.Add(new ModDelete
                {
                    Item = deleteElem.Attribute("item")?.Value ?? "",
                    Property = deleteElem.Attribute("property")?.Value ?? "",
                    Value = deleteElem.Attribute("value")?.Value ?? "",
                });
            }

            yield return new ModFile
            {
                FilePath = filePath,
                Changes = changes,
                Deletes = deletes,
                AddProperties = addProps,
            };
        }
    }
}
