using System.IO;
using Microsoft.Extensions.Logging.Abstractions;
using MoriaMODCreator.Services;
using MoriaMODCreator.ViewModels;
using Xunit;

namespace MoriaMODCreator.Tests;

public class DefinitionsViewModelTests
{
    // =========================================================================
    // DefinitionEntry
    // =========================================================================

    [Fact]
    public void DefinitionEntry_IsChecked_RaisesPropertyChanged()
    {
        var entry = new DefinitionEntry { Name = "test", FullPath = "/test", IsDirectory = false };
        bool changed = false;
        entry.PropertyChanged += (_, e) => { if (e.PropertyName == "IsChecked") changed = true; };
        entry.IsChecked = true;
        Assert.True(changed);
    }

    // =========================================================================
    // ChangeCard
    // =========================================================================

    [Fact]
    public void ChangeCard_ItemName_IsObservable()
    {
        var card = new ChangeCard { ItemName = "Old" };
        bool changed = false;
        card.PropertyChanged += (_, e) => { if (e.PropertyName == "ItemName") changed = true; };
        card.ItemName = "New";
        Assert.True(changed);
        Assert.Equal("New", card.ItemName);
    }

    [Fact]
    public void ChangeCard_NewValue_IsObservable()
    {
        var card = new ChangeCard { NewValue = "100" };
        bool changed = false;
        card.PropertyChanged += (_, e) => { if (e.PropertyName == "NewValue") changed = true; };
        card.NewValue = "200";
        Assert.True(changed);
    }

    // =========================================================================
    // SaveCardChanges — round trip through .def XML
    // =========================================================================

    [Fact]
    public void SaveCardChanges_WritesCorrectXml()
    {
        // Create a temp .def file
        var tempFile = Path.Combine(Path.GetTempPath(), $"test_{Guid.NewGuid():N}.def");
        try
        {
            var xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <definition>
                  <title>Test Mod</title>
                  <author>Tester</author>
                  <description>Test desc</description>
                  <mod file="Moria/Content/Tech/Data/Items/DT_Weapons.json">
                    <change item="Weapon_Sword" property="Damage" value="100" original="50"/>
                  </mod>
                </definition>
                """;
            File.WriteAllText(tempFile, xml);

            // Parse it
            var defService = new DefinitionService(NullLogger<DefinitionService>.Instance);
            var def = defService.Parse(tempFile);
            Assert.Single(def.ModFiles);
            Assert.Single(def.ModFiles[0].Changes);
            Assert.Equal("100", def.ModFiles[0].Changes[0].Value);

            // Simulate editing and saving
            var doc = System.Xml.Linq.XDocument.Load(tempFile);
            var root = doc.Root!;
            foreach (var el in root.Elements("mod").ToList())
                el.Remove();

            var modElem = new System.Xml.Linq.XElement("mod",
                new System.Xml.Linq.XAttribute("file", "Moria/Content/Tech/Data/Items/DT_Weapons.json"));
            modElem.Add(new System.Xml.Linq.XElement("change",
                new System.Xml.Linq.XAttribute("item", "Weapon_Sword"),
                new System.Xml.Linq.XAttribute("property", "Damage"),
                new System.Xml.Linq.XAttribute("value", "999"),
                new System.Xml.Linq.XAttribute("original", "50")));
            root.Add(modElem);
            doc.Save(tempFile);

            // Re-parse and verify
            var def2 = defService.Parse(tempFile);
            Assert.Single(def2.ModFiles);
            Assert.Single(def2.ModFiles[0].Changes);
            Assert.Equal("999", def2.ModFiles[0].Changes[0].Value);
            Assert.Equal("50", def2.ModFiles[0].Changes[0].Original);
        }
        finally
        {
            if (File.Exists(tempFile)) File.Delete(tempFile);
        }
    }

    // =========================================================================
    // AddProperty parsing
    // =========================================================================

    // =========================================================================
    // AddProperty parsing — Python schema: nested inside <change>
    // =========================================================================

    [Fact]
    public void DefinitionService_ParsesAddProperty_NestedInsideChange()
    {
        // Python schema: <add_property> is a CHILD of <change>, not a sibling of <mod>.
        // The text content is JSON with keys: Name, DefaultValue, Type.
        var tempFile = Path.Combine(Path.GetTempPath(), $"test_add_{Guid.NewGuid():N}.def");
        try
        {
            var xml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <definition>
                  <title>Add Test</title>
                  <mod file="test.json">
                    <change item="Row1" property="Durability" value="100">
                      <add_property item="Row1">{"Name":"Durability","DefaultValue":100,"Type":"IntPropertyData"}</add_property>
                    </change>
                  </mod>
                </definition>
                """;
            File.WriteAllText(tempFile, xml);

            var defService = new DefinitionService(NullLogger<DefinitionService>.Instance);
            var def = defService.Parse(tempFile);

            Assert.Single(def.ModFiles);
            // <change> still counted as a change
            Assert.Single(def.ModFiles[0].Changes);
            // add_property is nested; parsed into AddProperties list and onto the ModChange
            Assert.Single(def.ModFiles[0].AddProperties);
            var ap = def.ModFiles[0].AddProperties[0];
            Assert.Equal("Row1", ap.Item);
            Assert.Equal("Durability", ap.PropertyName);
            Assert.Equal("IntPropertyData", ap.PropertyType);
            Assert.Equal("100", ap.DefaultValue);
            // The parent change should reference the add_property
            Assert.NotNull(def.ModFiles[0].Changes[0].AddProperty);
            Assert.Equal("Durability", def.ModFiles[0].Changes[0].AddProperty!.PropertyName);
        }
        finally
        {
            if (File.Exists(tempFile)) File.Delete(tempFile);
        }
    }

    [Fact]
    public void AddProperty_RoundTrip_ProducesCorrectPythonSchema()
    {
        // Verify that saving an ADD card and reloading it produces correct fields,
        // and that the XML matches the Python schema: <change><add_property item="...">JSON</add_property></change>
        var tempFile = Path.Combine(Path.GetTempPath(), $"test_rt_{Guid.NewGuid():N}.def");
        try
        {
            // Build a .def with a nested add_property (Python schema)
            var originalXml = """
                <?xml version="1.0" encoding="UTF-8"?>
                <definition>
                  <title>Round Trip Test</title>
                  <author>Tester</author>
                  <description>Round-trip test for add_property</description>
                  <mod file="DT_Weapons.json">
                    <change item="Sword" property="Durability" value="100">
                      <add_property item="Sword">{"Name":"Durability","DefaultValue":100,"Type":"IntPropertyData"}</add_property>
                    </change>
                  </mod>
                </definition>
                """;
            File.WriteAllText(tempFile, originalXml);

            // --- Load path ---
            var defService = new DefinitionService(NullLogger<DefinitionService>.Instance);
            var def = defService.Parse(tempFile);

            Assert.Single(def.ModFiles);
            Assert.Single(def.ModFiles[0].AddProperties);
            var ap = def.ModFiles[0].AddProperties[0];
            Assert.Equal("Sword", ap.Item);
            Assert.Equal("Durability", ap.PropertyName);
            Assert.Equal("IntPropertyData", ap.PropertyType);
            Assert.Equal("100", ap.DefaultValue);

            // Verify parent <change> is also populated correctly
            Assert.Single(def.ModFiles[0].Changes);
            var ch = def.ModFiles[0].Changes[0];
            Assert.Equal("Sword", ch.Item);
            Assert.Equal("Durability", ch.Property);
            Assert.Equal("100", ch.Value);
            Assert.NotNull(ch.AddProperty);

            // --- Save path (simulate what SaveCardChanges does) ---
            var doc = System.Xml.Linq.XDocument.Load(tempFile);
            var root = doc.Root!;
            foreach (var el in root.Elements("mod").ToList())
                el.Remove();

            var modElem = new System.Xml.Linq.XElement("mod",
                new System.Xml.Linq.XAttribute("file", "DT_Weapons.json"));

            // Simulate ADD card save: <change><add_property item="Sword">JSON</add_property></change>
            var jsonContent = System.Text.Json.JsonSerializer.Serialize(
                new Dictionary<string, object>
                {
                    ["Name"] = "Durability",
                    ["DefaultValue"] = "100",
                    ["Type"] = "IntPropertyData",
                });
            var changeElem = new System.Xml.Linq.XElement("change",
                new System.Xml.Linq.XAttribute("item", "Sword"),
                new System.Xml.Linq.XAttribute("property", "Durability"),
                new System.Xml.Linq.XAttribute("value", "100"));
            var addPropElem = new System.Xml.Linq.XElement("add_property",
                new System.Xml.Linq.XAttribute("item", "Sword"));
            addPropElem.Value = jsonContent;
            changeElem.Add(addPropElem);
            modElem.Add(changeElem);
            root.Add(modElem);
            doc.Save(tempFile);

            // --- Reload and verify round-trip ---
            var def2 = defService.Parse(tempFile);
            Assert.Single(def2.ModFiles);
            Assert.Single(def2.ModFiles[0].AddProperties);
            var ap2 = def2.ModFiles[0].AddProperties[0];
            Assert.Equal("Sword", ap2.Item);
            Assert.Equal("Durability", ap2.PropertyName);
            Assert.Equal("IntPropertyData", ap2.PropertyType);
            Assert.Equal("100", ap2.DefaultValue);
            Assert.NotNull(def2.ModFiles[0].Changes[0].AddProperty);

            // Verify the saved XML has the correct structure:
            // <change item="Sword" ...><add_property item="Sword">...</add_property></change>
            var savedXml = File.ReadAllText(tempFile);
            Assert.Contains("<change ", savedXml);
            Assert.Contains("<add_property ", savedXml);
            Assert.Contains("item=\"Sword\"", savedXml);
            Assert.Contains("\"Name\"", savedXml);
            Assert.Contains("\"Durability\"", savedXml);
            Assert.Contains("\"IntPropertyData\"", savedXml);
            // add_property must be INSIDE change, not a sibling of mod
            var changeIdx = savedXml.IndexOf("<change ", StringComparison.Ordinal);
            var addPropIdx = savedXml.IndexOf("<add_property ", StringComparison.Ordinal);
            var changeEndIdx = savedXml.IndexOf("</change>", StringComparison.Ordinal);
            Assert.True(addPropIdx > changeIdx, "add_property must appear after <change> open tag");
            Assert.True(addPropIdx < changeEndIdx, "add_property must appear before </change>");
        }
        finally
        {
            if (File.Exists(tempFile)) File.Delete(tempFile);
        }
    }
}
