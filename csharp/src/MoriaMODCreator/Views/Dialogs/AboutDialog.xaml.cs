using System.Diagnostics;
using System.Windows;
using System.Windows.Input;

namespace MoriaMODCreator.Views.Dialogs;

public partial class AboutDialog : Window
{
    public AboutDialog()
    {
        InitializeComponent();
    }

    private void OnGitHubLink(object sender, MouseButtonEventArgs e)
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = "https://github.com/jbowensii/MoriaModCreator",
            UseShellExecute = true,
        });
    }

    private void OnClose(object sender, RoutedEventArgs e) => Close();
}
