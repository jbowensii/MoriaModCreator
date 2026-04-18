using System.Collections.ObjectModel;
using MoriaMODCreator.Models;
using MoriaMODCreator.ViewModels;
using Xunit;

namespace MoriaMODCreator.Tests;

public class FormBuilderTests
{
    [Fact]
    public void AddTextField_PopulatesFromFieldsDict()
    {
        var fields = new Dictionary<string, object?> { ["Damage"] = "100" };
        var list = new ObservableCollection<FormField>();
        var builder = new FormBuilder(list);
        builder.AddTextField(fields, "Damage");
        Assert.Single(list);
        Assert.Equal("100", list[0].Value);
        Assert.Equal("Damage", list[0].Name);
    }

    [Fact]
    public void AddDropdown_StripsEnumPrefix()
    {
        var fields = new Dictionary<string, object?> { ["Mode"] = "EMode::Advanced" };
        var list = new ObservableCollection<FormField>();
        var builder = new FormBuilder(list);
        builder.AddDropdown(fields, "Mode", new List<string> { "Simple", "Advanced" });
        Assert.Equal("Advanced", list[0].Value);
    }

    [Fact]
    public void AddSection_CreatesSectionHeader()
    {
        var list = new ObservableCollection<FormField>();
        var builder = new FormBuilder(list);
        builder.AddSection("Stats", "#4CAF50");
        Assert.Single(list);
        Assert.Equal(FormFieldType.SectionHeader, list[0].FieldType);
        Assert.Equal("Stats", list[0].Label);
    }
}
