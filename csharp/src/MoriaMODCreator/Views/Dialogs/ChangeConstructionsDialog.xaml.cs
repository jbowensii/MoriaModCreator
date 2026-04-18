using System.IO;
using System.Windows;
using System.Windows.Input;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ChangeConstructionsDialog : Window
{
    private readonly ConfigService _config;
    private readonly string _mode;

    public string? SelectedPrefix { get; private set; }

    public ChangeConstructionsDialog(string mode, ConfigService config)
    {
        InitializeComponent();
        _mode = mode;
        _config = config;
        Title = mode == "secrets" ? "Change Secrets Prefix" : "Change Constructions Prefix";
        LoadPrefixes();
    }

    private void LoadPrefixes()
    {
        var baseDir = _mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        if (!Directory.Exists(baseDir)) return;
        foreach (var dir in Directory.GetDirectories(baseDir))
            ExistingCombo.Items.Add(Path.GetFileName(dir));
    }

    private void OnSet(object sender, RoutedEventArgs e)
    {
        var typed = NewPrefixBox.Text?.Trim();
        var picked = ExistingCombo.SelectedItem as string;
        var chosen = !string.IsNullOrEmpty(typed) ? typed : picked;
        if (string.IsNullOrWhiteSpace(chosen))
        {
            MessageBox.Show(this, "Enter a new prefix or select an existing one.",
                Title, MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        var baseDir = _mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        if (chosen.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0
            || chosen.Contains("..")
            || Path.IsPathRooted(chosen))
        {
            MessageBox.Show(this, "Invalid prefix name (no path separators, '..', or rooted paths).",
                Title, MessageBoxButton.OK, MessageBoxImage.Warning);
            return;
        }
        Directory.CreateDirectory(Path.Combine(baseDir, chosen));
        SelectedPrefix = chosen;
        DialogResult = true;
        Close();
    }

    private void OnDelete(object sender, RoutedEventArgs e)
    {
        var picked = ExistingCombo.SelectedItem as string;
        if (string.IsNullOrEmpty(picked)) return;
        var result = MessageBox.Show(this, $"Delete change set '{picked}'?",
            "Confirm Delete", MessageBoxButton.YesNo, MessageBoxImage.Warning);
        if (result != MessageBoxResult.Yes) return;
        var baseDir = _mode == "secrets" ? _config.ChangeSecretsDir : _config.ChangeConstructionsDir;
        var target = Path.Combine(baseDir, picked);
        var full = Path.GetFullPath(target);
        var root = Path.GetFullPath(baseDir);
        if (!full.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            return;
        if (Directory.Exists(target)) Directory.Delete(target, recursive: true);
        ExistingCombo.Items.Remove(picked);
        ExistingCombo.SelectedItem = null;
        NewPrefixBox.Text = "";
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        DialogResult = false;
        Close();
    }

    private void OnNewPrefixKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) OnSet(sender, e);
    }
}
