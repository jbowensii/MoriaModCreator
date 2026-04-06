using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.ViewModels;

public partial class MainViewModel : ObservableObject
{
    private readonly ConfigService _config;

    [ObservableProperty]
    private string _title = "Moria MOD Creator";

    [ObservableProperty]
    private string _version = "2.10.0";

    [ObservableProperty]
    private int _selectedTabIndex;

    public MainViewModel(ConfigService config)
    {
        _config = config;
    }

    [RelayCommand]
    private void OpenSettings()
    {
        // TODO: Open config dialog
    }

    [RelayCommand]
    private void OpenAbout()
    {
        // TODO: Open about dialog
    }
}
