"""Import Construction Dialog for importing buildings from game JSON files.

This dialog allows users to:
1. Select a directory containing DT_Constructions.json and DT_ConstructionRecipes.json
2. Browse and select constructions to import
3. Generate .def files for the selected constructions

Uses tkinter Treeview for efficient virtual scrolling with large datasets.
"""

import html
import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import customtkinter as ctk

from src.config import (
    get_constructions_json_dir,
    set_constructions_json_dir,
    get_buildings_dir,
)

logger = logging.getLogger(__name__)


def escape_xml_value(value: str) -> str:
    """Escape special characters for XML attribute values."""
    return html.escape(value, quote=True)


def get_icon_import_index(construction_item: dict) -> Optional[int]:
    """Extract the Icon import index from a construction item.

    Icon property uses negative indices to reference Imports array.
    e.g., -2 means Imports[abs(-2) - 1] = Imports[1]
    """
    for prop in construction_item.get('Value', []):
        if prop.get('Name') == 'Icon':
            value = prop.get('Value')
            if isinstance(value, int) and value < 0:
                return value
    return None


def get_import_entries_for_icon(icon_index: int, all_imports: list) -> list:
    """Get the Import entries for an icon reference.

    Each icon typically needs 2 Import entries:
    - The Package entry (path to the icon asset)
    - The Texture2D entry (the actual texture reference)

    Icon index is negative, e.g., -2 means Imports[1] and we also need Imports[0]
    """
    if icon_index >= 0:
        return []

    # Convert negative index to array index
    # -2 → index 1, -4 → index 3, etc.
    texture_idx = abs(icon_index) - 1
    package_idx = texture_idx - 1

    result = []
    if 0 <= package_idx < len(all_imports):
        result.append(all_imports[package_idx])
    if 0 <= texture_idx < len(all_imports):
        result.append(all_imports[texture_idx])

    return result


def generate_def_file(
    construction_name: str,
    recipe_item: Optional[dict],
    construction_item: dict,
    icon_imports: list,
    output_dir: Path
) -> Path:
    """Generate a .def file for a single construction in proper XML format.

    Args:
        construction_name: The name of the construction
        recipe_item: The recipe JSON object from DT_ConstructionRecipes (or None for blank)
        construction_item: The construction JSON object from DT_Constructions
        icon_imports: The Import entries for the icon (for DT_Constructions)
        output_dir: Directory to write the .def file
    """
    # Serialize the JSON objects exactly as they appear
    if recipe_item:
        recipe_json = json.dumps(recipe_item, separators=(',', ':'))
    else:
        # Create a blank/minimal recipe structure
        recipe_json = json.dumps({"Name": construction_name, "Value": []}, separators=(',', ':'))
    construction_json = json.dumps(construction_item, separators=(',', ':'))

    # Serialize imports if present
    imports_section = ""
    if icon_imports:
        imports_json = json.dumps(icon_imports, separators=(',', ':'))
        imports_section = f'''
    <add_imports><![CDATA[{imports_json}]]></add_imports>'''

    # Build the XML def file
    xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<definition>
  <title>{escape_xml_value(construction_name)}</title>
  <author>Imported from game files</author>
  <description>Construction imported from DT_Constructions.json</description>
  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_ConstructionRecipes.json">
    <add_row name="{escape_xml_value(construction_name)}"><![CDATA[{recipe_json}]]></add_row>
  </mod>
  <mod file="Moria\\Content\\Tech\\Data\\Building\\DT_Constructions.json">{imports_section}
    <add_row name="{escape_xml_value(construction_name)}"><![CDATA[{construction_json}]]></add_row>
  </mod>
</definition>
'''

    # Write the file
    output_path = output_dir / f"{construction_name}.def"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    return output_path


def get_existing_constructions() -> set:
    """Get the set of construction names that already exist as .def files."""
    buildings_dir = get_buildings_dir()
    existing = set()
    if buildings_dir.exists():
        for def_file in buildings_dir.glob("*.def"):
            existing.add(def_file.stem)
    return existing


class ImportConstructionDialog(ctk.CTkToplevel):
    """Dialog for importing constructions from game JSON files."""

    def __init__(self, parent: ctk.CTk, on_import_complete: callable = None):
        super().__init__(parent)

        self.title("Import Constructions from Game Files")
        self.geometry("750x650")
        self.minsize(650, 550)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 750) // 2
        y = (self.winfo_screenheight() - 650) // 2
        self.geometry(f"750x650+{x}+{y}")

        # Callback when import completes
        self.on_import_complete = on_import_complete

        # Data storage
        self.constructions_dir: Optional[Path] = None
        self.recipes_data: dict = {}
        self.constructions_data: dict = {}
        self.all_imports: list = []
        # List of (name, has_recipe, has_construction, is_imported)
        self.available_items: list = []
        self.existing_constructions: set = get_existing_constructions()

        # Treeview data
        self.tree = None
        self.tree_items: dict = {}  # name -> item_id
        self.checked_items: set = set()  # Set of checked item names

        # Load saved directory
        saved_dir = get_constructions_json_dir()
        if saved_dir and saved_dir.exists():
            self.constructions_dir = saved_dir

        self._create_widgets()

        # If we have a saved directory, try to load it
        if self.constructions_dir:
            self.dir_var.set(str(self.constructions_dir))
            self.after(100, self._load_json_files)

    def _get_theme_color(self, color_tuple):
        """Get the appropriate color based on current appearance mode."""
        if isinstance(color_tuple, tuple) and len(color_tuple) == 2:
            mode = ctk.get_appearance_mode()
            return color_tuple[0] if mode == "Light" else color_tuple[1]
        return color_tuple

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # === DIRECTORY SELECTION ===
        dir_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        dir_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            dir_frame,
            text="JSON Directory:",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left", padx=(0, 10))

        self.dir_var = ctk.StringVar(value="")
        dir_entry = ctk.CTkEntry(
            dir_frame,
            textvariable=self.dir_var,
            width=400,
            font=ctk.CTkFont(size=18),
            placeholder_text="Select directory containing DT_Constructions.json and DT_ConstructionRecipes.json"
        )
        dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))

        browse_btn = ctk.CTkButton(
            dir_frame,
            text="Browse...",
            width=100,
            font=ctk.CTkFont(size=18),
            command=self._browse_directory
        )
        browse_btn.pack(side="right")

        # === SEARCH BAR ===
        search_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            search_frame,
            text="🔍",
            font=ctk.CTkFont(size=18)
        ).pack(side="left", padx=(0, 5))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._apply_filter())
        self.search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            width=300,
            height=36,
            placeholder_text="Search constructions...",
            font=ctk.CTkFont(size=18)
        )
        self.search_entry.pack(side="left", fill="x", expand=True)

        # Clear search button
        clear_btn = ctk.CTkButton(
            search_frame,
            text="✕",
            width=36,
            height=36,
            font=ctk.CTkFont(size=18),
            fg_color="#757575",
            hover_color="#616161",
            command=self._clear_search
        )
        clear_btn.pack(side="left", padx=(5, 0))

        # === STATUS LABEL ===
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Select a directory containing the game JSON files",
            font=ctk.CTkFont(size=18),
            text_color="gray"
        )
        self.status_label.pack(fill="x", pady=(0, 10))

        # === TREEVIEW CONTAINER ===
        tree_container = ctk.CTkFrame(main_frame)
        tree_container.pack(fill="both", expand=True, pady=(0, 10))

        # Style the Treeview
        style = ttk.Style()
        bg_color = self._get_theme_color(("#F5F5F5", "#2B2B2B"))
        fg_color = self._get_theme_color(("#1A1A1A", "#E0E0E0"))
        selected_color = self._get_theme_color(("#D0D0D0", "#404040"))
        header_bg = self._get_theme_color(("#1F6AA5", "#1F6AA5"))

        style.theme_use("clam")
        style.configure("Import.Treeview",
                        background=bg_color,
                        foreground=fg_color,
                        fieldbackground=bg_color,
                        rowheight=32,
                        font=("", 18))
        style.configure("Import.Treeview.Heading",
                        background=header_bg,
                        foreground="white",
                        font=("", 18, "bold"))
        style.map("Import.Treeview",
                  background=[("selected", selected_color)],
                  foreground=[("selected", fg_color)])

        # Create Treeview with columns
        columns = ("checked", "name")
        self.tree = ttk.Treeview(tree_container, columns=columns, show="headings",
                                  style="Import.Treeview", selectmode="extended")

        # Configure columns
        self.tree.heading("checked", text="☐", command=self._toggle_all_visible)
        self.tree.heading("name", text="Construction Name")

        self.tree.column("checked", width=40, minwidth=40, stretch=False, anchor="center")
        self.tree.column("name", width=600, minwidth=200, stretch=True, anchor="w")

        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # Configure tag colors for different statuses
        self.tree.tag_configure("available", foreground="#4CAF50")  # Green
        self.tree.tag_configure("missing_recipe", foreground="#FFC107")  # Yellow
        self.tree.tag_configure("imported", foreground="#9E9E9E")  # Gray
        self.tree.tag_configure("no_construction", foreground="#F44336")  # Red

        # Bind click event for checkbox toggling
        self.tree.bind("<Button-1>", self._on_tree_click)

        # === STATUS INFO FRAME (below treeview) ===
        status_info_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        status_info_frame.pack(fill="x", pady=(5, 5))

        # Legend/status labels
        legend_frame = ctk.CTkFrame(status_info_frame, fg_color="transparent")
        legend_frame.pack(fill="x")

        ctk.CTkLabel(
            legend_frame,
            text="Legend:",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="gray"
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            legend_frame,
            text="● Available",
            font=ctk.CTkFont(size=18),
            text_color="#4CAF50"
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(
            legend_frame,
            text="● Missing Recipe",
            font=ctk.CTkFont(size=18),
            text_color="#FFC107"
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(
            legend_frame,
            text="● Already Imported",
            font=ctk.CTkFont(size=18),
            text_color="#9E9E9E"
        ).pack(side="left", padx=(0, 15))

        ctk.CTkLabel(
            legend_frame,
            text="● Missing Construction",
            font=ctk.CTkFont(size=18),
            text_color="#F44336"
        ).pack(side="left", padx=(0, 15))

        # Count label
        self.count_label = ctk.CTkLabel(
            status_info_frame,
            text="",
            font=ctk.CTkFont(size=18),
            text_color="gray"
        )
        self.count_label.pack(fill="x", pady=(5, 0))

        # === BUTTONS ===
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x", pady=(10, 0))

        # Import button
        self.import_btn = ctk.CTkButton(
            button_frame,
            text="Import Selected",
            height=40,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color="#9C27B0",
            hover_color="#7B1FA2",
            command=self._import_selected,
            state="disabled"
        )
        self.import_btn.pack(side="right", padx=(10, 0))

        # Cancel button
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            height=40,
            font=ctk.CTkFont(size=18),
            fg_color="#757575",
            hover_color="#616161",
            command=self.destroy
        )
        cancel_btn.pack(side="right")

        # Selected count
        self.selected_label = ctk.CTkLabel(
            button_frame,
            text="0 selected",
            font=ctk.CTkFont(size=18),
            text_color="gray"
        )
        self.selected_label.pack(side="left")

    def _on_tree_click(self, event):
        """Handle click on treeview - toggle checkbox if clicking on checked column."""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)

        if not item_id:
            return

        # Column #1 is the checkbox column
        if column == "#1":
            # Get the item name
            values = self.tree.item(item_id, "values")
            if not values:
                return

            name = values[1]

            # Check if this item is selectable (has construction and not imported)
            item_data = next((item for item in self.available_items if item[0] == name), None)
            if item_data:
                _, _, has_construction, is_imported = item_data
                if has_construction and not is_imported:
                    # Toggle the checkbox
                    if name in self.checked_items:
                        self.checked_items.discard(name)
                        self.tree.item(item_id, values=("☐", name))
                    else:
                        self.checked_items.add(name)
                        self.tree.item(item_id, values=("☑", name))

                    self._update_selection_count()
                    self._update_header_checkbox()

    def _toggle_all_visible(self):
        """Toggle all visible items."""
        # Get all visible items that are selectable
        visible_selectable = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values:
                name = values[1]
                item_data = next((item for item in self.available_items if item[0] == name), None)
                if item_data:
                    _, _, has_construction, is_imported = item_data
                    if has_construction and not is_imported:
                        visible_selectable.append((item_id, name))

        if not visible_selectable:
            return

        # Check if all are selected
        all_selected = all(name in self.checked_items for _, name in visible_selectable)

        if all_selected:
            # Deselect all
            for item_id, name in visible_selectable:
                self.checked_items.discard(name)
                self.tree.item(item_id, values=("☐", name))
        else:
            # Select all
            for item_id, name in visible_selectable:
                self.checked_items.add(name)
                self.tree.item(item_id, values=("☑", name))

        self._update_selection_count()
        self._update_header_checkbox()

    def _update_header_checkbox(self):
        """Update the header checkbox text based on selection state."""
        # Get all visible selectable items
        visible_selectable = []
        for item_id in self.tree.get_children():
            values = self.tree.item(item_id, "values")
            if values:
                name = values[1]
                item_data = next((item for item in self.available_items if item[0] == name), None)
                if item_data:
                    _, _, has_construction, is_imported = item_data
                    if has_construction and not is_imported:
                        visible_selectable.append(name)

        if not visible_selectable:
            self.tree.heading("checked", text="☐")
            return

        selected_count = sum(1 for name in visible_selectable if name in self.checked_items)

        if selected_count == 0:
            self.tree.heading("checked", text="☐")
        elif selected_count == len(visible_selectable):
            self.tree.heading("checked", text="☑")
        else:
            self.tree.heading("checked", text="▣")

    def _browse_directory(self):
        """Open directory browser."""
        initial_dir = str(self.constructions_dir) if self.constructions_dir else str(Path.home())

        directory = filedialog.askdirectory(
            title="Select Directory with Construction JSON Files",
            initialdir=initial_dir
        )

        if directory:
            self.constructions_dir = Path(directory)
            self.dir_var.set(directory)
            self._load_json_files()

    def _load_json_files(self):
        """Load and parse the JSON files from the selected directory."""
        if not self.constructions_dir:
            return

        recipes_file = self.constructions_dir / "DT_ConstructionRecipes.json"
        constructions_file = self.constructions_dir / "DT_Constructions.json"

        # Check files exist
        missing = []
        if not recipes_file.exists():
            missing.append("DT_ConstructionRecipes.json")
        if not constructions_file.exists():
            missing.append("DT_Constructions.json")

        if missing:
            self.status_label.configure(
                text=f"Missing files: {', '.join(missing)}",
                text_color="#F44336"
            )
            return

        try:
            # Load recipes
            with open(recipes_file, 'r', encoding='utf-8') as f:
                recipes_data = json.load(f)
            recipes = recipes_data['Exports'][0]['Table']['Data']
            self.recipes_data = {r['Name']: r for r in recipes}

            # Load constructions
            with open(constructions_file, 'r', encoding='utf-8') as f:
                constructions_data = json.load(f)
            constructions = constructions_data['Exports'][0]['Table']['Data']
            self.constructions_data = {c['Name']: c for c in constructions}
            self.all_imports = constructions_data.get('Imports', [])

            # Refresh existing constructions list
            self.existing_constructions = get_existing_constructions()

            # Save the directory to config
            set_constructions_json_dir(self.constructions_dir)

            # Build available items list
            self._build_item_list()

            self.status_label.configure(
                text=f"Loaded {len(self.recipes_data)} recipes and {len(self.constructions_data)} constructions",
                text_color="#4CAF50"
            )

        except json.JSONDecodeError as e:
            self.status_label.configure(
                text=f"JSON parse error: {e}",
                text_color="#F44336"
            )
            logger.error("Failed to parse JSON: %s", e)
        except KeyError as e:
            self.status_label.configure(
                text=f"Invalid JSON structure: missing {e}",
                text_color="#F44336"
            )
            logger.error("Invalid JSON structure: %s", e)
        except OSError as e:
            self.status_label.configure(
                text=f"Error loading files: {e}",
                text_color="#F44336"
            )
            logger.error("Error loading JSON files: %s", e)

    def _build_item_list(self):
        """Build the list of available items from loaded data."""
        # Clear existing tree items
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        self.tree_items.clear()
        self.checked_items.clear()

        # Get all unique names from both files
        all_names = set(self.recipes_data.keys()) | set(self.constructions_data.keys())

        # Build list with detailed status
        self.available_items = []
        for name in sorted(all_names):
            has_recipe = name in self.recipes_data
            has_construction = name in self.constructions_data
            is_imported = name in self.existing_constructions
            self.available_items.append((name, has_recipe, has_construction, is_imported))

        # Populate tree
        for name, has_recipe, has_construction, is_imported in self.available_items:
            # Determine tag based on status
            if is_imported:
                tag = "imported"
            elif not has_construction:
                tag = "no_construction"
            elif not has_recipe:
                tag = "missing_recipe"
            else:
                tag = "available"

            item_id = self.tree.insert("", "end", values=("☐", name), tags=(tag,))
            self.tree_items[name] = item_id

        # Update counts
        total_count = len(self.available_items)
        with_construction = sum(1 for _, _, hc, _ in self.available_items if hc)
        missing_recipe_count = sum(1 for _, hr, hc, _ in self.available_items if not hr and hc)
        imported_count = sum(1 for _, _, hc, i in self.available_items if hc and i)
        available_count = with_construction - imported_count

        self.count_label.configure(
            text=f"{total_count} total | {with_construction} have construction | {missing_recipe_count} missing recipe | {imported_count} already imported | {available_count} available to import"
        )

        # Enable import button if we have importable items
        if available_count > 0:
            self.import_btn.configure(state="normal")

        self._update_header_checkbox()

    def _apply_filter(self):
        """Filter the item list based on search text."""
        filter_text = self.search_var.get().lower().strip()

        # Clear existing tree items
        for item_id in self.tree.get_children():
            self.tree.delete(item_id)
        self.tree_items.clear()

        # Repopulate with filtered items
        for name, has_recipe, has_construction, is_imported in self.available_items:
            # Case-insensitive search
            if filter_text and filter_text not in name.lower():
                continue

            # Determine tag based on status
            if is_imported:
                tag = "imported"
            elif not has_construction:
                tag = "no_construction"
            elif not has_recipe:
                tag = "missing_recipe"
            else:
                tag = "available"

            # Check if this item was previously checked
            checked = "☑" if name in self.checked_items else "☐"
            item_id = self.tree.insert("", "end", values=(checked, name), tags=(tag,))
            self.tree_items[name] = item_id

        # Scroll to top
        if self.tree.get_children():
            self.tree.see(self.tree.get_children()[0])

        self._update_header_checkbox()
        self._update_selection_count()

    def _clear_search(self):
        """Clear the search field."""
        self.search_var.set("")

    def _update_selection_count(self):
        """Update the selection count label."""
        selected = len(self.checked_items)
        self.selected_label.configure(text=f"{selected} selected")

    def _import_selected(self):
        """Import the selected constructions."""
        if not self.checked_items:
            messagebox.showwarning("No Selection", "Please select at least one construction to import.")
            return

        # Get output directory
        output_dir = get_buildings_dir()

        imported = 0
        skipped = 0
        errors = []

        for name in sorted(self.checked_items):
            # Check if file already exists
            output_path = output_dir / f"{name}.def"
            if output_path.exists():
                result = messagebox.askyesno(
                    "File Exists",
                    f"'{name}.def' already exists.\n\nOverwrite?"
                )
                if not result:
                    skipped += 1
                    continue

            try:
                # Get recipe (may be None if missing)
                recipe = self.recipes_data.get(name, None)
                construction = self.constructions_data[name]

                # Get icon import entries
                icon_index = get_icon_import_index(construction)
                icon_imports = get_import_entries_for_icon(icon_index, self.all_imports) if icon_index else []

                # Generate the .def file (will create blank recipe if None)
                generate_def_file(name, recipe, construction, icon_imports, output_dir)
                imported += 1

            except (OSError, KeyError, ValueError, ET.ParseError) as e:
                errors.append(f"{name}: {e}")
                logger.error("Failed to import %s: %s", name, e)

        # Show result
        message = f"Imported {imported} construction(s)."
        if skipped > 0:
            message += f"\nSkipped {skipped} file(s)."
        if errors:
            message += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors[:5])
            if len(errors) > 5:
                message += f"\n...and {len(errors) - 5} more"

        if errors:
            messagebox.showwarning("Import Complete with Errors", message)
        else:
            messagebox.showinfo("Import Complete", message)

        # Callback and close
        if imported > 0 and self.on_import_complete:
            self.on_import_complete()

        self.destroy()


def show_import_construction_dialog(parent: ctk.CTk, on_complete: callable = None):
    """Show the import construction dialog.

    Args:
        parent: The parent window
        on_complete: Callback function when import completes successfully
    """
    dialog = ImportConstructionDialog(parent, on_complete)
    dialog.focus_force()
