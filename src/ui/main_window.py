"""
Main application window for Moria MOD Creator.

This module provides the primary user interface for the Moria MOD Creator
application, including:
- Definition file browsing and selection in the left pane
- JSON data table editing in the right pane with virtual scrolling
- Toolbar with MOD building, import, and conversion tools
- Buildings/Constructions view for construction definitions
- Status bar for user feedback

The window uses a split-pane layout with the definitions list on the left
and the data editor on the right. Users can select definition files to
view and edit their JSON data tables.
"""

import configparser
import json
import logging
import re
import tkinter as tk
from tkinter import ttk
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PIL import Image
import customtkinter as ctk

from src.config import get_definitions_dir, get_output_dir, get_default_mymodfiles_dir
from src.constants import (
    TOOLBAR_ICON_SIZE,
    TITLE_ICON_SIZE,
    COLOR_CHECKBOX_DEFAULT,
    COLOR_CHECKBOX_MIXED,
    COLOR_STATUS_TEXT,
    COLOR_SAVE_BUTTON,
    COLOR_SAVE_BUTTON_HOVER,
)
from src.build_manager import BuildManager
from src.ui.about_dialog import show_about_dialog
from src.ui.buildings_view import BuildingsView
from src.ui.import_dialog import show_import_dialog
from src.ui.mod_name_dialog import show_mod_name_dialog
from src.ui.secrets_import_dialog import show_secrets_import_dialog

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_assets_dir() -> Path:
    """Get the assets directory path."""
    return Path(__file__).parent.parent.parent / "assets"


def get_icon_path(name: str) -> Path:
    """Get the path to an icon file."""
    return get_assets_dir() / "icons" / name


# =============================================================================
# MAIN WINDOW CLASS
# =============================================================================


class MainWindow(ctk.CTk):
    """
    Main application window for Moria MOD Creator.

    This window provides a comprehensive interface for creating and editing
    MOD definitions for the game Moria. Features include:

    - Left pane: File browser for .def definition files with checkboxes
    - Right pane: Data table editor with virtual scrolling for performance
    - Toolbar: MOD building, import, JSON conversion, and settings tools
    - Buildings view: Dedicated interface for construction/building editing
    - Status bar: Real-time feedback on operations

    The window maintains state for:
    - Definition file checkbox selections (persisted to INI file)
    - Currently selected definition file for editing
    - Row-level checkbox and value states for the data table
    - View mode switching between definitions and buildings views

    Attributes:
        definition_checkboxes: Maps file paths to their checkbox widgets
        definition_vars: Maps file paths to their BooleanVar states
        current_view: Either "definitions" or "buildings"
        current_definition_path: Path to currently loaded definition file
    """

    def __init__(self):
        """
        Initialize the main window.

        Sets up the window geometry, icon, and all widget state tracking
        dictionaries. Creates the UI layout and loads persisted checkbox states.
        """
        super().__init__()

        self.title("Moria MOD Creator")
        self.geometry("1024x768")
        self.minsize(800, 600)

        # Set application icon
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.iconbitmap(str(icon_path))

        # Start maximized/fullscreen
        self.after(10, lambda: self.state('zoomed'))

        # --- Definition Pane State ---
        # Track definition checkboxes and their states
        self.definition_checkboxes: dict[Path, ctk.CTkCheckBox] = {}
        self.definition_vars: dict[Path, ctk.BooleanVar] = {}
        self.definition_row_frames: dict[Path, ctk.CTkFrame] = {}

        # Track left pane header checkbox state (none/mixed/all)
        self.left_select_all_state = "none"
        self.left_select_all_btn = None

        # Persisted checkbox states loaded from INI file
        self._checkbox_states = {}
        self._load_checkbox_states()

        # --- Data Table State ---
        # Track row checkboxes and entries for the right pane editor
        self.row_checkboxes: list[ctk.CTkCheckBox] = []
        self.row_checkbox_vars: list[ctk.BooleanVar] = []
        self.row_entries: list[ctk.CTkEntry] = []
        self.row_entry_vars: list[ctk.StringVar] = []
        self.row_values: list[str] = []  # Original values for resetting
        self.row_frames: list[ctk.CTkFrame] = []  # Row frames for highlighting

        # --- Widget References ---
        # Initialize widget attributes (created in helper methods)
        self.content_frame = None
        self.main_content = None
        self.status_bar = None
        self.save_btn = None
        self.status_message = None
        self.current_definitions_dir = None
        self.definitions_list = None
        self.mod_name_var = None
        self.mod_name_entry = None
        self.current_definition_path = None
        self.select_all_state = "none"
        self.select_all_btn = None
        self.select_all_var = None  # BooleanVar for right pane select all
        self.row_names = []
        self.row_properties = []
        self.progress_frame = None
        self.progress_label = None
        self.progress_bar = None
        self._current_mod_name = None
        self.left_select_all_var = None  # BooleanVar for left pane select all
        self.buildings_view = None
        self.definitions_view_frame = None
        self.buildings_btn = None

        # Virtual scroll attributes
        self.virtual_display_data = []
        self.row_checked = []
        self.row_new_values = []
        self.row_height = 32
        self.visible_row_count = 20
        self.buffer_rows = 5
        self.scroll_position = 0
        self.row_name_labels = []
        self.row_property_labels = []
        self.row_value_labels = []
        self.widget_to_data_idx = {}
        self.virtual_canvas = None
        self.virtual_scrollbar = None
        self.rows_frame = None
        self.canvas_window = None
        self.tree = None
        self.tree_items = []
        self.tree_edit_entry = None
        self.search_var = None
        self.search_entry = None
        self.search_last_index = -1
        self.search_last_text = ""

        # View switching
        self.current_view = "definitions"  # "definitions" or "buildings"
        self.definitions_view_frame = None
        self.buildings_view = None
        self.buildings_btn = None
        self.main_area = None

        # Navigation buttons (initialized in _create_header)
        self.mod_builder_btn = None
        self.import_btn = None
        self.convert_btn = None

        self._create_widgets()

    # =========================================================================
    # WIDGET CREATION METHODS
    # =========================================================================
    # These methods create the main UI layout including header, content areas,
    # and status bar. The layout follows a split-pane design with definitions
    # on the left and the data editor on the right.
    # =========================================================================

    def _create_widgets(self):
        """
        Create the main window widgets.

        Sets up the overall layout with header, main content area, and status bar.
        """
        # Main content frame (container for everything)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True)

        # Header row with title, utility icons, and settings/help buttons
        self._create_header()

        # Main content area with definitions pane (1/3) and editor pane (2/3)
        self._create_main_area()

        # Status bar at the bottom for user feedback
        self._create_status_bar()

    def _create_header(self):
        """
        Create the header with app title, toolbar, and utility buttons.

        Layout:
        - Left: App icon and title
        - Center: Toolbar buttons (MOD Builder, Import, Convert, Buildings)
        - Right: Settings and Help icons
        """
        header_frame = ctk.CTkFrame(
            self.content_frame,
            fg_color="transparent",
            height=60
        )
        header_frame.pack(fill="x", padx=10, pady=(10, 0))
        header_frame.pack_propagate(False)

        # Configure grid columns for even spacing
        header_frame.grid_columnconfigure(0, weight=1)
        header_frame.grid_columnconfigure(1, weight=1)
        header_frame.grid_columnconfigure(2, weight=1)

        # LEFT: App icon and title
        left_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="w")

        icon_path = get_icon_path("app_icon.png")
        if icon_path.exists():
            try:
                img = Image.open(icon_path)
                icon_image = ctk.CTkImage(
                    light_image=img,
                    dark_image=img,
                    size=TITLE_ICON_SIZE
                )
                icon_label = ctk.CTkLabel(left_frame, image=icon_image, text="")
                icon_label.pack(side="left", padx=(0, 10))
            except (OSError, ValueError):
                pass

        title_label = ctk.CTkLabel(
            left_frame,
            text="Moria MOD Creator",
            font=ctk.CTkFont(size=28, weight="bold")
        )
        title_label.pack(side="left")

        # CENTER: Navigation buttons (Mod Builder, Constructions) and action buttons (Import, Convert)
        center_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        center_frame.grid(row=0, column=1)

        # Mod Builder button (default view)
        self.mod_builder_btn = ctk.CTkButton(
            center_frame,
            text="Mod Builder",
            width=120,
            height=40,
            fg_color=("#3B8ED0", "#1F6AA5"),  # Active by default
            hover_color=("#36719F", "#144870"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._show_definitions_view
        )
        self.mod_builder_btn.pack(side="left", padx=5)

        # Constructions button
        self.buildings_btn = ctk.CTkButton(
            center_frame,
            text="Constructions",
            width=120,
            height=40,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._show_buildings_view
        )
        self.buildings_btn.pack(side="left", padx=5)

        # Separator
        sep_label = ctk.CTkLabel(center_frame, text="|", text_color="gray50", font=ctk.CTkFont(size=20))
        sep_label.pack(side="left", padx=10)

        # Import Game Files button
        self.import_btn = ctk.CTkButton(
            center_frame,
            text="Import Game Files",
            width=140,
            height=40,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._run_import
        )
        self.import_btn.pack(side="left", padx=5)

        # Import Secrets button
        self.secrets_btn = ctk.CTkButton(
            center_frame,
            text="Import Secrets",
            width=150,
            height=40,
            fg_color=("#F57C00", "#E65100"),
            hover_color=("#E65100", "#BF360C"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._run_secrets_import
        )
        self.secrets_btn.pack(side="left", padx=5)

        # RIGHT: Settings and Help buttons
        right_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        right_frame.grid(row=0, column=2, sticky="e")

        self._create_toolbar_button(
            right_frame,
            "gear_icon.png",
            "Settings",
            self._open_settings
        )

        self._create_toolbar_button(
            right_frame,
            "help_icon.png",
            "Help",
            self._open_about
        )

    def _create_main_area(self):
        """Create the main content area with definitions pane."""
        # Container for the main area
        self.main_area = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        self.main_area.pack(fill="both", expand=True, padx=10, pady=10)

        # Configure grid: definitions pane (smaller) and main content (larger)
        self.main_area.grid_columnconfigure(0, weight=1)
        self.main_area.grid_columnconfigure(1, weight=3)
        self.main_area.grid_rowconfigure(0, weight=1)

        # === DEFINITIONS VIEW (default) ===
        self.definitions_view_frame = ctk.CTkFrame(self.main_area, fg_color="transparent")
        self.definitions_view_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.definitions_view_frame.grid_columnconfigure(0, weight=1)
        self.definitions_view_frame.grid_columnconfigure(1, weight=3)
        self.definitions_view_frame.grid_rowconfigure(0, weight=1)

        # Definitions pane (left)
        self._create_definitions_pane(self.definitions_view_frame)

        # Main content area (right)
        self.main_content = ctk.CTkFrame(self.definitions_view_frame, fg_color="transparent")
        self.main_content.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        # === BUILDINGS VIEW (hidden initially) ===
        self.buildings_view = BuildingsView(
            self.main_area,
            on_status_message=self.set_status_message,
            on_back=self._show_definitions_view
        )
        # Don't grid it yet - will be shown when Buildings button is clicked

    def _create_status_bar(self):
        """Create the status bar at the bottom of the window."""
        self.status_bar = ctk.CTkFrame(self.content_frame, height=50)
        self.status_bar.pack(fill="x", padx=10, pady=(0, 10))
        self.status_bar.pack_propagate(False)

        # Status message only - Save button moved to right pane
        self.status_message = ctk.CTkLabel(
            self.status_bar,
            text="",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.status_message.pack(fill="x", padx=10, pady=(5, 5))

        # Initialize save_btn to None (will be created in right pane)
        self.save_btn = None

    def set_status_message(self, message: str, is_error: bool = False):
        """Set the status bar message.

        Args:
            message: The message to display.
            is_error: If True, display in red color.
        """
        if self.status_message:
            self.status_message.configure(
                text=message,
                text_color="red" if is_error else COLOR_STATUS_TEXT
            )

    def clear_status_message(self):
        """Clear the status bar message."""
        if self.status_message:
            self.status_message.configure(text="")

    def _create_definitions_pane(self, parent):
        """Create the definitions file list pane."""
        # Track current directory for navigation
        self.current_definitions_dir = None

        # Definitions frame with border
        definitions_frame = ctk.CTkFrame(parent)
        definitions_frame.grid(row=0, column=0, sticky="nsew")

        # Header row with tri-state checkbox and "Mod Definition" title
        header_row = ctk.CTkFrame(definitions_frame, fg_color="transparent")
        header_row.pack(fill="x", pady=(10, 5), padx=10)

        # Tri-state checkbox for select all (uses color to indicate mixed state)
        self.left_select_all_var = ctk.BooleanVar(value=False)
        self.left_select_all_btn = ctk.CTkCheckBox(
            header_row,
            text="",
            variable=self.left_select_all_var,
            width=20,
            command=self._on_left_select_all_toggle
        )
        self.left_select_all_btn.pack(side="left")

        # Title
        title_label = ctk.CTkLabel(
            header_row,
            text="Mod Definition",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        title_label.pack(side="left", padx=(5, 0))

        # Refresh button
        refresh_btn = ctk.CTkButton(
            header_row,
            text="↻",
            width=28,
            height=28,
            font=ctk.CTkFont(size=16),
            fg_color="transparent",
            hover_color=("gray75", "gray25"),
            command=self._refresh_definitions_list
        )
        refresh_btn.pack(side="right")

        # Scrollable frame for file list
        self.definitions_list = ctk.CTkScrollableFrame(
            definitions_frame,
            fg_color="transparent"
        )
        self.definitions_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Bottom section with mod name and build button
        bottom_frame = ctk.CTkFrame(definitions_frame, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=10, pady=(0, 10))

        # Left side: "My Mod Name" button and text field
        left_bottom = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        left_bottom.pack(side="left", fill="x", expand=True)

        mod_name_btn = ctk.CTkButton(
            left_bottom,
            text="My Mod Name",
            fg_color="#2196F3",  # Blue
            hover_color="#1976D2",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=120,
            command=self._on_mod_name_click
        )
        mod_name_btn.pack(side="left")

        # Text field for mod name (read-only display)
        self.mod_name_var = ctk.StringVar(value="")
        self.mod_name_entry = ctk.CTkEntry(
            left_bottom,
            textvariable=self.mod_name_var,
            width=120,
            placeholder_text="No mod selected...",
            state="disabled"
        )
        self.mod_name_entry.pack(side="left", padx=(10, 0), fill="x", expand=True)

        # Right side: "Build" button
        build_btn = ctk.CTkButton(
            bottom_frame,
            text="Build",
            fg_color="#4CAF50",  # Green
            hover_color="#388E3C",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=80,
            command=self._on_build_click
        )
        build_btn.pack(side="right")

        # Load definitions files
        self._refresh_definitions_list()

    def _refresh_definitions_list(self, target_dir: Optional[Path] = None):
        """Refresh the list of definition files and directories.

        Args:
            target_dir: Directory to display. If None, uses root definitions dir.
        """
        # Clear existing items
        if self.definitions_list:
            for widget in self.definitions_list.winfo_children():
                widget.destroy()

        # Clear tracking dictionaries
        self.definition_checkboxes.clear()
        self.definition_vars.clear()

        # Get definitions directory
        root_dir = get_definitions_dir()

        if target_dir is None:
            target_dir = root_dir

        # Store current directory
        self.current_definitions_dir = target_dir

        if not target_dir.exists():
            no_files_label = ctk.CTkLabel(
                self.definitions_list,
                text="No definitions directory found",
                text_color="gray"
            )
            no_files_label.pack(pady=10)
            return

        # Add ".." back navigation if not at root
        if target_dir != root_dir:
            back_frame = ctk.CTkFrame(self.definitions_list, fg_color="transparent")
            back_frame.pack(fill="x", pady=2, anchor="w")

            back_label = ctk.CTkLabel(
                back_frame,
                text="📁 ..",
                anchor="w",
                cursor="hand2",
                font=ctk.CTkFont(size=18),
                text_color="#FFD700"
            )
            back_label.pack(side="left", fill="x", expand=True, padx=(25, 0))
            back_label.bind("<Button-1>", lambda e: self._refresh_definitions_list(target_dir.parent))

        # List directories first, then .def files
        dirs = sorted([d for d in target_dir.iterdir() if d.is_dir()])
        def_files = sorted([f for f in target_dir.iterdir()
                           if f.is_file() and f.suffix.lower() == '.def'])

        if not dirs and not def_files:
            no_files_label = ctk.CTkLabel(
                self.definitions_list,
                text="No items found",
                text_color="gray"
            )
            no_files_label.pack(pady=10)
            return

        # Create entries for directories with tri-state checkboxes
        for dir_path in dirs:
            row_frame = ctk.CTkFrame(self.definitions_list, fg_color="transparent")
            row_frame.pack(fill="x", pady=2, anchor="w")

            # Create BooleanVar for checkbox state
            var = ctk.BooleanVar(value=False)  # Will be updated by _update_directory_checkbox_display
            self.definition_vars[dir_path] = var
            self.definition_row_frames[dir_path] = row_frame

            # Create checkbox for directory (will use color to indicate mixed state)
            checkbox = ctk.CTkCheckBox(
                row_frame,
                text="",
                variable=var,
                onvalue=True,
                offvalue=False,
                width=20,
                command=lambda p=dir_path: self._on_directory_checkbox_toggle(p)
            )
            checkbox.pack(side="left")
            self.definition_checkboxes[dir_path] = checkbox

            # Update the checkbox display based on children's state
            self._update_directory_checkbox_display(dir_path)

            # Apply initial highlight based on state
            self._update_definition_row_highlight(dir_path)

            # Folder icon and name (clickable for navigation)
            dir_label = ctk.CTkLabel(
                row_frame,
                text=f"📁 {dir_path.name}",
                anchor="w",
                cursor="hand2",
                font=ctk.CTkFont(size=18),
                text_color="#FFD700"
            )
            dir_label.pack(side="left", fill="x", expand=True)
            dir_label.bind("<Button-1>", lambda e, p=dir_path: self._refresh_definitions_list(p))

        # Create a checkbox for each .def file
        for file_path in def_files:
            title = self._get_definition_title(file_path)

            # Create a row frame for checkbox and clickable label
            row_frame = ctk.CTkFrame(self.definitions_list, fg_color="transparent")
            row_frame.pack(fill="x", pady=2, anchor="w")

            # Check if file should be checked (from saved state)
            saved_state = self._get_saved_checkbox_state(file_path)

            # Create BooleanVar for checkbox state
            var = ctk.BooleanVar(value=saved_state)
            self.definition_vars[file_path] = var
            self.definition_row_frames[file_path] = row_frame

            # Create checkbox (no text)
            checkbox = ctk.CTkCheckBox(
                row_frame,
                text="",
                variable=var,
                onvalue=True,
                offvalue=False,
                width=20,
                command=lambda p=file_path: self._on_definition_checkbox_toggle(p)
            )
            checkbox.pack(side="left")
            self.definition_checkboxes[file_path] = checkbox

            # Apply initial highlight if checked
            self._update_definition_row_highlight(file_path)

            # Create clickable label for the title
            title_label = ctk.CTkLabel(
                row_frame,
                text=title,
                anchor="w",
                cursor="hand2"
            )
            title_label.pack(side="left", fill="x", expand=True)
            # Bind click to show details pane
            title_label.bind("<Button-1>", lambda e, p=file_path: self._show_definition_details(p))

        # Update header checkbox state
        self._update_left_select_all_state()

    # =========================================================================
    # CHECKBOX STATE PERSISTENCE
    # =========================================================================
    # These methods handle saving and loading checkbox states to/from an INI
    # file, allowing users to maintain their selection across sessions. States
    # are stored per-mod in the mod's directory.
    # =========================================================================

    def _get_checkbox_ini_path(self) -> Path:
        """
        Get the path to the checkbox states INI file.

        If a mod name is set, uses the mod's directory.
        Otherwise uses the default mymodfiles directory.

        Returns:
            Path to the checkbox_states.ini file
        """
        mymodfiles_dir = get_default_mymodfiles_dir()

        # If we have a current mod name, use its directory
        if hasattr(self, '_current_mod_name') and self._current_mod_name:
            mod_dir = mymodfiles_dir / self._current_mod_name
            mod_dir.mkdir(parents=True, exist_ok=True)
            return mod_dir / "checkbox_states.ini"

        # Fallback to default location
        mymodfiles_dir.mkdir(parents=True, exist_ok=True)
        return mymodfiles_dir / "checkbox_states.ini"

    def _load_checkbox_states(self):
        """
        Load checkbox states from the INI file.

        Clears existing checkbox states and loads saved states for the
        current mod from the checkbox_states.ini file.
        """
        # Clear existing checkbox states
        self._checkbox_states = {}

        # Clear all checkboxes in the current view
        for var in self.definition_vars.values():
            var.set(False)

        # Only load if a mod is selected
        if not hasattr(self, '_current_mod_name') or not self._current_mod_name:
            return

        ini_path = self._get_checkbox_ini_path()
        if ini_path.exists():
            config = configparser.ConfigParser()
            # config.optionxform = str  # Preserve case (removed, not supported)
            try:
                config.read(ini_path, encoding='utf-8')
                if 'Paths' in config:
                    for key, value in config['Paths'].items():
                        if value.lower() == 'true':
                            # Reconstruct path from key (replace | with \ and ~ with :)
                            path_str = key.replace('|', '\\').replace('~', ':')
                            self._checkbox_states[path_str] = True
            except (OSError, configparser.Error) as e:
                logger.error("Error loading checkbox states: %s", e)

    def _save_checkbox_states(self):
        """Save checkbox states to the INI file."""
        # Don't save if no mod is selected
        if not hasattr(self, '_current_mod_name') or not self._current_mod_name:
            return

        ini_path = self._get_checkbox_ini_path()
        config = configparser.ConfigParser()
        # config.optionxform = str  # Preserve case (removed, not supported)
        config['Paths'] = {}

        # First, update _checkbox_states with current UI state
        for path, var in self.definition_vars.items():
            self._checkbox_states[str(path)] = var.get()

        # Save all checkbox states
        for path_str, is_checked in self._checkbox_states.items():
            if is_checked:
                # Convert path to key (replace \ with | and : with ~ to avoid configparser issues)
                path_key = path_str.replace('\\', '|').replace('/', '|').replace(':', '~')
                config['Paths'][path_key] = 'true'

        try:
            with open(ini_path, 'w', encoding='utf-8') as f:
                config.write(f)
        except OSError as e:
            logger.error("Error saving checkbox states: %s", e)

    def _get_saved_checkbox_state(self, path: Path) -> bool:
        """Get the saved checkbox state for a path.

        Args:
            path: Path to check.

        Returns:
            True if the item was checked, False otherwise.
        """
        if not hasattr(self, '_checkbox_states'):
            return False

        # Check for exact match first
        path_str = str(path)
        if path_str in self._checkbox_states:
            return self._checkbox_states[path_str]

        # Case-insensitive fallback for Windows paths
        path_lower = path_str.lower()
        for saved_path, is_checked in self._checkbox_states.items():
            if saved_path.lower() == path_lower:
                return is_checked

        return False

    def _on_left_select_all_toggle(self):
        """Handle left pane header checkbox toggle."""
        if self.left_select_all_state == "all":
            # Uncheck all
            for var in self.definition_vars.values():
                var.set(False)
        else:
            # Check all
            for var in self.definition_vars.values():
                var.set(True)

        # Update button state
        self._update_left_select_all_state()

        # Save states
        self._save_checkbox_states()

    def _update_left_select_all_state(self):
        """Update the left pane header checkbox to reflect the state of row checkboxes."""
        if not self.definition_vars or self.left_select_all_btn is None:
            return

        checked_count = sum(1 for var in self.definition_vars.values() if var.get())
        total_count = len(self.definition_vars)

        # Checkbox colors from constants
        default_color = (COLOR_CHECKBOX_DEFAULT, COLOR_CHECKBOX_DEFAULT)
        mixed_color = (COLOR_CHECKBOX_MIXED, COLOR_CHECKBOX_MIXED)

        if checked_count == 0:
            # None checked
            self.left_select_all_state = "none"
            self.left_select_all_btn.deselect()
            self.left_select_all_btn.configure(fg_color=default_color)
        elif checked_count == total_count:
            # All checked
            self.left_select_all_state = "all"
            self.left_select_all_btn.select()
            self.left_select_all_btn.configure(fg_color=default_color)
        else:
            # Mixed state - checked with orange color
            self.left_select_all_state = "mixed"
            self.left_select_all_btn.select()
            self.left_select_all_btn.configure(fg_color=mixed_color)

    def _get_directory_child_state(self, dir_path: Path) -> str:
        """Calculate the tri-state checkbox state for a directory based on its children.

        Args:
            dir_path: Path to the directory.

        Returns:
            "none" if no children are checked,
            "all" if all children are checked,
            "mixed" if some children are checked.
        """
        if not dir_path.exists() or not dir_path.is_dir():
            return "none"

        checked_count = 0
        total_count = 0

        for item in dir_path.iterdir():
            # Only count .def files and directories
            if item.is_file() and item.suffix == '.def':
                total_count += 1
                if self._get_saved_checkbox_state(item):
                    checked_count += 1
            elif item.is_dir():
                total_count += 1
                # For subdirectories, check if they're in a checked state
                sub_state = self._get_directory_child_state(item)
                if sub_state == "all":
                    checked_count += 1
                elif sub_state == "mixed":
                    # If any subdirectory is mixed, the parent is also mixed
                    return "mixed"

        if total_count == 0:
            return "none"
        elif checked_count == 0:
            return "none"
        elif checked_count == total_count:
            return "all"
        else:
            return "mixed"

    def _update_directory_checkbox_display(self, dir_path: Path):
        """Update a directory checkbox button to show tri-state based on children.

        Args:
            dir_path: Path to the directory.
        """
        if dir_path not in self.definition_checkboxes:
            return

        checkbox = self.definition_checkboxes[dir_path]
        state = self._get_directory_child_state(dir_path)

        # Checkbox colors from constants
        default_color = (COLOR_CHECKBOX_DEFAULT, COLOR_CHECKBOX_DEFAULT)
        mixed_color = (COLOR_CHECKBOX_MIXED, COLOR_CHECKBOX_MIXED)

        if state == "none":
            checkbox.deselect()
            checkbox.configure(fg_color=default_color)
            if dir_path in self.definition_vars:
                self.definition_vars[dir_path].set(False)
        elif state == "all":
            checkbox.select()
            checkbox.configure(fg_color=default_color)
            if dir_path in self.definition_vars:
                self.definition_vars[dir_path].set(True)
        else:  # mixed
            checkbox.select()  # Show as checked but with different color
            checkbox.configure(fg_color=mixed_color)
            if dir_path in self.definition_vars:
                self.definition_vars[dir_path].set(True)  # Treat mixed as "some checked"

    def _on_directory_checkbox_toggle(self, dir_path: Path):
        """Handle directory checkbox toggle - cycles between check all and uncheck all.

        Args:
            dir_path: Path to the directory that was toggled.
        """
        # Get current state of directory's children
        current_state = self._get_directory_child_state(dir_path)

        # If all checked, uncheck all. Otherwise, check all.
        new_checked = current_state != "all"

        # Update all items under this directory recursively
        self._set_directory_items_checked(dir_path, new_checked)

        # Update directory checkbox display
        self._update_directory_checkbox_display(dir_path)

        # Update row highlight
        self._update_definition_row_highlight(dir_path)

        # Update header state
        self._update_left_select_all_state()

        # Save states
        self._save_checkbox_states()

    def _set_directory_items_checked(self, dir_path: Path, checked: bool):
        """Recursively set all items under a directory to checked/unchecked.

        Args:
            dir_path: Directory path.
            checked: Whether to check or uncheck items.
        """
        if not dir_path.exists():
            return

        for item in dir_path.iterdir():
            # Update the saved state
            self._checkbox_states[str(item)] = checked

            # If item is in current view, update its checkbox and highlight
            if item in self.definition_vars:
                self.definition_vars[item].set(checked)
                self._update_definition_row_highlight(item)

            # Recurse into subdirectories
            if item.is_dir():
                self._set_directory_items_checked(item, checked)

    def _on_definition_checkbox_toggle(self, file_path: Path):
        """Handle definition file checkbox toggle.

        Args:
            file_path: Path to the file that was toggled.
        """
        # Update saved state
        self._checkbox_states[str(file_path)] = self.definition_vars[file_path].get()

        # Update row highlight
        self._update_definition_row_highlight(file_path)

        # Update parent directory's tri-state checkbox if visible
        parent_dir = file_path.parent
        if parent_dir in self.definition_checkboxes:
            self._update_directory_checkbox_display(parent_dir)
            self._update_definition_row_highlight(parent_dir)

        # Update header state
        self._update_left_select_all_state()

        # Save states
        self._save_checkbox_states()

    def _update_definition_row_highlight(self, path: Path):
        """Update the background highlight for a definition row based on checkbox state.

        Args:
            path: Path to the definition file or directory.
        """
        if path not in self.definition_row_frames or path not in self.definition_vars:
            return

        row_frame = self.definition_row_frames[path]
        is_checked = self.definition_vars[path].get()

        if is_checked:
            # Highlight with a subtle color
            row_frame.configure(fg_color=("gray85", "gray25"))
        else:
            # Reset to transparent
            row_frame.configure(fg_color="transparent")

    def _get_definition_title(self, file_path: Path) -> str:
        """Extract the title from a .def file.

        Args:
            file_path: Path to the .def file.

        Returns:
            The title value, or filename if not found.
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            title_elem = root.find('title')
            if title_elem is not None and title_elem.text:
                return title_elem.text.strip()
        except (ET.ParseError, OSError):
            pass
        # Fallback to filename without extension
        return file_path.stem

    def get_selected_definitions(self) -> list[Path]:
        """Get list of checked definition file paths.

        Returns:
            List of paths to checked definition files.
        """
        return [path for path, var in self.definition_vars.items() if var.get()]

    def _get_all_selected_definitions_from_ini(self) -> list[Path]:
        """Get all selected definition files from the checkbox_states.ini file.

        This reads from the saved INI file rather than the current UI state,
        so it includes selections from all subdirectories, not just the
        currently visible ones.

        Returns:
            List of paths to all checked .def files.
        """
        selected = []

        # Make sure checkbox states are loaded
        if not hasattr(self, '_checkbox_states') or not self._checkbox_states:
            return selected

        for path_str, is_checked in self._checkbox_states.items():
            if is_checked:
                path = Path(path_str)
                # Only include .def files (not directories)
                if path.suffix.lower() == '.def' and path.exists():
                    selected.append(path)

        return selected

    def _get_definition_description(self, file_path: Path) -> str:
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
        except (ET.ParseError, OSError):
            pass
        return ""

    def _get_definition_author(self, file_path: Path) -> str:
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
        except (ET.ParseError, OSError):
            pass
        return ""

    def _get_definition_changes(self, file_path: Path) -> list[dict]:
        """Extract the change and delete elements from a .def file.

        Args:
            file_path: Path to the .def file.

        Returns:
            List of dictionaries with item, property, value keys.
        """
        changes = []
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            # Find all <change> elements at root level and inside <mod> elements
            for change_elem in root.iter('change'):
                item = change_elem.get('item', '')
                prop = change_elem.get('property', '')
                value = change_elem.get('value', '')
                if item and prop:  # Only add if we have at least item and property
                    changes.append({
                        'item': item,
                        'property': prop,
                        'value': value
                    })
            # Also find all <delete> elements (for GameplayTagContainer properties)
            for delete_elem in root.iter('delete'):
                item = delete_elem.get('item', '')
                prop = delete_elem.get('property', '')
                # For delete, the 'value' is the tag being deleted (original value)
                value = delete_elem.get('value', '')
                if item and prop:
                    changes.append({
                        'item': item,
                        'property': prop,
                        'value': value,
                        'is_delete': True
                    })
        except (ET.ParseError, OSError):
            pass
        # Sort by item name
        return sorted(changes, key=lambda x: x['item'].lower())

    # =========================================================================
    # GAME DATA LOADING AND PARSING
    # =========================================================================
    # These methods handle loading game data JSON files, parsing property
    # values, and resolving string table references. They support both
    # multi-row data tables (like DT_Items) and single-asset files.
    # =========================================================================

    def _get_mod_file_path(self, file_path: Path) -> str | None:
        """
        Extract the mod file path from a .def file's <mod> element.

        Args:
            file_path: Path to the .def file.

        Returns:
            The file attribute value (e.g., "Moria/Content/Data/DT_Items.uasset"),
            or None if not found.
        """
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            mod_elem = root.find('mod')
            if mod_elem is not None:
                return mod_elem.get('file', None)
        except (ET.ParseError, OSError):
            pass
        return None

    def _load_game_data(self, mod_file_path: str) -> dict | None:
        """
        Load game data JSON file from the jsondata directory.

        Args:
            mod_file_path: Relative path from the mod element (e.g., \\Moria\\Content\\...)

        Returns:
            Parsed JSON data or None if file not found.
        """
        try:
            # Normalize the path - remove leading backslash and convert to forward slashes
            normalized_path = mod_file_path.lstrip('\\').lstrip('/').replace('\\', '/')

            # Build full path: %APPDATA%/MoriaMODCreator/output/jsondata/ + normalized_path
            jsondata_dir = get_output_dir() / 'jsondata'
            full_path = jsondata_dir / normalized_path

            if full_path.exists():
                with open(full_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _load_string_table(self, table_path: str) -> dict:
        """Load a string table and return a lookup dictionary.

        Args:
            table_path: The TableId path (e.g., /Game/Tech/Data/StringTables/Items.Items)

        Returns:
            Dictionary mapping string keys to their values.
        """
        try:
            # Convert TableId to file path
            # /Game/Tech/Data/StringTables/Items.Items -> Moria/Content/Tech/Data/StringTables/Items.json
            # The .Items suffix is the table namespace, not part of the file name
            path_parts = table_path.lstrip('/').split('.')
            base_path = path_parts[0]  # e.g., "Game/Tech/Data/StringTables/Items"

            # Replace "Game" with "Moria/Content"
            if base_path.startswith('Game/'):
                base_path = 'Moria/Content/' + base_path[5:]

            # Add .json extension
            json_path = base_path + '.json'

            jsondata_dir = get_output_dir() / 'jsondata'
            full_path = jsondata_dir / json_path

            if not full_path.exists():
                return {}

            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Parse the string table: Exports[0].Table.Value is array of [key, value] pairs
            lookup = {}
            try:
                entries = data['Exports'][0]['Table']['Value']
                for entry in entries:
                    if isinstance(entry, list) and len(entry) >= 2:
                        lookup[entry[0]] = entry[1]
            except (KeyError, IndexError):
                pass

            return lookup
        except (OSError, json.JSONDecodeError, KeyError):
            return {}

    def _expand_wildcard_property(self, item_data: dict, property_pattern: str) -> list[tuple[str, str]]:
        """Expand a property pattern with [*] wildcard to all matching indices.

        Args:
            item_data: The item's data from the JSON.
            property_pattern: Property path that may contain [*] wildcard.

        Returns:
            List of (expanded_property, value) tuples. If no wildcard, returns single item.
        """
        if '[*]' not in property_pattern:
            # No wildcard - return single property
            value = self._get_item_property_value(item_data, property_pattern)
            if value:
                return [(property_pattern, value)]
            return []

        # Find the array name and rest of path
        # e.g., "StageDataList[*].MonumentProgressonPointsNeeded"
        # -> array_name="StageDataList", rest=".MonumentProgressonPointsNeeded"
        match = re.match(r'^(.*?)\[\*\](.*)$', property_pattern)
        if not match:
            return []

        array_name = match.group(1)
        rest_of_path = match.group(2)
        if rest_of_path.startswith('.'):
            rest_of_path = rest_of_path[1:]  # Remove leading dot

        # Get the array from item data
        value_array = item_data.get('Value', [])
        if not value_array:
            return []

        # Find the array property
        array_data = None
        for prop in value_array:
            if prop.get('Name') == array_name and 'Value' in prop:
                array_data = prop['Value']
                break

        if not array_data or not isinstance(array_data, list):
            return []

        # Expand to all indices
        results = []
        for i, _ in enumerate(array_data):
            expanded_prop = f"{array_name}[{i}]"
            if rest_of_path:
                expanded_prop += f".{rest_of_path}"

            # Get the value for this specific index
            value = self._get_item_property_value(item_data, expanded_prop)
            if value:
                results.append((expanded_prop, value))

        return results

    def _get_nested_property_value(self, data: list | dict, property_path: str) -> str:
        """Get a property value using dot notation for nested traversal.

        Supports array indexing with bracket notation, e.g.:
        - "StageDataList[1].MonumentProgressonPointsNeeded"
        - "StageBuildItems[0].Count"

        Args:
            data: The data to search (list of properties or dict).
            property_path: Dot-separated property path with optional array indices.

        Returns:
            The property value as a string, or empty string if not found.
        """
        if not data or not property_path:
            return ''

        # Parse property path into parts, handling array indices
        # e.g., "StageDataList[1].MonumentProgressonPointsNeeded" ->
        # [("StageDataList", 1), ("MonumentProgressonPointsNeeded", None)]
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

        for name, index in parts:
            if isinstance(current, list):
                # Search for property by Name in list
                found = False
                for item in current:
                    if isinstance(item, dict) and item.get('Name') == name:
                        # Check if this has a Value that is a list (nested struct)
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
                                    return ''  # Index out of bounds
                            found = True
                            break
                if not found:
                    return ''
            elif isinstance(current, dict):
                if name in current:
                    current = current[name]
                    # Handle array indexing
                    if index is not None and isinstance(current, list):
                        if 0 <= index < len(current):
                            indexed_item = current[index]
                            if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                                current = indexed_item['Value']
                            else:
                                current = indexed_item
                        else:
                            return ''
                elif 'Value' in current:
                    # Try to traverse into Value
                    current = current['Value']
                    # Then look for the part
                    if isinstance(current, list):
                        found = False
                        for item in current:
                            if isinstance(item, dict) and item.get('Name') == name:
                                current = item.get('Value', item)
                                # Handle array indexing
                                if index is not None and isinstance(current, list):
                                    if 0 <= index < len(current):
                                        indexed_item = current[index]
                                        if isinstance(indexed_item, dict) and 'Value' in indexed_item:
                                            current = indexed_item['Value']
                                        else:
                                            current = indexed_item
                                    else:
                                        return ''
                                found = True
                                break
                        if not found:
                            return ''
                    elif isinstance(current, dict) and name in current:
                        current = current[name]
                    else:
                        return ''
                else:
                    return ''
            else:
                # Reached a leaf value
                return ''

        # Extract final value
        if isinstance(current, (str, int, float, bool)):
            return str(current)
        elif isinstance(current, dict) and 'Value' in current:
            val = current['Value']
            if isinstance(val, (str, int, float, bool)):
                return str(val)
        elif isinstance(current, list) and len(current) > 0:
            # Could be a final value in an unexpected format
            pass

        return ''

    def _get_item_property_value(self, item_data: dict, property_name: str) -> str:
        """Get a property value from an item's data.

        Args:
            item_data: The item's Value array from the JSON.
            property_name: The property name to find (supports dot notation for nested properties).

        Returns:
            The property value as a string, or empty string if not found.
        """
        if not item_data:
            return ''

        # Get the Value array (for data table items)
        value_array = item_data.get('Value', [])
        if not value_array:
            return ''

        # Check if property uses dot notation or array indexing (nested path)
        if '.' in property_name or '[' in property_name:
            return self._get_nested_property_value(value_array, property_name)

        # Simple property lookup
        for prop in value_array:
            if prop.get('Name') == property_name:
                # Handle different property types
                if 'Value' in prop:
                    val = prop['Value']
                    # If it's a simple value, return it
                    if isinstance(val, (str, int, float, bool)):
                        return str(val)
                    # If it's a dict with nested value, try to extract
                    if isinstance(val, dict):
                        return str(val)
                return ''
        return ''

    def _get_gameplay_tag_container(self, item_data: dict, property_name: str) -> list[str]:
        """Get the list of tags from a GameplayTagContainer property.

        Args:
            item_data: The item's data from the JSON.
            property_name: The property name (e.g., 'ExcludeItems', 'AllowedItems').

        Returns:
            List of tag strings (e.g., ["Item.Unstorable.HandsOnly", "Item.Brew"]).
        """
        value_array = item_data.get('Value', [])
        if not value_array:
            return []

        # Find the specified property
        for prop in value_array:
            if prop.get('Name') == property_name:
                # GameplayTagContainer has nested Value array with GameplayTagContainerPropertyData
                outer_value = prop.get('Value', [])
                if isinstance(outer_value, list) and len(outer_value) > 0:
                    # First element contains the actual tag values
                    inner = outer_value[0]
                    if isinstance(inner, dict):
                        tags = inner.get('Value', [])
                        if isinstance(tags, list):
                            return [str(tag) for tag in tags]
        return []

    def _get_item_display_name(self, item_data: dict, string_tables: dict) -> str:
        """Get the display name for an item by resolving from string tables.

        Args:
            item_data: The item's data from the JSON.
            string_tables: Cache of loaded string tables {table_path: {key: value}}

        Returns:
            The resolved display name, or the item's Name as fallback.
        """
        item_name = item_data.get('Name', '')

        # Find the DisplayName property in the item's Value array
        for prop in item_data.get('Value', []):
            if prop.get('Name') == 'DisplayName':
                table_id = prop.get('TableId', '')
                string_key = prop.get('Value', '')

                if table_id and string_key:
                    # Load string table if not cached
                    if table_id not in string_tables:
                        string_tables[table_id] = self._load_string_table(table_id)

                    # Look up the display name
                    display_name = string_tables[table_id].get(string_key, '')
                    if display_name:
                        return display_name
                break

        # Fallback to item's internal Name
        return item_name

    def _build_display_data(self, file_path: Path) -> list[dict]:
        """Build the display data by merging game data with XML changes.

        Args:
            file_path: Path to the .def file.

        Returns:
            List of dictionaries with name, property, value, new_value keys.
        """
        display_data = []

        # Get mod file path and load game data
        mod_file_path = self._get_mod_file_path(file_path)
        if not mod_file_path:
            return display_data

        game_data = self._load_game_data(mod_file_path)
        if not game_data:
            return display_data

        # Get XML changes as a lookup: {item_name: {property: new_value}}
        # For GameplayTagContainer (delete), we track: {item_name: {property: {tag: is_delete}}}
        xml_changes = self._get_definition_changes(file_path)
        changes_lookup = {}
        tag_deletes = {}  # Separate lookup for tag-based deletes: {item_name: {property: set(tags)}}

        for change in xml_changes:
            item_name = change['item']
            prop = change['property']
            value = change['value']
            is_delete = change.get('is_delete', False)

            if is_delete and prop in ('ExcludeItems', 'AllowedItems'):
                # Track as a tag deletion
                if item_name not in tag_deletes:
                    tag_deletes[item_name] = {}
                if prop not in tag_deletes[item_name]:
                    tag_deletes[item_name][prop] = set()
                tag_deletes[item_name][prop].add(value)
            else:
                # Regular change
                if item_name not in changes_lookup:
                    changes_lookup[item_name] = {}
                changes_lookup[item_name][prop] = value

        # Get all items from the game data
        # Try data table format first (Exports[0].Table.Data)
        items = None
        is_data_table = False
        try:
            items = game_data['Exports'][0]['Table']['Data']
            is_data_table = True
        except (KeyError, IndexError, TypeError):
            pass

        # If not a data table, try single asset format (Exports with Data array)
        if not is_data_table:
            return self._build_display_data_single_asset(game_data, changes_lookup)

        # Cache for string tables to avoid reloading
        string_tables = {}

        # Collect all properties being modified by the XML to know which to display
        all_properties = set()
        wildcard_properties = set()  # Properties that should expand with [*]
        none_defaults = {}  # Store property -> value from NONE entries
        for item_changes in changes_lookup.values():
            all_properties.update(item_changes.keys())
        # Also include properties from tag_deletes
        for item_tags in tag_deletes.values():
            all_properties.update(item_tags.keys())

        # Check for NONE entries - these define properties/values but no items selected
        if 'NONE' in changes_lookup:
            none_defaults = changes_lookup['NONE']
            # Remove NONE from lookup so it doesn't match any real items
            del changes_lookup['NONE']

        # Convert specific array indices to wildcard patterns to show ALL indices
        # e.g., StageDataList[1].Prop and StageDataList[3].Prop -> StageDataList[*].Prop
        expanded_properties = set()
        for prop in all_properties:
            # Check if this property has a specific array index like [1], [3], etc.
            match = re.match(r'^(.+?)\[\d+\](.*)$', prop)
            if match:
                # Convert to wildcard pattern
                wildcard_prop = f"{match.group(1)}[*]{match.group(2)}"
                wildcard_properties.add(wildcard_prop)
            else:
                expanded_properties.add(prop)

        # Add wildcard properties to the set (they'll be expanded per-item)
        expanded_properties.update(wildcard_properties)
        all_properties = expanded_properties

        # For each item, show the properties (with XML changes where applicable)
        if items is None:
            items = []
        for item in items:
            item_name = item.get('Name', '')
            display_name = self._get_item_display_name(item, string_tables)

            # For each property type being tracked
            for prop_name in all_properties:
                # Special handling for GameplayTagContainer properties - one row per tag
                if prop_name in ('ExcludeItems', 'AllowedItems'):
                    tags = self._get_gameplay_tag_container(item, prop_name)

                    if tags:
                        # Show one row per existing tag
                        for tag in tags:
                            # Check if this tag is marked for deletion
                            has_mod = (item_name in tag_deletes and
                                       prop_name in tag_deletes[item_name] and
                                       tag in tag_deletes[item_name][prop_name])
                            # Show "NULL" for deleted items
                            new_value = 'NULL' if has_mod else ''

                            display_data.append({
                                'row_name': item_name,  # Storage name for XML
                                'name': item_name,      # Display as storage name
                                'property': prop_name,
                                'value': tag,           # The tag is the current value
                                'new_value': new_value,
                                'has_mod': has_mod
                            })
                    else:
                        # No tags - show empty row for this object (allows adding)
                        display_data.append({
                            'row_name': item_name,
                            'name': item_name,
                            'property': prop_name,
                            'value': '',              # No current tags
                            'new_value': '',
                            'has_mod': False
                        })
                    continue

                # Check if property has wildcard [*] - expand to all array indices
                if '[*]' in prop_name:
                    expanded_props = self._expand_wildcard_property(item, prop_name)
                    for expanded_prop, current_value in expanded_props:
                        # Check if there's an XML change for this specific item/property
                        has_mod = item_name in changes_lookup and expanded_prop in changes_lookup[item_name]
                        if has_mod:
                            new_value = changes_lookup[item_name][expanded_prop]
                        elif prop_name in none_defaults:
                            # Use NONE default value but don't check the item
                            new_value = none_defaults[prop_name]
                        else:
                            new_value = current_value

                        display_data.append({
                            'row_name': item_name,
                            'name': display_name,
                            'property': expanded_prop,  # Use expanded property with actual index
                            'value': current_value,
                            'new_value': new_value,
                            'has_mod': has_mod
                        })
                    continue

                current_value = self._get_item_property_value(item, prop_name)

                # Skip if this item doesn't have this property
                if not current_value:
                    continue

                # Check if there's an XML change for this item/property
                has_mod = item_name in changes_lookup and prop_name in changes_lookup[item_name]
                if has_mod:
                    new_value = changes_lookup[item_name][prop_name]
                elif prop_name in none_defaults:
                    # Use NONE default value but don't check the item
                    new_value = none_defaults[prop_name]
                else:
                    # No XML modification - new equals current value
                    new_value = current_value

                display_data.append({
                    'row_name': item_name,  # Original name for XML
                    'name': display_name,   # Display name from string table
                    'property': prop_name,
                    'value': current_value,
                    'new_value': new_value,
                    'has_mod': has_mod
                })

        # Sort by name
        return sorted(display_data, key=lambda x: x['name'].lower())

    def _build_display_data_single_asset(self, game_data: dict, changes_lookup: dict) -> list[dict]:
        """Build display data for single asset files (non-data-table).

        Args:
            game_data: The parsed JSON game data.
            changes_lookup: Dictionary of {item_name: {property: new_value}}.

        Returns:
            List of dictionaries with name, property, value, new_value keys.
        """
        display_data = []

        # Check for NONE entries - these define properties/values for all exports
        none_defaults = {}
        if 'NONE' in changes_lookup:
            none_defaults = changes_lookup['NONE']
            # Remove NONE from lookup so it doesn't try to match as item name
            changes_lookup = {k: v for k, v in changes_lookup.items() if k != 'NONE'}

        # Collect all properties being modified by the XML
        all_properties = set()
        for item_changes in changes_lookup.values():
            all_properties.update(item_changes.keys())
        all_properties.update(none_defaults.keys())

        # Find exports with Data arrays (skip class exports)
        for export in game_data.get('Exports', []):
            if 'Data' not in export or not isinstance(export.get('Data'), list):
                continue
            if len(export.get('Data', [])) == 0:
                continue

            # Get the item name from ObjectName
            item_name = export.get('ObjectName', '')

            # Skip class definition exports (non-Default__ exports that are just class defs)
            # Focus on Default__ exports which contain actual property values

            # For each property we're tracking, try to get the value from this export
            for prop_name in all_properties:
                # Check if property has wildcard - if so, expand it
                if '[*]' in prop_name:
                    expanded_results = self._expand_wildcard_property_single_asset(export['Data'], prop_name)
                    for expanded_prop, current_value in expanded_results:
                        # Determine if this is a modification and what the new value should be
                        has_mod = False
                        new_value = current_value
                        row_name = item_name

                        # Check for item-specific match
                        for lookup_item_name, properties in changes_lookup.items():
                            if lookup_item_name == item_name or lookup_item_name in item_name:
                                if prop_name in properties:
                                    has_mod = True
                                    new_value = properties[prop_name]
                                    row_name = lookup_item_name
                                    break

                        # If no specific match but NONE defaults exist for this property
                        if not has_mod and prop_name in none_defaults:
                            new_value = none_defaults[prop_name]
                            has_mod = True  # NONE with wildcard applies to all

                        display_data.append({
                            'row_name': row_name,
                            'name': item_name,
                            'property': expanded_prop,  # Use expanded property (with index)
                            'value': current_value,
                            'new_value': new_value,
                            'has_mod': has_mod
                        })
                else:
                    # Get current value using nested property lookup
                    current_value = self._get_nested_property_value(export['Data'], prop_name)

                    if not current_value:
                        continue

                    # Check if there's a specific item match in changes_lookup
                    has_mod = False
                    new_value = current_value
                    row_name = item_name

                    for lookup_item_name, properties in changes_lookup.items():
                        if lookup_item_name == item_name or lookup_item_name in item_name:
                            if prop_name in properties:
                                has_mod = True
                                new_value = properties[prop_name]
                                row_name = lookup_item_name
                                break

                    # If no specific match but NONE defaults exist for this property
                    if not has_mod and prop_name in none_defaults:
                        new_value = none_defaults[prop_name]

                    display_data.append({
                        'row_name': row_name,  # Always use actual item name for XML saving
                        'name': item_name,
                        'property': prop_name,
                        'value': current_value,
                        'new_value': new_value,
                        'has_mod': has_mod
                    })

        return display_data

    def _expand_wildcard_property_single_asset(self, data: list, property_pattern: str) -> list[tuple[str, str]]:
        """Expand a wildcard [*] property pattern to all matching indices for single asset data.

        Args:
            data: The export Data array.
            property_pattern: Property path with [*] wildcard.

        Returns:
            List of (expanded_property, value) tuples.
        """
        if '[*]' not in property_pattern:
            value = self._get_nested_property_value(data, property_pattern)
            if value:
                return [(property_pattern, value)]
            return []

        # Parse the path before and after [*]
        # e.g., "FloatCurve.Keys[*].Keys.Time" -> before="FloatCurve.Keys", after="Keys.Time"
        match = re.match(r'^(.+?)\[\*\]\.?(.*)$', property_pattern)
        if not match:
            return []

        path_before = match.group(1)
        path_after = match.group(2)

        # Navigate to the array
        current = data
        for segment in path_before.split('.'):
            seg_match = re.match(r'^(\w+)(?:\[(\d+)\])?$', segment)
            if not seg_match:
                return []
            name = seg_match.group(1)
            index = int(seg_match.group(2)) if seg_match.group(2) is not None else None

            if isinstance(current, list):
                found = False
                for item in current:
                    if isinstance(item, dict) and item.get('Name') == name:
                        current = item.get('Value', [])
                        if index is not None and isinstance(current, list):
                            if 0 <= index < len(current):
                                indexed = current[index]
                                current = indexed.get('Value', indexed) if isinstance(indexed, dict) else indexed
                            else:
                                return []
                        found = True
                        break
                if not found:
                    return []
            elif isinstance(current, dict):
                if name in current:
                    current = current[name]
                    if index is not None and isinstance(current, list):
                        if 0 <= index < len(current):
                            indexed = current[index]
                            current = indexed.get('Value', indexed) if isinstance(indexed, dict) else indexed
                        else:
                            return []
                else:
                    return []

        # current should now be an array
        if not isinstance(current, list):
            return []

        # Expand to all indices
        results = []
        for i in range(len(current)):
            if path_after:
                expanded_prop = f"{path_before}[{i}].{path_after}"
            else:
                expanded_prop = f"{path_before}[{i}]"

            value = self._get_nested_property_value(data, expanded_prop)
            if value:
                results.append((expanded_prop, value))

        return results

    # =========================================================================
    # DEFINITION DETAILS DISPLAY
    # =========================================================================
    # These methods handle displaying definition file details in the right
    # pane, including the data table with virtual scrolling for performance.
    # =========================================================================

    def _show_definition_details(self, file_path: Path):
        """
        Show the definition details in the right pane.

        Loads the definition file, extracts metadata, builds the display data,
        and creates the editable data table.

        Args:
            file_path: Path to the .def file to display.
        """
        # Store current definition path for saving
        self.current_definition_path = file_path

        # Clear existing content in main_content
        if self.main_content:
            for widget in self.main_content.winfo_children():
                widget.destroy()

        # Show loading indicator in status bar
        self.set_status_message("Loading definition data...")
        self.update_idletasks()  # Force UI update to show the message

        # Get description and build display data from game files
        title = self._get_definition_title(file_path)
        author = self._get_definition_author(file_path)
        description = self._get_definition_description(file_path)
        display_data = self._build_display_data(file_path)

        # Clear loading message
        self.clear_status_message()

        # Create details frame
        details_frame = ctk.CTkFrame(self.main_content)
        details_frame.pack(fill="both", expand=True)

        # Header section with Title, Author, Description
        header_info_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        header_info_frame.pack(fill="x", padx=10, pady=(10, 5))

        label_font = ctk.CTkFont(size=14, weight="bold")
        value_font = ctk.CTkFont(size=14)

        # Title row
        title_row = ctk.CTkFrame(header_info_frame, fg_color="transparent")
        title_row.pack(fill="x", anchor="w")
        ctk.CTkLabel(
            title_row, text="TITLE:", font=label_font, width=100, anchor="w"
        ).pack(side="left")
        ctk.CTkLabel(
            title_row, text=title if title else file_path.stem, font=value_font, anchor="w"
        ).pack(side="left", fill="x", expand=True)

        # Author row (only if author exists)
        if author:
            author_row = ctk.CTkFrame(header_info_frame, fg_color="transparent")
            author_row.pack(fill="x", anchor="w")
            ctk.CTkLabel(
                author_row, text="AUTHOR:", font=label_font, width=100, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                author_row, text=author, font=value_font, anchor="w"
            ).pack(side="left", fill="x", expand=True)

        # Description row
        if description:
            desc_row = ctk.CTkFrame(header_info_frame, fg_color="transparent")
            desc_row.pack(fill="x", anchor="w")
            ctk.CTkLabel(
                desc_row, text="DESCRIPTION:", font=label_font, width=100, anchor="w"
            ).pack(side="left")
            ctk.CTkLabel(
                desc_row, text=description, font=value_font, anchor="w"
            ).pack(side="left", fill="x", expand=True)

        # Table header with tri-state checkbox only (column headers are in Treeview)
        header_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=(10, 0))

        # Header tri-state checkbox for select all/none/mixed (uses color to indicate mixed)
        self.select_all_state = "none"  # Track state: "none", "all", "mixed"
        self.select_all_var = ctk.BooleanVar(value=False)
        self.select_all_btn = ctk.CTkCheckBox(
            header_frame,
            text="Select All / None",
            variable=self.select_all_var,
            width=20,
            font=ctk.CTkFont(size=14),
            command=self._on_select_all_toggle
        )
        self.select_all_btn.pack(side="left")

        # Virtual scrolling container - uses canvas for efficient scrolling
        self._setup_virtual_scroll_table(details_frame, display_data)

        # Add Save button row at bottom of right pane with row count
        save_button_frame = ctk.CTkFrame(details_frame, fg_color="transparent")
        save_button_frame.pack(fill="x", padx=10, pady=(10, 10))

        # Row count on the left
        total_rows = len(display_data) if display_data else 0
        row_count_label = ctk.CTkLabel(
            save_button_frame,
            text=f"Total: {total_rows} rows",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        row_count_label.pack(side="left")

        # Search section in center
        search_frame = ctk.CTkFrame(save_button_frame, fg_color="transparent")
        search_frame.pack(side="left", expand=True)

        # Search entry
        self.search_var = ctk.StringVar()
        def search_text_changed_callback(_, __, ___):
            self._on_search_text_changed()
        self.search_var.trace_add("write", search_text_changed_callback)
        self.search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            width=200,
            height=32,
            placeholder_text="Search name...",
            font=ctk.CTkFont(size=14)
        )
        self.search_entry.pack(side="left", padx=(0, 5))
        self.search_entry.bind("<Return>", lambda e: self._on_search_next())

        # Search button (purple)
        search_btn = ctk.CTkButton(
            search_frame,
            text="Find Next",
            width=80,
            height=32,
            fg_color="#8B5CF6",  # Purple
            hover_color="#7C3AED",  # Darker purple on hover
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_search_next
        )
        search_btn.pack(side="left")

        # Track search position
        self.search_last_index = -1
        self.search_last_text = ""

        self.save_btn = ctk.CTkButton(
            save_button_frame,
            text="Save",
            width=80,
            height=32,
            fg_color=COLOR_SAVE_BUTTON,
            hover_color=COLOR_SAVE_BUTTON_HOVER,
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_save_click
        )
        self.save_btn.pack(side="right")

    def _setup_virtual_scroll_table(self, parent: ctk.CTkFrame, display_data: list[dict]):
        """Set up a virtual scrolling table that only renders visible rows.

        Uses tkinter Treeview which natively supports virtual scrolling for large datasets.

        Args:
            parent: Parent frame to contain the table.
            display_data: List of row data dictionaries.
        """
        # Store display data for access by other methods
        self.virtual_display_data = display_data if display_data else []

        # Data model - stores state for ALL rows (not tied to widgets)
        self.row_values = []      # Original values
        self.row_names = []       # Item names for XML
        self.row_properties = []  # Property names for XML
        self.row_checked = []     # Checkbox states (bool)
        self.row_new_values = []  # New value entries (str)

        # Initialize data model from display_data
        for item in self.virtual_display_data:
            self.row_values.append(str(item['value']))
            self.row_names.append(item['row_name'])
            self.row_properties.append(item['property'])
            self.row_checked.append(item.get('has_mod', False))
            self.row_new_values.append(str(item['new_value']))

        if not self.virtual_display_data:
            # Show empty state message
            empty_frame = ctk.CTkFrame(parent, fg_color="transparent")
            empty_frame.pack(fill="both", expand=True, padx=10, pady=10)
            ctk.CTkLabel(
                empty_frame,
                text="No data found - ensure game files are imported and converted",
                text_color="gray",
                font=ctk.CTkFont(size=16)
            ).pack(pady=20)
            return

        # Create container frame
        container = ctk.CTkFrame(parent)
        container.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # Style the Treeview to match dark theme
        style = ttk.Style()
        bg_color = self._get_theme_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
        fg_color = self._get_theme_color(("gray10", "gray90"))
        selected_color = self._get_theme_color(("gray80", "gray30"))

        style.theme_use("clam")
        style.configure("Virtual.Treeview",
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=bg_color,
                        rowheight=44,
                        font=("", 20))
        style.configure("Virtual.Treeview.Heading",
                        background=self._get_theme_color(("gray85", "gray25")),
                        foreground=fg_color,
                        font=("", 20, "bold"))
        style.map("Virtual.Treeview",
                  background=[("selected", selected_color)],
                  foreground=[("selected", fg_color)])

        # Create Treeview with columns
        columns = ("checked", "name", "property", "value", "new")
        self.tree = ttk.Treeview(container, columns=columns, show="headings",
                                  style="Virtual.Treeview", selectmode="extended")

        # Configure columns - make them resizable
        self.tree.heading("checked", text="☑")
        self.tree.heading("name", text="Name")
        self.tree.heading("property", text="Property")
        self.tree.heading("value", text="Value")
        self.tree.heading("new", text="New")

        self.tree.column("checked", width=40, minwidth=30, stretch=False, anchor="center")
        self.tree.column("name", width=250, minwidth=100, stretch=True)
        self.tree.column("property", width=200, minwidth=80, stretch=True)
        self.tree.column("value", width=120, minwidth=60, stretch=True)
        self.tree.column("new", width=120, minwidth=60, stretch=True)

        # Add scrollbar
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # Populate tree with data
        self.tree_items = []  # Store item IDs for reference
        for i, item in enumerate(self.virtual_display_data):
            checked_symbol = "☑" if self.row_checked[i] else "☐"
            item_id = self.tree.insert("", "end", values=(
                checked_symbol,
                item['name'],
                item['property'],
                item['value'],
                self.row_new_values[i]
            ), tags=("checked" if self.row_checked[i] else "unchecked",))
            self.tree_items.append(item_id)

        # Configure tag colors for checked rows
        if self.tree and hasattr(self.tree, 'tag_configure'):
            self.tree.tag_configure("checked", background=str(selected_color))
            self.tree.tag_configure("unchecked", background=str(bg_color))

        # Bind events
        self.tree.bind("<Double-1>", self._on_tree_double_click)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<MouseWheel>", lambda e: None)  # Let default scrolling work

        # Store reference to editing entry
        self.tree_edit_entry = None

        # Update select all checkbox state
        self._update_select_all_checkbox_state()

    def _get_tree_data_index(self, item_id: str) -> int:
        """Get the data index for a tree item ID."""
        try:
            return self.tree_items.index(item_id)
        except (ValueError, AttributeError):
            return -1

    def _on_tree_click(self, event):
        """Handle single click on tree - toggle checkbox if clicked on first column."""
        if self.tree and hasattr(self.tree, 'identify_region'):
            region = self.tree.identify_region(event.x, event.y)
        else:
            return
        if region != "cell":
            return

        if self.tree and hasattr(self.tree, 'identify_column'):
            column = self.tree.identify_column(event.x)
        else:
            return
        if self.tree and hasattr(self.tree, 'identify_row'):
            item_id = self.tree.identify_row(event.y)
        else:
            return

        if not item_id:
            return

        data_idx = self._get_tree_data_index(item_id)
        if data_idx < 0:
            return

        # If clicked on checkbox column, toggle it
        if column == "#1":  # First column (checked)
            self.row_checked[data_idx] = not self.row_checked[data_idx]
            is_checked = self.row_checked[data_idx]

            # If unchecking, reset new value to original
            if not is_checked:
                self.row_new_values[data_idx] = self.row_values[data_idx]

            # Update display
            checked_symbol = "☑" if is_checked else "☐"
            if self.tree and hasattr(self.tree, 'item'):
                values = list(self.tree.item(item_id, "values"))
                values[0] = checked_symbol
                values[4] = self.row_new_values[data_idx]
                self.tree.item(item_id, values=values,
                              tags=("checked" if is_checked else "unchecked",))

            self._update_select_all_checkbox_state()

    def _on_tree_double_click(self, event):
        """Handle double-click to edit the New column."""
        if self.tree and hasattr(self.tree, 'identify_region'):
            region = self.tree.identify_region(event.x, event.y)
        else:
            return
        if region != "cell":
            return

        if self.tree and hasattr(self.tree, 'identify_column'):
            column = self.tree.identify_column(event.x)
        else:
            return
        if self.tree and hasattr(self.tree, 'identify_row'):
            item_id = self.tree.identify_row(event.y)
        else:
            return

        if not item_id:
            return

        # Only allow editing the "new" column (#5)
        if column != "#5":
            return

        data_idx = self._get_tree_data_index(item_id)
        if data_idx < 0:
            return

        # Get cell bounding box
        if self.tree and hasattr(self.tree, 'bbox'):
            bbox = self.tree.bbox(item_id, column)
        else:
            return
        if not bbox:
            return

        x, y, width, height = bbox

        # Destroy any existing edit entry
        if self.tree_edit_entry and hasattr(self.tree_edit_entry, 'destroy'):
            self.tree_edit_entry.destroy()

        # Create entry for editing using tkinter Entry for better compatibility
        current_value = self.row_new_values[data_idx]
        def theme_color(val):
            # Ensure _get_theme_color returns a string
            color = self._get_theme_color(val)
            if isinstance(color, (tuple, list)):
                return str(color[0])
            return str(color)
        self.tree_edit_entry = tk.Entry(
            self.tree,
            font=("", 18),
            bg=theme_color(("white", "gray20")),
            fg=theme_color(("black", "white")),
            insertbackground=theme_color(("black", "white"))
        )
        self.tree_edit_entry.place(x=x, y=y, width=width, height=height)
        self.tree_edit_entry.insert(0, current_value)
        self.tree_edit_entry.select_range(0, tk.END)
        self.tree_edit_entry.focus_set()

        def save_edit():
            new_value = self.tree_edit_entry.get()
            self.row_new_values[data_idx] = new_value

            # Update tree display
            values = list(self.tree.item(item_id, "values"))
            values[4] = new_value
            self.tree.item(item_id, values=values)

            self.tree_edit_entry.destroy()
            self.tree_edit_entry = None

        def cancel_edit():
            self.tree_edit_entry.destroy()
            self.tree_edit_entry = None

        self.tree_edit_entry.bind("<Return>", save_edit)
        self.tree_edit_entry.bind("<Escape>", cancel_edit)
        self.tree_edit_entry.bind("<FocusOut>", save_edit)

    def _get_theme_color(self, color_tuple):
        """Get the appropriate color based on current appearance mode."""
        if isinstance(color_tuple, (list, tuple)) and len(color_tuple) == 2:
            mode = ctk.get_appearance_mode()
            return color_tuple[0] if mode == "Light" else color_tuple[1]
        return color_tuple

    def _on_select_all_toggle(self):
        """Handle select all button toggle - cycles between all checked and all unchecked."""
        if not hasattr(self, 'tree') or not hasattr(self, 'tree_items'):
            return

        # If currently none or mixed, select all. If all, deselect all.
        new_state = self.select_all_state != "all"

        # Theme colors available if needed
        _ = self._get_theme_color(ctk.ThemeManager.theme["CTkFrame"]["fg_color"])
        _ = self._get_theme_color(("gray80", "gray30"))

        for i, item_id in enumerate(self.tree_items):
            self.row_checked[i] = new_state
            if not new_state:
                self.row_new_values[i] = self.row_values[i]

            # Update tree display
            checked_symbol = "☑" if new_state else "☐"
            values = list(self.tree.item(item_id, "values"))
            values[0] = checked_symbol
            values[4] = self.row_new_values[i]
            self.tree.item(item_id, values=values,
                          tags=("checked" if new_state else "unchecked",))

        # Update button state
        self._update_select_all_checkbox_state()

    def _on_search_text_changed(self):
        """Reset search position when search text changes."""
        current_text = self.search_var.get().strip().lower() if self.search_var else ""
        if current_text != self.search_last_text:
            self.search_last_index = -1
            self.search_last_text = current_text

    def _on_search_next(self):
        """Find next match for the search text."""
        if not hasattr(self, 'tree') or not self.tree or not hasattr(self, 'tree_items') or not self.tree_items:
            self.set_status_message("No data to search", is_error=True)
            return

        search_text = self.search_var.get().strip().lower() if self.search_var else ""
        if not search_text:
            return

        # Start searching from the position after the last found item
        start_index = self.search_last_index + 1
        total_items = len(self.tree_items)

        # Search from start_index to end, then wrap around from beginning
        for offset in range(total_items):
            i = (start_index + offset) % total_items
            item_name = self.virtual_display_data[i]['name'].lower()

            if search_text in item_name:
                # Found - scroll to this item and select it
                item_id = self.tree_items[i]
                self.tree.see(item_id)
                self.tree.selection_set(item_id)
                self.tree.focus(item_id)
                self.search_last_index = i

                # Show match info
                self.set_status_message(f"Found: {self.virtual_display_data[i]['name']}")
                return

        # No match found
        if self.search_var and hasattr(self.search_var, 'get'):
            search_text = self.search_var.get()
        else:
            search_text = ''
        self.set_status_message(f"No match found for '{search_text}'", is_error=True)
        self.search_last_index = -1

    def _update_select_all_checkbox_state(self):
        """Update the select all button to reflect the state of row checkboxes."""
        if not hasattr(self, 'row_checked') or not self.row_checked:
            return

        checked_count = sum(1 for checked in self.row_checked if checked)
        total_count = len(self.row_checked)

        # Checkbox colors from constants
        default_color = (COLOR_CHECKBOX_DEFAULT, COLOR_CHECKBOX_DEFAULT)
        mixed_color = (COLOR_CHECKBOX_MIXED, COLOR_CHECKBOX_MIXED)

        if checked_count == 0:
            # None checked
            self.select_all_state = "none"
            if self.select_all_btn and hasattr(self.select_all_btn, 'deselect'):
                self.select_all_btn.deselect()
            if self.select_all_btn and hasattr(self.select_all_btn, 'configure'):
                self.select_all_btn.configure(fg_color=default_color)
        elif checked_count == total_count:
            # All checked
            self.select_all_state = "all"
            if self.select_all_btn and hasattr(self.select_all_btn, 'select'):
                self.select_all_btn.select()
            if self.select_all_btn and hasattr(self.select_all_btn, 'configure'):
                self.select_all_btn.configure(fg_color=default_color)
        else:
            # Mixed state - checked with orange color
            self.select_all_state = "mixed"
            if self.select_all_btn and hasattr(self.select_all_btn, 'select'):
                self.select_all_btn.select()
            if self.select_all_btn and hasattr(self.select_all_btn, 'configure'):
                self.select_all_btn.configure(fg_color=mixed_color)

    # =========================================================================
    # BUILD AND SAVE OPERATIONS
    # =========================================================================
    # These methods handle building MOD files from selected definitions and
    # saving changes made in the data table back to definition files.
    # =========================================================================

    def _on_build_click(self):
        """
        Handle Build button click - build the mod from selected definitions.

        Validates that a mod name is set and definitions are selected,
        then invokes the BuildManager to create the PAK file.
        """
        mod_name = self.mod_name_var.get().strip() if self.mod_name_var else ""

        if not mod_name:
            self.set_status_message("Please enter a mod name", is_error=True)
            return

        # Save current checkbox states first to ensure INI is up to date
        self._save_checkbox_states()

        # Get selected definitions from INI file (includes all subdirectories)
        selected = self._get_all_selected_definitions_from_ini()

        if not selected:
            self.set_status_message("No definition files selected for build", is_error=True)
            return

        # Show progress bar
        self._show_build_progress()

        try:
            # Create build manager with progress callback
            def progress_callback(message: str, progress: float):
                self._update_build_progress(message, progress)
                self.update()  # Force UI update

            build_manager = BuildManager(progress_callback=progress_callback)
            success, message = build_manager.build(mod_name, selected)

            # Hide progress bar
            self._hide_build_progress()

            if success:
                self.set_status_message(f"Build complete! {message}")
            else:
                self.set_status_message(f"Build failed: {message}", is_error=True)

        except (OSError, RuntimeError) as e:
            logger.exception("Build failed with exception")
            self._hide_build_progress()
            self.set_status_message(f"Build failed: {e}", is_error=True)

    def _show_build_progress(self):
        """Show the build progress bar."""
        if not hasattr(self, 'progress_frame') or self.progress_frame is None:
            self.progress_frame = ctk.CTkFrame(self.status_bar)
            self.progress_frame.pack(side="right", padx=10)

            self.progress_label = ctk.CTkLabel(
                self.progress_frame,
                text="Building...",
                font=ctk.CTkFont(size=12)
            )
            self.progress_label.pack(side="left", padx=(0, 10))

            self.progress_bar = ctk.CTkProgressBar(
                self.progress_frame,
                width=200,
                height=15
            )
            self.progress_bar.pack(side="left")
            self.progress_bar.set(0)

    def _update_build_progress(self, message: str, progress: float):
        """Update the build progress bar.

        Args:
            message: Status message to display.
            progress: Progress percentage (0.0 to 1.0).
        """
        if hasattr(self, 'progress_label') and self.progress_label:
            self.progress_label.configure(text=message)
        if hasattr(self, 'progress_bar') and self.progress_bar:
            self.progress_bar.set(progress)

    def _hide_build_progress(self):
        """Hide the build progress bar."""
        if hasattr(self, 'progress_frame') and self.progress_frame:
            self.progress_frame.destroy()
            self.progress_frame = None
            self.progress_label = None
            self.progress_bar = None

    def _on_mod_name_click(self):
        """Handle My Mod Name button click - open dialog to set mod name."""
        current_name = self.mod_name_var.get() if self.mod_name_var and hasattr(self.mod_name_var, 'get') else ''
        result = show_mod_name_dialog(self, current_name)

        if result:
            # Update the mod name display
            if self.mod_name_var and hasattr(self.mod_name_var, 'set'):
                self.mod_name_var.set(result)

            # Store the current mod name for INI path
            self._current_mod_name = result

            # Reload checkbox states from the new mod's directory
            self._load_checkbox_states()

            # Refresh the definitions list to update checkbox states
            self._refresh_definitions_list(self.current_definitions_dir)

            self.set_status_message(f"Mod '{result}' selected")

    def _on_save_click(self):
        """Handle Save button click - update the XML definition file."""
        if not hasattr(self, 'current_definition_path') or not self.current_definition_path:
            self.set_status_message("No definition file selected", is_error=True)
            return

        try:
            file_path = self.current_definition_path

            # Parse the existing XML
            tree = ET.parse(file_path)
            root = tree.getroot()

            # Find the <mod> element
            mod_element = root.find('mod')
            if mod_element is None:
                self.set_status_message("No <mod> element found in definition file", is_error=True)
                return

            # Clear existing <change> and <delete> elements
            for change in mod_element.findall('change'):
                mod_element.remove(change)
            for delete in mod_element.findall('delete'):
                mod_element.remove(delete)

            # Add new <change> or <delete> elements for checked rows
            changes_added = 0
            properties_used = {}  # Track property -> value for NONE fallback

            # Use the virtual scroll data model
            for i in range(len(self.row_checked)):
                prop_name = self.row_properties[i]
                new_value = self.row_new_values[i].strip() if self.row_new_values[i] else ""

                # Track the first value seen for each property (for NONE fallback)
                if prop_name not in properties_used:
                    properties_used[prop_name] = new_value

                if self.row_checked[i]:  # Only add if checked
                    row_name = self.row_names[i]
                    original_value = self.row_values[i]

                    # For ExcludeItems: use <delete> if value is empty/NULL, else <change>
                    # For GameplayTagContainer properties: use <delete> if value is empty/NULL, else <change>
                    if prop_name in ('ExcludeItems', 'AllowedItems'):
                        if not new_value or new_value.upper() == 'NULL':
                            # Delete: remove the original tag
                            delete_elem = ET.SubElement(mod_element, 'delete')
                            delete_elem.set('item', row_name)
                            delete_elem.set('property', prop_name)
                            delete_elem.set('value', original_value)
                        else:
                            # Change: replace original with new
                            change_elem = ET.SubElement(mod_element, 'change')
                            change_elem.set('item', row_name)
                            change_elem.set('property', prop_name)
                            change_elem.set('value', new_value)
                            change_elem.set('original', original_value)
                    else:
                        # Regular property change
                        change_elem = ET.SubElement(mod_element, 'change')
                        change_elem.set('item', row_name)
                        change_elem.set('property', prop_name)
                        change_elem.set('value', new_value)

                    changes_added += 1

            # If no items were checked, save NONE entries to preserve property/value
            if changes_added == 0 and properties_used:
                for prop_name, value in properties_used.items():
                    change_elem = ET.SubElement(mod_element, 'change')
                    change_elem.set('item', 'NONE')
                    change_elem.set('property', prop_name)
                    change_elem.set('value', value)

            # Format the XML with proper indentation
            self._indent_xml(root)

            # Write back to file
            tree.write(file_path, encoding='UTF-8', xml_declaration=True)

            if changes_added == 0 and properties_used:
                self.set_status_message(f"Saved template (no items selected) to {file_path.name}")
            else:
                self.set_status_message(f"Saved {changes_added} changes to {file_path.name}")

        except (ET.ParseError, OSError) as e:
            self.set_status_message(f"Error saving: {e}", is_error=True)

    def _indent_xml(self, elem, level=0):
        """Add proper indentation to XML elements.

        Args:
            elem: The XML element to indent.
            level: Current indentation level.
        """
        indent = "\n" + "  " * level
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = indent + "  "
            if not elem.tail or not elem.tail.strip():
                elem.tail = indent
            last_child = None
            for child in elem:
                self._indent_xml(child, level + 1)
                last_child = child
            if last_child is not None and (not last_child.tail or not last_child.tail.strip()):
                last_child.tail = indent
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = indent

    def _create_toolbar_button(self, parent, icon_name: str, tooltip: str, command):
        """Create a toolbar button with icon.

        Args:
            parent: Parent widget.
            icon_name: Name of the icon file.
            tooltip: Tooltip text for the button.
            command: Command to execute when clicked.
        """
        icon_path = get_icon_path(icon_name)

        if icon_path.exists():
            try:
                img = Image.open(icon_path)
                icon_image = ctk.CTkImage(
                    light_image=img,
                    dark_image=img,
                    size=TOOLBAR_ICON_SIZE
                )
                btn = ctk.CTkButton(
                    parent,
                    image=icon_image,
                    text="",
                    width=50,
                    height=50,
                    fg_color="transparent",
                    hover_color=("gray75", "gray25"),
                    command=command
                )
            except (OSError, ValueError):
                # Fallback to text button
                btn = ctk.CTkButton(
                    parent,
                    text=tooltip[:3],
                    width=50,
                    height=50,
                    fg_color="transparent",
                    hover_color=("gray75", "gray25"),
                    command=command
                )
        else:
            # Fallback to text button with abbreviation
            btn = ctk.CTkButton(
                parent,
                text=tooltip[:3],
                width=50,
                height=50,
                fg_color="transparent",
                hover_color=("gray75", "gray25"),
                command=command
            )

        btn.pack(side="left", padx=5)

        # Store tooltip reference for future tooltip implementation
        # tooltip_text = tooltip  # For future use

    def _run_import(self):
        """Run the retoc import and JSON conversion process."""
        show_import_dialog(self)

    def _run_secrets_import(self):
        """Run the Secrets Source import process."""
        show_secrets_import_dialog(self)

    def _open_settings(self):
        """Open the settings/configuration dialog."""
        from src.ui.config_dialog import show_config_dialog  # pylint: disable=import-outside-toplevel
        show_config_dialog(self)

    def _open_about(self):
        """Open the Help About dialog."""
        show_about_dialog(self)

    def _show_error(self, message: str):
        """Show an error message dialog.

        Args:
            message: The error message to display.
        """
        error_dialog = ctk.CTkToplevel(self)
        error_dialog.title("Error")
        error_dialog.geometry("400x150")
        error_dialog.resizable(False, False)
        error_dialog.transient(self)
        error_dialog.grab_set()

        # Center on screen
        error_dialog.update_idletasks()
        x = (error_dialog.winfo_screenwidth() - 400) // 2
        y = (error_dialog.winfo_screenheight() - 150) // 2
        error_dialog.geometry(f"400x150+{x}+{y}")

        # Message
        msg_label = ctk.CTkLabel(
            error_dialog,
            text=message,
            wraplength=350,
            justify="center"
        )
        msg_label.pack(expand=True, padx=20, pady=20)

        # OK button
        ok_btn = ctk.CTkButton(
            error_dialog,
            text="OK",
            command=error_dialog.destroy,
            width=80
        )
        ok_btn.pack(pady=(0, 20))

    # =========================================================================
    # VIEW SWITCHING
    # =========================================================================
    # These methods handle switching between the main Definitions view and
    # the Buildings/Constructions view.
    # =========================================================================

    def _show_buildings_view(self):
        """
        Switch to the Constructions view.

        If already in buildings view, toggles back to definitions view.
        """
        if self.current_view == "buildings":
            # Already in buildings view, switch back to definitions
            self._show_definitions_view()
            return

        self.current_view = "buildings"

        # Hide definitions view
        if self.definitions_view_frame:
            self.definitions_view_frame.grid_forget()

        # Show buildings view
        if self.buildings_view:
            self.buildings_view.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # Update button appearances - Constructions active, Mod Builder inactive
        if self.buildings_btn:
            self.buildings_btn.configure(fg_color=("#3B8ED0", "#1F6AA5"))
        if self.mod_builder_btn:
            self.mod_builder_btn.configure(fg_color=("gray70", "gray30"))

        self.set_status_message("Constructions view active")

    def _show_definitions_view(self):
        """Switch back to the Mod Builder view."""
        self.current_view = "definitions"

        # Hide buildings view
        if self.buildings_view:
            self.buildings_view.grid_forget()

        # Show definitions view
        if self.definitions_view_frame:
            self.definitions_view_frame.grid(row=0, column=0, columnspan=2, sticky="nsew")

        # Update button appearances - Mod Builder active, Constructions inactive
        if self.mod_builder_btn:
            self.mod_builder_btn.configure(fg_color=("#3B8ED0", "#1F6AA5"))
        if self.buildings_btn:
            self.buildings_btn.configure(fg_color=("gray70", "gray30"))

        self.clear_status_message()
