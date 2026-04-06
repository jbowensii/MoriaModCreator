// Import dialog — runs the combined import pipeline with progress display.
// Mirrors Python combined_import_dialog.py.

using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ImportDialog : Window, IDisposable
{
    private readonly CancellationTokenSource _cts = new();
    private readonly ImportService _importService;
    private bool _disposed;

    public bool ImportSuccess { get; private set; }

    public ImportDialog()
    {
        InitializeComponent();
        _importService = App.Services.GetRequiredService<ImportService>();
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Check prerequisites before starting
        var config = App.Services.GetRequiredService<ConfigService>();
        var gamePath = config.GetGameInstallPath();
        if (string.IsNullOrEmpty(gamePath) || !System.IO.Directory.Exists(gamePath))
        {
            TitleText.Text = "Configuration Required";
            StatusText.Text = "Game install path is not configured. Open Settings first.";
            FileText.Text = "";
            CancelBtn.Content = "Close";
            return;
        }

        var errors = config.ValidateConfig();
        if (errors.Count > 0)
        {
            TitleText.Text = "Configuration Issues";
            StatusText.Text = string.Join("\n", errors);
            FileText.Text = "Fix these issues in Settings, then try again.";
            CancelBtn.Content = "Close";
            return;
        }

        var progress = new Progress<ImportProgress>(p =>
        {
            // Use BeginInvoke for non-blocking UI updates
            Dispatcher.BeginInvoke(() =>
            {
                TitleText.Text = p.Title;
                StatusText.Text = p.Status;
                ProgressBar.Value = p.Progress;
                FileText.Text = $"{p.Progress:P0}";
            });
        });

        try
        {
            TitleText.Text = "Starting Import...";
            StatusText.Text = "Checking configuration...";
            FileText.Text = "";

            var result = await _importService.RunCombinedImportAsync(progress, _cts.Token);
            ImportSuccess = result.Success;

            TitleText.Text = result.Success ? "Import Complete" : "Import Failed";
            StatusText.Text = result.Message;
            ProgressBar.Value = result.Success ? 1.0 : ProgressBar.Value;
            CancelBtn.Content = "Close";
        }
        catch (OperationCanceledException)
        {
            TitleText.Text = "Import Cancelled";
            StatusText.Text = "Import was cancelled by user.";
            CancelBtn.Content = "Close";
        }
        catch (Exception ex)
        {
            TitleText.Text = "Import Error";
            StatusText.Text = $"Error: {ex.Message}";
            FileText.Text = ex.InnerException?.Message ?? "";
            CancelBtn.Content = "Close";
        }
    }

    private void OnCancel(object sender, RoutedEventArgs e)
    {
        if (CancelBtn.Content.ToString() == "Close")
        {
            DialogResult = ImportSuccess;
            Close();
        }
        else
        {
            _cts.Cancel();
            StatusText.Text = "Cancelling...";
            CancelBtn.IsEnabled = false;
        }
    }

    public void Dispose()
    {
        if (!_disposed)
        {
            _cts.Dispose();
            _disposed = true;
        }
        GC.SuppressFinalize(this);
    }

    protected override void OnClosed(EventArgs e)
    {
        Dispose();
        base.OnClosed(e);
    }
}
