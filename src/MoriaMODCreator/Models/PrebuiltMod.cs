using CommunityToolkit.Mvvm.ComponentModel;

namespace MoriaMODCreator.Models;

/// <summary>
/// Represents a prebuilt mod .ini file for Novice mode.
/// </summary>
public partial class PrebuiltMod : ObservableObject
{
    public string FilePath { get; init; } = "";
    public string Name { get; init; } = "";
    public string Title { get; init; } = "";
    public string Author { get; init; } = "";
    public string Description { get; init; } = "";
    public bool IncludeSecrets { get; init; }
    public List<string> DefPaths { get; init; } = [];

    [ObservableProperty]
    private bool _isChecked;
}
