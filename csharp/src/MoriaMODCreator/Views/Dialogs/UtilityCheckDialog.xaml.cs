using System.IO;
using System.Windows;
using System.Windows.Media;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class UtilityCheckDialog : Window
{
    public UtilityCheckDialog()
    {
        InitializeComponent();
        CheckUtilities();
    }

    private void CheckUtilities()
    {
        var config = App.Services.GetRequiredService<ConfigService>();
        var utilities = new[]
        {
            new UtilityInfo("retoc.exe", config.RetocExePath, "IoStore pak operations"),
            new UtilityInfo("UAssetGUI.exe", config.UAssetGuiExePath, "JSON ↔ uasset conversion"),
            new UtilityInfo("FModel.exe",
                Path.Combine(config.UtilitiesDir, Constants.FModelExe), "Asset viewer (optional)"),
        };

        var results = new List<UtilityCheckResult>();
        int found = 0;

        foreach (var util in utilities)
        {
            var exists = File.Exists(util.Path);
            if (exists) found++;

            results.Add(new UtilityCheckResult
            {
                Icon = exists ? "✅" : "❌",
                Name = $"{util.Name} — {util.Description}",
                Path = util.Path,
                StatusText = exists ? "Found" : "Missing",
                StatusColor = exists
                    ? new SolidColorBrush(Colors.LimeGreen)
                    : new SolidColorBrush(Colors.Red),
            });
        }

        UtilityList.ItemsSource = results;
        StatusText.Text = found == utilities.Length
            ? "All required utilities found!"
            : $"{found}/{utilities.Length} utilities found. Missing utilities may limit functionality.";
    }

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    /// <summary>Check if all required utilities exist (static helper).</summary>
    public static bool CheckUtilitiesExist()
    {
        var config = App.Services.GetRequiredService<ConfigService>();
        return File.Exists(config.RetocExePath) && File.Exists(config.UAssetGuiExePath);
    }

    /// <summary>Get list of missing utilities.</summary>
    public static List<string> GetMissingUtilities()
    {
        var config = App.Services.GetRequiredService<ConfigService>();
        var missing = new List<string>();
        if (!File.Exists(config.RetocExePath)) missing.Add("retoc.exe");
        if (!File.Exists(config.UAssetGuiExePath)) missing.Add("UAssetGUI.exe");
        return missing;
    }
}

record UtilityInfo(string Name, string Path, string Description);

class UtilityCheckResult
{
    public string Icon { get; init; } = "";
    public string Name { get; init; } = "";
    public string Path { get; init; } = "";
    public string StatusText { get; init; } = "";
    public SolidColorBrush StatusColor { get; init; } = new(Colors.White);
}
