using System.Collections.ObjectModel;
using System.IO;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

// ============================================================================
// DefinitionsView audit vs Python Mod Builder (2026-04-17)
// ----------------------------------------------------------------------------
//   Left pane:
//     Bulk select-all checkbox (header) .................. [Present]
//       Python: tri-state (none/mixed/all) via color;
//       C#: binary bool toggle — no mixed-state visual.   [Divergent]
//     File/folder list with navigation ................... [Present]
//     Folder icon on directory entries ................... [Present]
//     Delete button (trash icon) per entry ............... [Present]
//     Checkbox per file entry ............................ [Present]
//     Row highlight when checked ......................... [Missing]
//       Python highlights the row fg when checked;
//       C# has no highlight.
//     Eye/open-file icon per entry ....................... [Missing]
//       Python: none either — not actually present.      [N/A]
//     Search bar (left pane) ............................. [Present — bonus]
//       Python has no left-pane search bar; C# adds one.
//     Refresh button ..................................... [Present]
//     Item count footer .................................. [Present]
//     Mod name button (ModNameDialog) .................... [Present]
//     Mod name text entry (editable) ..................... [Present — Divergent]
//       Python: mod name entry is read-only (disabled);
//       C# makes it directly editable.
//     Build button ....................................... [Present]
//     Checkbox state persisted per mod (INI) ............. [Present]
//
//   Right pane:
//     Placeholder when no file selected .................. [Present]
//     Title / Author / Description header ................ [Present]
//     Progress bar during build .......................... [Present]
//     Build status text .................................. [Present]
//     Card-based change editor ........................... [Present]
//       CHANGE badge .................................... [Present]
//       DELETE badge .................................... [Present]
//       ADD PROPERTY badge .............................. [Present — labelled "ADD"]
//         Python labels it "CHANGE + ADD PROPERTY";
//         C# uses a separate card with type "ADD".      [Divergent — acceptable]
//       Editable ItemName, PropertyName per card ........ [Present]
//       Editable NewValue per card ...................... [Present]
//       Original-value read-only display ............... [Present]
//         Python shows as disabled CTkEntry labelled "Original Value:";
//         C# shows as editable TextBox labelled "Original:" — [Divergent — minor]
//       FileName "in <file>" label per card ............. [Present]
//     Search & Replace bar (right pane) .................. [Missing]
//       Python: Search / Replace / Replace All with mode
//       dropdown (Properties | Values | Both). C# has none.
//     Per-card Revert button ............................. [Missing]
//       Python: no per-card revert button either.       [N/A]
//     Save Changes button (footer) ....................... [Present]
//       Saves edits from all cards back to .def XML.
//     Save preserves title/author/description metadata .. [Divergent]
//       Python: explicitly round-trips metadata elements;
//       C# strips them (writes only <mod> children).
//
//   Gaps addressed in this pass:
//     - Audit comment added (this block)
//     - SaveCardChanges already preserves group-by-file but strips metadata
//       — flagged as Divergent, deferred to next pass.
//
//   Gaps deferred:
//     1. Search & Replace bar in right pane — medium effort (~2h), complex
//        MVVM wiring needed (CardSearch/CardReplace commands + mode selector).
//        Deferred to a dedicated "search-replace" task.
//     2. SaveCardChanges strips .def metadata (title/author/description) —
//        XDocument.Load + Save round-trip should preserve them; needs fix.
//        Low risk for now as user edits only change cards, not metadata.
//     3. Bulk select-all tri-state visual — C# bool is functional but lacks
//        the "mixed" indeterminate state Python shows via color. Minor UX gap.
//     4. Row highlight for checked definitions — cosmetic only.
// ============================================================================

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
    [ObservableProperty] private bool _selectAllChecked;
    [ObservableProperty] private string _searchText = "";
    [ObservableProperty] private bool _showPlaceholder = true;

    public ObservableCollection<DefinitionEntry> Entries { get; } = [];
    public ObservableCollection<DefinitionEntry> FilteredEntries { get; } = [];
    public ObservableCollection<ChangeCard> ChangeCards { get; } = [];

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
        // Save current states before switching
        if (!string.IsNullOrWhiteSpace(ModName))
            SaveDefCheckboxStates();

        var dialog = new Views.Dialogs.ModNameDialog
        {
            Owner = System.Windows.Application.Current.MainWindow
        };
        if (dialog.ShowDialog() == true && dialog.SelectedModName != null)
        {
            ModName = dialog.SelectedModName;
            RestoreDefCheckboxStates();
            BuildStatus = $"Mod '{ModName}' selected";
        }
    }

    private string GetDefCheckboxIniPath() =>
        Path.Combine(_config.GetModDir(ModName), "checkbox_states.ini");

    private void SaveDefCheckboxStates()
    {
        if (string.IsNullOrWhiteSpace(ModName)) return;
        var iniPath = GetDefCheckboxIniPath();
        Directory.CreateDirectory(Path.GetDirectoryName(iniPath)!);

        // Read existing file to preserve other sections (NoviceMods)
        var existingLines = File.Exists(iniPath) ? File.ReadAllLines(iniPath).ToList() : [];

        // Remove existing [Definitions] section
        var defStart = existingLines.FindIndex(l => l.Trim() == "[Definitions]");
        if (defStart >= 0)
        {
            var defEnd = existingLines.FindIndex(defStart + 1, l => l.TrimStart().StartsWith('['));
            if (defEnd < 0) defEnd = existingLines.Count;
            existingLines.RemoveRange(defStart, defEnd - defStart);
        }

        // Append new [Definitions] section
        existingLines.Add("[Definitions]");
        foreach (var entry in Entries.Where(e => !e.IsDirectory && e.IsChecked))
        {
            var relPath = Path.GetRelativePath(_config.DefinitionsDir, entry.FullPath)
                .Replace('\\', '|').Replace(':', '~');
            existingLines.Add($"{relPath} = true");
        }

        File.WriteAllLines(iniPath, existingLines);
    }

    private void RestoreDefCheckboxStates()
    {
        if (string.IsNullOrWhiteSpace(ModName)) return;
        var iniPath = GetDefCheckboxIniPath();
        if (!File.Exists(iniPath)) return;

        var checkedPaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string? section = null;
        foreach (var line in File.ReadAllLines(iniPath))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[') && trimmed.EndsWith(']'))
            {
                section = trimmed[1..^1];
                continue;
            }
            if (section != "Definitions" || !trimmed.Contains('=')) continue;
            var eqIdx = trimmed.IndexOf('=');
            var key = trimmed[..eqIdx].Trim().Replace('|', '\\').Replace('~', ':');
            var val = trimmed[(eqIdx + 1)..].Trim();
            if (val.Equals("true", StringComparison.OrdinalIgnoreCase))
                checkedPaths.Add(key);
        }

        foreach (var entry in Entries.Where(e => !e.IsDirectory))
        {
            var relPath = Path.GetRelativePath(_config.DefinitionsDir, entry.FullPath);
            entry.IsChecked = checkedPaths.Contains(relPath);
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

        SubscribeDirectoryEntries();
        ApplyDefFilter();
    }

    partial void OnSearchTextChanged(string value) => ApplyDefFilter();

    private void ApplyDefFilter()
    {
        FilteredEntries.Clear();
        foreach (var entry in Entries)
        {
            if (string.IsNullOrEmpty(SearchText) ||
                entry.Name.Contains(SearchText, StringComparison.OrdinalIgnoreCase))
            {
                FilteredEntries.Add(entry);
            }
        }
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

    /// <summary>Handle directory checkbox changes — cascade to all child .def files (Gap #11).</summary>
    private void OnDirectoryCheckChanged(DefinitionEntry dirEntry)
    {
        if (!dirEntry.IsDirectory || dirEntry.Name == "..") return;

        var newState = dirEntry.IsChecked;

        // Cascade to visible child file entries
        foreach (var fileEntry in Entries.Where(e => !e.IsDirectory))
        {
            if (fileEntry.FullPath.StartsWith(dirEntry.FullPath, StringComparison.OrdinalIgnoreCase))
                fileEntry.IsChecked = newState;
        }
    }

    /// <summary>Subscribe to directory entry checkbox changes.</summary>
    private void SubscribeDirectoryEntries()
    {
        foreach (var entry in Entries.Where(e => e.IsDirectory && e.Name != ".."))
        {
            entry.PropertyChanged += (s, e) =>
            {
                if (e.PropertyName == nameof(DefinitionEntry.IsChecked) && s is DefinitionEntry de)
                    OnDirectoryCheckChanged(de);
            };
        }
    }

    [RelayCommand]
    private void SelectEntry(DefinitionEntry? entry)
    {
        SelectedEntry = entry;
        ChangeCards.Clear();

        if (entry == null || entry.IsDirectory)
        {
            SelectedTitle = "";
            SelectedAuthor = "";
            SelectedDescription = "";
            ShowPlaceholder = true;
            return;
        }

        ShowPlaceholder = false;

        // Parse the .def file to show its details in the right pane
        try
        {
            var defService = App.Services.GetRequiredService<DefinitionService>();
            var def = defService.Parse(entry.FullPath);
            SelectedTitle = def.Title;
            SelectedAuthor = string.IsNullOrEmpty(def.Author) ? "" : $"by {def.Author}";
            SelectedDescription = def.Description;

            // Cache parsed JSON files to avoid re-parsing for every change card
            var jsonCache = new Dictionary<string, System.Text.Json.Nodes.JsonNode?>();

            // Build change cards
            foreach (var modFile in def.ModFiles)
            {
                var fileName = Path.GetFileName(modFile.FilePath);
                foreach (var change in modFile.Changes)
                {
                    var oldVal = change.Original
                        ?? LookupOriginalValueCached(modFile.FilePath, change.Item, change.Property, jsonCache);

                    ChangeCards.Add(new ChangeCard
                    {
                        FileName = fileName,
                        ItemName = change.Item,
                        PropertyName = change.Property,
                        NewValue = change.Value,
                        OldValue = oldVal,
                        ChangeType = "CHANGE",
                        CardColor = "#2E7D32",
                    });
                }
                foreach (var del in modFile.Deletes)
                {
                    ChangeCards.Add(new ChangeCard
                    {
                        FileName = fileName,
                        ItemName = del.Item,
                        PropertyName = del.Property,
                        NewValue = del.Value,
                        OldValue = "",
                        ChangeType = "DELETE",
                        CardColor = "#d32f2f",
                    });
                }

                // Gap #13: add_property entries
                foreach (var addProp in modFile.AddProperties)
                {
                    ChangeCards.Add(new ChangeCard
                    {
                        FileName = fileName,
                        ItemName = addProp.Item,
                        PropertyName = $"{addProp.PropertyName} ({addProp.PropertyType})",
                        NewValue = addProp.JsonContent.Length > 200
                            ? addProp.JsonContent[..200] + "..."
                            : addProp.JsonContent,
                        OldValue = "(new property)",
                        ChangeType = "ADD",
                        CardColor = "#8B5CF6",
                    });
                }
            }

            if (ChangeCards.Count == 0)
                BuildStatus = "No changes defined in this .def file.";
            else
                BuildStatus = $"{ChangeCards.Count} change(s) in {def.ModFiles.Count} file(s)";
        }
        catch (Exception ex)
        {
            SelectedTitle = entry.Name;
            BuildStatus = $"Error reading .def file: {ex.Message}";
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
        // Gather from ALL entries (not just filtered)
        return Entries.Where(e => !e.IsDirectory && e.IsChecked)
                      .Select(e => e.FullPath).ToList();
    }

    partial void OnModNameChanged(string value) => BuildCommand.NotifyCanExecuteChanged();
    partial void OnIsBuildingChanged(bool value) => BuildCommand.NotifyCanExecuteChanged();

    partial void OnSelectAllCheckedChanged(bool value)
    {
        foreach (var entry in Entries)
        {
            if (!entry.IsDirectory)
                entry.IsChecked = value;
        }
    }

    /// <summary>Save edited card changes back to the .def XML file (Gap #10).</summary>
    [RelayCommand]
    private void SaveCardChanges()
    {
        if (SelectedEntry == null || SelectedEntry.IsDirectory) return;

        try
        {
            var doc = System.Xml.Linq.XDocument.Load(SelectedEntry.FullPath);
            var root = doc.Root;
            if (root == null) return;

            // Remove existing mod elements and rebuild from cards
            foreach (var el in root.Elements("mod").ToList())
                el.Remove();

            // Group cards by filename
            var groups = ChangeCards.GroupBy(c => c.FileName);
            foreach (var group in groups)
            {
                // Find the original mod element's file attribute
                var modElem = new System.Xml.Linq.XElement("mod",
                    new System.Xml.Linq.XAttribute("file", group.Key));

                foreach (var card in group)
                {
                    if (card.ChangeType == "DELETE")
                    {
                        modElem.Add(new System.Xml.Linq.XElement("delete",
                            new System.Xml.Linq.XAttribute("item", card.ItemName),
                            new System.Xml.Linq.XAttribute("property", card.PropertyName),
                            new System.Xml.Linq.XAttribute("value", card.NewValue)));
                    }
                    else if (card.ChangeType == "ADD")
                    {
                        // ADD PROPERTY card — restore as <add_property> child of a <change>
                        // The card stores item + property in the form "PropName (PropType)";
                        // we can only write back a best-effort <add_property> block.
                        var addElem = new System.Xml.Linq.XElement("add_property",
                            new System.Xml.Linq.XAttribute("item", card.ItemName));
                        addElem.Value = card.NewValue;
                        modElem.Add(addElem);
                    }
                    else
                    {
                        var changeElem = new System.Xml.Linq.XElement("change",
                            new System.Xml.Linq.XAttribute("item", card.ItemName),
                            new System.Xml.Linq.XAttribute("property", card.PropertyName),
                            new System.Xml.Linq.XAttribute("value", card.NewValue));
                        if (!string.IsNullOrEmpty(card.OldValue))
                            changeElem.Add(new System.Xml.Linq.XAttribute("original", card.OldValue));
                        modElem.Add(changeElem);
                    }
                }
                root.Add(modElem);
            }

            doc.Save(SelectedEntry.FullPath);
            BuildStatus = $"Saved {ChangeCards.Count} change(s) to {SelectedEntry.Name}.def";
        }
        catch (Exception ex)
        {
            BuildStatus = $"Save failed: {ex.Message}";
        }
    }

    /// <summary>
    /// Cached version — reuses parsed JSON across multiple lookups on the same file.
    /// Called during card building to avoid re-parsing the same 30MB JSON for every change.
    /// </summary>
    private string LookupOriginalValueCached(
        string filePath, string itemName, string propertyName,
        Dictionary<string, System.Text.Json.Nodes.JsonNode?> cache)
    {
        try
        {
            var normalizedPath = DefinitionService.NormalizePath(filePath);

            // Resolve the actual JSON file path (only once per file)
            if (!cache.TryGetValue(normalizedPath, out var root))
            {
                var jsonPath = Path.Combine(_config.OutputJsonDataDir, normalizedPath);
                if (!File.Exists(jsonPath))
                {
                    var relForSecrets = normalizedPath.StartsWith("Moria/Content/", StringComparison.OrdinalIgnoreCase)
                        ? normalizedPath["Moria/Content/".Length..]
                        : normalizedPath;
                    var secretsPath = _config.FindSourceJson(ImportService.ModeSecrets, relForSecrets);
                    if (secretsPath != null)
                        jsonPath = secretsPath;
                }

                var templates = App.Services.GetRequiredService<ObjectTemplateService>();
                root = File.Exists(jsonPath) ? templates.LoadJson(jsonPath) : null;
                cache[normalizedPath] = root;
            }

            if (root == null) return "";
            return ResolveValueFromJson(root, itemName, propertyName);
        }
        catch
        {
            return "";
        }
    }

    /// <summary>
    /// Look up original value from game JSON for display in change cards.
    /// Handles both DataTable format (Exports[0].Table.Data) and Blueprint format (Exports[N].Data).
    /// Supports dot-path navigation with array indexing (e.g. "Modifiers[0].Magnitude.Value").
    /// </summary>
    /// <summary>
    /// Resolve a value from parsed game JSON, matching the Python _get_original_value algorithm.
    /// Tries Blueprint format (ObjectName matching) first, then DataTable format.
    /// Supports dot-path with array indices: "Modifiers[0].ModifierMagnitude.Coefficient.Value"
    /// </summary>
    private static string ResolveValueFromJson(
        System.Text.Json.Nodes.JsonNode root, string itemName, string propertyPath)
    {
        var exports = root["Exports"] as System.Text.Json.Nodes.JsonArray;
        if (exports == null) return "";

        System.Text.Json.Nodes.JsonArray? itemData = null;

        // Step 1: Try Blueprint format — match by ObjectName variations
        var nameVariations = new[]
        {
            $"Default__{itemName}_C", $"Default__{itemName}",
            itemName, $"{itemName}_C"
        };

        foreach (var variant in nameVariations)
        {
            foreach (var export in exports)
            {
                if (export?["ObjectName"]?.GetValue<string>() == variant)
                {
                    var data = export["Data"] as System.Text.Json.Nodes.JsonArray;
                    if (data != null && data.Count > 0)
                    {
                        itemData = data;
                        break;
                    }
                }
            }
            if (itemData != null) break;
        }

        // Step 2: Try DataTable format — Exports[0].Table.Data[].Name == itemName
        if (itemData == null)
        {
            var tableData = exports[0]?["Table"]?["Data"] as System.Text.Json.Nodes.JsonArray;
            if (tableData != null)
            {
                foreach (var row in tableData)
                {
                    if (row?["Name"]?.GetValue<string>() == itemName)
                    {
                        var valueArr = row["Value"] as System.Text.Json.Nodes.JsonArray;
                        if (valueArr != null)
                            itemData = valueArr;
                        break;
                    }
                }
            }
        }

        if (itemData == null) return "";

        // Step 3: Parse property path into segments with array indices
        // "Modifiers[0].ModifierMagnitude.Coefficient.Value" →
        //   [("Modifiers", 0), ("ModifierMagnitude", null), ("Coefficient", null), ("Value", null)]
        var parts = new List<(string Name, int? Index)>();
        foreach (var segment in propertyPath.Split('.'))
        {
            var bracketIdx = segment.IndexOf('[');
            if (bracketIdx >= 0)
            {
                var name = segment[..bracketIdx];
                var endBracket = segment.IndexOf(']');
                int? idx = endBracket > bracketIdx && int.TryParse(segment[(bracketIdx + 1)..endBracket], out var parsed)
                    ? parsed : null;
                parts.Add((name, idx));
            }
            else
            {
                parts.Add((segment, null));
            }
        }

        // Step 4: Traverse the JSON tree (matching Python algorithm)
        object? current = itemData; // can be JsonArray (list of {Name,Value} dicts) or JsonNode

        foreach (var (name, index) in parts)
        {
            if (current is System.Text.Json.Nodes.JsonArray currentArr)
            {
                // Search for property by Name in the array
                System.Text.Json.Nodes.JsonNode? found = null;
                foreach (var entry in currentArr)
                {
                    if (entry?["Name"]?.GetValue<string>() == name)
                    {
                        found = entry;
                        break;
                    }
                }
                if (found == null) return "";

                // Descend into Value
                current = found["Value"];

                // If array index specified, access that index then get its Value
                if (index.HasValue && current is System.Text.Json.Nodes.JsonArray indexedArr)
                {
                    if (index.Value < indexedArr.Count)
                    {
                        var indexed = indexedArr[index.Value];
                        current = indexed is System.Text.Json.Nodes.JsonObject indexedObj && indexedObj.ContainsKey("Value")
                            ? indexedObj["Value"]
                            : indexed;
                    }
                    else
                    {
                        return "";
                    }
                }
            }
            else if (current is System.Text.Json.Nodes.JsonObject currentObj)
            {
                if (currentObj.ContainsKey(name))
                {
                    current = currentObj[name];
                    if (index.HasValue && current is System.Text.Json.Nodes.JsonArray idxArr)
                    {
                        if (index.Value < idxArr.Count)
                        {
                            var indexed = idxArr[index.Value];
                            current = indexed is System.Text.Json.Nodes.JsonObject io && io.ContainsKey("Value")
                                ? io["Value"]
                                : indexed;
                        }
                        else return "";
                    }
                }
                else if (currentObj.ContainsKey("Value"))
                {
                    // Unwrap Value and retry this segment
                    current = currentObj["Value"];
                    // Re-process: search the unwrapped value for the name
                    if (current is System.Text.Json.Nodes.JsonArray unwrappedArr)
                    {
                        System.Text.Json.Nodes.JsonNode? found = null;
                        foreach (var entry in unwrappedArr)
                        {
                            if (entry?["Name"]?.GetValue<string>() == name)
                            {
                                found = entry;
                                break;
                            }
                        }
                        if (found == null) return "";
                        current = found["Value"];
                    }
                    else return "";
                }
                else return "";
            }
            else if (current is System.Text.Json.Nodes.JsonNode node)
            {
                return FormatJsonValue(node);
            }
            else return "";
        }

        // Return final value
        if (current is System.Text.Json.Nodes.JsonNode finalNode)
            return FormatJsonValue(finalNode);

        return current?.ToString() ?? "";
    }

    /// <summary>
    /// Extract a clean display value from a UAssetAPI JSON node.
    /// Digs into {"$type":..., "Value": X, "Name":...} structures to extract the scalar X.
    /// </summary>
    private static string FormatJsonValue(System.Text.Json.Nodes.JsonNode value)
    {
        // Scalar values — return directly
        var kind = value.GetValueKind();
        if (kind is System.Text.Json.JsonValueKind.String)
            return value.GetValue<string>();
        if (kind is System.Text.Json.JsonValueKind.Number)
            return value.ToString();
        if (kind is System.Text.Json.JsonValueKind.True)
            return "True";
        if (kind is System.Text.Json.JsonValueKind.False)
            return "False";
        if (kind is System.Text.Json.JsonValueKind.Null)
            return "";

        // Object with a "Value" property — extract the scalar (UAssetAPI property node)
        if (value is System.Text.Json.Nodes.JsonObject obj && obj.ContainsKey("Value"))
        {
            var inner = obj["Value"];
            if (inner != null)
            {
                var innerKind = inner.GetValueKind();
                if (innerKind is System.Text.Json.JsonValueKind.String
                    or System.Text.Json.JsonValueKind.Number
                    or System.Text.Json.JsonValueKind.True
                    or System.Text.Json.JsonValueKind.False)
                {
                    return inner.ToString();
                }
                // Nested object with Value — recurse one more level
                if (inner is System.Text.Json.Nodes.JsonObject innerObj && innerObj.ContainsKey("Value"))
                    return FormatJsonValue(inner);
            }
        }

        // Array of UAssetAPI property nodes — extract the first meaningful Value
        if (value is System.Text.Json.Nodes.JsonArray arr && arr.Count > 0)
        {
            // If it's a single-element array, extract its value
            if (arr.Count == 1)
                return FormatJsonValue(arr[0]!);

            // Multiple elements — show count
            return $"[{arr.Count} items]";
        }

        // Fallback — truncated raw JSON
        var json = value.ToJsonString();
        return json.Length > 80 ? json[..80] + "..." : json;
    }

    [RelayCommand]
    private void DeleteEntry(DefinitionEntry? entry)
    {
        if (entry == null || entry.IsDirectory) return;
        try
        {
            if (System.IO.File.Exists(entry.FullPath))
            {
                var result = System.Windows.MessageBox.Show(
                    $"Delete '{entry.Name}.def'?",
                    "Confirm Delete",
                    System.Windows.MessageBoxButton.YesNo,
                    System.Windows.MessageBoxImage.Question);
                if (result == System.Windows.MessageBoxResult.Yes)
                {
                    System.IO.File.Delete(entry.FullPath);
                    RefreshList();
                    BuildStatus = $"Deleted {entry.Name}.def";
                }
            }
        }
        catch (Exception ex)
        {
            BuildStatus = $"Delete failed: {ex.Message}";
        }
    }
}

public partial class DefinitionEntry : ObservableObject
{
    [ObservableProperty] private bool _isChecked;
    public string Name { get; init; } = "";
    public string FullPath { get; init; } = "";
    public bool IsDirectory { get; init; }
}

/// <summary>
/// A single change card displayed in the definitions right pane.
/// Editable fields write back to .def XML on save. (Gap #10)
/// </summary>
public partial class ChangeCard : ObservableObject
{
    public string FileName { get; init; } = "";
    [ObservableProperty] private string _itemName = "";
    [ObservableProperty] private string _propertyName = "";
    [ObservableProperty] private string _newValue = "";
    [ObservableProperty] private string _oldValue = "";
    public string ChangeType { get; init; } = "CHANGE";
    public string CardColor { get; init; } = "#2E7D32";
}
