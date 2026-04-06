using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

public partial class NoviceViewModel : ObservableObject
{
    private readonly PrebuiltModService _modService;
    private readonly BuildService _buildService;
    private readonly ConfigService _config;

    [ObservableProperty] private string _modName = "";
    [ObservableProperty] private bool _isBuilding;
    [ObservableProperty] private string _buildStatus = "";
    [ObservableProperty] private double _buildProgress;
    [ObservableProperty] private PrebuiltMod? _selectedMod;
    [ObservableProperty] private string _selectedModTitle = "";
    [ObservableProperty] private string _selectedModAuthor = "";
    [ObservableProperty] private string _selectedModDescription = "Select a mod from the list to see its details.";

    public ObservableCollection<PrebuiltMod> Mods { get; } = [];

    public NoviceViewModel(PrebuiltModService modService, BuildService buildService, ConfigService config)
    {
        _modService = modService;
        _buildService = buildService;
        _config = config;
        LoadMods();
    }

    [RelayCommand]
    private void LoadMods()
    {
        Mods.Clear();
        foreach (var mod in _modService.LoadAll())
            Mods.Add(mod);
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
    private void SelectAll()
    {
        foreach (var mod in Mods)
            mod.IsChecked = true;
        OnPropertyChanged(nameof(Mods));
    }

    [RelayCommand]
    private void DeselectAll()
    {
        foreach (var mod in Mods)
            mod.IsChecked = false;
        OnPropertyChanged(nameof(Mods));
    }

    [RelayCommand(CanExecute = nameof(CanBuild))]
    private async Task BuildAsync()
    {
        IsBuilding = true;
        BuildStatus = "Preparing build...";
        BuildProgress = 0;

        try
        {
            var selectedMods = Mods.Where(m => m.IsChecked).ToList();
            if (selectedMods.Count == 0)
            {
                BuildStatus = "No mods selected";
                return;
            }

            // Gather all .def paths from selected mods
            var allDefPaths = new HashSet<string>();
            var includeSecrets = false;

            foreach (var mod in selectedMods)
            {
                var resolved = _modService.ResolveDefPaths(mod);
                foreach (var path in resolved)
                    allDefPaths.Add(path);
                if (mod.IncludeSecrets)
                    includeSecrets = true;
            }

            var progress = new Progress<BuildProgress>(p =>
            {
                BuildStatus = p.Status;
                BuildProgress = p.Progress;
            });

            var result = await _buildService.BuildAsync(
                ModName, allDefPaths.ToList(), includeSecrets, progress);

            BuildStatus = result.Success
                ? $"Build complete! {result.Message}"
                : $"Build failed: {result.Message}";
        }
        catch (Exception ex)
        {
            BuildStatus = $"Error: {ex.Message}";
        }
        finally
        {
            IsBuilding = false;
        }
    }

    private bool CanBuild() => !IsBuilding && !string.IsNullOrWhiteSpace(ModName);

    [RelayCommand]
    private void ViewModInfo(PrebuiltMod? mod)
    {
        SelectedMod = mod;
        if (mod == null)
        {
            SelectedModTitle = "";
            SelectedModAuthor = "";
            SelectedModDescription = "Select a mod from the list to see its details.";
            return;
        }
        SelectedModTitle = mod.Title;
        SelectedModAuthor = string.IsNullOrEmpty(mod.Author) ? "" : $"by {mod.Author}";
        SelectedModDescription = string.IsNullOrEmpty(mod.Description)
            ? $"This mod includes {mod.DefPaths.Count} definition file(s)."
            : mod.Description;
    }

    partial void OnModNameChanged(string value) => BuildCommand.NotifyCanExecuteChanged();
    partial void OnIsBuildingChanged(bool value) => BuildCommand.NotifyCanExecuteChanged();
}
