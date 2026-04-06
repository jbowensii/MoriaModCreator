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

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var services = new ServiceCollection();

        // Logging — debug output for development, file logging can be added later
        services.AddLogging(builder =>
        {
            builder.SetMinimumLevel(LogLevel.Debug);
            builder.AddDebug();
        });

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

        Services = services.BuildServiceProvider();

        var mainWindow = new MainWindow();
        mainWindow.Show();
    }
}
