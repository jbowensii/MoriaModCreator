namespace MoriaMODCreator.Models;

/// <summary>
/// Represents a parsed .def XML file with its modification rules.
/// </summary>
public class ModDefinition
{
    public string FilePath { get; init; } = "";
    public string Title { get; init; } = "";
    public string Author { get; init; } = "";
    public string Description { get; init; } = "";
    public List<ModFile> ModFiles { get; init; } = [];
}

/// <summary>
/// A single <mod file="..."> block within a .def file.
/// </summary>
public class ModFile
{
    public string FilePath { get; init; } = "";
    public List<ModChange> Changes { get; init; } = [];
    public List<ModDelete> Deletes { get; init; } = [];
    public List<ModAddProperty> AddProperties { get; init; } = [];
}

/// <summary>
/// An &lt;add_property&gt; element nested inside a &lt;change&gt; element.
/// Adds a new property to a DataTable row before the parent change applies.
/// Python schema: the text content is JSON with keys Name, DefaultValue, Type.
/// </summary>
public class ModAddProperty
{
    public string Item { get; init; } = "";
    /// <summary>The 'Name' field from the JSON content (property name in the DataTable).</summary>
    public string PropertyName { get; init; } = "";
    /// <summary>The 'Type' field from the JSON content (UAsset property type, e.g. IntPropertyData).</summary>
    public string PropertyType { get; init; } = "";
    /// <summary>The 'DefaultValue' field from the JSON content, as a string.</summary>
    public string DefaultValue { get; init; } = "";
    /// <summary>The raw JSON text content of the element.</summary>
    public string JsonContent { get; init; } = "";
}

/// <summary>
/// A &lt;change&gt; element: modify a property value on a DataTable row.
/// May optionally contain a nested &lt;add_property&gt; child (Python schema).
/// </summary>
public class ModChange
{
    public string Item { get; init; } = "";
    public string Property { get; init; } = "";
    public string Value { get; init; } = "";
    public string? Original { get; init; }
    /// <summary>Optional nested &lt;add_property&gt; child element.</summary>
    public ModAddProperty? AddProperty { get; init; }
}

/// <summary>
/// A <delete> element: remove a gameplay tag from a row.
/// </summary>
public class ModDelete
{
    public string Item { get; init; } = "";
    public string Property { get; init; } = "";
    public string Value { get; init; } = "";
}
