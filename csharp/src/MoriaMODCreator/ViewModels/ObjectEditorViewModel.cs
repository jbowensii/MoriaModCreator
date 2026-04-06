using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Object Editor tab: create/edit construction objects with property editing.
/// </summary>
public partial class ObjectEditorViewModel : ObservableObject
{
    private readonly ConfigService _config;
    private readonly ObjectTemplateService _templates;
    private readonly CategoryDataService _categoryData;

    [ObservableProperty] private string _status = "";
    [ObservableProperty] private string? _selectedBuilding;
    [ObservableProperty] private string _searchText = "";

    public ObservableCollection<string> Buildings { get; } = [];
    public ObservableCollection<FieldEntry> Properties { get; } = [];

    public ObjectEditorViewModel(ConfigService config, ObjectTemplateService templates, CategoryDataService categoryData)
    {
        _config = config;
        _templates = templates;
        _categoryData = categoryData;
        LoadBuildings();
    }

    [RelayCommand]
    private void LoadBuildings()
    {
        Buildings.Clear();

        // Load from New Secrets jsondata
        var jsonDir = _config.NewSecretsJsonDataDir;
        if (!Directory.Exists(jsonDir)) return;

        // Look for construction-related JSON files
        var dtConstructions = Path.Combine(jsonDir, "Moria", "Content", "Tech", "Data", "Building", "DT_Constructions.json");
        if (!File.Exists(dtConstructions)) return;

        var root = _templates.LoadJson(dtConstructions);
        if (root == null) return;

        var names = _templates.GetRowNames(root);
        foreach (var name in names.OrderBy(n => n))
        {
            if (string.IsNullOrEmpty(SearchText) ||
                name.Contains(SearchText, StringComparison.OrdinalIgnoreCase))
            {
                Buildings.Add(name);
            }
        }

        Status = $"Loaded {Buildings.Count} buildings";
    }

    [RelayCommand]
    private void SelectBuilding(string? buildingName)
    {
        SelectedBuilding = buildingName;
        Properties.Clear();

        if (buildingName == null) return;

        var jsonDir = _config.NewSecretsJsonDataDir;
        var dtPath = Path.Combine(jsonDir, "Moria", "Content", "Tech", "Data", "Building", "DT_Constructions.json");
        if (!File.Exists(dtPath)) return;

        var root = _templates.LoadJson(dtPath);
        if (root == null) return;

        var row = _templates.GetRowByName(root, buildingName);
        if (row == null) return;

        var fields = _templates.ExtractConstructionFields(row);
        foreach (var (name, value) in fields)
        {
            Properties.Add(new FieldEntry
            {
                Name = name,
                Value = value?.ToString() ?? "",
                OriginalValue = value?.ToString() ?? "",
            });
        }

        Status = $"Loaded {Properties.Count} properties for {buildingName}";
    }

    [RelayCommand]
    private void SaveProperties()
    {
        if (SelectedBuilding == null) return;

        var jsonDir = _config.NewSecretsJsonDataDir;
        var dtPath = Path.Combine(jsonDir, "Moria", "Content", "Tech", "Data", "Building", "DT_Constructions.json");
        if (!File.Exists(dtPath)) return;

        var root = _templates.LoadJson(dtPath);
        if (root == null) return;

        var row = _templates.GetRowByName(root, SelectedBuilding);
        if (row == null) return;

        int changes = 0;
        foreach (var field in Properties)
        {
            if (field.Value != field.OriginalValue)
            {
                _templates.SetRowProperty(row, field.Name, JsonValue.Create(field.Value)!);
                changes++;
            }
        }

        if (changes > 0)
        {
            _templates.SaveJson(dtPath, root);
            Status = $"Saved {changes} change(s) to {SelectedBuilding}";
        }
        else
        {
            Status = "No changes to save";
        }
    }

    partial void OnSearchTextChanged(string value) => LoadBuildings();
}
