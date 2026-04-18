using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Create DEF tab: compare modded vs original game files and generate .def/.ini files.
/// Mirrors Python def_creator_view.py.
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
    [ObservableProperty] private string _modFolderPath = "";
    [ObservableProperty] private string _origFolderPath = "";
    [ObservableProperty] private string _defTitle = "Custom Mod";
    [ObservableProperty] private string _defAuthor = "";
    [ObservableProperty] private string _defDescription = "";
    [ObservableProperty] private string _defChangeNote = "";
    [ObservableProperty] private bool _includeComments;
    [ObservableProperty] private string _logText = "";
    [ObservableProperty] private GeneratedFile? _selectedGeneratedFile;

    partial void OnSelectedGeneratedFileChanged(GeneratedFile? value)
    {
        if (value != null) SelectGeneratedFile(value);
    }

    public ObservableCollection<string> ExtractedFiles { get; } = [];
    public ObservableCollection<DiffEntry> Differences { get; } = [];
    public ObservableCollection<GeneratedFile> GeneratedFiles { get; } = [];

    private static readonly string[] GlobalFileNames = ["global.ucas", "global.utoc"];

    public DefCreatorViewModel(ConfigService config, RetocService retoc, UAssetService uasset, DiffService diff)
    {
        _config = config;
        _retoc = retoc;
        _uasset = uasset;
        _diff = diff;

        // Default original folder to game output jsondata
        OrigFolderPath = config.OutputJsonDataDir;
    }

    private void Log(string message)
    {
        LogText += $"[{DateTime.Now:HH:mm:ss}] {message}\n";
    }

    [RelayCommand]
    private void BrowseModFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "Select Modded Files Folder",
        };
        if (dialog.ShowDialog() == true)
        {
            ModFolderPath = dialog.FolderName;
            Log($"Mod folder: {ModFolderPath}");
        }
    }

    [RelayCommand]
    private void BrowseOrigFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "Select Original Files Folder",
        };
        if (dialog.ShowDialog() == true)
        {
            OrigFolderPath = dialog.FolderName;
            Log($"Original folder: {OrigFolderPath}");
        }
    }

    [RelayCommand]
    private async Task ScanAndCompareAsync()
    {
        if (string.IsNullOrEmpty(ModFolderPath))
        {
            Status = "Select a mod folder first (Modded files)";
            return;
        }
        if (string.IsNullOrEmpty(OrigFolderPath) || !Directory.Exists(OrigFolderPath))
        {
            Status = "Select an original folder (game JSON output). Run Import first if needed.";
            return;
        }
        if (!Directory.Exists(ModFolderPath))
        {
            Status = $"Mod folder not found: {ModFolderPath}";
            return;
        }

        IsWorking = true;
        Progress = 0;
        GeneratedFiles.Clear();
        Differences.Clear();
        ExtractedFiles.Clear();
        LogText = "";

        Log($"Mod folder: {ModFolderPath}");
        Log($"Original folder: {OrigFolderPath}");
        Log($"Mod folder exists: {Directory.Exists(ModFolderPath)}");
        Log($"Original folder exists: {Directory.Exists(OrigFolderPath)}");

        try
        {
            await Task.Run(async () =>
            {
                // Step 1: Check for IoStore files and extract if needed
                var modJsonDir = ModFolderPath;
                var hasUtoc = Directory.GetFiles(ModFolderPath, "*.utoc", SearchOption.TopDirectoryOnly).Length > 0;
                if (hasUtoc)
                {
                    Log("Detected IoStore pak files. Extracting...");
                    Status = "Extracting IoStore mod files...";

                    var retocDir = Path.Combine(ModFolderPath, "retoc");
                    modJsonDir = Path.Combine(ModFolderPath, "jsondata");
                    Directory.CreateDirectory(retocDir);
                    Directory.CreateDirectory(modJsonDir);

                    // Copy global files for retoc
                    var gamePaks = _config.GetGamePaksPath();
                    if (gamePaks != null)
                    {
                        var tempPaks = Path.Combine(Path.GetTempPath(), $"defcreator_{Guid.NewGuid():N}");
                        Directory.CreateDirectory(tempPaks);

                        foreach (var f in Directory.GetFiles(ModFolderPath))
                            File.Copy(f, Path.Combine(tempPaks, Path.GetFileName(f)), true);
                        foreach (var name in GlobalFileNames)
                        {
                            var src = Path.Combine(gamePaks, name);
                            if (File.Exists(src))
                                File.Copy(src, Path.Combine(tempPaks, name), true);
                        }

                        var result = await _retoc.ToLegacyAsync(tempPaks, retocDir);
                        Log($"retoc extraction: {(result.Success ? "success" : "failed")}");
                        if (!string.IsNullOrEmpty(result.Output))
                            Log($"retoc output: {result.Output[..Math.Min(result.Output.Length, 200)]}");

                        // Convert uassets to JSON
                        var uassets = Directory.GetFiles(retocDir, "*.uasset", SearchOption.AllDirectories).ToList();
                        var umaps = Directory.GetFiles(retocDir, "*.umap", SearchOption.AllDirectories);
                        Log($"retoc extracted: {uassets.Count} .uasset + {umaps.Length} .umap files");

                        if (uassets.Count == 0 && umaps.Length == 0)
                        {
                            Log("[WARNING] retoc produced no extractable files. This mod may not contain DataTable assets.");
                            Log("[INFO] Checking if mod folder already has JSON files...");
                        }

                        if (uassets.Count > 0)
                        {
                            Log($"Converting {uassets.Count} uasset files to JSON...");
                            await _uasset.BatchToJsonAsync(uassets, retocDir, modJsonDir,
                                new Progress<(int Done, int Total)>(p =>
                                {
                                    Progress = 0.3 * p.Done / Math.Max(p.Total, 1);
                                    Status = $"Converting {p.Done}/{p.Total}...";
                                }));
                        }

                        try { Directory.Delete(tempPaks, true); } catch { }
                    }
                }

                // Step 2: Check for uasset files and convert
                var uassetFiles = Directory.GetFiles(modJsonDir, "*.uasset", SearchOption.AllDirectories);
                if (uassetFiles.Length > 0 && !hasUtoc)
                {
                    Log($"Converting {uassetFiles.Length} uasset files...");
                    var jsonDir = Path.Combine(ModFolderPath, "jsondata");
                    Directory.CreateDirectory(jsonDir);
                    await _uasset.BatchToJsonAsync(uassetFiles.ToList(), modJsonDir, jsonDir,
                        new Progress<(int Done, int Total)>(p =>
                        {
                            Progress = 0.3 * p.Done / Math.Max(p.Total, 1);
                            Status = $"Converting {p.Done}/{p.Total}...";
                        }));
                    modJsonDir = jsonDir;
                }

                // Step 3: Find JSON files in mod folder
                var modJsonFiles = Directory.GetFiles(modJsonDir, "*.json", SearchOption.AllDirectories);
                Log($"Found {modJsonFiles.Length} JSON files in mod folder");

                // Step 4: Compare each mod file against original
                Status = "Comparing files...";
                int totalDiffs = 0;

                foreach (var modFile in modJsonFiles)
                {
                    var relPath = Path.GetRelativePath(modJsonDir, modFile);

                    System.Windows.Application.Current.Dispatcher.Invoke(() =>
                        ExtractedFiles.Add(relPath));

                    // Find matching original file
                    var origFile = Path.Combine(OrigFolderPath, relPath);
                    if (!File.Exists(origFile))
                    {
                        // Try auto-import: strip Moria/Content/ prefix for FindSourceJson
                        var normalizedRel = relPath.Replace('\\', '/');
                        var contentIdx = normalizedRel.IndexOf("Moria/Content/", StringComparison.OrdinalIgnoreCase);
                        var searchRel = contentIdx >= 0
                            ? normalizedRel[(contentIdx + "Moria/Content/".Length)..]
                            : normalizedRel;

                        var gamePath = _config.FindSourceJson(ImportService.ModeSecrets, searchRel);
                        if (gamePath != null)
                        {
                            origFile = gamePath;
                        }
                        else
                        {
                            Log($"No original found for: {relPath}");
                            continue;
                        }
                    }

                    // Compare
                    var diffs = _diff.FindDifferences(modFile, origFile);
                    if (diffs.Count > 0)
                    {
                        Log($"{Path.GetFileName(modFile)}: {diffs.Count} difference(s)");
                        totalDiffs += diffs.Count;

                        // Generate .def XML for this file
                        var defXml = _diff.GenerateDefXml(DefTitle, relPath, diffs,
                            description: DefDescription, changeNote: DefChangeNote,
                            includeComments: IncludeComments);
                        var category = DetectCategory(relPath);
                        var defFileName = $"{Path.GetFileNameWithoutExtension(modFile)}.def";

                        System.Windows.Application.Current.Dispatcher.Invoke(() =>
                        {
                            GeneratedFiles.Add(new GeneratedFile
                            {
                                FileName = defFileName,
                                Category = category,
                                Content = defXml,
                                DiffCount = diffs.Count,
                            });

                            foreach (var d in diffs)
                            {
                                Differences.Add(new DiffEntry
                                {
                                    ItemName = d.ItemName,
                                    PropertyPath = d.PropertyPath,
                                    NewValue = d.NewValue,
                                    OriginalValue = d.OriginalValue ?? "",
                                });
                            }
                        });
                    }
                }

                Status = $"Comparison complete: {totalDiffs} total differences in {GeneratedFiles.Count} file(s)";
                Log($"Total: {totalDiffs} differences across {modJsonFiles.Length} files");
                Progress = 1.0;
            });

            // Show first generated file in preview
            if (GeneratedFiles.Count > 0)
                DefOutput = GeneratedFiles[0].Content;
        }
        catch (Exception ex)
        {
            Status = $"Error: {ex.Message}";
            Log($"ERROR: {ex.Message}");
        }
        finally
        {
            IsWorking = false;
        }
    }

    [RelayCommand]
    private void SelectFile(string? filePath)
    {
        if (filePath == null) return;
        SelectedFile = filePath;
        Status = $"Selected: {Path.GetFileName(filePath)}";
    }

    private void SelectGeneratedFile(GeneratedFile? file)
    {
        if (file == null) return;
        DefOutput = file.Content;
        Status = $"Viewing: {file.FileName} ({file.DiffCount} changes)";
    }

    [RelayCommand]
    private void SaveAllFiles()
    {
        if (GeneratedFiles.Count == 0)
        {
            Status = "Nothing to save — run comparison first";
            return;
        }

        int saved = 0;
        foreach (var file in GeneratedFiles)
        {
            var outputDir = Path.Combine(_config.DefinitionsDir, file.Category);
            Directory.CreateDirectory(outputDir);
            var outputPath = Path.Combine(outputDir, file.FileName);
            File.WriteAllText(outputPath, file.Content);
            saved++;
            Log($"Saved: {file.Category}/{file.FileName}");
        }

        // Generate .ini for prebuilt modfiles
        if (saved > 0)
        {
            var defRelPaths = GeneratedFiles
                .Select(f => $"{f.Category}/{f.FileName}")
                .ToList();
            var iniContent = _diff.GenerateIniContent(DefTitle, DefAuthor, defRelPaths, false);
            var iniPath = Path.Combine(_config.PrebuiltModfilesDir, $"{DefTitle}.ini");
            Directory.CreateDirectory(_config.PrebuiltModfilesDir);
            File.WriteAllText(iniPath, iniContent);
            Log($"Generated .ini: {iniPath}");
        }

        Status = $"Saved {saved} .def file(s) to Definitions directory";
    }

    private static string DetectCategory(string filePath)
    {
        var fileName = Path.GetFileNameWithoutExtension(filePath);

        // Map DT_* filenames to category folders (matches Python _detect_category)
        if (fileName.Contains("Weapon", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Armor", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Tool", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Item", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Ore", StringComparison.OrdinalIgnoreCase))
            return "Items";
        if (fileName.Contains("Construction", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Building", StringComparison.OrdinalIgnoreCase))
            return "Building";
        if (fileName.Contains("Flora", StringComparison.OrdinalIgnoreCase))
            return "Flora";
        if (fileName.Contains("Loot", StringComparison.OrdinalIgnoreCase))
            return "Loot";
        if (fileName.Contains("Effect", StringComparison.OrdinalIgnoreCase) ||
            fileName.Contains("Tint", StringComparison.OrdinalIgnoreCase))
            return "Effects";
        if (fileName.Contains("Buff", StringComparison.OrdinalIgnoreCase))
            return "Buffs";

        // Fallback: use parent directory name
        var parts = filePath.Replace('\\', '/').Split('/');
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

public class GeneratedFile
{
    public string FileName { get; init; } = "";
    public string Category { get; init; } = "";
    public string Content { get; set; } = "";
    public int DiffCount { get; init; }
}
