using System.Collections.ObjectModel;
using MoriaMODCreator.Models;

namespace MoriaMODCreator.ViewModels;

/// <summary>
/// Shared form-field builder used by BuildingsViewModel and ObjectEditorViewModel.
/// Encapsulates the AddTextField / AddDropdown / AddCheckbox / AddSection / AddInlineRow helpers
/// so both view models render identical form layouts for the same category.
/// </summary>
public class FormBuilder
{
    private readonly ObservableCollection<FormField> _target;

    public FormBuilder(ObservableCollection<FormField> target) => _target = target;

    public void AddSection(string title, string color) =>
        _target.Add(new FormField
        {
            Name = $"__section_{title}",
            Label = title,
            FieldType = FormFieldType.SectionHeader,
            SectionColor = color,
        });

    public void AddTextField(Dictionary<string, object?> fields, string name,
        string? label = null, bool readOnly = false)
    {
        var value = FieldValueToString(fields.GetValueOrDefault(name));
        _target.Add(new FormField
        {
            Name = name,
            Label = label ?? FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = readOnly ? FormFieldType.ReadOnly : FormFieldType.Text,
            Value = value,
            OriginalValue = value,
            IsReadOnly = readOnly,
        });
    }

    public void AddDropdown(Dictionary<string, object?> fields, string name,
        List<string> options, string? label = null)
    {
        var raw = FieldValueToString(fields.GetValueOrDefault(name));
        var value = StripEnumPrefix(raw);
        if (!string.IsNullOrEmpty(value) && !options.Contains(value))
            options = [value, .. options];
        _target.Add(new FormField
        {
            Name = name,
            Label = label ?? FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = FormFieldType.Dropdown,
            Value = value,
            OriginalValue = value,
            Options = options,
        });
    }

    public void AddCheckbox(Dictionary<string, object?> fields, string name)
    {
        var raw = fields.GetValueOrDefault(name);
        var boolStr = raw switch
        {
            bool b => b.ToString(),
            _ => FieldValueToString(raw),
        };
        if (string.IsNullOrEmpty(boolStr) || boolStr == "0") boolStr = "False";
        if (boolStr == "1") boolStr = "True";
        _target.Add(new FormField
        {
            Name = name,
            Label = FieldDescriptions.ToFriendlyLabel(name),
            Tooltip = FieldDescriptions.GetTooltip(name),
            FieldType = FormFieldType.Checkbox,
            Value = boolStr,
            OriginalValue = boolStr,
        });
    }

    public void AddInlineRow(Dictionary<string, object?> fields, params string[] names)
    {
        var inlineFields = new List<FormField>();
        foreach (var name in names)
        {
            var value = fields.GetValueOrDefault(name)?.ToString() ?? "";
            inlineFields.Add(new FormField
            {
                Name = name,
                Label = FieldDescriptions.ToFriendlyLabel(name),
                Tooltip = FieldDescriptions.GetTooltip(name),
                FieldType = FormFieldType.Text,
                Value = value,
                OriginalValue = value,
            });
        }
        _target.Add(new FormField
        {
            Name = $"__inline_{string.Join("_", names)}",
            FieldType = FormFieldType.InlineRow,
            InlineFields = inlineFields,
        });
    }

    public static string FieldValueToString(object? value)
    {
        if (value == null) return "";
        if (value is string s) return s;
        if (value is bool b) return b.ToString();
        if (value is int or double or float or long) return value.ToString() ?? "";
        if (value is Dictionary<string, object?> dict)
        {
            if (dict.TryGetValue("RowName", out var rn) && rn != null) return rn.ToString() ?? "";
            if (dict.TryGetValue("Value", out var v) && v != null) return FieldValueToString(v);
            return string.Join(", ", dict.Where(kv => kv.Value != null)
                .Select(kv => $"{kv.Key}={FieldValueToString(kv.Value)}").Take(5));
        }
        if (value is List<object?> list)
        {
            if (list.Count == 0) return "";
            var items = list.Select(FieldValueToString).Where(x => !string.IsNullOrEmpty(x)).ToList();
            return items.Count <= 5 ? string.Join(", ", items)
                : $"{string.Join(", ", items.Take(5))}... ({items.Count} total)";
        }
        if (value is List<string> strList) return string.Join(", ", strList);
        return value.ToString() ?? "";
    }

    public static string StripEnumPrefix(string value)
    {
        var idx = value.LastIndexOf("::", StringComparison.Ordinal);
        return idx >= 0 ? value[(idx + 2)..] : value;
    }
}
