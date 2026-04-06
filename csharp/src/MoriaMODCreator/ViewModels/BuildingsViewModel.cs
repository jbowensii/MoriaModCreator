using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Shared view model for Change Secrets and Change Constructions tabs.
/// Manages category buttons, item list, right-pane editing, and build.
/// </summary>
public partial class BuildingsViewModel : ObservableObject
{
    private readonly ConfigService _config;
    private readonly string _mode; // "secrets" or "constructions"

    [ObservableProperty] private string _prefix = "";
    [ObservableProperty] private string _selectedCategory = "";
    [ObservableProperty] private string? _selectedItem;
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private string _buildStatus = "";
    [ObservableProperty] private double _buildProgress;

    public ObservableCollection<string> Categories { get; } = [];
    public ObservableCollection<ItemEntry> Items { get; } = [];
    public ObservableCollection<PropertyField> Fields { get; } = [];

    public string ModeLabel { get; }

    public BuildingsViewModel(ConfigService config, string mode)
    {
        _config = config;
        _mode = mode;
        ModeLabel = mode == "secrets" ? "Change Secrets" : "Change Constructions";

        // Standard categories
        foreach (var cat in new[] { "Buildings", "Weapons", "Armor", "Tools", "Flora", "Loot", "Items", "Ores" })
            Categories.Add(cat);
    }

    [RelayCommand]
    private void SelectCategory(string category)
    {
        SelectedCategory = category;
        Items.Clear();
        Fields.Clear();
        // TODO: Load items for selected category from cached JSON
        BuildStatus = $"Selected category: {category}";
    }

    [RelayCommand]
    private void SelectItem(ItemEntry? item)
    {
        SelectedItem = item?.Name;
        Fields.Clear();
        if (item == null) return;
        // TODO: Load fields for selected item from JSON
    }

    [RelayCommand]
    private void SaveItem()
    {
        // TODO: Save edited fields back to JSON and edits.json manifest
        BuildStatus = "Item saved";
    }

    [RelayCommand]
    private async Task BuildAsync()
    {
        IsBuilding = true;
        BuildStatus = "Building...";
        // TODO: Build from change set
        await Task.Delay(100);
        BuildStatus = "Build not yet implemented for change sets";
        IsBuilding = false;
    }
}

public partial class ItemEntry : ObservableObject
{
    [ObservableProperty] private bool _isChecked;
    public string Name { get; init; } = "";
    public string DisplayName { get; init; } = "";
}

public partial class PropertyField : ObservableObject
{
    [ObservableProperty] private string _value = "";
    public string Name { get; init; } = "";
    public string OriginalValue { get; init; } = "";
    public string FieldType { get; init; } = "text"; // text, dropdown, checkbox
    public List<string> Options { get; init; } = [];
}
