using System.Windows;
using System.Windows.Input;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ConstructionNameDialog : Window
{
    public string? EnteredName { get; private set; }

    public ConstructionNameDialog(string? defaultName = null)
    {
        InitializeComponent();
        if (defaultName != null)
            NameBox.Text = defaultName;
        NameBox.Focus();
        NameBox.SelectAll();
    }

    private void OnOk(object sender, RoutedEventArgs e)
    {
        var name = NameBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(name))
        {
            MessageBox.Show("Please enter a name.", "Validation", MessageBoxButton.OK);
            return;
        }
        EnteredName = name;
        DialogResult = true;
        Close();
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }

    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) OnOk(sender, e);
        if (e.Key == Key.Escape) OnCancel(sender, e);
    }
}
