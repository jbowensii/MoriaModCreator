using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;

namespace MoriaMODCreator;

public partial class App : Application
{
    public static IServiceProvider Services { get; private set; } = null!;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var services = new ServiceCollection();

        // Logging
        services.AddLogging(builder =>
        {
            builder.SetMinimumLevel(LogLevel.Debug);
            builder.AddDebug();
        });

        // Services
        services.AddSingleton<ConfigService>();
        services.AddSingleton<RetocService>();
        services.AddSingleton<UAssetService>();
        services.AddSingleton<DefinitionService>();
        services.AddSingleton<JsonDataService>();
        services.AddSingleton<BuildService>();
        services.AddSingleton<PrebuiltModService>();
        services.AddSingleton<ImportService>();
        services.AddSingleton<ObjectTemplateService>();
        services.AddSingleton<DefinitionManagerService>();

        // ViewModels
        services.AddTransient<MainViewModel>();
        services.AddTransient<NoviceViewModel>();
        services.AddTransient<DefinitionsViewModel>();
        services.AddTransient(sp => new BuildingsViewModel(
            sp.GetRequiredService<ConfigService>(), "secrets"));
        services.AddTransient(sp =>
        {
            // Named instance for constructions — use a factory key
            var vm = new BuildingsViewModel(
                sp.GetRequiredService<ConfigService>(), "constructions");
            return vm;
        });

        Services = services.BuildServiceProvider();

        var mainWindow = new MainWindow();
        mainWindow.Show();
    }
}
