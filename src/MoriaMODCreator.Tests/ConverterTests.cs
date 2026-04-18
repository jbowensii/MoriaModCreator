using System.Globalization;
using System.Windows;
using MoriaMODCreator.Converters;
using Xunit;

namespace MoriaMODCreator.Tests;

public class ConverterTests
{
    // =========================================================================
    // BoolToVisibilityConverter
    // =========================================================================

    [Fact]
    public void BoolToVisibility_True_ReturnsVisible()
    {
        var converter = new BoolToVisibilityConverter();
        var result = converter.Convert(true, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Visible, result);
    }

    [Fact]
    public void BoolToVisibility_False_ReturnsCollapsed()
    {
        var converter = new BoolToVisibilityConverter();
        var result = converter.Convert(false, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    // =========================================================================
    // InverseBoolToVisibilityConverter
    // =========================================================================

    [Fact]
    public void InverseBoolToVisibility_True_ReturnsCollapsed()
    {
        var converter = new InverseBoolToVisibilityConverter();
        var result = converter.Convert(true, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Collapsed, result);
    }

    [Fact]
    public void InverseBoolToVisibility_False_ReturnsVisible()
    {
        var converter = new InverseBoolToVisibilityConverter();
        var result = converter.Convert(false, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(Visibility.Visible, result);
    }

    // =========================================================================
    // StringToVisibilityConverter
    // =========================================================================

    [Theory]
    [InlineData(null, Visibility.Collapsed)]
    [InlineData("", Visibility.Collapsed)]
    [InlineData("  ", Visibility.Collapsed)]
    [InlineData("hello", Visibility.Visible)]
    public void StringToVisibility_ReturnsExpected(string? input, Visibility expected)
    {
        var converter = new StringToVisibilityConverter();
        var result = converter.Convert(input!, typeof(Visibility), null!, CultureInfo.InvariantCulture);
        Assert.Equal(expected, result);
    }

    // =========================================================================
    // StringToBoolConverter
    // =========================================================================

    [Theory]
    [InlineData("True", true)]
    [InlineData("true", true)]
    [InlineData("TRUE", true)]
    [InlineData("False", false)]
    [InlineData("false", false)]
    [InlineData("", false)]
    [InlineData("anything", false)]
    public void StringToBool_Convert(string input, bool expected)
    {
        var converter = new StringToBoolConverter();
        var result = converter.Convert(input, typeof(bool), null!, CultureInfo.InvariantCulture);
        Assert.Equal(expected, result);
    }

    [Theory]
    [InlineData(true, "True")]
    [InlineData(false, "False")]
    public void StringToBool_ConvertBack(bool input, string expected)
    {
        var converter = new StringToBoolConverter();
        var result = converter.ConvertBack(input, typeof(string), null!, CultureInfo.InvariantCulture);
        Assert.Equal(expected, result);
    }

    // =========================================================================
    // NullTooltipConverter
    // =========================================================================

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    public void NullTooltip_ReturnsNull_ForEmptyStrings(string? input)
    {
        var converter = new NullTooltipConverter();
        var result = converter.Convert(input!, typeof(string), null!, CultureInfo.InvariantCulture);
        Assert.Null(result);
    }

    [Fact]
    public void NullTooltip_ReturnsString_ForNonEmpty()
    {
        var converter = new NullTooltipConverter();
        var result = converter.Convert("tooltip text", typeof(string), null!, CultureInfo.InvariantCulture);
        Assert.Equal("tooltip text", result);
    }
}
