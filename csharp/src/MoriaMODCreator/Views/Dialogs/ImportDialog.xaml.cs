using System.Windows;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class ImportDialog : Window, IDisposable
{
    private readonly CancellationTokenSource _cts = new();
    private bool _disposed;
    private readonly ImportService _importService;

    public bool ImportSuccess { get; private set; }

    public ImportDialog()
    {
        InitializeComponent();
        _importService = App.Services.GetRequiredService<ImportService>();
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        var progress = new Progress<ImportProgress>(p =>
        {
            Dispatcher.Invoke(() =>
            {
                TitleText.Text = p.Title;
                StatusText.Text = p.Status;
                ProgressBar.Value = p.Progress;
            });
        });

        try
        {
            var result = await _importService.RunCombinedImportAsync(progress, _cts.Token);
            ImportSuccess = result.Success;
            StatusText.Text = result.Message;
            CancelBtn.Content = "Close";
        }
        catch (OperationCanceledException)
        {
            StatusText.Text = "Import cancelled";
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
