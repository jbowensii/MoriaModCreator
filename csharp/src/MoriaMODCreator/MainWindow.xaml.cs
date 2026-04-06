using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;
using MoriaMODCreator.Views.Dialogs;

namespace MoriaMODCreator;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();

        // Wire up view models
        NoviceTab.DataContext = App.Services.GetRequiredService<NoviceViewModel>();
        DefinitionsTab.DataContext = App.Services.GetRequiredService<DefinitionsViewModel>();

        var config = App.Services.GetRequiredService<ConfigService>();
        SecretsTab.DataContext = new BuildingsViewModel(config, "secrets");
        ConstructionsTab.DataContext = new BuildingsViewModel(config, "constructions");
    }

    private void OnSettingsClick(object sender, RoutedEventArgs e)
    {
        // TODO: Open settings dialog
    }

    private void OnAboutClick(object sender, RoutedEventArgs e)
    {
        var dialog = new AboutDialog { Owner = this };
        dialog.ShowDialog();
    }
}

/// <summary>Static data for placeholder views.</summary>
public static class PlaceholderData
{
    public static object ObjectEditor { get; } = new { Title = "Object Editor" };
    public static object CreateDef { get; } = new { Title = "Create DEF" };
}
