using System.IO;
using System.Windows;
using Microsoft.Win32;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

/// <summary>
/// Dialog that prompts the user to provide a Nexus Mods Secrets ZIP file.
/// GitHub JSON download happens automatically in ImportService after this.
/// </summary>
public partial class SecretsDownloadDialog : Window
{
    private readonly ConfigService _config;

    /// <summary>Path to the ZIP file the user selected, or null if skipped.</summary>
    public string? SelectedZipPath { get; private set; }

    public SecretsDownloadDialog(ConfigService config)
    {
        InitializeComponent();
        _config = config;
    }

    private void OnBrowse(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Title = "Select Secrets of Khazad-Dum ZIP File",
            Filter = "ZIP files (*.zip)|*.zip|All files (*.*)|*.*",
            Multiselect = false,
        };

        if (dialog.ShowDialog() == true)
        {
            CopyZipToSecrets(dialog.FileName);
        }
    }

    private void OnDragOver(object sender, DragEventArgs e)
    {
        if (e.Data.GetDataPresent(DataFormats.FileDrop))
        {
            var files = (string[])e.Data.GetData(DataFormats.FileDrop)!;
            e.Effects = files.Any(f => f.EndsWith(".zip", StringComparison.OrdinalIgnoreCase))
                ? DragDropEffects.Copy
                : DragDropEffects.None;
        }
        else
        {
            e.Effects = DragDropEffects.None;
        }
        e.Handled = true;
    }

    private void OnDrop(object sender, DragEventArgs e)
    {
        if (!e.Data.GetDataPresent(DataFormats.FileDrop)) return;

        var files = (string[])e.Data.GetData(DataFormats.FileDrop)!;
        var zipFile = files.FirstOrDefault(f => f.EndsWith(".zip", StringComparison.OrdinalIgnoreCase));

        if (zipFile == null)
        {
            StatusText.Text = "No ZIP file found in drop. Please drop a .zip file.";
            return;
        }

        CopyZipToSecrets(zipFile);
    }

    private void CopyZipToSecrets(string sourcePath)
    {
        try
        {
            var secretsDir = _config.SecretsSourceDir;
            Directory.CreateDirectory(secretsDir);
            var destPath = Path.Combine(secretsDir, Path.GetFileName(sourcePath));
            File.Copy(sourcePath, destPath, overwrite: true);

            ZipPathBox.Text = destPath;
            SelectedZipPath = destPath;
            ImportBtn.IsEnabled = true;

            var sizeKb = new FileInfo(destPath).Length / 1024;
            StatusText.Text = $"Copied: {Path.GetFileName(sourcePath)} ({sizeKb:N0} KB)\n" +
                              "Click 'Continue' to proceed. GitHub JSON data will be downloaded automatically.";
        }
        catch (Exception ex)
        {
            StatusText.Text = $"Error copying ZIP: {ex.Message}";
        }
    }

    private void OnImport(object sender, RoutedEventArgs e)
    {
        if (SelectedZipPath != null)
            DialogResult = true;
    }

    private void OnSkip(object sender, RoutedEventArgs e)
    {
        SelectedZipPath = null;
        DialogResult = true;
    }
}
