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
    private readonly CategoryDataService _categoryData;
    private readonly DiffService _diffService;
    private readonly string _mode;

    [ObservableProperty] private string _prefix = "";
    [ObservableProperty] private string _selectedCategory = "";
    [ObservableProperty] private CategoryItem? _selectedItem;
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private string _buildStatus = "";
    [ObservableProperty] private double _buildProgress;

    public ObservableCollection<string> Categories { get; } = [];
    public ObservableCollection<CategoryItem> Items { get; } = [];
    public ObservableCollection<FieldEntry> Fields { get; } = [];

    public string ModeLabel { get; }

    public BuildingsViewModel(ConfigService config, CategoryDataService categoryData, DiffService diffService, string mode)
    {
        _config = config;
        _categoryData = categoryData;
        _diffService = diffService;
        _mode = mode;
        ModeLabel = mode == "secrets" ? "Change Secrets" : "Change Constructions";

        foreach (var cat in new[] { "Buildings", "Weapons", "Armor", "Tools", "Flora", "Loot", "Items", "Ores" })
            Categories.Add(cat);
    }

    [RelayCommand]
    private void SelectCategory(string category)
    {
        SelectedCategory = category;
        Items.Clear();
        Fields.Clear();
        SelectedItem = null;

        if (string.IsNullOrWhiteSpace(Prefix))
        {
            BuildStatus = "Enter a prefix/change set name first, then select a category.";
            return;
        }

        try
        {
            var items = _categoryData.LoadCategoryItems(_mode, category, Prefix);
            foreach (var item in items)
                Items.Add(item);

            BuildStatus = items.Count > 0
                ? $"{category}: {items.Count} items loaded"
                : $"{category}: No items found. Try running Import first.";
        }
        catch (Exception ex)
        {
            BuildStatus = $"Error loading {category}: {ex.Message}";
        }
    }

    [RelayCommand]
    private void SelectItem(CategoryItem? item)
    {
        SelectedItem = item;
        Fields.Clear();
        if (item == null) return;

        foreach (var (name, value) in item.Fields)
        {
            var strValue = value?.ToString() ?? "";
            Fields.Add(new FieldEntry
            {
                Name = name,
                Value = strValue,
                OriginalValue = strValue,
            });
        }
    }

    [RelayCommand]
    private void SaveItem()
    {
        if (SelectedItem == null) return;

        var editedFields = new Dictionary<string, object?>();
        foreach (var field in Fields)
        {
            if (field.Value != field.OriginalValue)
                editedFields[field.Name] = field.Value;
        }

        if (editedFields.Count == 0)
        {
            BuildStatus = "No changes to save";
            return;
        }

        _categoryData.SaveItemEdits(SelectedItem, editedFields);
        BuildStatus = $"Saved {editedFields.Count} change(s) to {SelectedItem.RowName}";
    }

    [RelayCommand]
    private async Task BuildAsync()
    {
        if (string.IsNullOrWhiteSpace(Prefix))
        {
            BuildStatus = "Enter a prefix name first";
            return;
        }

        IsBuilding = true;
        BuildStatus = "Building change set...";

        await Task.Run(() =>
        {
            // TODO: Generate .def files from diffs and trigger build
            BuildStatus = "Build for change sets — implementation in progress";
        });

        IsBuilding = false;
    }

    [RelayCommand]
    private void RefreshCache()
    {
        if (!string.IsNullOrWhiteSpace(SelectedCategory))
            SelectCategory(SelectedCategory);
    }
}

public partial class FieldEntry : ObservableObject
{
    [ObservableProperty] private string _value = "";
    public string Name { get; init; } = "";
    public string OriginalValue { get; init; } = "";
}
