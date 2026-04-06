using System.IO;
using System.Windows;
using System.Windows.Input;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ModNameDialog : Window
{
    private readonly ConfigService _config;
    public string? SelectedModName { get; private set; }

    public ModNameDialog()
    {
        InitializeComponent();
        _config = App.Services.GetRequiredService<ConfigService>();
        RefreshModList();
    }

    private void RefreshModList()
    {
        var modsDir = _config.MyModFilesDir;
        var mods = new List<string>();
        if (Directory.Exists(modsDir))
        {
            foreach (var dir in Directory.GetDirectories(modsDir))
                mods.Add(Path.GetFileName(dir));
        }
        mods.Sort();
        ModList.ItemsSource = mods;
    }

    private void OnSelectMod(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button btn && btn.Content is string modName)
        {
            SelectedModName = modName;
            DialogResult = true;
            Close();
        }
    }

    private void OnDeleteMod(object sender, RoutedEventArgs e)
    {
        if (sender is System.Windows.Controls.Button btn && btn.Tag is string modName)
        {
            var result = MessageBox.Show(
                $"Delete mod '{modName}' and all its files?",
                "Confirm Delete", MessageBoxButton.YesNo, MessageBoxImage.Warning);

            if (result == MessageBoxResult.Yes)
            {
                var modDir = Path.Combine(_config.MyModFilesDir, modName);
                if (Directory.Exists(modDir))
                    Directory.Delete(modDir, true);
                RefreshModList();
            }
        }
    }

    private void OnCreateMod(object sender, RoutedEventArgs e)
    {
        var name = NewModNameBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(name)) return;

        var modDir = Path.Combine(_config.MyModFilesDir, name);
        Directory.CreateDirectory(modDir);

        SelectedModName = name;
        DialogResult = true;
        Close();
    }

    private void OnNewModKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter)
            OnCreateMod(sender, e);
    }

    private void OnClose(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }
}
