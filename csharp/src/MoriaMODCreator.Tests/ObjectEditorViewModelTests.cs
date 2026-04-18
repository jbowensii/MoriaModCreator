using Microsoft.Extensions.Logging.Abstractions;
using MoriaMODCreator.Models;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ObjectEditorViewModelTests
{
    private static ObjectEditorViewModel CreateVm()
    {
        var cfg = new ConfigService();
        var tpl = new ObjectTemplateService(cfg, NullLogger<ObjectTemplateService>.Instance);
        var cat = new CategoryDataService(cfg, tpl, NullLogger<CategoryDataService>.Instance);
        return new ObjectEditorViewModel(cfg, tpl, cat,
            /* buildService */ null!,
            /* buildingsData */ null!,
            /* diffService */ null!);
    }

    [Fact]
    public void Ctor_PopulatesCategories()
    {
        var vm = CreateVm();
        Assert.Equal(8, vm.Categories.Count);
        Assert.Contains("Buildings", vm.Categories);
        Assert.Contains("Ores", vm.Categories);
    }

    [Fact]
    public void ApplyFilter_FiltersBySearchText()
    {
        var vm = CreateVm();
        vm.Items.Add(new CategoryItem("Sword", "Sword", [], ""));
        vm.Items.Add(new CategoryItem("Axe", "Battle Axe", [], ""));
        vm.SearchText = "sword";
        Assert.Single(vm.FilteredItems);
        Assert.Equal("Sword", vm.FilteredItems[0].RowName);
    }

    [Fact]
    public void Commands_AreGenerated()
    {
        var vm = CreateVm();
        Assert.NotNull(vm.NewItemCommand);
        Assert.NotNull(vm.SaveItemCommand);
        Assert.NotNull(vm.RevertItemCommand);
        Assert.NotNull(vm.BuildCommand);
        Assert.NotNull(vm.ChooseModNameCommand);
    }
}
