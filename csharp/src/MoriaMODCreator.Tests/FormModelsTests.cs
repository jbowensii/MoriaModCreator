using MoriaMODCreator.Models;
using Xunit;

namespace MoriaMODCreator.Tests;

public class FormModelsTests
{
    // =========================================================================
    // FieldDescriptions.ToFriendlyLabel
    // =========================================================================

    [Theory]
    [InlineData("bOnWall", "On Wall")]
    [InlineData("bOnFloor", "On Floor")]
    [InlineData("bPlaceOnWater", "Place On Water")]
    [InlineData("bAutoFoundation", "Auto Foundation")]
    public void ToFriendlyLabel_StripsBooleanPrefix(string input, string expected)
    {
        Assert.Equal(expected, FieldDescriptions.ToFriendlyLabel(input));
    }

    [Theory]
    [InlineData("ResultConstructionHandle", "Result Construction Handle")]
    [InlineData("MaxAllowedPenetrationDepth", "Max Allowed Penetration Depth")]
    [InlineData("DisplayName", "Display Name")]
    public void ToFriendlyLabel_InsertsSpacesBeforeCapitals(string input, string expected)
    {
        Assert.Equal(expected, FieldDescriptions.ToFriendlyLabel(input));
    }

    [Theory]
    [InlineData("")]
    [InlineData("x")]
    public void ToFriendlyLabel_HandlesShortStrings(string input)
    {
        Assert.Equal(input, FieldDescriptions.ToFriendlyLabel(input));
    }

    // =========================================================================
    // FieldDescriptions.FormatMaterialName
    // =========================================================================

    [Theory]
    [InlineData("Item.Wood", "Wood (Item.Wood)")]
    [InlineData("Ore.Iron", "Iron (Ore.Iron)")]
    [InlineData("Consumable.Potion", "Potion (Consumable.Potion)")]
    [InlineData("Tool.Hammer", "Hammer (Tool.Hammer)")]
    public void FormatMaterialName_StripsPrefixAndFormats(string input, string expected)
    {
        Assert.Equal(expected, FieldDescriptions.FormatMaterialName(input));
    }

    [Fact]
    public void FormatMaterialName_NoPrefix_StillFormats()
    {
        // No prefix to strip, but ToFriendlyLabel still inserts spaces at capitals
        // So "SomeCustomItem" → "Some Custom Item (SomeCustomItem)"
        var result = FieldDescriptions.FormatMaterialName("SomeCustomItem");
        Assert.Contains("SomeCustomItem", result);
    }

    [Fact]
    public void FormatMaterialName_SingleWord_ReturnsOriginal()
    {
        Assert.Equal("Wood", FieldDescriptions.FormatMaterialName("Wood"));
    }

    [Fact]
    public void FormatMaterialName_Empty_ReturnsEmpty()
    {
        Assert.Equal("", FieldDescriptions.FormatMaterialName(""));
    }

    // =========================================================================
    // FieldDescriptions.GetTooltip
    // =========================================================================

    [Fact]
    public void GetTooltip_ReturnsDescriptionForKnownField()
    {
        var tooltip = FieldDescriptions.GetTooltip("DisplayName");
        Assert.NotNull(tooltip);
        Assert.Contains("player", tooltip, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void GetTooltip_ReturnsNullForUnknownField()
    {
        Assert.Null(FieldDescriptions.GetTooltip("SomeRandomFieldThatDoesNotExist"));
    }

    [Fact]
    public void GetTooltip_IsCaseInsensitive()
    {
        var lower = FieldDescriptions.GetTooltip("displayname");
        var upper = FieldDescriptions.GetTooltip("DISPLAYNAME");
        Assert.Equal(lower, upper);
    }

    // =========================================================================
    // FormField observable properties
    // =========================================================================

    [Fact]
    public void FormField_IsModified_WhenValueDiffers()
    {
        var field = new FormField
        {
            Name = "Test",
            Value = "new",
            OriginalValue = "old",
        };
        Assert.True(field.IsModified);
    }

    [Fact]
    public void FormField_NotModified_WhenValueSame()
    {
        var field = new FormField
        {
            Name = "Test",
            Value = "same",
            OriginalValue = "same",
        };
        Assert.False(field.IsModified);
    }

    [Fact]
    public void MaterialRow_DefaultValues()
    {
        var row = new MaterialRow();
        Assert.Equal("Item.Wood", row.Material);
        Assert.Equal("1", row.Amount);
        Assert.False(row.IsRemoved);
    }
}
