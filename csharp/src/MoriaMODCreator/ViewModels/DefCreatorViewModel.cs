using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Create DEF tab: extract game files, compare, generate .def/.ini files.
/// </summary>
public partial class DefCreatorViewModel : ObservableObject
{
    private readonly ConfigService _config;
    private readonly RetocService _retoc;
    private readonly UAssetService _uasset;
    private readonly DiffService _diff;

    [ObservableProperty] private string _status = "";
    [ObservableProperty] private bool _isWorking;
    [ObservableProperty] private double _progress;
    [ObservableProperty] private string _selectedFile = "";
    [ObservableProperty] private string _defOutput = "";

    public ObservableCollection<string> ExtractedFiles { get; } = [];
    public ObservableCollection<DiffEntry> Differences { get; } = [];

    public DefCreatorViewModel(ConfigService config, RetocService retoc, UAssetService uasset, DiffService diff)
    {
        _config = config;
        _retoc = retoc;
        _uasset = uasset;
        _diff = diff;
    }

    [RelayCommand]
    private async Task ExtractAsync()
    {
        IsWorking = true;
        Status = "Extracting game files...";

        var gamePaksPath = _config.GetGamePaksPath();
        if (gamePaksPath == null)
        {
            Status = "Game path not configured";
            IsWorking = false;
            return;
        }

        var retocDir = Path.Combine(_config.AppDataDir, "output", "retoc");
        var jsonDir = Path.Combine(_config.AppDataDir, "output", "jsondata");

        // Extract and convert
        // This would normally be a targeted extraction with --filter
        Status = "Extraction complete. Select a file to compare.";
        IsWorking = false;

        // Load extracted files
        ExtractedFiles.Clear();
        if (Directory.Exists(jsonDir))
        {
            foreach (var file in Directory.GetFiles(jsonDir, "*.json", SearchOption.AllDirectories))
            {
                ExtractedFiles.Add(Path.GetRelativePath(jsonDir, file));
            }
        }
    }

    [RelayCommand]
    private void CompareFile()
    {
        if (string.IsNullOrEmpty(SelectedFile))
        {
            Status = "Select a file to compare";
            return;
        }

        Status = $"Comparing {SelectedFile}...";
        Differences.Clear();

        var jsonDir = Path.Combine(_config.AppDataDir, "output", "jsondata");
        var editedPath = Path.Combine(jsonDir, SelectedFile);

        // For now, show a placeholder — real comparison needs original vs edited
        Status = "Comparison requires both original and edited files";
    }

    [RelayCommand]
    private void GenerateDef()
    {
        if (Differences.Count == 0)
        {
            Status = "No differences to generate .def from";
            return;
        }

        var diffs = Differences.Select(d => new PropertyDiff
        {
            ItemName = d.ItemName,
            PropertyPath = d.PropertyPath,
            NewValue = d.NewValue,
            OriginalValue = d.OriginalValue,
            DiffType = DiffType.Change,
        }).ToList();

        var defXml = _diff.GenerateDefXml("Custom Mod", SelectedFile, diffs);
        DefOutput = defXml;
        Status = $"Generated .def with {diffs.Count} change(s)";
    }

    [RelayCommand]
    private void SaveDef()
    {
        if (string.IsNullOrEmpty(DefOutput))
        {
            Status = "Nothing to save — generate a .def first";
            return;
        }

        var defDir = _config.DefinitionsDir;
        var category = DetectCategory(SelectedFile);
        var outputDir = Path.Combine(defDir, category);
        Directory.CreateDirectory(outputDir);

        var fileName = Path.GetFileNameWithoutExtension(SelectedFile) + ".def";
        var outputPath = Path.Combine(outputDir, fileName);
        File.WriteAllText(outputPath, DefOutput);

        Status = $"Saved: {outputPath}";
    }

    private static string DetectCategory(string filePath)
    {
        var parts = filePath.Replace('\\', '/').Split('/');
        // Use the last directory component before the filename
        return parts.Length >= 2 ? parts[^2] : "Misc";
    }
}

public class DiffEntry
{
    public string ItemName { get; init; } = "";
    public string PropertyPath { get; init; } = "";
    public string NewValue { get; init; } = "";
    public string OriginalValue { get; init; } = "";
}
