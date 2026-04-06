using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Advanced mode — definition file tree with tri-state checkboxes and build.
/// </summary>
public partial class DefinitionsViewModel : ObservableObject
{
    private readonly ConfigService _config;
    private readonly BuildService _buildService;

    [ObservableProperty] private string _currentPath = "";
    [ObservableProperty] private string _modName = "";
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private string _buildStatus = "";
    [ObservableProperty] private double _buildProgress;
    [ObservableProperty] private DefinitionEntry? _selectedEntry;
    [ObservableProperty] private string _selectedTitle = "";
    [ObservableProperty] private string _selectedAuthor = "";
    [ObservableProperty] private string _selectedDescription = "";
    [ObservableProperty] private string _selectedChanges = "Select a .def file to view its changes.";

    public ObservableCollection<DefinitionEntry> Entries { get; } = [];

    public DefinitionsViewModel(ConfigService config, BuildService buildService)
    {
        _config = config;
        _buildService = buildService;
        CurrentPath = config.DefinitionsDir;
        RefreshList();
    }

    [RelayCommand]
    private void ChooseModName()
    {
        var dialog = new Views.Dialogs.ModNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow
        };
        if (dialog.ShowDialog() == true && dialog.SelectedModName != null)
        {
            ModName = dialog.SelectedModName;
            BuildStatus = $"Mod '{ModName}' selected";
        }
    }

    [RelayCommand]
    private void RefreshList()
    {
        Entries.Clear();
        if (!Directory.Exists(CurrentPath)) return;

        // Add ".." for navigation if not at root
        if (CurrentPath != _config.DefinitionsDir)
            Entries.Add(new DefinitionEntry { Name = "..", IsDirectory = true, FullPath = Path.GetDirectoryName(CurrentPath)! });

        foreach (var dir in Directory.GetDirectories(CurrentPath).OrderBy(d => d))
            Entries.Add(new DefinitionEntry
            {
                Name = Path.GetFileName(dir),
                IsDirectory = true,
                FullPath = dir,
            });

        foreach (var file in Directory.GetFiles(CurrentPath, "*.def").OrderBy(f => f))
            Entries.Add(new DefinitionEntry
            {
                Name = Path.GetFileNameWithoutExtension(file),
                IsDirectory = false,
                FullPath = file,
            });
    }

    /// <summary>Handle a click on a definition entry — navigate dirs, select files.</summary>
    [RelayCommand]
    private void ClickEntry(DefinitionEntry entry)
    {
        if (entry.IsDirectory)
        {
            CurrentPath = entry.FullPath;
            RefreshList();
        }
        else
        {
            SelectEntry(entry);
        }
    }

    [RelayCommand]
    private void SelectEntry(DefinitionEntry? entry)
    {
        SelectedEntry = entry;
        if (entry == null || entry.IsDirectory)
        {
            SelectedTitle = "";
            SelectedAuthor = "";
            SelectedDescription = "";
            SelectedChanges = "Select a .def file to view its changes.";
            return;
        }

        // Parse the .def file to show its details in the right pane
        try
        {
            var defService = App.Services.GetRequiredService<DefinitionService>();
            var def = defService.Parse(entry.FullPath);
            SelectedTitle = def.Title;
            SelectedAuthor = string.IsNullOrEmpty(def.Author) ? "" : $"by {def.Author}";
            SelectedDescription = def.Description;

            // Build changes summary
            var lines = new List<string>();
            foreach (var modFile in def.ModFiles)
            {
                lines.Add($"File: {Path.GetFileName(modFile.FilePath)}");
                foreach (var change in modFile.Changes)
                    lines.Add($"  CHANGE: {change.Item}.{change.Property} = {change.Value}");
                foreach (var del in modFile.Deletes)
                    lines.Add($"  DELETE: {del.Item}.{del.Property} = {del.Value}");
            }
            SelectedChanges = lines.Count > 0
                ? string.Join("\n", lines)
                : "No changes defined.";
        }
        catch (Exception ex)
        {
            SelectedTitle = entry.Name;
            SelectedChanges = $"Error reading .def file: {ex.Message}";
        }
    }

    [RelayCommand(CanExecute = nameof(CanBuild))]
    private async Task BuildAsync()
    {
        IsBuilding = true;
        var checkedDefs = GetCheckedDefFiles();

        var progress = new Progress<BuildProgress>(p =>
        {
            BuildStatus = p.Status;
            BuildProgress = p.Progress;
        });

        var result = await _buildService.BuildAsync(ModName, checkedDefs, false, progress);
        BuildStatus = result.Success ? $"Build complete! {result.Message}" : $"Build failed: {result.Message}";
        IsBuilding = false;
    }

    private bool CanBuild() => !IsBuilding && !string.IsNullOrWhiteSpace(ModName);

    private List<string> GetCheckedDefFiles()
    {
        return Entries.Where(e => !e.IsDirectory && e.IsChecked)
                      .Select(e => e.FullPath).ToList();
    }

    partial void OnModNameChanged(string value) => BuildCommand.NotifyCanExecuteChanged();
    partial void OnIsBuildingChanged(bool value) => BuildCommand.NotifyCanExecuteChanged();
}

public partial class DefinitionEntry : ObservableObject
{
    [ObservableProperty] private bool _isChecked;
    public string Name { get; init; } = "";
    public string FullPath { get; init; } = "";
    public bool IsDirectory { get; init; }
}
