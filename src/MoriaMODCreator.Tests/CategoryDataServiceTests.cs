using System.IO;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging.Abstractions;
using MoriaMODCreator.Services;
using Xunit;

namespace MoriaMODCreator.Tests;

public class CategoryDataServiceTests
{
    private readonly ConfigService _config = new();
    private readonly ObjectTemplateService _templates;
    private readonly CategoryDataService _service;

    public CategoryDataServiceTests()
    {
        _templates = new ObjectTemplateService(_config, NullLogger<ObjectTemplateService>.Instance);
        _service = new CategoryDataService(_config, _templates, NullLogger<CategoryDataService>.Instance);
    }

    // =========================================================================
    // CategoryItem
    // =========================================================================

    [Fact]
    public void CategoryItem_IsChecked_IsObservable()
    {
        var item = new CategoryItem("TestRow", "Test Display", [], "test.json");
        bool changed = false;
        item.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(CategoryItem.IsChecked)) changed = true; };

        item.IsChecked = true;
        Assert.True(changed);
        Assert.True(item.IsChecked);
    }

    [Fact]
    public void CategoryItem_IsVisible_UpdatesEyeIcon()
    {
        var item = new CategoryItem("TestRow", "Test", [], "test.json");
        Assert.True(item.IsVisible);
        Assert.Equal("\U0001F441", item.EyeIcon); // eye visible

        item.IsVisible = false;
        Assert.Equal("\u2014", item.EyeIcon); // em dash hidden
    }

    [Fact]
    public void CategoryItem_DefaultConstructor_Works()
    {
        var item = new CategoryItem();
        Assert.Equal("", item.RowName);
        Assert.Equal("", item.DisplayName);
        Assert.True(item.IsVisible);
        Assert.False(item.IsChecked);
    }

    // =========================================================================
    // CategoryPaths
    // =========================================================================

    [Fact]
    public void SecretsPaths_ContainsAll8Categories()
    {
        var paths = CategoryDataService.SecretsPaths;
        Assert.Equal(8, paths.Count);
        Assert.True(paths.ContainsKey("Buildings"));
        Assert.True(paths.ContainsKey("Weapons"));
        Assert.True(paths.ContainsKey("Armor"));
        Assert.True(paths.ContainsKey("Tools"));
        Assert.True(paths.ContainsKey("Flora"));
        Assert.True(paths.ContainsKey("Loot"));
        Assert.True(paths.ContainsKey("Items"));
        Assert.True(paths.ContainsKey("Ores"));
    }

    [Fact]
    public void ConstructionsPaths_MirrorsSecretsPaths()
    {
        // Both should have same keys
        Assert.Equal(
            CategoryDataService.SecretsPaths.Keys.OrderBy(k => k),
            CategoryDataService.ConstructionsPaths.Keys.OrderBy(k => k));
    }

    [Fact]
    public void FloraPath_HasNoRecipe()
    {
        Assert.Null(CategoryDataService.SecretsPaths["Flora"].RecipePath);
    }

    [Fact]
    public void BuildingsPath_HasRecipe()
    {
        Assert.NotNull(CategoryDataService.SecretsPaths["Buildings"].RecipePath);
        Assert.Contains("ConstructionRecipes", CategoryDataService.SecretsPaths["Buildings"].RecipePath);
    }

    // =========================================================================
    // ResolveDisplayName (via LoadCategoryItems item formatting)
    // =========================================================================

    [Fact]
    public void LoadCategoryItems_ReturnsListOrEmpty_ForValidCategory()
    {
        // On a machine with imported data, this may return items (from game output/jsondata).
        // On a clean machine with no import, returns empty. Either result is valid.
        var items = _service.LoadCategoryItems("secrets", "Buildings", $"test_{Guid.NewGuid():N}");
        Assert.NotNull(items); // Just verify it doesn't throw
    }

    // =========================================================================
    // ScanDropdownOptions
    // =========================================================================

    [Fact]
    public void ScanDropdownOptions_ReturnsExpectedKeys()
    {
        var opts = _service.ScanDropdownOptions("secrets");
        Assert.True(opts.ContainsKey("Materials"));
        Assert.True(opts.ContainsKey("Actors"));
        Assert.True(opts.ContainsKey("Constructions"));
        Assert.True(opts.ContainsKey("Tags"));
        Assert.True(opts.ContainsKey("AllValues"));
    }

    // =========================================================================
    // InvalidateCache
    // =========================================================================

    [Fact]
    public void InvalidateCache_DoesNotThrow()
    {
        _service.InvalidateCache();
        _service.InvalidateCache("nonexistent_file.json");
    }
}
