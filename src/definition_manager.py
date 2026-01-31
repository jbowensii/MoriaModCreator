"""Definition manager for Moria MOD Creator.

This module handles:
- Loading and saving checkbox states to INI files
- Parsing .def definition files
- Managing definition file collections
"""

import configparser
import logging
import xml.etree.ElementTree as ET
from pathlib import Path

from src.config import get_default_mymodfiles_dir
from src.constants import (
    CHECKBOX_STATES_FILE,
    CHECKBOX_STATES_SECTION,
    DEF_FILE_EXTENSION,
)

logger = logging.getLogger(__name__)


class DefinitionManager:
    """Manages mod definition files and their states."""

    def __init__(self, mod_name: str | None = None):
        """Initialize the definition manager.
        
        Args:
            mod_name: Name of the current mod (for checkbox states).
        """
        self._mod_name = mod_name
        self._checkbox_states: dict[str, bool] = {}
        
        if mod_name:
            self.load_checkbox_states()

    @property
    def mod_name(self) -> str | None:
        """Get the current mod name."""
        return self._mod_name

    @mod_name.setter
    def mod_name(self, value: str | None):
        """Set the current mod name and reload checkbox states."""
        self._mod_name = value
        if value:
            self.load_checkbox_states()
        else:
            self._checkbox_states = {}

    def get_checkbox_ini_path(self) -> Path:
        """Get the path to the checkbox states INI file.
        
        Returns:
            Path to the INI file.
        """
        if not self._mod_name:
            return Path()
        return get_default_mymodfiles_dir() / self._mod_name / CHECKBOX_STATES_FILE

    def load_checkbox_states(self):
        """Load checkbox states from the INI file."""
        self._checkbox_states = {}
        
        if not self._mod_name:
            return
            
        ini_path = self.get_checkbox_ini_path()
        if not ini_path.exists():
            return
            
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case
        
        try:
            config.read(ini_path, encoding='utf-8')
            if CHECKBOX_STATES_SECTION in config:
                for key, value in config[CHECKBOX_STATES_SECTION].items():
                    if value.lower() == 'true':
                        # Reconstruct path from key (replace | with \ and ~ with :)
                        path_str = key.replace('|', '\\').replace('~', ':')
                        self._checkbox_states[path_str] = True
        except (OSError, configparser.Error) as e:
            logger.error("Error loading checkbox states: %s", e)

    def save_checkbox_states(self, ui_states: dict[Path, bool] | None = None):
        """Save checkbox states to the INI file.
        
        Args:
            ui_states: Optional dict of Path -> bool from UI checkboxes to merge in.
        """
        if not self._mod_name:
            return
        
        # Merge UI states if provided
        if ui_states:
            for path, is_checked in ui_states.items():
                self._checkbox_states[str(path)] = is_checked
            
        ini_path = self.get_checkbox_ini_path()
        config = configparser.ConfigParser()
        config.optionxform = str  # Preserve case
        config[CHECKBOX_STATES_SECTION] = {}
        
        # Save all checked states
        for path_str, is_checked in self._checkbox_states.items():
            if is_checked:
                # Convert path to key (replace \ with | and : with ~ to avoid configparser issues)
                path_key = path_str.replace('\\', '|').replace('/', '|').replace(':', '~')
                config[CHECKBOX_STATES_SECTION][path_key] = 'true'
        
        try:
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            with open(ini_path, 'w', encoding='utf-8') as f:
                config.write(f)
        except OSError as e:
            logger.error("Error saving checkbox states: %s", e)

    def get_saved_state(self, path: Path) -> bool:
        """Get the saved checkbox state for a path.
        
        Args:
            path: Path to check.
            
        Returns:
            True if the item was checked, False otherwise.
        """
        path_str = str(path)
        
        # Check for exact match first
        if path_str in self._checkbox_states:
            return self._checkbox_states[path_str]
        
        # Case-insensitive fallback for Windows paths
        path_lower = path_str.lower()
        for saved_path, is_checked in self._checkbox_states.items():
            if saved_path.lower() == path_lower:
                return is_checked
        
        return False

    def set_state(self, path: Path, is_checked: bool):
        """Set the checkbox state for a path.
        
        Args:
            path: Path to update.
            is_checked: Whether the item is checked.
        """
        self._checkbox_states[str(path)] = is_checked

    def get_all_selected_definitions(self) -> list[Path]:
        """Get all selected definition files from saved states.
        
        Returns:
            List of paths to all checked .def files.
        """
        selected = []
        
        for path_str, is_checked in self._checkbox_states.items():
            if is_checked:
                path = Path(path_str)
                # Only include .def files (not directories)
                if path.suffix.lower() == DEF_FILE_EXTENSION and path.exists():
                    selected.append(path)
        
        return selected

    @staticmethod
    def parse_definition(file_path: Path) -> dict | None:
        """Parse a .def file and return its contents.
        
        Args:
            file_path: Path to the .def file.
            
        Returns:
            Dictionary with parsed contents, or None if parsing failed.
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            result = {
                'path': file_path,
                'description': '',
                'author': '',
                'mod_file': '',
                'changes': []
            }
            
            # Get description
            desc_elem = root.find('description')
            if desc_elem is not None and desc_elem.text:
                result['description'] = desc_elem.text.strip()
            
            # Get author
            author_elem = root.find('author')
            if author_elem is not None and author_elem.text:
                result['author'] = author_elem.text.strip()
            
            # Get mod element
            mod_elem = root.find('mod')
            if mod_elem is not None:
                result['mod_file'] = mod_elem.get('file', '')
                
                # Get all changes
                for change in mod_elem.findall('change'):
                    result['changes'].append({
                        'item': change.get('item', ''),
                        'property': change.get('property', ''),
                        'value': change.get('value', ''),
                    })
            
            return result
            
        except ET.ParseError as e:
            logger.error("XML parse error in %s: %s", file_path, e)
            return None
        except OSError as e:
            logger.error("Error parsing %s: %s", file_path, e)
            return None

    @staticmethod
    def get_description(file_path: Path) -> str:
        """Extract the description from a .def file.
        
        Args:
            file_path: Path to the .def file.
            
        Returns:
            The description value, or empty string if not found.
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            desc_elem = root.find('description')
            if desc_elem is not None and desc_elem.text:
                return desc_elem.text.strip()
        except (OSError, ET.ParseError):
            pass
        return ""

    @staticmethod
    def get_author(file_path: Path) -> str:
        """Extract the author from a .def file.
        
        Args:
            file_path: Path to the .def file.
            
        Returns:
            The author value, or empty string if not found.
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            author_elem = root.find('author')
            if author_elem is not None and author_elem.text:
                return author_elem.text.strip()
        except (OSError, ET.ParseError):
            pass
        return ""
