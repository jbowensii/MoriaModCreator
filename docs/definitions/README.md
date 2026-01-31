# Definition Files

This directory contains reference copies of `.def` files used by Moria MOD Creator.

## Purpose

These files are stored here for:
- Documentation and reference
- Version control tracking of definition changes
- Sharing definitions with other users

## Note

The application loads definitions from the path configured in **Settings → Definitions Folder**, not from this directory. These are informational copies only.

## Definition File Format

Definition files are XML documents that describe mod changes. Example:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<definition>
  <title>TITLE</title>
  <author>Nexus Mods Member:AUTHOR NAME</author>
  <description>DESCRIPTION</description>
  <mod file="PATH TO FILE\FILENAME.json">
    <change item="NONE" property="Property.Name.DOT.Format" value="NEW VALUE" />
  <!--  

  <add item="NewItem" property="MaxStackSize" value="100"/>
  <change item="Scrap" property="MaxStackSize" value="9999"/>
  <delete item="OldItem" property="MaxStackSize"/>

  -->
  </mod>
</definition>
```

### Operations

- `<change>` - Modify an existing property value
- `<add>` - Add a new property (commented example above)
- `<delete>` - Remove a property (commented example above)

### Attributes

- `item` - The item name to target, or `NONE` for non-item properties
- `property` - Property path in dot notation (e.g., `MaxStackSize`, `Value.Value`)
- `value` - The new value to set
