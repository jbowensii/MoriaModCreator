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
        logger.info(f"Build progress: {progress:.0%} - {message}")
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
            # Step 1: Process definition files (0-40%)
            self._report_progress("Processing definition files...", 0.0)
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

        except Exception as e:
            logger.exception("Build failed with exception")
            return False, str(e)

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
            except Exception as e:
                logger.error(f"Error processing {def_file.name}: {e}")
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
                logger.error(f"No <mod> element in {def_file.name}")
                return False
            
            mod_file_path = mod_element.get('file', '')
            if not mod_file_path:
                logger.error(f"No file attribute in <mod> element of {def_file.name}")
                return False
            
            # Normalize the path
            normalized_path = mod_file_path.lstrip('\\').lstrip('/').replace('\\', '/')
            
            # Source and destination files
            source_file = jsondata_dir / normalized_path
            if not source_file.exists():
                logger.error(f"Source file not found: {source_file}")
                return False
            
            dest_file = mymodfiles_dir / normalized_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Copy the file
            shutil.copy2(source_file, dest_file)
            
            # Load and modify JSON
            with open(dest_file, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
            
            # Apply changes
            for change in mod_element.findall('change'):
                item_name = change.get('item', '')
                property_path = change.get('property', '')
                new_value = change.get('value', '')
                
                if item_name == 'NONE':
                    continue
                
                self._apply_json_change(json_data, item_name, property_path, new_value)
            
            # Save modified JSON
            with open(dest_file, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, indent=2, ensure_ascii=False)
            
            return True
            
        except ET.ParseError as e:
            logger.error(f"XML parse error in {def_file.name}: {e}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
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
            item_name: The export name to find.
            property_path: Dot-separated property path.
            new_value: The new value to set.
        """
        if 'Exports' not in json_data:
            return
        
        # Try multiple ObjectName variations - prefer Default__ versions first
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

    def _set_nested_property_value(self, data: list, property_path: str, new_value: str):
        """Set a property value using dot notation for nested traversal.
        
        Args:
            data: The data list to modify.
            property_path: Dot-separated property path.
            new_value: The new value to set.
        """
        if not data or not property_path:
            return
        
        parts = property_path.split('.')
        current = data
        
        # Traverse to the parent of the target property
        for part in parts[:-1]:
            if isinstance(current, list):
                found = False
                for item in current:
                    if isinstance(item, dict) and item.get('Name') == part:
                        if 'Value' in item:
                            current = item['Value']
                            found = True
                            break
                if not found:
                    return
            else:
                return
        
        # Set the final property value
        target_name = parts[-1]
        if isinstance(current, list):
            for item in current:
                if isinstance(item, dict) and item.get('Name') == target_name:
                    if 'Value' in item:
                        old_value = item['Value']
                        # Check bool BEFORE int because bool is a subclass of int in Python
                        if isinstance(old_value, bool):
                            item['Value'] = new_value.lower() in ('true', '1', 'yes')
                        elif isinstance(old_value, float):
                            try:
                                item['Value'] = float(new_value)
                            except ValueError:
                                item['Value'] = new_value
                        elif isinstance(old_value, int):
                            try:
                                item['Value'] = int(float(new_value))
                            except ValueError:
                                item['Value'] = new_value
                        else:
                            item['Value'] = new_value
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
            logger.error(f"{UASSETGUI_EXE} not found at {uassetgui_path}")
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
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                )
                
                if result.returncode != 0 or not uasset_file.exists():
                    logger.error(f"Failed to convert {json_file.name}: {result.stderr}")
                    return False
                    
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout converting {json_file.name}")
                return False
            except Exception as e:
                logger.error(f"Error converting {json_file.name}: {e}")
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
            logger.error(f"{RETOC_EXE} not found at {retoc_path}")
            return False
        
        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        uasset_dir = mymodfiles_base / UASSET_DIR
        final_dir = mymodfiles_base / FINALMOD_DIR
        
        final_dir.mkdir(parents=True, exist_ok=True)
        
        output_utoc = final_dir / f'{mod_name}_P.utoc'
        
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
                cwd=str(utilities_dir)
            )
            
            if result.returncode != 0:
                logger.error(f"retoc failed with code {result.returncode}")
                logger.error(f"stdout: {result.stdout}")
                logger.error(f"stderr: {result.stderr}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error running retoc: {e}")
            return False

    def _create_zip(self, mod_name: str) -> Path | None:
        """Create a zip file of the mod in Downloads folder.
        
        Args:
            mod_name: Name of the mod.
            
        Returns:
            Path to the created zip file, or None if failed.
        """
        mymodfiles_base = get_default_mymodfiles_dir() / mod_name
        final_dir = mymodfiles_base / FINALMOD_DIR
        
        if not final_dir.exists():
            logger.error(f"finalmod directory not found: {final_dir}")
            return None
        
        downloads_dir = Path.home() / 'Downloads'
        downloads_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = downloads_dir / f'{mod_name}.zip'
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in final_dir.rglob('*'):
                    if file_path.is_file():
                        rel_path = file_path.relative_to(final_dir)
                        zipf.write(file_path, rel_path)
            
            logger.info(f"Created mod zip: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Error creating zip file: {e}")
            return None
