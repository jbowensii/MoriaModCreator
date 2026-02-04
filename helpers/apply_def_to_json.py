"""Apply .def file modifications to baseline JSON files.

This helper script applies .def file modifications (add_row, add_imports, change)
to baseline JSON files. This was previously part of the Constructions tab build
functionality but has been extracted for standalone use.

Usage:
    python apply_def_to_json.py <def_file> <json_file> [--output <output_file>]

Example:
    python apply_def_to_json.py construction.def DT_Constructions.json --output modified.json
"""

import argparse
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def row_exists_in_json(json_data: dict, row_name: str) -> bool:
    """Check if a row with the given name already exists in the JSON data."""
    if 'Exports' not in json_data:
        return False

    for export in json_data['Exports']:
        if 'Table' in export and 'Data' in export['Table']:
            table_data = export['Table']['Data']
            for existing_row in table_data:
                if existing_row.get('Name') == row_name:
                    return True
    return False


def apply_add_imports(json_data: dict, imports_text: str):
    """Add imports to the JSON data."""
    try:
        new_imports = json.loads(imports_text)
        if 'Imports' in json_data and isinstance(json_data['Imports'], list):
            # Avoid duplicates by checking if import already exists
            existing_paths = {imp.get('ObjectName', '') for imp in json_data['Imports']}
            for imp in new_imports:
                if imp.get('ObjectName', '') not in existing_paths:
                    json_data['Imports'].append(imp)
                    logger.info("Added import: %s", imp.get('ObjectName', ''))
    except json.JSONDecodeError as e:
        logger.error("Failed to parse imports JSON: %s", e)


def apply_add_row(json_data: dict, row_name: str, row_data_text: str, overwrite: bool = True):
    """Add a row to a DataTable JSON structure."""
    try:
        new_row = json.loads(row_data_text)

        # Find the Table.Data array
        if 'Exports' not in json_data:
            return False

        for export in json_data['Exports']:
            if 'Table' in export and 'Data' in export['Table']:
                table_data = export['Table']['Data']

                # Check if row already exists
                for i, existing_row in enumerate(table_data):
                    if existing_row.get('Name') == row_name:
                        if overwrite:
                            table_data[i] = new_row
                            logger.info("Updated existing row: %s", row_name)
                        else:
                            logger.info("Skipped existing row: %s", row_name)
                        return True

                # Row doesn't exist, add it
                table_data.append(new_row)
                logger.info("Added new row: %s", row_name)
                return True

    except json.JSONDecodeError as e:
        logger.error("Failed to parse row JSON for %s: %s", row_name, e)
    return False


def apply_json_change(json_data: dict, item_name: str, property_path: str, new_value: str):
    """Apply a simple change to a DataTable row."""
    if 'Exports' not in json_data:
        return

    for export in json_data['Exports']:
        if 'Table' in export and 'Data' in export['Table']:
            table_data = export['Table']['Data']
            for row in table_data:
                if row.get('Name') == item_name:
                    value_array = row.get('Value', [])
                    if value_array:
                        set_property_in_value_array(value_array, property_path, new_value)
                        logger.info("Changed %s.%s = %s", item_name, property_path, new_value)
                    return


def set_property_in_value_array(value_array: list, property_path: str, new_value: str):
    """Set a property value in a UAssetAPI Value array."""
    for prop in value_array:
        if prop.get('Name') == property_path:
            # Determine the type and set appropriately
            if 'Value' in prop:
                # Try to convert to appropriate type
                try:
                    if new_value.lower() in ('true', 'false'):
                        prop['Value'] = new_value.lower() == 'true'
                    elif '.' in new_value:
                        prop['Value'] = float(new_value)
                    else:
                        prop['Value'] = int(new_value)
                except ValueError:
                    prop['Value'] = new_value
            return


def apply_def_to_json(def_file: Path, json_file: Path, output_file: Path = None, overwrite: bool = True):
    """Apply a .def file's modifications to a JSON file.
    
    Args:
        def_file: Path to the .def XML file
        json_file: Path to the baseline JSON file
        output_file: Path for output (defaults to overwriting json_file)
        overwrite: Whether to overwrite existing rows
    """
    if output_file is None:
        output_file = json_file

    # Parse the .def file
    tree = ET.parse(def_file)
    root = tree.getroot()

    # Load the JSON file
    with open(json_file, 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    json_filename = json_file.name

    # Process all <mod> elements in the .def file
    for mod_element in root.findall('mod'):
        mod_file_attr = mod_element.get('file', '')
        if not mod_file_attr:
            continue

        # Check if this mod element targets our JSON file
        mod_target = Path(mod_file_attr.replace('\\', '/')).name
        if mod_target != json_filename:
            logger.debug("Skipping mod for %s (looking for %s)", mod_target, json_filename)
            continue

        logger.info("Processing mod section for %s", json_filename)

        # Apply add_imports if present
        for add_imports_elem in mod_element.findall('add_imports'):
            imports_text = add_imports_elem.text
            if imports_text:
                apply_add_imports(json_data, imports_text)

        # Apply add_row operations
        for add_row_elem in mod_element.findall('add_row'):
            row_name = add_row_elem.get('name', '')
            row_data_text = add_row_elem.text
            if row_name and row_data_text:
                apply_add_row(json_data, row_name, row_data_text, overwrite)

        # Apply change operations
        for change_elem in mod_element.findall('change'):
            item_name = change_elem.get('item', '')
            property_path = change_elem.get('property', '')
            new_value = change_elem.get('value', '')
            if item_name and property_path:
                apply_json_change(json_data, item_name, property_path, new_value)

    # Save the modified JSON
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    logger.info("Saved modified JSON to: %s", output_file)


def main():
    parser = argparse.ArgumentParser(
        description='Apply .def file modifications to baseline JSON files.'
    )
    parser.add_argument('def_file', type=Path, help='Path to the .def XML file')
    parser.add_argument('json_file', type=Path, help='Path to the baseline JSON file')
    parser.add_argument('--output', '-o', type=Path, help='Output file path (defaults to overwriting input)')
    parser.add_argument('--no-overwrite', action='store_true', help='Skip existing rows instead of overwriting')
    
    args = parser.parse_args()

    if not args.def_file.exists():
        logger.error("Definition file not found: %s", args.def_file)
        return 1

    if not args.json_file.exists():
        logger.error("JSON file not found: %s", args.json_file)
        return 1

    apply_def_to_json(
        args.def_file,
        args.json_file,
        args.output,
        overwrite=not args.no_overwrite
    )
    return 0


if __name__ == '__main__':
    exit(main())
