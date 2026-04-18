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
    [ObservableProperty] private bool _selectAllChecked;

    public ObservableCollection<PrebuiltMod> Mods { get; } = [];

    partial void OnSelectAllCheckedChanged(bool value)
    {
        foreach (var mod in Mods)
            mod.IsChecked = value;
    }

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
        // Save current checkbox states before switching
        if (!string.IsNullOrWhiteSpace(ModName))
            SaveCheckboxStates();

        var dialog = new Views.Dialogs.ModNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow
        };
        if (dialog.ShowDialog() == true && dialog.SelectedModName != null)
        {
            ModName = dialog.SelectedModName;
            RestoreCheckboxStates();
            BuildStatus = $"Mod '{ModName}' selected";
        }
    }

    private string GetCheckboxIniPath() =>
        System.IO.Path.Combine(_config.GetModDir(ModName), "checkbox_states.ini");

    private void SaveCheckboxStates()
    {
        if (string.IsNullOrWhiteSpace(ModName)) return;
        var iniPath = GetCheckboxIniPath();
        System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(iniPath)!);

        // Read existing file to preserve other sections (e.g. [Definitions])
        var existingLines = System.IO.File.Exists(iniPath) ? System.IO.File.ReadAllLines(iniPath).ToList() : [];

        // Remove existing [NoviceMods] section
        var secStart = existingLines.FindIndex(l => l.Trim() == "[NoviceMods]");
        if (secStart >= 0)
        {
            var secEnd = existingLines.FindIndex(secStart + 1, l => l.TrimStart().StartsWith('['));
            if (secEnd < 0) secEnd = existingLines.Count;
            existingLines.RemoveRange(secStart, secEnd - secStart);
        }

        // Append [NoviceMods] section
        existingLines.Add("[NoviceMods]");
        foreach (var mod in Mods)
            existingLines.Add($"{mod.Name} = {(mod.IsChecked ? "true" : "false")}");

        System.IO.File.WriteAllLines(iniPath, existingLines);
    }

    private void RestoreCheckboxStates()
    {
        if (string.IsNullOrWhiteSpace(ModName)) return;
        var iniPath = GetCheckboxIniPath();
        if (!System.IO.File.Exists(iniPath)) return;

        var states = new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);
        string? section = null;
        foreach (var line in System.IO.File.ReadAllLines(iniPath))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                section = trimmed[1..^1];
                continue;
            }
            if (section != "NoviceMods" || !trimmed.Contains('=')) continue;
            var eqIdx = trimmed.IndexOf('=');
            var key = trimmed[..eqIdx].Trim();
            var val = trimmed[(eqIdx + 1)..].Trim();
            states[key] = val.Equals("true", StringComparison.OrdinalIgnoreCase);
        }

        foreach (var mod in Mods)
        {
            if (states.TryGetValue(mod.Name, out var isChecked))
                mod.IsChecked = isChecked;
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
        SaveCheckboxStates();
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

    [RelayCommand]
    private void DeleteMod(PrebuiltMod? mod)
    {
        if (mod == null) return;
        var result = System.Windows.MessageBox.Show(
            $"Delete prebuilt mod '{mod.Title}'?\nThis will remove the .ini file.",
            "Confirm Delete",
            System.Windows.MessageBoxButton.YesNo,
            System.Windows.MessageBoxImage.Question);
        if (result == System.Windows.MessageBoxResult.Yes)
        {
            try
            {
                if (File.Exists(mod.FilePath))
                    File.Delete(mod.FilePath);
                Mods.Remove(mod);
                BuildStatus = $"Deleted '{mod.Title}'";
            }
            catch (Exception ex)
            {
                BuildStatus = $"Delete failed: {ex.Message}";
            }
        }
    }

    partial void OnModNameChanged(string value) => BuildCommand.NotifyCanExecuteChanged();
    partial void OnIsBuildingChanged(bool value) => BuildCommand.NotifyCanExecuteChanged();
}
