using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Win32;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ConfigDialog : Window
{
    private readonly ConfigService _config;

    public ConfigDialog()
    {
        InitializeComponent();
        _config = App.Services.GetRequiredService<ConfigService>();
        LoadSettings();
    }

    private void LoadSettings()
    {
        GamePathBox.Text = _config.GetGameInstallPath() ?? "";
        TimeoutBox.Text = _config.GetValue("Settings", "build_timeout") ?? "120";
        DebugCheck.IsChecked = _config.GetValue("Debug", "debug_mode")
            ?.Equals("true", StringComparison.OrdinalIgnoreCase) ?? false;
    }

    private void OnBrowseGamePath(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFolderDialog
        {
            Title = "Select Return to Moria Install Directory",
        };
        if (dialog.ShowDialog() == true)
        {
            GamePathBox.Text = dialog.FolderName;
        }
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        _config.SetValue("Settings", "game_path", GamePathBox.Text);
        _config.SetValue("Settings", "build_timeout", TimeoutBox.Text);
        _config.SetValue("Debug", "debug_mode", DebugCheck.IsChecked == true ? "true" : "false");
        _config.Save();
        DialogResult = true;
        Close();
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
