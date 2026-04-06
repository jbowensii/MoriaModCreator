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
}

/// <summary>
/// A <change> element: modify a property value on a DataTable row.
/// </summary>
public class ModChange
{
    public string Item { get; init; } = "";
    public string Property { get; init; } = "";
    public string Value { get; init; } = "";
    public string? Original { get; init; }
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
