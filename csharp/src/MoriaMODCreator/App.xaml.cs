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

        // ViewModels
        services.AddTransient<MainViewModel>();

        Services = services.BuildServiceProvider();

        var mainWindow = new MainWindow
        {
            DataContext = Services.GetRequiredService<MainViewModel>()
        };
        mainWindow.Show();
    }
}
