// Moria MOD Creator — C# / WPF Edition
// Application entry point and dependency injection container.
//
// Converted from Python/CustomTkinter to C#/WPF for improved performance
// with large JSON files (33MB+) and in-process UAssetAPI integration.
//
// Architecture: MVVM with CommunityToolkit.Mvvm
// DI Container: Microsoft.Extensions.DependencyInjection
//
// Original Python version: John B Owens II (Mereak Firmaxe)
// C# conversion: Claude Opus 4.6

using System.IO;
using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;

namespace MoriaMODCreator;

/// <summary>
/// Application entry point. Configures the DI container with all services
/// and view models, then launches the main window.
/// </summary>
public partial class App : Application
{
    /// <summary>Global service provider for dependency injection.</summary>
    public static IServiceProvider Services { get; private set; } = null!;

    private static string? _logFilePath;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Global exception handlers — catch and display all unhandled crashes
        DispatcherUnhandledException += (_, args) =>
        {
            LogCrash(args.Exception);
            ShowCrashDialog(args.Exception);
            args.Handled = true;
        };
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
        {
            if (args.ExceptionObject is Exception ex)
            {
                LogCrash(ex);
                // Must dispatch to UI thread — this handler can fire on background threads
                Current?.Dispatcher?.Invoke(() => ShowCrashDialog(ex));
            }
        };
        TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            LogCrash(args.Exception);
            Current?.Dispatcher?.BeginInvoke(() => ShowCrashDialog(args.Exception));
            args.SetObserved();
        };

        var services = new ServiceCollection();

        // Logging — debug output + file logging (Gap #26)
        var logDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "MoriaMODCreator");
        Directory.CreateDirectory(logDir);
        var logFilePath = Path.Combine(logDir, "MoriaMODCreator.log");

        services.AddLogging(builder =>
        {
            builder.SetMinimumLevel(LogLevel.Debug);
            builder.AddDebug();
            // File logging — all ILogger calls go to MoriaMODCreator.log
            builder.AddProvider(new Services.FileLoggerProvider(logFilePath, LogLevel.Information));
        });

        _logFilePath = logFilePath;

        // Write startup marker to log file
        try
        {
            File.AppendAllText(logFilePath,
                $"\n=== Moria MOD Creator v{Models.Constants.AppVersion} started {DateTime.Now:yyyy-MM-dd HH:mm:ss} ===\n");
        }
        catch { /* ignore log file errors */ }

        // Core services — mirrors Python src/ modules
        services.AddSingleton<ConfigService>();          // config.py — app paths, INI read/write
        services.AddSingleton<RetocService>();            // retoc subprocess wrapper (IoStore operations)
        services.AddSingleton<UAssetService>();            // UAssetGUI subprocess wrapper (JSON ↔ uasset)
        services.AddSingleton<DefinitionService>();        // definition_manager.py — .def XML parsing
        services.AddSingleton<JsonDataService>();          // DataTable JSON operations (rows, tags, NameMap)
        services.AddSingleton<BuildService>();             // build_manager.py — Phases A through G
        services.AddSingleton<PrebuiltModService>();       // Prebuilt mod .ini file parsing (Novice mode)
        services.AddSingleton<ImportService>();             // combined_import_dialog.py — game + secrets import
        services.AddSingleton<ObjectTemplateService>();     // object_templates.py — row CRUD, field extraction
        services.AddSingleton<DefinitionManagerService>(); // Checkbox state persistence for mod selections
        services.AddSingleton<CategoryDataService>();      // Category-based data loading for Change views
        services.AddSingleton<DiffService>();               // .def XML generation from DataTable diffs
        services.AddSingleton<BuildingsDataService>();     // Cache management, edit manifests, display names

        // View models — BuildingsViewModel created in MainWindow with mode parameter
        services.AddTransient<NoviceViewModel>();
        services.AddTransient<DefinitionsViewModel>();
        services.AddTransient<ObjectEditorViewModel>();

        Services = services.BuildServiceProvider();

        // Apply saved color scheme on startup
        var configSvc = Services.GetRequiredService<ConfigService>();
        ConfigService.ApplyColorScheme(configSvc.GetColorScheme());

        var mainWindow = new MainWindow();
        mainWindow.Show();
    }

    /// <summary>Log crash to the MoriaMODCreator.log file.</summary>
    private static void LogCrash(Exception ex)
    {
        try
        {
            if (_logFilePath == null) return;
            var timestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
            var entry = $"\n=== CRASH {timestamp} ===\n{ex}\n";
            File.AppendAllText(_logFilePath, entry);
        }
        catch { /* can't log the crash — nothing we can do */ }
    }

    /// <summary>Show crash dialog with full exception details and Copy to Clipboard button.</summary>
    private static void ShowCrashDialog(Exception ex)
    {
        try
        {
            var detail = $"{ex.GetType().Name}: {ex.Message}\n\n{ex.StackTrace}";
            if (ex.InnerException != null)
                detail += $"\n\n--- Inner Exception ---\n{ex.InnerException.GetType().Name}: {ex.InnerException.Message}\n{ex.InnerException.StackTrace}";

            var win = new Window
            {
                Title = "Moria MOD Creator — Crash Report",
                Width = 700,
                Height = 450,
                WindowStartupLocation = WindowStartupLocation.CenterScreen,
                Background = new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0x1a, 0x1a, 0x2e)),
            };

            var grid = new System.Windows.Controls.Grid { Margin = new Thickness(15) };
            grid.RowDefinitions.Add(new System.Windows.Controls.RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new System.Windows.Controls.RowDefinition { Height = GridLength.Auto });
            grid.RowDefinitions.Add(new System.Windows.Controls.RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            grid.RowDefinitions.Add(new System.Windows.Controls.RowDefinition { Height = GridLength.Auto });

            var header = new System.Windows.Controls.TextBlock
            {
                Text = "An unhandled error occurred",
                FontSize = 18,
                FontWeight = FontWeights.Bold,
                Foreground = new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xFF, 0x44, 0x44)),
                Margin = new Thickness(0, 0, 0, 5),
            };
            System.Windows.Controls.Grid.SetRow(header, 0);

            var logNote = new System.Windows.Controls.TextBlock
            {
                Text = _logFilePath != null ? $"Logged to: {_logFilePath}" : "",
                FontSize = 11,
                Foreground = new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xa0, 0xa0, 0xa0)),
                Margin = new Thickness(0, 0, 0, 10),
            };
            System.Windows.Controls.Grid.SetRow(logNote, 1);

            var textBox = new System.Windows.Controls.TextBox
            {
                Text = detail,
                IsReadOnly = true,
                AcceptsReturn = true,
                TextWrapping = TextWrapping.Wrap,
                VerticalScrollBarVisibility = System.Windows.Controls.ScrollBarVisibility.Auto,
                FontFamily = new System.Windows.Media.FontFamily("Consolas"),
                FontSize = 12,
                Background = new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0x2d, 0x2d, 0x44)),
                Foreground = new System.Windows.Media.SolidColorBrush(
                    System.Windows.Media.Color.FromRgb(0xe0, 0xe0, 0xe0)),
                BorderThickness = new Thickness(1),
                Padding = new Thickness(8),
            };
            System.Windows.Controls.Grid.SetRow(textBox, 2);

            var btnPanel = new System.Windows.Controls.StackPanel
            {
                Orientation = System.Windows.Controls.Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
                Margin = new Thickness(0, 10, 0, 0),
            };
            System.Windows.Controls.Grid.SetRow(btnPanel, 3);

            var copyBtn = new System.Windows.Controls.Button
            {
                Content = "Copy to Clipboard",
                Padding = new Thickness(12, 6, 12, 6),
                Margin = new Thickness(0, 0, 6, 0),
            };
            copyBtn.Click += (_, _) => Clipboard.SetText(detail);

            var closeBtn = new System.Windows.Controls.Button
            {
                Content = "Close",
                Padding = new Thickness(12, 6, 12, 6),
            };
            closeBtn.Click += (_, _) => win.Close();

            btnPanel.Children.Add(copyBtn);
            btnPanel.Children.Add(closeBtn);

            grid.Children.Add(header);
            grid.Children.Add(logNote);
            grid.Children.Add(textBox);
            grid.Children.Add(btnPanel);
            win.Content = grid;
            win.ShowDialog();
        }
        catch
        {
            // Last resort — MessageBox if the crash dialog itself fails
            MessageBox.Show($"CRASH: {ex.Message}\n\n{ex.StackTrace}",
                "Moria MOD Creator — Crash", MessageBoxButton.OK, MessageBoxImage.Error);
        }
    }
}
