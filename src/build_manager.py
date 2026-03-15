"""Build manager for Moria MOD Creator.

This module handles all build-related operations including:
- Processing definition files
- Modifying JSON files
- Converting JSON to uasset format
- Packaging mods using retoc
- Creating zip files
"""

import json
import logging
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Callable

from src.config import get_appdata_dir, get_output_dir, get_default_mymodfiles_dir, get_utilities_dir, get_final_destination_dir
from src.ui.import_dialog import merge_secrets_rows
from src.constants import (
    UE_VERSION,
    RETOC_UE_VERSION,
    UASSETGUI_EXE,
    RETOC_EXE,
    JSONFILES_DIR,
    UASSET_DIR,
    FINALMOD_DIR,
    JSONDATA_DIR,
    BUILD_TIMEOUT,
)

logger = logging.getLogger(__name__)


class BuildManager:  # pylint: disable=too-few-public-methods
    """Manages the mod build process."""

    def __init__(self, progress_callback: Callable[[str, float], None] | None = None):
        """Initialize the build manager.

        Args:
            progress_callback: Optional callback function(message, progress_percent)
                              for reporting progress.
        """
        self.progress_callback = progress_callback
        self._setup_build_log()

    def _setup_build_log(self):
        """Set up a file handler so build logs are saved to build_log.txt."""
        log_path = get_appdata_dir() / 'build_log.txt'
        # Remove any previous file handlers on our logger
        for handler in logger.handlers[:]:
            if isinstance(handler, logging.FileHandler):
                logger.removeHandler(handler)
        file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'
        ))
        logger.addHandler(file_handler)
        self._log_path = log_path

    def _report_progress(self, message: str, progress: float):
        """Report progress if callback is set.

        Args:
            message: Status message.
            progress: Progress percentage (0.0 to 1.0).
        """
        logger.info("Build progress: %.0f%% - %s", progress * 100, message)
        if self.progress_callback:
            self.progress_callback(message, progress)

    def build(self, mod_name: str, def_files: list[Path], include_secrets: bool = False) -> tuple[bool, str]:
        """Build a complete mod from definition files.

        Uses a three-phase approach:
        - Phase A: Copy non-secrets source files to jsonfiles/
        - Phase B: Overlay secrets manifest files (if any secrets .defs found)
        - Phase C: Apply all .def changes to the assembled jsonfiles/

        Args:
            mod_name: Name of the mod.
            def_files: List of definition file paths.

        Returns:
            Tuple of (success, message).
        """
        if not def_files:
            logger.warning("Build called with no definition files")
            return False, "No definition files selected"

        logger.info("Build started for mod '%s' with %d definition file(s)", mod_name, len(def_files))
        try:
            # Step 0: Clear previous build files
            self._report_progress("Cleaning previous build files...", 0.0)
            self._clean_build_directories(mod_name)

            # Step 1 Phase A: Copy non-secrets source files (5-15%)
            self._report_progress("Copying source files...", 0.05)
            uses_secrets = self._phase_a_copy_sources(mod_name, def_files)

            # Also enable secrets if the checkbox was checked
            if include_secrets:
                uses_secrets = True

            # Step 1 Phase B: Overlay secrets manifest (15-20%)
            if uses_secrets:
                self._report_progress("Overlaying secrets manifest...", 0.15)
                self._phase_b_overlay_secrets(mod_name)

            # Step 1 Phase C: Apply all .def changes (20-40%)
            self._report_progress("Applying definition changes...", 0.20)
            success_count, error_count = self._phase_c_apply_changes(mod_name, def_files)

            if error_count > 0:
                logger.error("Definition apply failed: %d succeeded, %d failed", success_count, error_count)
                return False, f"{success_count} succeeded, {error_count} failed"

            if success_count == 0:
                logger.error("No files were processed from %d definition files", len(def_files))
                return False, "No files were processed"

            # Step 2: Convert JSON to uasset (40-70%)
            logger.info("Step 2: Converting JSON to uasset format")
            self._report_progress("Converting to uasset format...", 0.4)
            convert_ok, convert_error = self._convert_json_to_uasset(mod_name)
            if not convert_ok:
                logger.error("JSON to uasset conversion failed: %s", convert_error)
                return False, convert_error or "JSON to uasset conversion failed"

            # Step 3: Run retoc (70-90%)
            logger.info("Step 3: Running retoc to package mod files")
            self._report_progress("Packaging mod files...", 0.7)
            if not self._run_retoc(mod_name):
                logger.error("retoc packaging failed for mod '%s'", mod_name)
                return False, "retoc packaging failed"

            # Step 3.5: Copy secrets pak files if applicable (85-90%)
            if uses_secrets:
                self._report_progress("Copying secrets pak files...", 0.85)
                self._copy_secrets_pak_files(mod_name)

            # Step 4: Create zip (90-100%)
            logger.info("Step 4: Creating zip file")
            self._report_progress("Creating zip file...", 0.9)
            zip_path = self._create_zip(mod_name)

            if zip_path:
                logger.info("Build completed successfully for mod '%s': %s", mod_name, zip_path)
                self._report_progress("Build complete!", 1.0)
                return True, f"Mod saved to: {zip_path}"
            logger.error("Could not create zip file for mod '%s'", mod_name)
            return False, "Could not create zip file"

        except (OSError, ValueError, KeyError) as e:
            logger.exception("Build failed with exception")
            return False, str(e)

    def _clean_build_directories(self, mod_name: str):
        """Clean the build directories before starting a new build.

        Args:
            mod_name: Name of the mod.
        """
        mymodfiles_base = get_default_mymodfiles_dir() / mod_name

        dirs_to_clean = [
            mymodfiles_base / JSONFILES_DIR,
            mymodfiles_base / UASSET_DIR,
            mymodfiles_base / FINALMOD_DIR,
        ]

        for dir_path in dirs_to_clean:
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    logger.info("Cleaned directory: %s", dir_path)
                except OSError as e:
                    logger.warning("Could not clean directory %s: %s", dir_path, e)

    def _phase_a_copy_sources(self, mod_name: str, def_files: list[Path]) -> bool:
        """Phase A: Copy non-secrets source files to jsonfiles/.

        For each .def file, if the <mod file> path does NOT contain
        "Secrets Source", copy the source JSON to the build directory.
        If it does contain "Secrets Source", skip the copy and flag
        that secrets are in use.

        Args:
            mod_name: Name of the mod.
            def_files: List of definition file paths.

        Returns:
            True if any .def file references Secrets Source.
        """
        uses_secrets = False
        jsondata_dir = get_output_dir() / JSONDATA_DIR
        mymodfiles_dir = get_default_mymodfiles_dir() / mod_name / JSONFILES_DIR

        for i, def_file in enumerate(def_files):
            step_progress = 0.05 + (0.10 * (i / len(def_files)))
            self._report_progress(f"Copying {def_file.name}...", step_progress)

            try:
                tree = ET.parse(def_file)
                root = tree.getroot()
                mod_element = root.find('mod')
                if mod_element is None:
                    continue

                mod_file_path = mod_element.get('file', '')
                if not mod_file_path:
                    continue

                # Check if this is a secrets file - skip copy
                if 'Secrets Source' in mod_file_path:
                    uses_secrets = True
                    logger.info("Phase A: Skipping secrets file: %s", def_file.name)
                    continue

                # Normalize and copy non-secrets file
                normalized_path = mod_file_path.lstrip('\\').lstrip('/').replace('\\', '/')
                source_file = jsondata_dir / normalized_path

                if not source_file.exists():
                    logger.warning("Phase A: Source file not found, skipping: %s", normalized_path)
                    continue

                dest_file = mymodfiles_dir / normalized_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, dest_file)
                logger.info("Phase A: Copied %s", normalized_path)

            except (ET.ParseError, OSError) as e:
                logger.error("Phase A: Error processing %s: %s", def_file.name, e)

        return uses_secrets

    def _phase_b_overlay_secrets(self, mod_name: str):
        """Phase B: Overlay secrets manifest files onto jsonfiles/.

        Reads the secrets manifest.def and copies ALL listed files from
        Secrets Source/jsondata/ to the build jsonfiles/ directory,
        overwriting any existing files.

        Args:
            mod_name: Name of the mod.
        """
        manifest_path = get_appdata_dir() / 'Secrets Source' / 'secrets manifest.def'
        if not manifest_path.exists():
            logger.info("Phase B: Secrets manifest not found at %s, skipping", manifest_path)
            return

        secrets_jsondata = get_appdata_dir() / 'Secrets Source' / JSONDATA_DIR
        mymodfiles_dir = get_default_mymodfiles_dir() / mod_name / JSONFILES_DIR

        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()

            # Parse manifest - look for <mod file="..."> elements
            file_count = 0
            for mod_element in root.findall('mod'):
                file_path = mod_element.get('file', '')
                if not file_path:
                    continue

                normalized_path = file_path.lstrip('\\').lstrip('/').replace('\\', '/')
                source_file = secrets_jsondata / normalized_path

                if not source_file.exists():
                    logger.warning("Phase B: Manifest file not found: %s", source_file)
                    continue

                dest_file = mymodfiles_dir / normalized_path
                dest_file.parent.mkdir(parents=True, exist_ok=True)

                if dest_file.exists():
                    # Merge new secrets rows into the existing game file
                    merged = merge_secrets_rows(dest_file, source_file, dest_file)
                    logger.info("Phase B: Merged %d new rows into: %s", merged, normalized_path)
                else:
                    # No game file — just copy the secrets file
                    shutil.copy2(source_file, dest_file)
                    logger.info("Phase B: Copied new secrets file: %s", normalized_path)
                file_count += 1

            logger.info("Phase B: Copied %d files from secrets manifest", file_count)

        except (ET.ParseError, OSError) as e:
            logger.error("Phase B: Error processing secrets manifest: %s", e)

    @staticmethod
    def _normalize_secrets_path(mod_file_path: str) -> str:
        """Normalize a .def file path, stripping Secrets Source prefix if present.

        Converts a path like "Secrets Source/jsondata/Building/DT_X.json"
        to "Building/DT_X.json" so it can be found in the jsonfiles/ directory.

        Args:
            mod_file_path: Raw path from <mod file="..."> attribute.

        Returns:
            Normalized relative path suitable for jsonfiles/ lookup.
        """
        clean_path = mod_file_path.replace('\\', '/')

        # Strip everything up to and including "jsondata/" if Secrets Source is present
        if 'Secrets Source' in clean_path:
            for marker in ('jsondata/', 'jsondata\\'):
                idx = clean_path.find(marker)
                if idx >= 0:
                    clean_path = clean_path[idx + len(marker):]
                    break
            else:
                # No jsondata/ found - strip just "Secrets Source/"
                idx = clean_path.find('Secrets Source/')
                if idx >= 0:
                    clean_path = clean_path[idx + len('Secrets Source/'):]

        return clean_path.lstrip('/')

    def _phase_c_apply_changes(self, mod_name: str, def_files: list[Path]) -> tuple[int, int]:
        """Phase C: Apply all .def changes to the assembled jsonfiles/.

        Processes ALL .def files (both normal and secrets) and applies
        their <delete> and <change> operations to the target files
        in jsonfiles/.

        Args:
            mod_name: Name of the mod.
            def_files: List of definition file paths.

        Returns:
            Tuple of (success_count, error_count).
        """
        success_count = 0
        error_count = 0
        mymodfiles_dir = get_default_mymodfiles_dir() / mod_name / JSONFILES_DIR

        for i, def_file in enumerate(def_files):
            step_progress = 0.20 + (0.20 * (i / len(def_files)))
            self._report_progress(f"Applying changes from {def_file.name}...", step_progress)

            try:
                tree = ET.parse(def_file)
                root = tree.getroot()
                mod_element = root.find('mod')

                if mod_element is None:
                    logger.error("Phase C: No <mod> element in %s", def_file.name)
                    error_count += 1
                    continue

                mod_file_path = mod_element.get('file', '')
                if not mod_file_path:
                    logger.error("Phase C: No file attribute in <mod> of %s", def_file.name)
                    error_count += 1
                    continue

                # Normalize path (strips Secrets Source prefix if present)
                normalized_path = self._normalize_secrets_path(mod_file_path)
                target_file = mymodfiles_dir / normalized_path

                if not target_file.exists():
                    logger.warning(
                        "Phase C: Target file not found for %s: %s, skipping",
                        def_file.name, normalized_path
                    )
                    continue

                # Load JSON
                with open(target_file, 'r', encoding='utf-8') as f:
                    json_data = json.load(f)

                # Apply delete operations first
                delete_ops = mod_element.findall('delete')
                change_ops = mod_element.findall('change')
                logger.info(
                    "Phase C: %s -> %s (%d deletes, %d changes)",
                    def_file.name, normalized_path, len(delete_ops), len(change_ops)
                )

                for delete in delete_ops:
                    item_name = delete.get('item', '')
                    property_path = delete.get('property', '')
                    value_to_delete = delete.get('value', '')

                    if item_name == 'NONE':
                        continue

                    if property_path and value_to_delete:
                        logger.info(
                            "  DELETE: item=%s prop=%s value=%s",
                            item_name, property_path, value_to_delete
                        )
                        self._remove_gameplay_tag(json_data, item_name, property_path, value_to_delete)

                # Apply change operations
                for change in change_ops:
                    item_name = change.get('item', '')
                    property_path = change.get('property', '')
                    new_value = change.get('value', '')

                    # Handle <add_property> child - ensure property exists before change
                    add_prop_elem = change.find('add_property')
                    if add_prop_elem is not None and add_prop_elem.text:
                        prop_item = add_prop_elem.get('item', item_name)
                        self._add_property_to_json(
                            json_data, prop_item,
                            add_prop_elem.text.strip(), property_path,
                        )

                    logger.info(
                        "  CHANGE: item=%s prop=%s value=%s",
                        item_name, property_path, new_value
                    )

                    if self._is_gameplay_tag_container(json_data, item_name, property_path):
                        if item_name == 'NONE':
                            continue
                        original_tag = change.get('original', '')
                        new_tag = new_value.strip()

                        if original_tag:
                            self._remove_gameplay_tag(json_data, item_name, property_path, original_tag)
                        if new_tag:
                            self._add_gameplay_tag(json_data, item_name, property_path, new_tag)
                    else:
                        self._apply_json_change(json_data, item_name, property_path, new_value)

                # Ensure any new FName values are in the NameMap
                self._sync_namemap(json_data)

                # Save modified JSON
                with open(target_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, indent=2, ensure_ascii=False)

                success_count += 1
                logger.info("Phase C: Applied changes from %s", def_file.name)

            except ET.ParseError as e:
                logger.error("Phase C: XML parse error in %s: %s", def_file.name, e)
                error_count += 1
            except json.JSONDecodeError as e:
                logger.error("Phase C: JSON parse error for %s: %s", def_file.name, e)
                error_count += 1
            except OSError as e:
                logger.error("Phase C: File error for %s: %s", def_file.name, e)
                error_count += 1

        return success_count, error_count

    def _apply_json_change(
        self,
        json_data: dict,
        item_name: str,
        property_path: str,
        new_value: str
    ):
        """Apply a change to the JSON data.

        Args:
            json_data: The JSON data to modify.
            item_name: The export name or row name to find. Use 'NONE' to apply to all.
            property_path: Dot-separated property path.
            new_value: The new value to set.
        """
        if 'Exports' not in json_data:
            return

        # Handle NONE - apply to first export's Data (for single asset files like curves)
        # or to all rows in DataTable format
        if item_name == 'NONE':
            # Try DataTable format first - apply to all rows
            try:
                table_data = json_data['Exports'][0]['Table']['Data']
                for row in table_data:
                    value_array = row.get('Value', [])
                    if value_array:
                        self._set_nested_property_value(value_array, property_path, new_value)
                logger.debug("Applied NONE change to all DataTable rows: %s = %s", property_path, new_value)
                return
            except (KeyError, IndexError, TypeError):
                pass

            # Try single asset format - apply to first export's Data
            for export in json_data['Exports']:
                if 'Data' in export and isinstance(export['Data'], list) and len(export['Data']) > 0:
                    self._set_nested_property_value(export['Data'], property_path, new_value)
                    logger.debug("Applied NONE change to single asset: %s = %s", property_path, new_value)
                    return
            return

        # First, try ObjectName matching for class-based exports (GameplayEffects, etc.)
        name_variations = [
            f"Default__{item_name}_C",
            f"Default__{item_name}",
            item_name,
            f"{item_name}_C",
        ]

        for name_variant in name_variations:
            for export in json_data['Exports']:
                obj_name = export.get('ObjectName', '')
                if obj_name == name_variant:
                    if 'Data' in export and isinstance(export['Data'], list) and len(export['Data']) > 0:
                        self._set_nested_property_value(export['Data'], property_path, new_value)
                        return

        # If not found by ObjectName, try DataTable format (Table.Data rows)
        # This handles files like DT_Items, DT_Armor, DT_Storage, etc.
        try:
            table_data = json_data['Exports'][0]['Table']['Data']
            for row in table_data:
                if row.get('Name') == item_name:
                    # Found the row, now set the property in its Value array
                    value_array = row.get('Value', [])
                    if value_array:
                        self._set_nested_property_value(value_array, property_path, new_value)
                        logger.debug("Applied DataTable change: %s.%s = %s", item_name, property_path, new_value)
                    return
        except (KeyError, IndexError, TypeError):
            # Not a DataTable format, that's fine
            pass

    def _add_property_to_json(
        self, json_data: dict, item_name: str,
        property_json_text: str, change_property_path: str = '',
    ):
        """Add a property to a JSON structure if it doesn't already exist.

        This handles the <add_property> element inside <change>, which ensures
        a property exists before the change attempts to set its value.

        Uses the parent change's property_path to navigate to the correct
        nested location. For example, if change path is "PrimaryDrop.DropRate",
        the property is added inside PrimaryDrop's Value array.

        Args:
            json_data: The full JSON data structure.
            item_name: The row/export name to find.
            property_json_text: JSON string defining the property to add.
            change_property_path: The parent change's property path (dot notation).
        """
        try:
            new_property = json.loads(property_json_text)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse add_property JSON for %s: %s",
                item_name, e,
            )
            return

        prop_name = new_property.get('Name', '')
        if not prop_name:
            logger.error(
                "add_property missing 'Name' field for item %s", item_name,
            )
            return

        if 'Exports' not in json_data:
            return

        # Determine parent path segments from the change's property path
        # e.g., "PrimaryDrop.DropRate" -> parent_parts = ["PrimaryDrop"]
        parent_parts = []
        if '.' in change_property_path:
            parent_parts = change_property_path.split('.')[:-1]

        # Find the target data array for this item
        target_data = self._find_item_data(json_data, item_name)
        if target_data is None:
            return

        # Navigate parent path to find the correct container
        for part in parent_parts:
            found = False
            if isinstance(target_data, list):
                for item in target_data:
                    if isinstance(item, dict) and item.get('Name') == part:
                        target_data = item.get('Value', [])
                        found = True
                        break
            if not found:
                logger.debug(
                    "  ADD_PROPERTY: parent '%s' not found for %s",
                    part, item_name,
                )
                return

        # Add property if not already present
        if isinstance(target_data, list):
            exists = any(
                p.get('Name') == prop_name
                for p in target_data if isinstance(p, dict)
            )
            if not exists:
                target_data.append(new_property)
                logger.info(
                    "  ADD_PROPERTY: %s.%s", item_name, prop_name,
                )
            else:
                logger.debug(
                    "  ADD_PROPERTY: %s.%s already exists",
                    item_name, prop_name,
                )

    def _find_item_data(self, json_data: dict, item_name: str):
        """Find the Data/Value array for a given item name.

        Returns the list to search/modify, or None if not found.
        """
        # Try single-asset exports (ObjectName matching)
        name_variations = [
            f"Default__{item_name}_C",
            f"Default__{item_name}",
            item_name,
            f"{item_name}_C",
        ]
        for name_variant in name_variations:
            for export in json_data['Exports']:
                if export.get('ObjectName', '') == name_variant:
                    data = export.get('Data', [])
                    if isinstance(data, list):
                        return data

        # Try DataTable format (Table.Data rows)
        try:
            table_data = json_data['Exports'][0]['Table']['Data']
            for row in table_data:
                if row.get('Name') == item_name:
                    value_array = row.get('Value', [])
                    if isinstance(value_array, list):
                        return value_array
        except (KeyError, IndexError, TypeError):
            pass

        return None

    def _set_nested_property_value(self, data: list | dict, property_path: str, new_value: str):
        """Set a property value using dot notation for nested traversal.

        Supports array indexing with bracket notation, e.g.:
        - "StageDataList[1].MonumentProgressonPointsNeeded"
        - "Value[0].Count"
        - "FloatCurve.Keys[*].Time" (wildcard applies to all elements)

        Also handles dict-style properties where the value is a direct key
        (e.g., {"Time": 0, "Value": 90} instead of [{"Name": "Time", "Value": 0}])

        Args:
            data: The data list or dict to modify.
            property_path: Dot-separated property path with optional array indices.
            new_value: The new value to set.
        """
        if not data or not property_path:
            return

        # Check for wildcard [*] - expand and recursively call for each index
        if '[*]' in property_path:
            self._set_wildcard_property_value(data, property_path, new_value)
            return

        # Parse property path into parts, handling array indices
        parts = []
        for segment in property_path.split('.'):
            match = re.match(r'^(\w+)(?:\[(\d+)\])?$', segment)
            if match:
                name = match.group(1)
                index = int(match.group(2)) if match.group(2) is not None else None
                parts.append((name, index))
            else:
                parts.append((segment, None))

        current = data

        # Traverse to the parent of the target property
        for name, index in parts[:-1]:
            current = self._traverse_property(current, name, index)
            if current is None:
                return

        # Set the final property value
        target_name, target_index = parts[-1]
        self._set_final_property(current, target_name, target_index, new_value)

    def _traverse_property(self, current, name: str, index: int | None):
        """Traverse one level of property path.

        Returns the next level of data, or None if not found.
        """
        if isinstance(current, list):
            for item in current:
                if isinstance(item, dict) and item.get('Name') == name:
                    if 'Value' in item:
                        result = item['Value']
                        # Handle array indexing
                        if index is not None and isinstance(result, list):
                            if 0 <= index < len(result):
                                indexed_item = result[index]
                                if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                                    return indexed_item['Value']
                                return indexed_item
                            return None  # Index out of bounds
                        return result
            return None
        if isinstance(current, dict):
            # Handle dict-style access (e.g., for RichCurveKey)
            if name in current:
                result = current[name]
                if index is not None and isinstance(result, list):
                    if 0 <= index < len(result):
                        indexed_item = result[index]
                        if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                            return indexed_item['Value']
                        return indexed_item
                    return None
                return result
            if 'Value' in current:
                # Try to traverse into Value
                return self._traverse_property(current['Value'], name, index)
        return None

    def _set_final_property(self, current, target_name: str, target_index: int | None, new_value: str):
        """Set the final property value."""
        if isinstance(current, list):
            for item in current:
                if isinstance(item, dict) and item.get('Name') == target_name:
                    # Handle array indexing on the final property
                    if target_index is not None:
                        if 'Value' in item and isinstance(item['Value'], list):
                            if 0 <= target_index < len(item['Value']):
                                indexed_item = item['Value'][target_index]
                                if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                                    old_value = indexed_item['Value']
                                    indexed_item['Value'] = self._convert_value(old_value, new_value)
                        return

                    if 'Value' in item:
                        old_value = item['Value']
                        item['Value'] = self._convert_value(old_value, new_value)
                    return
        if isinstance(current, dict):
            # Handle dict-style property (e.g., {"Time": 0, "Value": 90})
            if target_name in current:
                old_value = current[target_name]
                current[target_name] = self._convert_value(old_value, new_value)

    def _set_wildcard_property_value(self, data: list | dict, property_path: str, new_value: str):
        """Handle [*] wildcard by expanding to all array indices."""
        # Find the array with wildcard and get its length
        match = re.match(r'^(.+?)\[\*\](.*)$', property_path)
        if not match:
            return

        array_path = match.group(1)  # e.g., "FloatCurve.Keys"
        rest_of_path = match.group(2)  # e.g., ".Time" or ""
        if rest_of_path.startswith('.'):
            rest_of_path = rest_of_path[1:]

        # Traverse to the array
        parts = []
        for segment in array_path.split('.'):
            match_part = re.match(r'^(\w+)(?:\[(\d+)\])?$', segment)
            if match_part:
                name = match_part.group(1)
                index = int(match_part.group(2)) if match_part.group(2) is not None else None
                parts.append((name, index))
            else:
                parts.append((segment, None))

        current = data
        for name, index in parts:
            current = self._traverse_property(current, name, index)
            if current is None:
                return

        # current should now be the array
        if not isinstance(current, list):
            return

        # Apply to each element
        for i in range(len(current)):
            if rest_of_path:
                expanded_path = f"{array_path}[{i}].{rest_of_path}"
            else:
                expanded_path = f"{array_path}[{i}]"
            self._set_nested_property_value(data, expanded_path, new_value)

    def _convert_value(self, old_value, new_value: str):
        """Convert new_value to match the type of old_value."""
        # Check bool BEFORE int because bool is a subclass of int in Python
        if isinstance(old_value, bool):
            return new_value.lower() in ('true', '1', 'yes')
        if isinstance(old_value, float):
            try:
                return float(new_value)
            except ValueError:
                return new_value
        if isinstance(old_value, int):
            try:
                return int(float(new_value))
            except ValueError:
                return new_value
        return new_value

    def _is_gameplay_tag_container(
        self,
        json_data: dict,
        item_name: str,
        property_name: str
    ) -> bool:
        """Check if a property is a GameplayTagContainer by inspecting the JSON structure."""
        try:
            items = json_data['Exports'][0]['Table']['Data']
        except (KeyError, IndexError, TypeError):
            return False

        for item in items:
            if item.get('Name') != item_name:
                continue
            for prop in item.get('Value', []):
                if prop.get('Name') != property_name:
                    continue
                # Check if it's a struct with GameplayTagContainer type,
                # or directly a GameplayTagContainerPropertyData
                t = prop.get('$type', '')
                if 'GameplayTagContainer' in t:
                    return True
                if prop.get('StructType') == 'GameplayTagContainer':
                    return True
                # Check inner Value for GameplayTagContainerPropertyData
                outer = prop.get('Value', [])
                if isinstance(outer, list) and outer:
                    inner = outer[0] if isinstance(outer[0], dict) else None
                    if inner and 'GameplayTagContainer' in inner.get('$type', ''):
                        return True
            break
        return False

    def _remove_gameplay_tag(
        self,
        json_data: dict,
        item_name: str,
        property_name: str,
        tag_to_remove: str
    ):
        """Remove a tag from a GameplayTagContainer array in DT_Storage data.

        Args:
            json_data: The JSON data to modify.
            item_name: The storage row name (e.g., "Dwarf.Inventory").
            property_name: The property name (e.g., "ExcludeItems", "AllowedItems").
            tag_to_remove: The tag to remove (e.g., "Item.Brew").
        """
        if 'Exports' not in json_data:
            return

        # Find the Table.Data for data tables (DT_Storage format)
        try:
            items = json_data['Exports'][0]['Table']['Data']
        except (KeyError, IndexError, TypeError):
            return

        # Find the item by name
        for item in items:
            if item.get('Name') != item_name:
                continue

            # Find the specified property in the Value array
            value_array = item.get('Value', [])
            for prop in value_array:
                if prop.get('Name') != property_name:
                    continue

                # Navigate to the inner Value array containing tags
                outer_value = prop.get('Value', [])
                if not isinstance(outer_value, list) or len(outer_value) == 0:
                    continue

                inner = outer_value[0]
                if not isinstance(inner, dict):
                    continue

                tags = inner.get('Value', [])
                if not isinstance(tags, list):
                    continue

                # Remove the tag if it exists
                if tag_to_remove in tags:
                    tags.remove(tag_to_remove)
                    logger.info(
                        "Removed tag '%s' from %s in '%s'",
                        tag_to_remove, property_name, item_name
                    )
                return

    def _add_gameplay_tag(
        self,
        json_data: dict,
        item_name: str,
        property_name: str,
        tag_to_add: str
    ):
        """Add a tag to a GameplayTagContainer array in DT_Storage data.

        Args:
            json_data: The JSON data to modify.
            item_name: The storage row name (e.g., "Dwarf.Inventory").
            property_name: The property name (e.g., "ExcludeItems", "AllowedItems").
            tag_to_add: The tag to add (e.g., "Item.NewTag").
        """
        if 'Exports' not in json_data:
            return

        # Find the Table.Data for data tables (DT_Storage format)
        try:
            items = json_data['Exports'][0]['Table']['Data']
        except (KeyError, IndexError, TypeError):
            return

        # Find the item by name
        for item in items:
            if item.get('Name') != item_name:
                continue

            # Find the specified property in the Value array
            value_array = item.get('Value', [])
            for prop in value_array:
                if prop.get('Name') != property_name:
                    continue

                # Navigate to the inner Value array containing tags
                outer_value = prop.get('Value', [])
                if not isinstance(outer_value, list) or len(outer_value) == 0:
                    continue

                inner = outer_value[0]
                if not isinstance(inner, dict):
                    continue

                tags = inner.get('Value', [])
                if not isinstance(tags, list):
                    continue

                # Add the tag if it doesn't already exist
                if tag_to_add not in tags:
                    tags.append(tag_to_add)
                    logger.info(
                        "Added tag '%s' to %s in '%s'",
                        tag_to_add, property_name, item_name
                    )
                return

    @staticmethod
    def _sync_namemap(json_data: dict):
        """Ensure all FName-referenced values are present in the NameMap.

        UAssetAPI requires every FName referenced in the data to exist in
        the top-level NameMap. After modifying values, new names may have
        been introduced that aren't in the map yet. This covers:
        - Property Name fields (every PropertyData has a Name that is an FName)
        - NamePropertyData values
        - EnumPropertyData values and EnumType fields
        - StructPropertyData StructType fields
        - ArrayPropertyData/SetPropertyData ArrayType fields
        - MapPropertyData KeyType/ValueType fields
        - TextPropertyData TableId and Value fields (StringTableEntry)
        """
        name_map = json_data.get('NameMap')
        if not isinstance(name_map, list):
            return

        name_set = set(name_map)
        added = []

        def _add_if_missing(val):
            if isinstance(val, str) and val and val not in name_set:
                name_set.add(val)
                name_map.append(val)
                added.append(val)

        def _scan(obj):
            """Recursively scan for all FName references in property data."""
            if isinstance(obj, dict):
                dtype = obj.get('$type', '')
                # Every property's Name field is an FName
                if 'PropertyData' in dtype:
                    _add_if_missing(obj.get('Name'))
                # Type-specific FName fields
                if 'NamePropertyData' in dtype:
                    _add_if_missing(obj.get('Value'))
                elif 'EnumPropertyData' in dtype:
                    _add_if_missing(obj.get('Value'))
                    _add_if_missing(obj.get('EnumType'))
                elif 'StructPropertyData' in dtype:
                    _add_if_missing(obj.get('StructType'))
                elif 'ArrayPropertyData' in dtype or 'SetPropertyData' in dtype:
                    _add_if_missing(obj.get('ArrayType'))
                elif 'MapPropertyData' in dtype:
                    _add_if_missing(obj.get('KeyType'))
                    _add_if_missing(obj.get('ValueType'))
                elif 'TextPropertyData' in dtype:
                    _add_if_missing(obj.get('TableId'))
                    _add_if_missing(obj.get('Value'))
                for v in obj.values():
                    _scan(v)
            elif isinstance(obj, list):
                for item in obj:
                    _scan(item)

        for export in json_data.get('Exports', []):
            _scan(export)

        if added:
            logger.info("NameMap: added %d new entries: %s", len(added), added)

    def _convert_json_to_uasset(self, mod_name: str) -> tuple[bool, str]:
        """Convert JSON files to uasset format using UAssetGUI.

        Args:
            mod_name: Name of the mod.

        Returns:
            Tuple of (success, error_detail). error_detail is empty on success.
        """
        utilities_dir = get_utilities_dir()
        uassetgui_path = utilities_dir / UASSETGUI_EXE

        if not uassetgui_path.exists():
            logger.error("%s not found at %s", UASSETGUI_EXE, uassetgui_path)
            return (False, f"{UASSETGUI_EXE} not found at {uassetgui_path}")

        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        json_dir = mymodfiles_base / JSONFILES_DIR
        uasset_dir = mymodfiles_base / UASSET_DIR

        uasset_dir.mkdir(parents=True, exist_ok=True)

        json_files = list(json_dir.rglob('*.json'))
        if not json_files:
            logger.error("No JSON files found to convert")
            return (False, "No JSON files found to convert")

        logger.info("Converting %d JSON files to uasset format", len(json_files))
        for i, json_file in enumerate(json_files):
            # Update progress
            step_progress = 0.4 + (0.3 * (i / len(json_files)))
            self._report_progress(f"Converting {json_file.name}...", step_progress)

            rel_path = json_file.relative_to(json_dir)
            uasset_file = uasset_dir / rel_path.with_suffix('.uasset')
            uasset_file.parent.mkdir(parents=True, exist_ok=True)

            cmd = [
                str(uassetgui_path),
                'fromjson',
                str(json_file),
                str(uasset_file),
                UE_VERSION
            ]

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=BUILD_TIMEOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                    check=False
                )

                if result.returncode != 0 or not uasset_file.exists():
                    error_output = (
                        result.stderr.strip() if result.stderr
                        else result.stdout.strip() if result.stdout
                        else "Unknown error"
                    )
                    logger.error(
                        "Failed to convert %s:\n  returncode=%s\n  stdout=%s\n  stderr=%s",
                        json_file.name, result.returncode,
                        result.stdout.strip() if result.stdout else "(empty)",
                        result.stderr.strip() if result.stderr else "(empty)"
                    )
                    return (False, f"File: {json_file.name}\n\n{error_output}")

            except subprocess.TimeoutExpired:
                logger.error("Timeout converting %s", json_file.name)
                return (False, f"File: {json_file.name}\n\nConversion timed out")
            except OSError as e:
                logger.error("Error converting %s: %s", json_file.name, e)
                return (False, f"File: {json_file.name}\n\n{e}")

        logger.info("All %d JSON files converted to uasset successfully", len(json_files))
        return (True, "")

    def _run_retoc(self, mod_name: str) -> bool:
        """Run retoc to package uasset files into zen format.

        Args:
            mod_name: Name of the mod.

        Returns:
            True if successful, False otherwise.
        """
        utilities_dir = get_utilities_dir()
        retoc_path = utilities_dir / RETOC_EXE

        if not retoc_path.exists():
            logger.error("%s not found at %s", RETOC_EXE, retoc_path)
            return False

        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        uasset_dir = mymodfiles_base / UASSET_DIR
        final_dir = mymodfiles_base / FINALMOD_DIR

        # Create mod_P subdirectory inside finalmod
        mod_p_name = f'{mod_name}_P'
        mod_p_dir = final_dir / mod_p_name
        mod_p_dir.mkdir(parents=True, exist_ok=True)

        output_utoc = mod_p_dir / f'{mod_p_name}.utoc'

        cmd = [
            str(retoc_path),
            'to-zen',
            '--version', RETOC_UE_VERSION,
            str(uasset_dir),
            str(output_utoc)
        ]

        logger.debug("Running retoc command: %s", ' '.join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(utilities_dir),
                check=False
            )

            if result.returncode != 0:
                logger.error("retoc failed with code %s", result.returncode)
                logger.error("stdout: %s", result.stdout)
                logger.error("stderr: %s", result.stderr)
                return False

            logger.info("retoc packaging completed successfully: %s", output_utoc)
            return True

        except OSError as e:
            logger.error("Error running retoc: %s", e)
            return False

    def _copy_secrets_pak_files(self, mod_name: str):
        """Copy secrets pak/ucas/utoc files into the finalmod directory.

        Searches Secrets Source/ recursively for specific pak files
        and copies them into the mod_P directory alongside the retoc output.

        Args:
            mod_name: Name of the mod.
        """
        secrets_dir = get_appdata_dir() / 'Secrets Source'
        if not secrets_dir.exists():
            logger.warning("Secrets Source directory not found, skipping pak copy")
            return

        target_files = {
            'SecretsOfKhazadDum_Localization_P.pak',
        }

        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        mod_p_dir = mymodfiles_base / FINALMOD_DIR / f'{mod_name}_P'
        mod_p_dir.mkdir(parents=True, exist_ok=True)

        found = 0
        for target_name in target_files:
            # Search recursively for the file
            matches = list(secrets_dir.rglob(target_name))
            if matches:
                source = matches[0]
                dest = mod_p_dir / target_name
                shutil.copy2(source, dest)
                found += 1
                logger.info("Copied secrets file: %s -> %s", source, dest)
            else:
                logger.warning("Secrets file not found: %s", target_name)

        logger.info("Copied %d of %d secrets pak files", found, len(target_files))

    def _create_zip(self, mod_name: str) -> Path | None:
        """Create a zip file of the mod in the configured destination directory.

        The zip contains the {mod_name}_P directory with all mod files.

        Args:
            mod_name: Name of the mod.

        Returns:
            Path to the created zip file, or None if failed.
        """
        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        final_dir = mymodfiles_base / FINALMOD_DIR
        mod_p_name = f'{mod_name}_P'
        mod_p_dir = final_dir / mod_p_name

        if not mod_p_dir.exists():
            logger.error("mod directory not found: %s", mod_p_dir)
            return None

        dest_dir = get_final_destination_dir()
        dest_dir.mkdir(parents=True, exist_ok=True)

        zip_path = dest_dir / f'{mod_name}.zip'

        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Include the mod_P directory in the zip structure
                for file_path in mod_p_dir.rglob('*'):
                    if file_path.is_file():
                        # Archive path includes the mod_P folder name
                        rel_path = file_path.relative_to(final_dir)
                        zipf.write(file_path, rel_path)

            logger.info("Created mod zip: %s", zip_path)
            return zip_path

        except OSError as e:
            logger.error("Error creating zip file: %s", e)
            return None
