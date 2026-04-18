using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Xml.Linq;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Win32;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ImportConstructionDialog : Window
{
    private readonly ConfigService _config;
    private readonly ObjectTemplateService _templates;
    private readonly List<ConstructionEntry> _entries = [];

    public ImportConstructionDialog()
    {
        InitializeComponent();
        _config = App.Services.GetRequiredService<ConfigService>();
        _templates = App.Services.GetRequiredService<ObjectTemplateService>();
    }

    private void OnBrowseSource(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select Construction JSON File",
            Filter = "JSON files (*.json)|*.json|All files (*.*)|*.*",
            InitialDirectory = _config.OutputJsonDataDir,
        };

        if (dialog.ShowDialog() == true)
        {
            SourcePathBox.Text = dialog.FileName;
            LoadConstructions(dialog.FileName);
        }
    }

    private void LoadConstructions(string jsonPath)
    {
        _entries.Clear();

        var root = _templates.LoadJson(jsonPath);
        if (root == null)
        {
            StatusText.Text = "Failed to load JSON file";
            return;
        }

        var rowNames = _templates.GetRowNames(root);
        foreach (var name in rowNames)
        {
            _entries.Add(new ConstructionEntry { Name = name, IsSelected = true });
        }

        ConstructionsList.ItemsSource = null;
        ConstructionsList.ItemsSource = _entries;
        StatusText.Text = $"Found {_entries.Count} construction(s)";
    }

    private void OnImport(object sender, RoutedEventArgs e)
    {
        var selected = _entries.Where(en => en.IsSelected).ToList();
        if (selected.Count == 0)
        {
            StatusText.Text = "No constructions selected";
            return;
        }

        var sourcePath = SourcePathBox.Text;
        if (string.IsNullOrEmpty(sourcePath) || !File.Exists(sourcePath))
        {
            StatusText.Text = "No source file selected";
            return;
        }

        // Generate .def file for selected constructions
        var relPath = Path.GetRelativePath(_config.OutputJsonDataDir, sourcePath)
            .Replace('\\', '/');
        if (relPath.StartsWith(".."))
            relPath = "Moria/Content/" + Path.GetFileName(sourcePath);

        var defRoot = new XElement("definition",
            new XElement("title", $"Import {Path.GetFileNameWithoutExtension(sourcePath)}"),
            new XElement("author", "Moria MOD Creator"),
            new XElement("description", $"Imported {selected.Count} construction(s)"));

        var modElem = new XElement("mod", new XAttribute("file", relPath));

        foreach (var entry in selected)
        {
            modElem.Add(new XElement("change",
                new XAttribute("item", entry.Name),
                new XAttribute("property", "EnabledState"),
                new XAttribute("value", "ERowEnabledState::Live")));
        }

        defRoot.Add(modElem);

        // Save .def file
        var category = DetectCategory(sourcePath);
        var defDir = Path.Combine(_config.DefinitionsDir, category);
        Directory.CreateDirectory(defDir);

        var defFileName = $"Import_{Path.GetFileNameWithoutExtension(sourcePath)}.def";
        var defPath = Path.Combine(defDir, defFileName);

        var doc = new XDocument(new XDeclaration("1.0", "UTF-8", null), defRoot);
        doc.Save(defPath);

        StatusText.Text = $"Imported {selected.Count} construction(s) to {defPath}";
        DialogResult = true;
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }

    private static string DetectCategory(string filePath)
    {
        var normalized = filePath.Replace('\\', '/');
        if (normalized.Contains("/Building/")) return "Building";
        if (normalized.Contains("/Items/")) return "Items";
        if (normalized.Contains("/GameWorld/")) return "GameWorld";
        if (normalized.Contains("/Economy/")) return "Economy";
        return "Misc";
    }
}

class ConstructionEntry
{
    public string Name { get; init; } = "";
    public bool IsSelected { get; set; }
}
