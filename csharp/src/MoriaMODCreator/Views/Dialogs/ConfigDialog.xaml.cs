using System.IO;
using System.Windows;
using System.Windows.Controls;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Win32;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ConfigDialog : Window
{
    private readonly ConfigService _config;
    private readonly List<(string Name, string Path)> _installOptions;

    public ConfigDialog()
    {
        InitializeComponent();
        _config = App.Services.GetRequiredService<ConfigService>();
        _installOptions = DetectInstallOptions();
        LoadSettings();
    }

    private void LoadSettings()
    {
        // Game dropdown
        GameDropdown.Items.Clear();
        foreach (var (name, _) in _installOptions)
            GameDropdown.Items.Add(name);

        var savedType = _config.GetValue("Game", "install_type") ?? "";
        if (!string.IsNullOrEmpty(savedType))
        {
            var idx = _installOptions.FindIndex(o => o.Name == savedType);
            if (idx >= 0) GameDropdown.SelectedIndex = idx;
        }
        else if (_installOptions.Count > 0)
        {
            GameDropdown.SelectedIndex = 0;
        }

        // Directory paths
        UtilitiesBox.Text = _config.UtilitiesDir;
        OutputBox.Text = _config.OutputDir;
        MyModFilesBox.Text = _config.MyModFilesDir;
        DefinitionsBox.Text = _config.DefinitionsDir;
        FinalDestBox.Text = _config.GetValue("Settings", "final_destination")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Downloads");

        // Color scheme
        ColorSchemeDropdown.Items.Clear();
        foreach (var scheme in new[] { "Blue (Default)", "Dark Blue", "Green" })
            ColorSchemeDropdown.Items.Add(scheme);
        var colorScheme = _config.GetValue("Settings", "color_scheme") ?? "Blue (Default)";
        ColorSchemeDropdown.SelectedItem = colorScheme;
        if (ColorSchemeDropdown.SelectedIndex < 0) ColorSchemeDropdown.SelectedIndex = 0;

        // Workers
        WorkersDropdown.Items.Clear();
        for (int i = 1; i <= 10; i++)
            WorkersDropdown.Items.Add(i.ToString());
        var workers = _config.GetValue("Settings", "max_workers") ?? "4";
        WorkersDropdown.SelectedItem = workers;
        if (WorkersDropdown.SelectedIndex < 0) WorkersDropdown.SelectedIndex = 3; // default 4

        // Debug
        DebugCheck.IsChecked = _config.GetValue("Debug", "debug_mode")
            ?.Equals("true", StringComparison.OrdinalIgnoreCase) ?? false;
    }

    private void OnGameDropdownChanged(object sender, SelectionChangedEventArgs e)
    {
        if (GameDropdown.SelectedIndex < 0) return;
        var selected = _installOptions[GameDropdown.SelectedIndex];

        if (selected.Name == "Custom")
        {
            GameBrowseBtn.Visibility = Visibility.Visible;
            GamePathLabel.Text = _config.GetGameInstallPath() ?? "Click Browse to select...";
        }
        else
        {
            GameBrowseBtn.Visibility = Visibility.Collapsed;
            GamePathLabel.Text = selected.Path;
        }
    }

    // --- Browse buttons ---

    private void OnBrowseGamePath(object sender, RoutedEventArgs e) => BrowseFolder(text => GamePathLabel.Text = text);
    private void OnBrowseUtilities(object sender, RoutedEventArgs e) => BrowseFolder(text => UtilitiesBox.Text = text);
    private void OnBrowseOutput(object sender, RoutedEventArgs e) => BrowseFolder(text => OutputBox.Text = text);
    private void OnBrowseMyModFiles(object sender, RoutedEventArgs e) => BrowseFolder(text => MyModFilesBox.Text = text);
    private void OnBrowseDefinitions(object sender, RoutedEventArgs e) => BrowseFolder(text => DefinitionsBox.Text = text);
    private void OnBrowseFinalDest(object sender, RoutedEventArgs e) => BrowseFolder(text => FinalDestBox.Text = text);

    private void BrowseFolder(Action<string> setPath)
    {
        var dialog = new OpenFolderDialog { Title = "Select Directory" };
        if (dialog.ShowDialog() == true)
            setPath(dialog.FolderName);
    }

    // --- Save/Cancel ---

    private void OnSave(object sender, RoutedEventArgs e)
    {
        if (GameDropdown.SelectedIndex >= 0)
        {
            var selected = _installOptions[GameDropdown.SelectedIndex];
            _config.SetValue("Game", "install_type", selected.Name);
            _config.SetValue("Game", "game_path",
                selected.Name == "Custom" ? GamePathLabel.Text : selected.Path);
        }

        // Write to Directories section for Python compatibility
        _config.SetValue("Directories", "utilities", UtilitiesBox.Text);
        _config.SetValue("Directories", "output", OutputBox.Text);
        _config.SetValue("Directories", "mymodfiles", MyModFilesBox.Text);
        _config.SetValue("Directories", "definitions", DefinitionsBox.Text);
        _config.SetValue("Directories", "final_destination", FinalDestBox.Text);
        _config.SetValue("Settings", "color_scheme", ColorSchemeDropdown.SelectedItem?.ToString() ?? "Blue (Default)");
        _config.SetValue("Settings", "max_workers", WorkersDropdown.SelectedItem?.ToString() ?? "4");
        _config.SetValue("Debug", "debug_mode", DebugCheck.IsChecked == true ? "true" : "false");

        _config.Save();

        // Apply color scheme immediately
        var scheme = ColorSchemeDropdown.SelectedItem?.ToString() ?? "Blue (Default)";
        ConfigService.ApplyColorScheme(scheme);

        DialogResult = true;
        Close();
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }

    // --- Auto-detect game installs ---

    private static List<(string Name, string Path)> DetectInstallOptions()
    {
        var options = new List<(string, string)>();

        // Epic Games
        var epicPath = @"C:\Program Files\Epic Games\ReturnToMoria";
        if (Directory.Exists(epicPath))
            options.Add(("Epic Games", epicPath));

        // Steam
        var steamPaths = new[]
        {
            @"C:\Program Files (x86)\Steam\steamapps\common\Return to Moria",
            @"C:\Program Files\Steam\steamapps\common\Return to Moria",
        };
        foreach (var sp in steamPaths)
        {
            if (Directory.Exists(sp))
            {
                options.Add(("Steam", sp));
                break;
            }
        }

        options.Add(("Custom", ""));
        return options;
    }
}
