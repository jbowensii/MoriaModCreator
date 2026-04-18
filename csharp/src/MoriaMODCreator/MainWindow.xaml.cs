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
        var catData = App.Services.GetRequiredService<CategoryDataService>();
        var buildingsData = App.Services.GetRequiredService<BuildingsDataService>();
        var buildService = App.Services.GetRequiredService<BuildService>();
        var diffService = App.Services.GetRequiredService<DiffService>();
        var templates = App.Services.GetRequiredService<ObjectTemplateService>();
        SecretsTab.DataContext = new BuildingsViewModel(config, catData, buildingsData, buildService, diffService, templates, "secrets");
        ConstructionsTab.DataContext = new BuildingsViewModel(config, catData, buildingsData, buildService, diffService, templates, "constructions");
        ObjectEditorTab.DataContext = App.Services.GetRequiredService<ObjectEditorViewModel>();
        CreateDefTab.DataContext = new DefCreatorViewModel(
            config,
            App.Services.GetRequiredService<RetocService>(),
            App.Services.GetRequiredService<UAssetService>(),
            diffService);

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
            CreateEditSecretBtn.Visibility = Visibility.Collapsed;
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
            CreateEditSecretBtn.Visibility = Visibility.Visible;
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
    private void OnConstructionsClick(object sender, RoutedEventArgs e) => SwitchToView("constructions");
    private void OnCreateDefClick(object sender, RoutedEventArgs e) => SwitchToView("create_def");
    private void OnCreateEditSecretClick(object sender, RoutedEventArgs e) => SwitchToView("create_edit_secret");

    private void OnImportClick(object sender, RoutedEventArgs e)
    {
        var dialog = new ImportDialog { Owner = this };
        dialog.ShowDialog();
        if (dialog.ImportSuccess)
            StatusText.Text = "Import completed successfully";
    }

    /// <summary>Gap #22: Show build error with copy-to-clipboard.</summary>
    public static void ShowBuildError(string detail)
    {
        var win = new Window
        {
            Title = "Build Failed",
            Width = 550,
            Height = 300,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Owner = Application.Current.MainWindow,
            Background = (System.Windows.Media.SolidColorBrush)Application.Current.FindResource("BackgroundBrush"),
        };

        var grid = new Grid { Margin = new Thickness(15) };
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });

        var header = new TextBlock
        {
            Text = "Build Failed",
            FontSize = 16,
            FontWeight = FontWeights.Bold,
            Foreground = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0xF4, 0x44, 0x44)),
            Margin = new Thickness(0, 0, 0, 10),
        };
        Grid.SetRow(header, 0);

        var textBox = new TextBox
        {
            Text = detail,
            IsReadOnly = true,
            AcceptsReturn = true,
            TextWrapping = TextWrapping.Wrap,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            FontFamily = new System.Windows.Media.FontFamily("Consolas"),
            FontSize = 12,
        };
        Grid.SetRow(textBox, 1);

        var btnPanel = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 10, 0, 0) };
        var copyBtn = new Button { Content = "Copy to Clipboard", Padding = new Thickness(12, 6, 12, 6), Margin = new Thickness(0, 0, 6, 0) };
        copyBtn.Click += (_, _) => { Clipboard.SetText(detail); };
        var okBtn = new Button { Content = "OK", Padding = new Thickness(12, 6, 12, 6) };
        okBtn.Click += (_, _) => win.Close();
        btnPanel.Children.Add(copyBtn);
        btnPanel.Children.Add(okBtn);
        Grid.SetRow(btnPanel, 2);

        grid.Children.Add(header);
        grid.Children.Add(textBox);
        grid.Children.Add(btnPanel);
        win.Content = grid;
        win.ShowDialog();
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
            case "create_def": CreateDefTab.Visibility = Visibility.Visible; break;
            case "create_edit_secret": ObjectEditorTab.Visibility = Visibility.Visible; break;
        }
    }

    private void HideAllViews()
    {
        NoviceTab.Visibility = Visibility.Collapsed;
        DefinitionsTab.Visibility = Visibility.Collapsed;
        SecretsTab.Visibility = Visibility.Collapsed;
        ConstructionsTab.Visibility = Visibility.Collapsed;
        CreateDefTab.Visibility = Visibility.Collapsed;
        ObjectEditorTab.Visibility = Visibility.Collapsed;
    }

    private void UpdateToolbarHighlight(string activeView)
    {
        ModBuilderBtn.Background = activeView == "mod_builder" ? _activeBrush : _inactiveBrush;
        SecretsBtn.Background = activeView == "secrets" ? _activeBrush : _inactiveBrush;
        CreateEditSecretBtn.Background = activeView == "create_edit_secret" ? _activeBrush : _inactiveBrush;
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
