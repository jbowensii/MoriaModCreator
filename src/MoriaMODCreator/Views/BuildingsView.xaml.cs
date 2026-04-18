using System.ComponentModel;
using System.Windows;
using System.Windows.Controls;
using MoriaMODCreator.ViewModels;

namespace MoriaMODCreator.Views;

public partial class BuildingsView : UserControl
{
    private readonly Dictionary<string, Button> _categoryButtons = [];

    public BuildingsView()
    {
        InitializeComponent();
        Loaded += OnLoaded;
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        _categoryButtons["Buildings"] = BtnBuildings;
        _categoryButtons["Weapons"] = BtnWeapons;
        _categoryButtons["Armor"] = BtnArmor;
        _categoryButtons["Tools"] = BtnTools;
        _categoryButtons["Flora"] = BtnFlora;
        _categoryButtons["Loot"] = BtnLoot;
        _categoryButtons["Items"] = BtnItems;
        _categoryButtons["Ores"] = BtnOres;

        if (DataContext is BuildingsViewModel vm)
        {
            vm.PropertyChanged += OnVmPropertyChanged;
        }
    }

    private void OnVmPropertyChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName != nameof(BuildingsViewModel.SelectedCategory)) return;
        if (DataContext is not BuildingsViewModel vm) return;

        foreach (var (cat, btn) in _categoryButtons)
        {
            btn.Opacity = cat == vm.SelectedCategory ? 1.0 : 0.6;
            btn.FontWeight = cat == vm.SelectedCategory ? FontWeights.Bold : FontWeights.Normal;
        }
    }
}
