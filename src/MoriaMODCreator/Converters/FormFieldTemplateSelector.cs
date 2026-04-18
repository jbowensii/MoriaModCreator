using System.Windows;
using System.Windows.Controls;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.Converters;

/// <summary>
/// Selects the appropriate DataTemplate for each FormField type.
/// Used in BuildingsView right pane ItemsControl.
/// </summary>
public class FormFieldTemplateSelector : DataTemplateSelector
{
    public DataTemplate? SectionHeaderTemplate { get; set; }
    public DataTemplate? TextFieldTemplate { get; set; }
    public DataTemplate? DropdownFieldTemplate { get; set; }
    public DataTemplate? CheckboxFieldTemplate { get; set; }
    public DataTemplate? ReadOnlyFieldTemplate { get; set; }
    public DataTemplate? InlineRowTemplate { get; set; }

    public override DataTemplate? SelectTemplate(object item, DependencyObject container)
    {
        if (item is not FormField field) return base.SelectTemplate(item, container);

        return field.FieldType switch
        {
            FormFieldType.SectionHeader => SectionHeaderTemplate,
            FormFieldType.Dropdown => DropdownFieldTemplate,
            FormFieldType.Checkbox => CheckboxFieldTemplate,
            FormFieldType.ReadOnly => ReadOnlyFieldTemplate,
            FormFieldType.InlineRow => InlineRowTemplate,
            _ => TextFieldTemplate,
        };
    }
}
