using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;
using MoriaMODCreator.Views.Dialogs;

namespace MoriaMODCreator;

public partial class MainWindow : Window
{
    private string _currentMode = "Novice";
    private string _currentView = "mod_builder";
    private readonly SolidColorBrush _activeBrush;
    private readonly SolidColorBrush _inactiveBrush;

    public MainWindow()
    {
        InitializeComponent();

        _activeBrush = (SolidColorBrush)FindResource("PrimaryBrush");
        _inactiveBrush = (SolidColorBrush)FindResource("ButtonInactiveBrush");

        // Wire up view models
        NoviceTab.DataContext = App.Services.GetRequiredService<NoviceViewModel>();
        DefinitionsTab.DataContext = App.Services.GetRequiredService<DefinitionsViewModel>();

        var config = App.Services.GetRequiredService<ConfigService>();
        SecretsTab.DataContext = new BuildingsViewModel(config, "secrets");
        ConstructionsTab.DataContext = new BuildingsViewModel(config, "constructions");
        ObjectEditorTab.DataContext = new { Title = "Object Editor" };
        CreateDefTab.DataContext = new { Title = "Create DEF" };

        // Apply initial mode
        ApplyMode("Novice");
    }

    // --- Mode toggle ---

    private void OnNoviceToggle(object sender, RoutedEventArgs e)
    {
        NoviceToggle.IsChecked = true;
        AdvancedToggle.IsChecked = false;
        ApplyMode("Novice");
    }

    private void OnAdvancedToggle(object sender, RoutedEventArgs e)
    {
        AdvancedToggle.IsChecked = true;
        NoviceToggle.IsChecked = false;
        ApplyMode("Advanced");
    }

    private void ApplyMode(string mode)
    {
        _currentMode = mode;
        ApplyToolbarMode(mode);
        ApplyViewMode(mode);
    }

    private void ApplyToolbarMode(string mode)
    {
        if (mode == "Novice")
        {
            // Hide all nav buttons, show only Import
            ModBuilderBtn.Visibility = Visibility.Collapsed;
            SecretsBtn.Visibility = Visibility.Collapsed;
            ObjectEditorBtn.Visibility = Visibility.Collapsed;
            ConstructionsBtn.Visibility = Visibility.Collapsed;
            CreateDefBtn.Visibility = Visibility.Collapsed;
            ToolbarSep.Visibility = Visibility.Collapsed;
            ImportBtn.Visibility = Visibility.Visible;
        }
        else
        {
            // Show all nav buttons + Import
            ModBuilderBtn.Visibility = Visibility.Visible;
            SecretsBtn.Visibility = Visibility.Visible;
            ObjectEditorBtn.Visibility = Visibility.Visible;
            ConstructionsBtn.Visibility = Visibility.Visible;
            CreateDefBtn.Visibility = Visibility.Visible;
            ToolbarSep.Visibility = Visibility.Visible;
            ImportBtn.Visibility = Visibility.Visible;
        }
    }

    private void ApplyViewMode(string mode)
    {
        HideAllViews();
        if (mode == "Novice")
        {
            NoviceTab.Visibility = Visibility.Visible;
        }
        else
        {
            ShowView(_currentView);
        }
    }

    // --- Toolbar button clicks ---

    private void OnModBuilderClick(object sender, RoutedEventArgs e) => SwitchToView("mod_builder");
    private void OnSecretsClick(object sender, RoutedEventArgs e) => SwitchToView("secrets");
    private void OnObjectEditorClick(object sender, RoutedEventArgs e) => SwitchToView("object_editor");
    private void OnConstructionsClick(object sender, RoutedEventArgs e) => SwitchToView("constructions");
    private void OnCreateDefClick(object sender, RoutedEventArgs e) => SwitchToView("create_def");

    private void OnImportClick(object sender, RoutedEventArgs e)
    {
        var dialog = new ImportDialog { Owner = this };
        dialog.ShowDialog();
        if (dialog.ImportSuccess)
            StatusText.Text = "Import completed successfully";
    }

    private void SwitchToView(string view)
    {
        _currentView = view;
        HideAllViews();
        ShowView(view);
        UpdateToolbarHighlight(view);
    }

    private void ShowView(string view)
    {
        switch (view)
        {
            case "mod_builder": DefinitionsTab.Visibility = Visibility.Visible; break;
            case "secrets": SecretsTab.Visibility = Visibility.Visible; break;
            case "constructions": ConstructionsTab.Visibility = Visibility.Visible; break;
            case "object_editor": ObjectEditorTab.Visibility = Visibility.Visible; break;
            case "create_def": CreateDefTab.Visibility = Visibility.Visible; break;
        }
    }

    private void HideAllViews()
    {
        NoviceTab.Visibility = Visibility.Collapsed;
        DefinitionsTab.Visibility = Visibility.Collapsed;
        SecretsTab.Visibility = Visibility.Collapsed;
        ConstructionsTab.Visibility = Visibility.Collapsed;
        ObjectEditorTab.Visibility = Visibility.Collapsed;
        CreateDefTab.Visibility = Visibility.Collapsed;
    }

    private void UpdateToolbarHighlight(string activeView)
    {
        ModBuilderBtn.Background = activeView == "mod_builder" ? _activeBrush : _inactiveBrush;
        SecretsBtn.Background = activeView == "secrets" ? _activeBrush : _inactiveBrush;
        ObjectEditorBtn.Background = activeView == "object_editor" ? _activeBrush : _inactiveBrush;
        ConstructionsBtn.Background = activeView == "constructions" ? _activeBrush : _inactiveBrush;
        CreateDefBtn.Background = activeView == "create_def" ? _activeBrush : _inactiveBrush;
    }

    // --- Settings / About ---

    private void OnSettingsClick(object sender, RoutedEventArgs e)
    {
        var dialog = new ConfigDialog { Owner = this };
        dialog.ShowDialog();
    }

    private void OnAboutClick(object sender, RoutedEventArgs e)
    {
        var dialog = new AboutDialog { Owner = this };
        dialog.ShowDialog();
    }
}
