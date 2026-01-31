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

from src.config import get_output_dir, get_default_mymodfiles_dir, get_utilities_dir
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


class BuildManager:
    """Manages the mod build process."""

    def __init__(self, progress_callback: Callable[[str, float], None] | None = None):
        """Initialize the build manager.
        
        Args:
            progress_callback: Optional callback function(message, progress_percent) 
                              for reporting progress.
        """
        self.progress_callback = progress_callback

    def _report_progress(self, message: str, progress: float):
        """Report progress if callback is set.
        
        Args:
            message: Status message.
            progress: Progress percentage (0.0 to 1.0).
        """
        logger.info("Build progress: %.0f%% - %s", progress * 100, message)
        if self.progress_callback:
            self.progress_callback(message, progress)

    def build(self, mod_name: str, def_files: list[Path]) -> tuple[bool, str]:
        """Build a complete mod from definition files.
        
        Args:
            mod_name: Name of the mod.
            def_files: List of definition file paths.
            
        Returns:
            Tuple of (success, message).
        """
        if not def_files:
            return False, "No definition files selected"

        try:
            # Step 0: Clear previous build files
            self._report_progress("Cleaning previous build files...", 0.0)
            self._clean_build_directories(mod_name)
            
            # Step 1: Process definition files (5-40%)
            self._report_progress("Processing definition files...", 0.05)
            success_count, error_count = self._process_definitions(mod_name, def_files)
            
            if error_count > 0:
                return False, f"{success_count} succeeded, {error_count} failed"
            
            if success_count == 0:
                return False, "No files were processed"

            # Step 2: Convert JSON to uasset (40-70%)
            self._report_progress("Converting to uasset format...", 0.4)
            if not self._convert_json_to_uasset(mod_name):
                return False, "JSON to uasset conversion failed"

            # Step 3: Run retoc (70-90%)
            self._report_progress("Packaging mod files...", 0.7)
            if not self._run_retoc(mod_name):
                return False, "retoc packaging failed"

            # Step 4: Create zip (90-100%)
            self._report_progress("Creating zip file...", 0.9)
            zip_path = self._create_zip(mod_name)
            
            if zip_path:
                self._report_progress("Build complete!", 1.0)
                return True, f"Mod saved to: {zip_path}"
            else:
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

    def _process_definitions(self, mod_name: str, def_files: list[Path]) -> tuple[int, int]:
        """Process all definition files and modify JSON.
        
        Args:
            mod_name: Name of the mod.
            def_files: List of definition file paths.
            
        Returns:
            Tuple of (success_count, error_count).
        """
        success_count = 0
        error_count = 0
        
        jsondata_dir = get_output_dir() / JSONDATA_DIR
        mymodfiles_dir = get_default_mymodfiles_dir() / mod_name / JSONFILES_DIR
        
        for i, def_file in enumerate(def_files):
            # Update progress within this step
            step_progress = 0.0 + (0.4 * (i / len(def_files)))
            self._report_progress(f"Processing {def_file.name}...", step_progress)
            
            try:
                if self._process_single_definition(def_file, jsondata_dir, mymodfiles_dir):
                    success_count += 1
                else:
                    error_count += 1
            except (OSError, ET.ParseError, json.JSONDecodeError) as e:
                logger.error("Error processing %s: %s", def_file.name, e)
                error_count += 1
        
        return success_count, error_count

    def _process_single_definition(
        self, 
        def_file: Path, 
        jsondata_dir: Path, 
        mymodfiles_dir: Path
    ) -> bool:
        """Process a single definition file.
        
        Args:
            def_file: Path to the .def file.
            jsondata_dir: Source JSON data directory.
            mymodfiles_dir: Destination directory for modified files.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            tree = ET.parse(def_file)
            root = tree.getroot()
            
            mod_element = root.find('mod')
            if mod_element is None:
                logger.error("No <mod> element in %s", def_file.name)
                return False
            
            mod_file_path = mod_element.get('file', '')
            if not mod_file_path:
                logger.error("No file attribute in <mod> element of %s", def_file.name)
                return False
            
            # Normalize the path
            normalized_path = mod_file_path.lstrip('\\').lstrip('/').replace('\\', '/')
            
            # Source and destination files
            source_file = jsondata_dir / normalized_path
            if not source_file.exists():
                logger.error("Source file not found: %s", source_file)
                return False
            
            dest_file = mymodfiles_dir / normalized_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source_file, dest_file)
            
            # Load and modify JSON
            with open(dest_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Apply delete operations first
            for delete in mod_element.findall('delete'):
                item_name = delete.get('item', '')
                property_path = delete.get('property', '')
                value_to_delete = delete.get('value', '')
                
                if item_name == 'NONE':
                    continue
                
                # Handle GameplayTagContainer deletions (ExcludeItems, AllowedItems)
                if property_path in ('ExcludeItems', 'AllowedItems') and value_to_delete:
                    self._remove_gameplay_tag(json_data, item_name, property_path, value_to_delete)
            
            # Apply change operations
            for change in mod_element.findall('change'):
                item_name = change.get('item', '')
                property_path = change.get('property', '')
                new_value = change.get('value', '')
                
                if item_name == 'NONE':
                    continue
                
                # Special handling for GameplayTagContainer - replace tag in array
                if property_path in ('ExcludeItems', 'AllowedItems'):
                    # 'original' = tag to remove, 'value' = tag to add
                    original_tag = change.get('original', '')
                    new_tag = new_value.strip()
                    
                    # Remove the original tag
                    if original_tag:
                        self._remove_gameplay_tag(json_data, item_name, property_path, original_tag)
                    
                    # Add the new tag
                    if new_tag:
                        self._add_gameplay_tag(json_data, item_name, property_path, new_tag)
                else:
                    self._apply_json_change(json_data, item_name, property_path, new_value)
            
            # Save modified JSON
            with open(dest_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except ET.ParseError as e:
            logger.error("XML parse error in %s: %s", def_file.name, e)
            return False
        except json.JSONDecodeError as e:
            logger.error("JSON parse error: %s", e)
            return False

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
            item_name: The export name or row name to find.
            property_path: Dot-separated property path.
            new_value: The new value to set.
        """
        if 'Exports' not in json_data:
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

    def _set_nested_property_value(self, data: list, property_path: str, new_value: str):
        """Set a property value using dot notation for nested traversal.
        
        Supports array indexing with bracket notation, e.g.:
        - "StageDataList[1].MonumentProgressonPointsNeeded"
        - "Value[0].Count"
        
        Args:
            data: The data list to modify.
            property_path: Dot-separated property path with optional array indices.
            new_value: The new value to set.
        """
        if not data or not property_path:
            return
        
        # Parse property path into parts, handling array indices
        # e.g., "StageDataList[1].MonumentProgressonPointsNeeded" -> [("StageDataList", 1), ("MonumentProgressonPointsNeeded", None)]
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
            if isinstance(current, list):
                found = False
                for item in current:
                    if isinstance(item, dict) and item.get('Name') == name:
                        if 'Value' in item:
                            current = item['Value']
                            # Handle array indexing
                            if index is not None and isinstance(current, list):
                                if 0 <= index < len(current):
                                    indexed_item = current[index]
                                    # If indexed item has a Value, traverse into it
                                    if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                                        current = indexed_item['Value']
                                    else:
                                        current = indexed_item
                                else:
                                    return  # Index out of bounds
                            found = True
                            break
                if not found:
                    return
            else:
                return
        
        # Set the final property value
        target_name, target_index = parts[-1]
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
    
    def _convert_value(self, old_value, new_value: str):
        """Convert new_value to match the type of old_value."""
        # Check bool BEFORE int because bool is a subclass of int in Python
        if isinstance(old_value, bool):
            return new_value.lower() in ('true', '1', 'yes')
        elif isinstance(old_value, float):
            try:
                return float(new_value)
            except ValueError:
                return new_value
        elif isinstance(old_value, int):
            try:
                return int(float(new_value))
            except ValueError:
                return new_value
        else:
            return new_value

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

    def _convert_json_to_uasset(self, mod_name: str) -> bool:
        """Convert JSON files to uasset format using UAssetGUI.
        
        Args:
            mod_name: Name of the mod.
            
        Returns:
            True if successful, False otherwise.
        """
        utilities_dir = get_utilities_dir()
        uassetgui_path = utilities_dir / UASSETGUI_EXE
        
        if not uassetgui_path.exists():
            logger.error("%s not found at %s", UASSETGUI_EXE, uassetgui_path)
            return False
        
        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        json_dir = mymodfiles_base / JSONFILES_DIR
        uasset_dir = mymodfiles_base / UASSET_DIR
        
        uasset_dir.mkdir(parents=True, exist_ok=True)
        
        json_files = list(json_dir.rglob('*.json'))
        if not json_files:
            logger.error("No JSON files found to convert")
            return False
        
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
                    timeout=BUILD_TIMEOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                    check=False
                )
                
                if result.returncode != 0 or not uasset_file.exists():
                    logger.error("Failed to convert %s: %s", json_file.name, result.stderr)
                    return False
                    
            except subprocess.TimeoutExpired:
                logger.error("Timeout converting %s", json_file.name)
                return False
            except OSError as e:
                logger.error("Error converting %s: %s", json_file.name, e)
                return False
        
        return True

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
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(utilities_dir),
                check=False
            )
            
            if result.returncode != 0:
                logger.error("retoc failed with code %s", result.returncode)
                logger.error("stdout: %s", result.stdout)
                logger.error("stderr: %s", result.stderr)
                return False
            
            return True
            
        except OSError as e:
            logger.error("Error running retoc: %s", e)
            return False

    def _create_zip(self, mod_name: str) -> Path | None:
        """Create a zip file of the mod in Downloads folder.
        
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
        
        downloads_dir = Path.home() / 'Downloads'
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = downloads_dir / f'{mod_name}.zip'
        
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
