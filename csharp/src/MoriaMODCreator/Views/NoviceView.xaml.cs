using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using MoriaMODCreator.ViewModels;

namespace MoriaMODCreator.Views;

public partial class NoviceView : UserControl
{
    private bool _webViewReady;

    public NoviceView()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private async void OnLoaded(object sender, RoutedEventArgs e)
    {
        // Initialize WebView2
        try
        {
            await DescriptionWebView.EnsureCoreWebView2Async();
            _webViewReady = true;

            // Disable navigation to external links
            DescriptionWebView.CoreWebView2.Settings.AreDefaultContextMenusEnabled = false;
            DescriptionWebView.CoreWebView2.Settings.AreDevToolsEnabled = false;

            // Listen for description changes
            if (DataContext is NoviceViewModel vm)
            {
                vm.PropertyChanged += OnVmPropertyChanged;
                // Render current description if any
                UpdateHtmlDescription(vm.SelectedModDescription);
            }
        }
        catch
        {
            // WebView2 runtime not installed — keep using plain text fallback
            _webViewReady = false;
        }
    }

    private void OnVmPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(NoviceViewModel.SelectedModDescription)) return;
        if (sender is NoviceViewModel vm)
            UpdateHtmlDescription(vm.SelectedModDescription);
    }

    private void UpdateHtmlDescription(string description)
    {
        if (!_webViewReady || string.IsNullOrEmpty(description))
        {
            DescriptionWebView.Visibility = Visibility.Collapsed;
            DescriptionFallback.Visibility = Visibility.Visible;
            return;
        }

        // Check if description contains any HTML tags
        var hasHtml = description.Contains('<') && description.Contains('>');
        if (!hasHtml)
        {
            // Plain text — use fallback for better performance
            DescriptionWebView.Visibility = Visibility.Collapsed;
            DescriptionFallback.Visibility = Visibility.Visible;
            return;
        }

        // Render HTML with dark theme styling matching the app
        var html = WrapInDarkHtml(description);
        DescriptionWebView.NavigateToString(html);
        DescriptionWebView.Visibility = Visibility.Visible;
        DescriptionFallback.Visibility = Visibility.Collapsed;
    }

    private static string WrapInDarkHtml(string body)
    {
        return $$"""
            <!DOCTYPE html>
            <html>
            <head>
            <style>
                body {
                    background-color: #2d2d44;
                    color: #e0e0e0;
                    font-family: 'Segoe UI', sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    margin: 0;
                    padding: 12px;
                }
                a { color: #3b8ed0; }
                h1, h2, h3 { color: #FFD700; margin-top: 16px; }
                ul, ol { padding-left: 20px; }
                li { margin-bottom: 4px; }
                code { background: #1a1a2e; padding: 2px 6px; border-radius: 3px; font-size: 13px; }
                pre { background: #1a1a2e; padding: 10px; border-radius: 4px; overflow-x: auto; }
                table { border-collapse: collapse; width: 100%; }
                th, td { border: 1px solid #4d4d4d; padding: 6px 10px; text-align: left; }
                th { background: #1a1a2e; color: #FFD700; }
                img { max-width: 100%; height: auto; }
                hr { border: none; border-top: 1px solid #4d4d4d; margin: 12px 0; }
            </style>
            </head>
            <body>
            {{body}}
            </body>
            </html>
            """;
    }
}
