using System.Windows;
using System.Windows.Controls;
using MoriaMODCreator.ViewModels;

namespace MoriaMODCreator.Views;

public partial class DefinitionsView : UserControl
{
    public DefinitionsView()
    {
        InitializeComponent();
    }

    private void OnClearSearch(object sender, RoutedEventArgs e)
    {
        if (DataContext is DefinitionsViewModel vm)
            vm.SearchText = "";
    }
}
