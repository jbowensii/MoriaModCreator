using System.Diagnostics;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media;
using Microsoft.Extensions.DependencyInjection;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;

namespace MoriaMODCreator.Views.Dialogs;

public partial class AboutDialog : Window
{
    private readonly SolidColorBrush _activeBrush = new(Color.FromRgb(0x1a, 0x5f, 0xb4));
    private readonly SolidColorBrush _inactiveBrush = new(Colors.Gray);

    public AboutDialog()
    {
        InitializeComponent();
        ShowAboutContent();
    }

    // --- Tab switching ---

    private void OnAboutTab(object sender, RoutedEventArgs e) => SwitchTab("about");
    private void OnDisclaimerTab(object sender, RoutedEventArgs e) => SwitchTab("disclaimer");
    private void OnCreditsTab(object sender, RoutedEventArgs e) => SwitchTab("credits");

    private void SwitchTab(string tab)
    {
        AboutBtn.Background = tab == "about" ? _activeBrush : _inactiveBrush;
        DisclaimerBtn.Background = tab == "disclaimer" ? _activeBrush : _inactiveBrush;
        CreditsBtn.Background = tab == "credits" ? _activeBrush : _inactiveBrush;

        ContentPanel.Children.Clear();

        switch (tab)
        {
            case "about": ShowAboutContent(); break;
            case "disclaimer": ShowDisclaimerContent(); break;
            case "credits": ShowCreditsContent(); break;
        }
    }

    // --- About tab ---

    private void ShowAboutContent()
    {
        AddText(Constants.AppName, 22, FontWeights.Bold);
        AddSpacer(5);
        AddText($"Version {Constants.AppVersion}  •  {Constants.AppDate}", 14, color: "#a0a0a0");
        AddSpacer(10);
        AddText($"Created by {Constants.AppAuthor}", 13);
        AddText("Create DEF functionality by Sqitey", 13);
        AddSpacer(15);

        // Separator
        var sep = new Border { Height = 2, Background = new SolidColorBrush(Colors.Gray), Margin = new Thickness(20, 0, 20, 0) };
        ContentPanel.Children.Add(sep);
        AddSpacer(15);

        // GitHub link
        AddClickableLink($"GitHub Repository: {Constants.GitHubUrl}", Constants.GitHubUrl, 11);
        AddSpacer(5);
        AddClickableLink("MIT License: View License", Constants.LicenseUrl, 11);
        AddSpacer(15);
        AddText("A tool for creating and managing mods for\nLord of the Rings: Return to Moria", 12, alignment: TextAlignment.Center);
    }

    // --- Disclaimer tab ---

    private void ShowDisclaimerContent()
    {
        AddText("DISCLAIMER OF WARRANTY", 18, FontWeights.Bold, color: "#c01c28");
        AddSpacer(20);
        AddText(
            "Software is provided \"as is,\" without warranties of any kind, " +
            "express or implied. Users accept all risks associated with using " +
            "the software, including its quality, performance, and accuracy.",
            13, wrap: true);
        AddSpacer(15);
        AddText("⚠️  Mods can be dangerous!", 14, FontWeights.Bold);
        AddSpacer(10);
        AddText("Please backup your game and character files often.", 13, wrap: true);
        AddSpacer(10);
        AddText(
            "If you use mods, do not report game or system crashes to the " +
            "game developers.",
            13, wrap: true);
        AddSpacer(10);
        AddText("Thank you for understanding.", 13);
    }

    // --- Credits tab ---

    private void ShowCreditsContent()
    {
        AddText("Credits & Acknowledgments", 18, FontWeights.Bold);
        AddSpacer(20);

        // Community contributors
        AddText("Community Contributors:", 13, FontWeights.Bold);
        AddSpacer(5);

        var contributors = CollectContributors();
        if (contributors.Count > 0)
        {
            foreach (var name in contributors)
                AddText($"  • {name}", 12);
        }
        else
        {
            AddText("  No prebuilt mod files found", 12, color: "#808080");
        }

        AddSpacer(15);
        AddSeparator();
        AddSpacer(10);

        // Third-party tools
        AddText("Third-Party Tools:", 13, FontWeights.Bold);
        AddSpacer(5);
        AddClickableLink("  • FModel - UE4/UE5 asset viewer", "https://fmodel.app/", 12);
        AddClickableLink("  • UAssetGUI - Unreal Engine asset editor", "https://github.com/atenfyr/UAssetGUI", 12);
        AddClickableLink("  • retoc - Table of contents rebuilder", "https://github.com/trumank/retoc/releases", 12);
        AddClickableLink("  • ZenTools - Zen asset tools", "https://github.com/WistfulHopes/ZenTools-UE4", 12);

        AddSpacer(15);
        AddSeparator();
        AddSpacer(10);

        // Libraries
        AddText("Libraries:", 13, FontWeights.Bold);
        AddSpacer(5);
        AddText("  • .NET / WPF - UI framework", 12);
        AddText("  • CommunityToolkit.Mvvm - MVVM helpers", 12);
        AddText("  • System.Text.Json - JSON processing", 12);
    }

    // --- Helpers ---

    private void AddText(string text, double fontSize, FontWeight? weight = null,
        string? color = null, TextAlignment alignment = TextAlignment.Left, bool wrap = false)
    {
        var tb = new TextBlock
        {
            Text = text,
            FontSize = fontSize,
            FontWeight = weight ?? FontWeights.Normal,
            Foreground = color != null
                ? new SolidColorBrush((Color)ColorConverter.ConvertFromString(color))
                : (SolidColorBrush)FindResource("TextBrush"),
            TextAlignment = alignment,
            TextWrapping = wrap ? TextWrapping.Wrap : TextWrapping.NoWrap,
            Margin = new Thickness(0, 2, 0, 2),
        };
        ContentPanel.Children.Add(tb);
    }

    private void AddSpacer(double height)
    {
        ContentPanel.Children.Add(new Border { Height = height });
    }

    private void AddSeparator()
    {
        ContentPanel.Children.Add(new Border
        {
            Height = 1,
            Background = new SolidColorBrush(Colors.Gray),
            Margin = new Thickness(10, 0, 10, 0),
        });
    }

    private void AddClickableLink(string text, string url, double fontSize)
    {
        var tb = new TextBlock
        {
            FontSize = fontSize,
            Foreground = new SolidColorBrush((Color)ColorConverter.ConvertFromString("#3584e4")),
            Cursor = Cursors.Hand,
            TextDecorations = TextDecorations.Underline,
            Margin = new Thickness(0, 2, 0, 2),
            Text = text,
        };
        tb.MouseDown += (_, _) => Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
        ContentPanel.Children.Add(tb);
    }

    private List<string> CollectContributors()
    {
        var config = App.Services.GetRequiredService<ConfigService>();
        var dir = config.PrebuiltModfilesDir;
        var authors = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);

        if (!Directory.Exists(dir)) return authors.ToList();

        foreach (var iniFile in Directory.GetFiles(dir, "*.ini"))
        {
            foreach (var line in File.ReadAllLines(iniFile))
            {
                var trimmed = line.Trim();
                if (trimmed.StartsWith("Authors", StringComparison.OrdinalIgnoreCase) ||
                    trimmed.StartsWith("Author", StringComparison.OrdinalIgnoreCase))
                {
                    var eqIdx = trimmed.IndexOf('=');
                    if (eqIdx < 0) continue;
                    var value = trimmed[(eqIdx + 1)..].Trim();
                    foreach (var name in value.Split(','))
                    {
                        var clean = name.Trim();
                        // Strip parenthetical notes
                        var parenIdx = clean.IndexOf('(');
                        if (parenIdx > 0)
                            clean = clean[..parenIdx].Trim();
                        if (!string.IsNullOrWhiteSpace(clean))
                            authors.Add(clean);
                    }
                }
            }
        }

        return authors.ToList();
    }

    private void OnGitHubLink(object sender, MouseButtonEventArgs e)
    {
        Process.Start(new ProcessStartInfo(Constants.GitHubUrl) { UseShellExecute = true });
    }

    private void OnClose(object sender, RoutedEventArgs e) => Close();
}
