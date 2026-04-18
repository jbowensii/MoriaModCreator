"""Object Editor view — Advanced tab for creating and editing game DataTable rows.

Two-pane layout:
  Left pane:  Browsable list of mod-only items per category (buildings, weapons,
              armor, tools, items, flora, loot). Base-game rows are filtered out
              so only user-added objects appear.
  Right pane: Structured form that mirrors the Secrets tab field layout. Supports
              viewing/editing existing rows and creating new objects via the
              "New" button with Construction, Recipe, or Both templates.

Workflow:
  1. User selects a category tab -> left pane loads mod-only row names from
     Secrets Source JSON files (compared against base-game output/jsondata).
  2. Clicking an item loads its definition + recipe JSON rows, extracts fields
     via extract_*_fields() helpers, and renders editable structured forms.
  3. The "New" button renders blank forms with game-accurate defaults. On save,
     rows are injected into the Secrets Source JSON files via object_templates.
  4. Search/replace bar allows batch-editing property names and values.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from src.config import (
    get_appdata_dir, get_output_dir,
    get_new_secrets_jsondata_dir, get_new_secrets_raw_json_dir,
)
from src.object_templates import (
    add_string_table_entry,
    create_construction_recipe_row,
    create_construction_row,
    create_item_recipe_row,
    gen_unique_tag,
    get_existing_row_names,
    load_json,
    save_json,
)
from src.ui.buildings_view import (
    FIELD_DESCRIPTIONS,
    DEFAULT_BUILD_PROCESS,
    DEFAULT_ENABLED_STATE,
    DEFAULT_FOUNDATION_RULE,
    DEFAULT_LOCATION,
    DEFAULT_MONUMENT_TYPE,
    DEFAULT_PLACEMENT,
    DEFAULT_UNLOCK_TYPE,
    AutocompleteEntry,
    FieldTooltip,
    extract_armor_fields,
    extract_construction_fields,
    extract_flora_fields,
    extract_item_fields,
    extract_item_recipe_fields,
    extract_loot_fields,
    extract_recipe_fields,
    extract_tool_fields,
    extract_weapon_fields,
)
from src.ui.filterable_combobox import FilterableComboBox
from src.ui.shared_utils import (
    SEARCH_BOTH,
    SEARCH_MODES,
    SEARCH_PROPERTIES,
    SEARCH_VALUES,
    find_next_match,
    find_search_matches,
    substring_replace,
)
from src.ui.virtual_scroll_list import VirtualScrollList

logger = logging.getLogger(__name__)

TEMPLATE_TYPES = ["Construction", "Recipe", "Both"]

CATEGORY_FLAGS_FILE = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "templates" / "CategoryFlags.json"
)


class ObjectEditorView(ctk.CTkFrame):
    """Two-pane view for creating/editing DataTable objects."""

    def __init__(
        self,
        parent,
        on_status_message: Optional[Callable] = None,
        on_back: Optional[Callable] = None,
    ):
        super().__init__(parent, fg_color="transparent")

        self.on_status_message = on_status_message
        self.on_back = on_back

        # Active category and selected item in the left pane
        self.view_mode = "buildings"
        self.current_selected_name = None

        # Loaded mod-only items, display name lookup, and row data cache
        self.secrets_items = {}
        self.string_table = {}
        self._json_row_cache = {}

        self.construction_check_vars = {}

        # Left pane widget references (set during _create_widgets)
        self.building_list = None
        self.def_search_var = None
        self.def_search_entry = None
        self.count_label = None

        # Right pane widget references
        self.form_scroll = None
        self.template_type_var = None
        self.placeholder_label = None
        self._search_bar = None

        # Search/replace cycling state
        self._form_search_index = -1
        self._form_search_matches = []

        # Tracks raw JSON property widgets for _apply_property_edits on save
        self._property_widgets = []
        self._showing_new_form = False

        # Structured form state — form_vars maps field names to StringVar/BooleanVar,
        # material_rows tracks dynamically added/removed material row widgets
        self.form_vars = {}
        self.form_content = None
        self.material_rows: list[dict] = []
        self.sandbox_material_rows: list[dict] = []
        self.materials_frame = None
        self.sandbox_materials_frame = None
        self.cached_options: dict = {}
        self._cached_material_display: list[str] = []
        self._cached_material_raw: set[str] = set()

        self._category_flags = {}
        self._load_category_flags()

        # Populated lazily from Secrets Source JSON on first load
        self._icon_paths = []
        self._material_items = []

        logger.debug("ObjectEditorView initialized")
        self._create_widgets()
        self.after(100, self._initial_load)

    # ---- Reference data loaders (icons, materials, category flags) ----

    def _load_category_flags(self):
        try:
            with open(CATEGORY_FLAGS_FILE, "r", encoding="utf-8") as f:
                self._category_flags = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to load category flags: %s", e)

    def _load_icon_paths(self):
        """Collect icon paths from DT_Constructions Imports array."""
        if self._icon_paths:
            return  # Already loaded

        defs_path = self._get_secrets_defs_path()
        if not defs_path or not defs_path.exists():
            return

        try:
            with open(defs_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            icons = set()
            for imp in data.get("Imports", []):
                if isinstance(imp, dict):
                    obj_name = imp.get("ObjectName", "")
                    if "Icon" in obj_name or "T_UI_Build" in obj_name:
                        icons.add(obj_name)
            self._icon_paths = sorted(icons)
            logger.info("ObjectEditor: Loaded %d icon references", len(self._icon_paths))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load icon paths: %s", e)

    def _load_material_items(self):
        """Collect item names from DT_Items for the ingredient picker."""
        if self._material_items:
            return  # Already loaded

        items_path = (
            get_new_secrets_jsondata_dir() / "Moria" / "Content"
            / "Tech" / "Data" / "Items" / "DT_Items.json"
        )
        if not items_path.exists():
            return

        try:
            with open(items_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            names = set()
            for export in data.get("Exports", []):
                for row in export.get("Table", {}).get("Data", []):
                    if isinstance(row, dict) and "Name" in row:
                        names.add(row["Name"])
            self._material_items = sorted(names)
            logger.info("ObjectEditor: Loaded %d material items", len(self._material_items))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to load material items: %s", e)

    # ---- Widget creation (two-pane grid layout) ----

    def _create_widgets(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)

        self._create_left_pane()
        self._create_right_pane()

    # ---- Left pane: filter bar, category buttons, virtual scroll list ----

    def _create_left_pane(self):
        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        filter_bar = ctk.CTkFrame(list_frame, fg_color="transparent")
        filter_bar.pack(fill="x", padx=10, pady=(8, 0))

        ctk.CTkLabel(
            filter_bar, text="\U0001F50D", font=ctk.CTkFont(size=14)
        ).pack(side="left", padx=(0, 4))

        self.def_search_var = ctk.StringVar()
        self.def_search_var.trace_add("write", lambda *_: self._filter_list())
        self.def_search_entry = ctk.CTkEntry(
            filter_bar,
            textvariable=self.def_search_var,
            height=28,
            placeholder_text="Filter items...",
            font=ctk.CTkFont(size=12),
        )
        self.def_search_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        ctk.CTkButton(
            filter_bar, text="✕", width=28, height=28,
            fg_color="transparent", hover_color=("gray75", "gray25"),
            command=lambda: self.def_search_var.set(""),
        ).pack(side="left")

        btn_container = ctk.CTkFrame(list_frame, fg_color="transparent")
        btn_container.pack(fill="x", padx=10, pady=(10, 5))

        btn_row1 = ctk.CTkFrame(btn_container, fg_color="transparent")
        btn_row1.pack(fill="x")
        for col in range(3):
            btn_row1.grid_columnconfigure(col, weight=1)

        self.buildings_btn = ctk.CTkButton(
            btn_row1, text="Buildings", height=28,
            fg_color="#2196F3", hover_color="#1976D2",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("buildings"),
        )
        self.buildings_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.weapons_btn = ctk.CTkButton(
            btn_row1, text="Weapons", height=28,
            fg_color="#9C27B0", hover_color="#7B1FA2",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("weapons"),
        )
        self.weapons_btn.grid(row=0, column=1, sticky="ew", padx=2)

        self.armor_btn = ctk.CTkButton(
            btn_row1, text="Armor", height=28,
            fg_color=("#E65100", "#FF9800"), hover_color=("#BF360C", "#F57C00"),
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("armor"),
        )
        self.armor_btn.grid(row=0, column=2, sticky="ew", padx=2)

        btn_row2 = ctk.CTkFrame(btn_container, fg_color="transparent")
        btn_row2.pack(fill="x", pady=(2, 0))
        btn_row2.grid_columnconfigure(0, weight=1)
        btn_row2.grid_columnconfigure(1, weight=1)

        self.tools_btn = ctk.CTkButton(
            btn_row2, text="Tools", height=28,
            fg_color="#00897B", hover_color="#00695C",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("tools"),
        )
        self.tools_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.flora_btn = ctk.CTkButton(
            btn_row2, text="Flora", height=28,
            fg_color="#43A047", hover_color="#2E7D32",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("flora"),
        )
        self.flora_btn.grid(row=0, column=1, sticky="ew", padx=2)

        btn_row3 = ctk.CTkFrame(btn_container, fg_color="transparent")
        btn_row3.pack(fill="x", pady=(2, 0))
        btn_row3.grid_columnconfigure(0, weight=1)
        btn_row3.grid_columnconfigure(1, weight=1)

        self.loot_btn = ctk.CTkButton(
            btn_row3, text="Loot", height=28,
            fg_color="#E53935", hover_color="#C62828",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("loot"),
        )
        self.loot_btn.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.items_btn = ctk.CTkButton(
            btn_row3, text="Items", height=28,
            fg_color="#5C6BC0", hover_color="#3949AB",
            font=ctk.CTkFont(weight="bold"),
            command=lambda: self._load_category("items"),
        )
        self.items_btn.grid(row=0, column=1, sticky="ew", padx=2)

        top_row = ctk.CTkFrame(list_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=(5, 2))

        refresh_btn = ctk.CTkButton(
            top_row, text="↻", width=28, height=28,
            font=ctk.CTkFont(size=16),
            fg_color="transparent", hover_color=("gray75", "gray25"),
            command=self._on_refresh_click,
        )
        refresh_btn.pack(side="right")

        self.building_list = VirtualScrollList(
            list_frame,
            on_item_click=self._on_item_click,
            on_checkbox_toggle=self._on_checkbox_toggle,
            check_vars=self.construction_check_vars,
            fg_color="transparent",
        )
        self.building_list.pack(fill="both", expand=True, padx=10, pady=(0, 5))

        self.count_label = ctk.CTkLabel(
            list_frame, text="", font=ctk.CTkFont(size=11), text_color="gray"
        )
        self.count_label.pack(padx=10, anchor="w", pady=(0, 10))

    # ---- Right pane: search bar, header, scrollable form, footer ----

    def _create_right_pane(self):
        self.form_container = ctk.CTkFrame(self)
        self.form_container.grid(row=0, column=1, sticky="nsew")
        self.form_container.grid_rowconfigure(2, weight=1)
        self.form_container.grid_columnconfigure(0, weight=1)

        # Search/replace bar — hidden until an item is clicked
        self._search_bar = ctk.CTkFrame(self.form_container, fg_color=("gray90", "gray17"))
        self._search_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
        self._search_bar.grid_remove()

        search_row = ctk.CTkFrame(self._search_bar, fg_color="transparent")
        search_row.pack(fill="x", padx=5, pady=5)
        ctk.CTkLabel(search_row, text="\U0001F50D", width=20).pack(side="left")

        self._form_search_mode_var = ctk.StringVar(value=SEARCH_PROPERTIES)
        ctk.CTkOptionMenu(
            search_row, variable=self._form_search_mode_var,
            values=SEARCH_MODES, width=95, height=28,
            font=ctk.CTkFont(size=11),
            command=lambda _: self._on_form_search_mode_change(),
        ).pack(side="left", padx=(2, 3))

        self._form_search_var = ctk.StringVar()
        self._form_search_entry = ctk.CTkEntry(
            search_row, textvariable=self._form_search_var,
            placeholder_text="Search property...", font=ctk.CTkFont(size=12), height=28
        )
        self._form_search_entry.pack(side="left", fill="x", expand=True, padx=(2, 3))

        ctk.CTkButton(
            search_row, text="Search", width=60, height=28,
            command=self._on_form_search,
        ).pack(side="left", padx=(0, 6))

        self._form_replace_var = ctk.StringVar()
        self._form_replace_entry = ctk.CTkEntry(
            search_row, textvariable=self._form_replace_var,
            placeholder_text="Replace value...", font=ctk.CTkFont(size=12), height=28
        )
        self._form_replace_entry.pack(side="left", fill="x", expand=True, padx=(0, 3))

        ctk.CTkButton(
            search_row, text="Replace", width=65, height=28,
            command=self._on_form_replace,
        ).pack(side="left", padx=(0, 3))

        ctk.CTkButton(
            search_row, text="Replace All", width=80, height=28,
            command=self._on_form_replace_all,
        ).pack(side="left")

        header = ctk.CTkFrame(self.form_container, fg_color=("gray90", "gray17"))
        header.grid(row=1, column=0, sticky="ew", padx=0, pady=0)

        ctk.CTkLabel(
            header, text="Object Editor",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(side="left", padx=15, pady=10)

        self.template_type_var = ctk.StringVar(value="Construction")
        ctk.CTkOptionMenu(
            header,
            values=TEMPLATE_TYPES,
            variable=self.template_type_var,
            width=160,
            font=ctk.CTkFont(size=12),
            command=lambda _: self._on_template_type_change(),
        ).pack(side="left", padx=(20, 5), pady=10)

        ctk.CTkButton(
            header, text="New", width=70,
            fg_color="#4CAF50", hover_color="#388E3C",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_new_object,
        ).pack(side="left", padx=5, pady=10)

        self.form_scroll = ctk.CTkScrollableFrame(
            self.form_container, fg_color="transparent"
        )
        self.form_scroll.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        self.form_content = ctk.CTkFrame(self.form_scroll, fg_color="transparent")
        self._show_placeholder()

        footer = ctk.CTkFrame(self.form_container, fg_color=("gray90", "gray17"))
        footer.grid(row=3, column=0, sticky="ew")

        self.save_btn = ctk.CTkButton(
            footer, text="\U0001F4BE Save Object", width=140,
            fg_color="#4CAF50", hover_color="#388E3C",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_save,
        )
        self.save_btn.pack(side="right", padx=15, pady=8)

        self.delete_btn = ctk.CTkButton(
            footer, text="\U0001F5D1 Delete", width=100,
            fg_color="#E53935", hover_color="#C62828",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_delete,
        )
        self.delete_btn.pack(side="right", padx=5, pady=8)

        self.clear_btn = ctk.CTkButton(
            footer, text="Clear", width=80,
            fg_color="#757575", hover_color="#616161",
            command=self._show_placeholder,
        )
        self.clear_btn.pack(side="right", padx=5, pady=8)

    # ---- Placeholder and form reset ----

    def _show_placeholder(self):
        self._clear_form_widgets()
        self.current_selected_name = None
        self._showing_new_form = False
        if self._search_bar:
            self._search_bar.grid_remove()
        ctk.CTkLabel(
            self.form_scroll,
            text=(
                "Select a category, then click an item to view/edit its JSON.\n\n"
                "Or select a template type and click 'New' to create a new object."
            ),
            font=ctk.CTkFont(size=14),
            text_color="gray",
            justify="center",
        ).pack(expand=True, pady=100)
    def _clear_form_widgets(self):
        """Destroy all form widgets and reset state for a fresh render."""
        for widget in self.form_scroll.winfo_children():
            widget.destroy()
        self.form_content = ctk.CTkFrame(self.form_scroll, fg_color="transparent")
        self._property_widgets.clear()
        self.form_vars.clear()
        self.material_rows.clear()
        self.sandbox_material_rows.clear()

    # ---- New object creation (blank template forms) ----

    def _on_new_object(self):
        """Render a blank structured form for the selected template type."""
        self.current_selected_name = None
        self._showing_new_form = True
        template_type = self.template_type_var.get()

        if self.building_list:
            self.building_list.set_selected(None)

        self._clear_form_widgets()
        if self._search_bar:
            self._search_bar.grid_remove()

        self.form_content.pack(fill="both", expand=True)

        ctk.CTkLabel(
            self.form_content, text=f"New {template_type}",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=15, pady=(10, 2), anchor="w")
        ctk.CTkFrame(
            self.form_content, height=2, fg_color=("gray70", "gray30")
        ).pack(fill="x", padx=15, pady=(2, 10))

        if template_type == "Construction":
            self._render_new_construction_recipe()
            self._render_new_construction_definition()
        elif template_type == "Recipe":
            self._render_new_item_recipe()
        elif template_type == "Both":
            self._render_new_both()

        self._set_status(f"New {template_type} — fill in the form and click Save")

    def _on_template_type_change(self):
        """Handle dropdown change — re-render the New form if one is showing."""
        if self._showing_new_form:
            self._on_new_object()

    # ---- Item click: load JSON rows and render per-category structured form ----

    def _on_item_click(self, key: str):
        """Load definition + recipe rows for the clicked item and render the form."""
        self.current_selected_name = key
        self._showing_new_form = False
        self._clear_form_widgets()
        if self._search_bar:
            self._search_bar.grid()

        def_row, recipe_row = self._load_both_rows(key)
        if not def_row and not recipe_row:
            ctk.CTkLabel(
                self.form_scroll,
                text=f"Could not find row data for: {key}",
                font=ctk.CTkFont(size=13),
                text_color="gray",
            ).pack(pady=20, padx=15)
            return

        self.form_content.pack(fill="both", expand=True)

        display_name = self._lookup_game_name(key)
        header_text = f"{display_name}" if display_name != key else key
        if display_name != key:
            header_text += f"  ({key})"

        ctk.CTkLabel(
            self.form_content, text=header_text,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=15, pady=(10, 2), anchor="w")

        ctk.CTkFrame(
            self.form_content, height=2, fg_color=("gray70", "gray30")
        ).pack(fill="x", padx=15, pady=(2, 10))

        mode = self.view_mode or "buildings"
        has_data = False

        if mode == "buildings":
            has_data = self._show_buildings_form(recipe_row, def_row)
        elif mode == "weapons":
            has_data = self._show_weapon_form(recipe_row, def_row)
        elif mode == "armor":
            has_data = self._show_armor_form(recipe_row, def_row)
        elif mode == "tools":
            has_data = self._show_tool_form(recipe_row, def_row)
        elif mode == "items":
            has_data = self._show_items_form(recipe_row, def_row)
        elif mode == "flora":
            has_data = self._show_flora_form(def_row)
        elif mode == "loot":
            has_data = self._show_loot_form(def_row)

        if not has_data:
            ctk.CTkLabel(
                self.form_content, text="No structured data found for this item.",
                text_color="gray",
            ).pack(anchor="center", pady=40)

        self._set_status(f"Loaded: {display_name}")

    # ---- Structured form helpers (shared field creation methods) ----
    # These create labeled widgets and store their variables in self.form_vars
    # so save operations can read back all field values by key name.

    def _get_options(self, key: str, defaults: list[str] | None = None) -> list[str]:
        """Get dropdown options, merging cached values with defaults."""
        cached = self.cached_options.get(key, [])
        if defaults:
            merged = list(cached)
            for d in defaults:
                if d not in merged:
                    merged.append(d)
            return merged
        return cached if cached else ["(none)"]

    def _create_section_header(self, text: str, color="#4CAF50"):
        """Create a colored section header with separator line."""
        header_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        header_frame.pack(fill="x", pady=(20, 5), anchor="w")

        header = ctk.CTkLabel(
            header_frame,
            text=text,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color
        )
        header.pack(side="left")

        sep = ctk.CTkFrame(self.form_content, height=2, fg_color=color)
        sep.pack(fill="x", pady=(0, 10))

    def _create_subsection_header(self, text: str):
        """Create a gray subsection header."""
        header = ctk.CTkLabel(
            self.form_content,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="gray"
        )
        header.pack(fill="x", pady=(10, 5), anchor="w")

    def _create_text_field(self, name: str, value: str, width: int = 600,
                           label: str | None = None, autocomplete_key: str | None = None,
                           readonly: bool = False):
        """Create a labeled text entry field."""
        frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        frame.pack(fill="x", pady=3)

        field_label = ctk.CTkLabel(
            frame,
            text=f"{label or name}:",
            width=140,
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)

        if autocomplete_key and not readonly:
            suggestions = self.cached_options.get(autocomplete_key, [])
            if suggestions:
                entry = AutocompleteEntry(
                    frame,
                    textvariable=self.form_vars[name],
                    suggestions=suggestions,
                    width=width
                )
                entry.pack(side="left", fill="x", expand=True, padx=(10, 0))
                return

        ctk.CTkEntry(
            frame,
            textvariable=self.form_vars[name],
            width=width,
            state="disabled" if readonly else "normal",
            text_color=("gray50", "gray60") if readonly else ("gray10", "gray90")
        ).pack(side="left", fill="x", expand=True, padx=(10, 0))

    def _create_dropdown_field(self, name: str, value: str, options: list[str],
                               label: str | None = None):
        """Create a labeled dropdown field."""
        frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        frame.pack(fill="x", pady=3)

        field_label = ctk.CTkLabel(
            frame,
            text=f"{label or name}:",
            width=120,
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)
        combo = FilterableComboBox(
            frame,
            variable=self.form_vars[name],
            values=options if options else ["(none)"],
            width=350
        )
        combo.pack(side="left", padx=(10, 0))

    def _create_dropdown_field_inline(self, parent, name: str, value: str,
                                      options: list[str], label: str | None = None):
        """Create an inline dropdown field (for placing multiple per row)."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(side="left", padx=(0, 20))

        display_label = label if label else name
        field_label = ctk.CTkLabel(
            frame,
            text=f"{display_label}:",
            anchor="w",
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        field_label.pack(side="left")

        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(field_label, FIELD_DESCRIPTIONS[name])

        self.form_vars[name] = ctk.StringVar(value=value)
        combo = FilterableComboBox(
            frame,
            variable=self.form_vars[name],
            values=options if options else ["(none)"],
            width=280
        )
        combo.pack(side="left", padx=(5, 0))

    def _create_checkbox_field(self, parent, name: str, value: bool):
        """Create a checkbox field with tooltip."""
        self.form_vars[name] = ctk.BooleanVar(value=value)
        display_text = name.replace("b", "", 1) if name.startswith("b") else name

        cb = ctk.CTkCheckBox(
            parent,
            text=display_text,
            variable=self.form_vars[name],
            cursor="question_arrow" if name in FIELD_DESCRIPTIONS else ""
        )
        cb.pack(side="left", padx=(0, 15))

        if name in FIELD_DESCRIPTIONS:
            FieldTooltip(cb, FIELD_DESCRIPTIONS[name])

    def _format_material_display(self, internal_name: str) -> str:
        """Format material as 'Display Name (InternalName)'."""
        display = self._lookup_game_name(internal_name)
        if display != internal_name:
            return f"{display} ({internal_name})"
        return internal_name

    def _add_structured_material_row(self, material: str = "Item.Wood", amount: int = 1):
        """Add an editable material row with combobox and amount entry."""
        row_frame = ctk.CTkFrame(self.materials_frame, fg_color=("gray85", "gray20"))
        row_frame.pack(fill="x", pady=2)

        material_options = list(self._cached_material_display)
        if material and material not in self._cached_material_raw:
            material_options.insert(0, self._format_material_display(material))

        mat_var = ctk.StringVar(value=self._format_material_display(material))
        mat_combo = FilterableComboBox(
            row_frame, variable=mat_var, values=material_options, width=350
        )
        mat_combo.pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(row_frame, text="x", width=20).pack(side="left")

        amount_var = ctk.StringVar(value=str(amount))
        ctk.CTkEntry(
            row_frame, textvariable=amount_var, width=60, placeholder_text="qty"
        ).pack(side="left", padx=5)

        remove_btn = ctk.CTkButton(
            row_frame, text="\u2715", width=28, height=28,
            fg_color="#f44336", hover_color="#d32f2f",
            command=lambda rf=row_frame: self._remove_structured_material_row(rf)
        )
        remove_btn.pack(side="right", padx=5, pady=5)

        self.material_rows.append({
            "frame": row_frame,
            "material_var": mat_var,
            "amount_var": amount_var
        })

    def _add_new_structured_material_row(self):
        """Add a new empty material row."""
        if self.materials_frame and not self.materials_frame.winfo_ismapped():
            self.materials_frame.pack(fill="x", pady=5)
        self._add_structured_material_row("Item.Wood", 1)

    def _remove_structured_material_row(self, row_frame):
        """Remove a material row."""
        row_frame.destroy()
        for row in self.material_rows:
            if row.get("frame") == row_frame:
                row["removed"] = True
                break

    def _add_sandbox_material_row(self, material: str = "Item.Wood", amount: int = 1):
        """Add an editable sandbox material row."""
        row_frame = ctk.CTkFrame(self.sandbox_materials_frame, fg_color=("gray85", "gray20"))
        row_frame.pack(fill="x", pady=2)

        material_options = list(self._cached_material_display)
        if material and material not in self._cached_material_raw:
            material_options.insert(0, self._format_material_display(material))

        mat_var = ctk.StringVar(value=self._format_material_display(material))
        FilterableComboBox(
            row_frame, variable=mat_var, values=material_options, width=350
        ).pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(row_frame, text="x", width=20).pack(side="left")

        amount_var = ctk.StringVar(value=str(amount))
        ctk.CTkEntry(
            row_frame, textvariable=amount_var, width=60, placeholder_text="qty"
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            row_frame, text="\u2715", width=28, height=28,
            fg_color="#f44336", hover_color="#d32f2f",
            command=lambda rf=row_frame: self._remove_sandbox_material_row(rf)
        ).pack(side="right", padx=5, pady=5)

        self.sandbox_material_rows.append({
            "frame": row_frame,
            "material_var": mat_var,
            "amount_var": amount_var
        })

    def _add_new_sandbox_material_row(self):
        if self.sandbox_materials_frame and not self.sandbox_materials_frame.winfo_ismapped():
            self.sandbox_materials_frame.pack(fill="x", pady=(0, 5))
        self._add_sandbox_material_row("Item.Wood", 1)

    def _remove_sandbox_material_row(self, row_frame):
        row_frame.destroy()
        for row in self.sandbox_material_rows:
            if row.get("frame") == row_frame:
                row["removed"] = True
                break

    def _render_materials_section(self, recipe):
        """Render required materials with add/remove buttons."""
        self._create_subsection_header("Required Materials")
        ctk.CTkButton(
            self.form_content, text="+ Add Material", width=120, height=28,
            fg_color="#4CAF50", hover_color="#45a049",
            command=self._add_new_structured_material_row
        ).pack(anchor="w", pady=(0, 5))

        self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        if recipe["Materials"]:
            self.materials_frame.pack(fill="x", pady=5)
            for mat in recipe["Materials"]:
                self._add_structured_material_row(mat["Material"], mat["Amount"])

        self._create_text_field(
            "DefaultRequiredConstructions",
            ", ".join(recipe.get("DefaultRequiredConstructions", [])),
            label="Required Constructions", autocomplete_key="Constructions"
        )

    def _render_unlocks_section(self, recipe):
        """Render default unlocks subsection."""
        self._create_subsection_header("Default Unlocks")
        self._create_dropdown_field(
            "DefaultUnlocks_UnlockType", recipe["DefaultUnlocks_UnlockType"],
            self._get_options("Enum_EMorRecipeUnlockType", DEFAULT_UNLOCK_TYPE),
            label="Unlock Type"
        )
        self._create_text_field(
            "DefaultUnlocks_NumFragments", str(recipe["DefaultUnlocks_NumFragments"]),
            label="Num Fragments", width=200
        )
        self._create_text_field(
            "DefaultUnlocks_RequiredItems",
            ", ".join(recipe["DefaultUnlocks_RequiredItems"]),
            label="Required Items", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "DefaultUnlocks_RequiredConstructions",
            ", ".join(recipe["DefaultUnlocks_RequiredConstructions"]),
            label="Required Constructions", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "DefaultUnlocks_RequiredFragments",
            ", ".join(recipe["DefaultUnlocks_RequiredFragments"]),
            label="Required Fragments", autocomplete_key="AllValues"
        )

    def _render_sandbox_section(self, recipe):
        """Render sandbox overrides subsection."""
        self._create_subsection_header("Sandbox Overrides")
        sandbox_bool_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        sandbox_bool_frame.pack(fill="x", pady=4)
        self._create_checkbox_field(sandbox_bool_frame, "bHasSandboxRequirementsOverride",
                                    recipe["bHasSandboxRequirementsOverride"])
        self._create_checkbox_field(sandbox_bool_frame, "bHasSandboxUnlockOverride",
                                    recipe["bHasSandboxUnlockOverride"])

        self._create_dropdown_field(
            "SandboxUnlocks_UnlockType", recipe["SandboxUnlocks_UnlockType"],
            self._get_options("Enum_EMorRecipeUnlockType", DEFAULT_UNLOCK_TYPE),
            label="Sandbox Unlock Type"
        )
        self._create_text_field(
            "SandboxUnlocks_NumFragments", str(recipe["SandboxUnlocks_NumFragments"]),
            label="Sandbox Num Fragments", width=200
        )
        self._create_text_field(
            "SandboxUnlocks_RequiredItems",
            ", ".join(recipe["SandboxUnlocks_RequiredItems"]),
            label="Sandbox Required Items", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "SandboxUnlocks_RequiredConstructions",
            ", ".join(recipe.get("SandboxUnlocks_RequiredConstructions", [])),
            label="Sandbox Req. Constructions", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "SandboxUnlocks_RequiredFragments",
            ", ".join(recipe.get("SandboxUnlocks_RequiredFragments", [])),
            label="Sandbox Req. Fragments", autocomplete_key="AllValues"
        )

        self._create_subsection_header("Sandbox Required Materials")
        ctk.CTkButton(
            self.form_content, text="+ Add Sandbox Material", width=160, height=28,
            fg_color="#4CAF50", hover_color="#45a049",
            command=self._add_new_sandbox_material_row
        ).pack(anchor="w", pady=(0, 5))

        self.sandbox_materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        sandbox_mats = recipe.get("SandboxRequiredMaterials", [])
        if sandbox_mats:
            self.sandbox_materials_frame.pack(fill="x", pady=(0, 5))
            for mat in sandbox_mats:
                self._add_sandbox_material_row(mat["Material"], mat["Amount"])

        self._create_text_field(
            "SandboxRequiredConstructions",
            ", ".join(recipe.get("SandboxRequiredConstructions", [])),
            label="Sandbox Req. Constructions", autocomplete_key="Constructions"
        )

    def _render_construction_definition(self, construction):
        """Render construction definition section."""
        self._create_section_header("Construction Definition", "#4CAF50")

        self._create_text_field("Construction_Name", construction["Name"], label="Row Name")
        self._create_text_field("DisplayName", construction["DisplayName"], label="Display Name")
        self._create_text_field("Description", construction["Description"])
        self._create_text_field("Actor", construction["Actor"],
                                label="Actor Path", autocomplete_key="Actors")
        icon_val = construction.get("Icon")
        self._create_text_field(
            "Icon", str(icon_val) if icon_val is not None else "",
            label="Icon (Import Index)", readonly=True
        )
        self._create_dropdown_field(
            "Tags",
            construction["Tags"][0] if construction["Tags"] else "",
            self._get_options("Tags", []),
            label="Category Tag"
        )
        self._create_text_field(
            "BackwardCompatibilityActors",
            ", ".join(construction["BackwardCompatibilityActors"]),
            label="Backward Compat Actors", autocomplete_key="Actors"
        )
        self._create_dropdown_field(
            "Construction_EnabledState", construction["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Construction Enabled State"
        )

    def _render_item_recipe_section(self, recipe_json):
        """Render item recipe section (shared by weapons, armor, tools, items)."""
        recipe = extract_item_recipe_fields(recipe_json)

        self._create_section_header("Item Recipe", ("#E65100", "#FF9800"))

        self._create_text_field("Name", recipe["Name"], label="Row Name")
        self._create_text_field(
            "ResultItemHandle", recipe["ResultItemHandle"],
            label="Result Item", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "ResultItemCount", str(recipe.get("ResultItemCount", 1)),
            label="Result Count", width=200
        )
        self._create_text_field(
            "CraftTimeSeconds", str(recipe.get("CraftTimeSeconds", 0.0)),
            label="Craft Time (s)", width=200
        )

        bool_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_frame.pack(fill="x", pady=4)
        self._create_checkbox_field(bool_frame, "bCanBePinned", recipe.get("bCanBePinned", True))
        self._create_checkbox_field(bool_frame, "bNpcOnlyRecipe", recipe.get("bNpcOnlyRecipe", False))

        self._render_materials_section(recipe)
        self._render_unlocks_section(recipe)
        self._render_sandbox_section(recipe)

        self._create_dropdown_field(
            "Recipe_EnabledState", recipe["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Recipe Enabled State"
        )

    def _render_common_item_fields(self, fields, section_title, section_color):
        """Render common item definition fields (display, inventory, tags)."""
        self._create_section_header(section_title, section_color)

        self._create_text_field("Def_Name", fields["Name"], label="Row Name", readonly=True)
        self._create_text_field("DisplayName", fields["DisplayName"], label="Display Name")
        self._create_text_field("Description", fields.get("Description", ""))
        self._create_text_field("Actor", fields.get("Actor", ""),
                                label="Actor Path", autocomplete_key="Actors")
        if "Icon" in fields:
            self._create_text_field("Icon", fields["Icon"], label="Icon Path", readonly=True)

        tags = fields.get("Tags", [])
        self._create_dropdown_field(
            "Tags", tags[0] if tags else "",
            self._get_options("Tags", []), label="Category Tag"
        )

        self._create_subsection_header("Inventory")
        self._create_dropdown_field(
            "Portability", fields.get("Portability", "EItemPortability::Storable"),
            ["EItemPortability::Storable", "EItemPortability::NotStorable",
             "EItemPortability::Holdable"], label="Portability"
        )
        inv_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        inv_row.pack(fill="x", pady=3)
        for col in range(3):
            inv_row.grid_columnconfigure(col, weight=1)
        for i, (key, label) in enumerate([
            ("MaxStackSize", "Max Stack"), ("SlotSize", "Slot Size"),
            ("BaseTradeValue", "Trade Value")
        ]):
            frame = ctk.CTkFrame(inv_row, fg_color="transparent")
            frame.grid(row=0, column=i, sticky="ew", padx=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         width=80, anchor="w").pack(side="left")
            var = ctk.StringVar(value=str(fields.get(key, 0)))
            self.form_vars[key] = var
            ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

        self._create_dropdown_field(
            "Def_EnabledState", fields["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Definition Enabled State"
        )

    # ---- Per-category form renderers ----
    # Each _show_*_form method extracts fields from raw JSON using the
    # extract_*_fields() helpers from buildings_view, then renders the
    # appropriate recipe + definition sections for that category.

    def _show_buildings_form(self, recipe_json, construction_json):
        """Render buildings form (construction recipe + construction definition)."""
        has_data = False

        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            recipe = extract_recipe_fields(recipe_json)

            self._create_section_header("Construction Recipe", ("#E65100", "#FF9800"))

            self._create_text_field("Name", recipe["Name"], label="Row Name")
            self._create_text_field(
                "ResultConstructionHandle", recipe["ResultConstructionHandle"],
                label="Result Construction", autocomplete_key="ResultConstructions"
            )

            row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row1.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row1, "BuildProcess", recipe["BuildProcess"],
                self._get_options("Enum_BuildProcess", DEFAULT_BUILD_PROCESS)
            )
            self._create_dropdown_field_inline(
                row1, "PlacementType", recipe["PlacementType"],
                self._get_options("Enum_PlacementType", DEFAULT_PLACEMENT)
            )

            row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row2.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row2, "LocationRequirement", recipe["LocationRequirement"],
                self._get_options("Enum_LocationRequirement", DEFAULT_LOCATION)
            )
            self._create_dropdown_field_inline(
                row2, "FoundationRule", recipe["FoundationRule"],
                self._get_options("Enum_FoundationRule", DEFAULT_FOUNDATION_RULE)
            )

            row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            row3.pack(fill="x", pady=3)
            self._create_dropdown_field_inline(
                row3, "MonumentType", recipe["MonumentType"],
                self._get_options("Enum_MonumentType", DEFAULT_MONUMENT_TYPE)
            )

            self._create_subsection_header("Placement Options")
            bool_row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row1.pack(fill="x", pady=4)
            for bf in ["bOnWall", "bOnFloor", "bPlaceOnWater", "bOverrideRotation"]:
                self._create_checkbox_field(bool_row1, bf, recipe[bf])

            bool_row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row2.pack(fill="x", pady=4)
            for bf in ["bAllowRefunds", "bAutoFoundation", "bInheritAutoFoundationStability", "bOnlyOnVoxel"]:
                self._create_checkbox_field(bool_row2, bf, recipe[bf])

            bool_row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            bool_row3.pack(fill="x", pady=4)
            for bf in ["bIsBlockedByNearbySettlementStones", "bIsBlockedByNearbyRavenConstructions"]:
                self._create_checkbox_field(bool_row3, bf, recipe[bf])

            self._create_subsection_header("Numeric Properties")
            self._create_text_field(
                "MaxAllowedPenetrationDepth", str(recipe["MaxAllowedPenetrationDepth"]),
                label="Max Penetration Depth", width=200
            )
            self._create_text_field(
                "RequireNearbyRadius", str(recipe["RequireNearbyRadius"]),
                label="Require Nearby Radius", width=200
            )
            self._create_text_field(
                "CameraStateOverridePriority", str(recipe["CameraStateOverridePriority"]),
                label="Camera Priority", width=200
            )

            self._render_materials_section(recipe)
            self._render_unlocks_section(recipe)
            self._render_sandbox_section(recipe)

            self._create_dropdown_field(
                "Recipe_EnabledState", recipe["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Recipe Enabled State"
            )

        if construction_json and isinstance(construction_json, dict):
            has_data = True
            construction = extract_construction_fields(construction_json)
            self._render_construction_definition(construction)

        return has_data

    def _show_weapon_form(self, recipe_json, definition_json):
        """Render weapon form (item recipe + weapon definition)."""
        has_data = False

        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            self._render_item_recipe_section(recipe_json)

        if definition_json and isinstance(definition_json, dict):
            has_data = True
            w = extract_weapon_fields(definition_json)

            self._create_section_header("Weapon Definition", "#9C27B0")
            self._create_text_field("Def_Name", w["Name"], label="Row Name", readonly=True)

            self._create_subsection_header("Combat Stats")
            self._create_text_field("DamageType", w["DamageType"], label="Damage Type",
                                    autocomplete_key="DamageTypes")
            stats_row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            stats_row1.pack(fill="x", pady=3)
            for col in range(4):
                stats_row1.grid_columnconfigure(col, weight=1)
            for i, (key, label) in enumerate([
                ("Damage", "Damage"), ("Speed", "Speed"),
                ("Durability", "Durability"), ("Tier", "Tier")
            ]):
                frame = ctk.CTkFrame(stats_row1, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                             width=70, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(w[key]))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=70).pack(side="left", padx=2)

            stats_row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            stats_row2.pack(fill="x", pady=3)
            for col in range(4):
                stats_row2.grid_columnconfigure(col, weight=1)
            for i, (key, label) in enumerate([
                ("ArmorPenetration", "Armor Pen"),
                ("StaminaCost", "Stamina Cost"),
                ("EnergyCost", "Energy Cost"),
                ("BlockDamageReduction", "Block Reduction")
            ]):
                frame = ctk.CTkFrame(stats_row2, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                             width=80, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(w[key]))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=70).pack(side="left", padx=2)

            if w["InitialRepairCost"]:
                self._create_subsection_header("Repair Cost")
                self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
                self.materials_frame.pack(fill="x", pady=5)
                for mat in w["InitialRepairCost"]:
                    self._add_structured_material_row(mat["Material"], mat["Amount"])

            self._create_subsection_header("Display")
            self._create_text_field("DisplayName", w["DisplayName"], label="Display Name")
            self._create_text_field("Description", w["Description"])
            self._create_text_field("Actor", w["Actor"],
                                    label="Actor Path", autocomplete_key="Actors")
            self._create_text_field("Icon", w["Icon"], label="Icon Path", readonly=True)

            tags = w.get("Tags", [])
            self._create_dropdown_field(
                "Tags", tags[0] if tags else "",
                self._get_options("Tags", []), label="Category Tag"
            )

            self._create_subsection_header("Inventory")
            self._create_dropdown_field(
                "Portability", w.get("Portability", "EItemPortability::Storable"),
                ["EItemPortability::Storable", "EItemPortability::NotStorable",
                 "EItemPortability::Holdable"], label="Portability"
            )
            inv_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            inv_row.pack(fill="x", pady=3)
            for col in range(3):
                inv_row.grid_columnconfigure(col, weight=1)
            for i, (key, lbl) in enumerate([
                ("MaxStackSize", "Max Stack"), ("SlotSize", "Slot Size"),
                ("BaseTradeValue", "Trade Value")
            ]):
                frame = ctk.CTkFrame(inv_row, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=lbl, font=ctk.CTkFont(size=11),
                             width=80, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(w.get(key, 0)))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            self._create_dropdown_field(
                "Def_EnabledState", w["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Definition Enabled State"
            )

        return has_data

    def _show_armor_form(self, recipe_json, definition_json):
        """Render armor form (item recipe + armor definition)."""
        has_data = False

        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            self._render_item_recipe_section(recipe_json)

        if definition_json and isinstance(definition_json, dict):
            has_data = True
            a = extract_armor_fields(definition_json)

            self._create_section_header("Armor Definition", ("#E65100", "#FF9800"))
            self._create_text_field("Def_Name", a["Name"], label="Row Name", readonly=True)

            self._create_subsection_header("Defense Stats")
            stats_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            stats_row.pack(fill="x", pady=3)
            for col in range(3):
                stats_row.grid_columnconfigure(col, weight=1)
            for i, (key, label) in enumerate([
                ("Durability", "Durability"),
                ("DamageReduction", "Damage Reduction"),
                ("DamageProtection", "Damage Protection"),
            ]):
                frame = ctk.CTkFrame(stats_row, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                             width=100, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(a[key]))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            if a["InitialRepairCost"]:
                self._create_subsection_header("Repair Cost")
                self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
                self.materials_frame.pack(fill="x", pady=5)
                for mat in a["InitialRepairCost"]:
                    self._add_structured_material_row(mat["Material"], mat["Amount"])

            self._create_subsection_header("Display")
            self._create_text_field("DisplayName", a["DisplayName"], label="Display Name")
            self._create_text_field("Description", a["Description"])
            self._create_text_field("Actor", a["Actor"],
                                    label="Actor Path", autocomplete_key="Actors")
            self._create_text_field("Icon", a["Icon"], label="Icon Path", readonly=True)

            tags = a.get("Tags", [])
            self._create_dropdown_field(
                "Tags", tags[0] if tags else "",
                self._get_options("Tags", []), label="Category Tag"
            )

            self._create_subsection_header("Inventory")
            self._create_dropdown_field(
                "Portability", a.get("Portability", "EItemPortability::Storable"),
                ["EItemPortability::Storable", "EItemPortability::NotStorable",
                 "EItemPortability::Holdable"], label="Portability"
            )
            inv_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            inv_row.pack(fill="x", pady=3)
            for col in range(3):
                inv_row.grid_columnconfigure(col, weight=1)
            for i, (key, lbl) in enumerate([
                ("MaxStackSize", "Max Stack"), ("SlotSize", "Slot Size"),
                ("BaseTradeValue", "Trade Value")
            ]):
                frame = ctk.CTkFrame(inv_row, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=lbl, font=ctk.CTkFont(size=11),
                             width=80, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(a.get(key, 0)))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            self._create_dropdown_field(
                "Def_EnabledState", a["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Definition Enabled State"
            )

        return has_data

    def _show_tool_form(self, recipe_json, definition_json):
        """Render tool form (item recipe + tool definition)."""
        has_data = False

        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            self._render_item_recipe_section(recipe_json)

        if definition_json and isinstance(definition_json, dict):
            has_data = True
            t = extract_tool_fields(definition_json)

            self._create_section_header("Tool Definition", "#00897B")
            self._create_text_field("Def_Name", t["Name"], label="Row Name", readonly=True)

            self._create_subsection_header("Tool Stats")
            stats_row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            stats_row1.pack(fill="x", pady=3)
            for col in range(3):
                stats_row1.grid_columnconfigure(col, weight=1)
            for i, (key, label) in enumerate([
                ("Durability", "Durability"),
                ("DurabilityDecayWhileEquipped", "Durability Decay"),
                ("CarveHits", "Carve Hits"),
            ]):
                frame = ctk.CTkFrame(stats_row1, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                             width=90, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(t[key]))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            stats_row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
            stats_row2.pack(fill="x", pady=3)
            for col in range(3):
                stats_row2.grid_columnconfigure(col, weight=1)
            for i, (key, label) in enumerate([
                ("StaminaCost", "Stamina Cost"),
                ("EnergyCost", "Energy Cost"),
                ("NpcMiningRate", "NPC Mining Rate"),
            ]):
                frame = ctk.CTkFrame(stats_row2, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                             width=90, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(t[key]))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            if t["InitialRepairCost"]:
                self._create_subsection_header("Repair Cost")
                self.materials_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
                self.materials_frame.pack(fill="x", pady=5)
                for mat in t["InitialRepairCost"]:
                    self._add_structured_material_row(mat["Material"], mat["Amount"])

            self._create_subsection_header("Display")
            self._create_text_field("DisplayName", t["DisplayName"], label="Display Name")
            self._create_text_field("Description", t["Description"])
            self._create_text_field("Actor", t["Actor"],
                                    label="Actor Path", autocomplete_key="Actors")
            self._create_text_field("Icon", t["Icon"], label="Icon Path", readonly=True)

            tags = t.get("Tags", [])
            self._create_dropdown_field(
                "Tags", tags[0] if tags else "",
                self._get_options("Tags", []), label="Category Tag"
            )

            self._create_subsection_header("Inventory")
            self._create_dropdown_field(
                "Portability", t.get("Portability", "EItemPortability::Storable"),
                ["EItemPortability::Storable", "EItemPortability::NotStorable",
                 "EItemPortability::Holdable"], label="Portability"
            )
            inv_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
            inv_row.pack(fill="x", pady=3)
            for col in range(3):
                inv_row.grid_columnconfigure(col, weight=1)
            for i, (key, lbl) in enumerate([
                ("MaxStackSize", "Max Stack"), ("SlotSize", "Slot Size"),
                ("BaseTradeValue", "Trade Value")
            ]):
                frame = ctk.CTkFrame(inv_row, fg_color="transparent")
                frame.grid(row=0, column=i, sticky="ew", padx=2)
                ctk.CTkLabel(frame, text=lbl, font=ctk.CTkFont(size=11),
                             width=80, anchor="w").pack(side="left")
                var = ctk.StringVar(value=str(t.get(key, 0)))
                self.form_vars[key] = var
                ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

            self._create_dropdown_field(
                "Def_EnabledState", t["EnabledState"],
                DEFAULT_ENABLED_STATE, label="Definition Enabled State"
            )

        return has_data

    def _show_items_form(self, recipe_json, definition_json):
        """Render generic items form (item recipe + item definition)."""
        has_data = False

        if recipe_json and isinstance(recipe_json, dict):
            has_data = True
            self._render_item_recipe_section(recipe_json)

        if definition_json and isinstance(definition_json, dict):
            has_data = True
            item = extract_item_fields(definition_json)
            self._render_common_item_fields(item, "Item Definition", "#5C6BC0")

        return has_data

    def _show_flora_form(self, definition_json):
        """Render flora form (no recipe)."""
        if not definition_json or not isinstance(definition_json, dict):
            return False

        f = extract_flora_fields(definition_json)

        self._create_section_header("Flora Definition", "#43A047")
        self._create_text_field("Def_Name", f["Name"], label="Row Name", readonly=True)
        self._create_text_field("DisplayName", f["DisplayName"], label="Display Name")

        self._create_subsection_header("Item References")
        self._create_text_field("ItemRowHandle", f["ItemRowHandle"],
                                label="Item Row Handle", autocomplete_key="AllValues")
        self._create_text_field("OverrideItemDropHandle", f["OverrideItemDropHandle"],
                                label="Override Drop Handle", autocomplete_key="AllValues")

        self._create_subsection_header("Drop Amounts")
        drop_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        drop_row.pack(fill="x", pady=3)
        for col in range(2):
            drop_row.grid_columnconfigure(col, weight=1)
        for i, (key, label) in enumerate([("MinCount", "Min Count"), ("MaxCount", "Max Count")]):
            frame = ctk.CTkFrame(drop_row, fg_color="transparent")
            frame.grid(row=0, column=i, sticky="ew", padx=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         width=80, anchor="w").pack(side="left")
            var = ctk.StringVar(value=str(f[key]))
            self.form_vars[key] = var
            ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

        self._create_subsection_header("Growth Timing")
        for key, label in [
            ("NumToGrowPerCycle", "Grow Per Cycle"),
            ("RegrowthSleepCount", "Regrowth Sleep Count"),
            ("TimeUntilGrowingStage", "Time Until Growing"),
            ("TimeUntilReadyStage", "Time Until Ready"),
            ("TimeUntilSpoiledStage", "Time Until Spoiled"),
            ("MinVariableGrowthTime", "Min Variable Growth"),
            ("MaxVariableGrowthTime", "Max Variable Growth"),
        ]:
            self._create_text_field(key, str(f[key]), label=label, width=200)

        self._create_subsection_header("Growth Properties")
        bool_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_row.pack(fill="x", pady=4)
        for bf in ["bPrefersInShade", "bCanSpoil", "IsPlantable", "IsFungus"]:
            self._create_checkbox_field(bool_row, bf, f.get(bf, False))

        self._create_text_field("MinimumFarmingLight", str(f["MinimumFarmingLight"]),
                                label="Min Farming Light", width=200)

        enum_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        enum_row.pack(fill="x", pady=3)
        self._create_dropdown_field_inline(
            enum_row, "FloraType", f["FloraType"],
            ["EMorFarmingFloraType::Flora", "EMorFarmingFloraType::Fungus",
             "EMorFarmingFloraType::Tree", "EMorFarmingFloraType::Crop"]
        )
        self._create_dropdown_field_inline(
            enum_row, "GrowthRate", f["GrowthRate"],
            ["EMorFarmingFloraGrowthRate::None", "EMorFarmingFloraGrowthRate::Slow",
             "EMorFarmingFloraGrowthRate::Medium", "EMorFarmingFloraGrowthRate::Fast"]
        )

        self._create_subsection_header("Visual")
        scale_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        scale_row.pack(fill="x", pady=3)
        for col in range(2):
            scale_row.grid_columnconfigure(col, weight=1)
        for i, (key, label) in enumerate([
            ("MinRandomScale", "Min Scale"), ("MaxRandomScale", "Max Scale")
        ]):
            frame = ctk.CTkFrame(scale_row, fg_color="transparent")
            frame.grid(row=0, column=i, sticky="ew", padx=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         width=80, anchor="w").pack(side="left")
            var = ctk.StringVar(value=str(f[key]))
            self.form_vars[key] = var
            ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

        self._create_text_field("ReceptacleActorToSpawn", f["ReceptacleActorToSpawn"],
                                label="Receptacle Actor", autocomplete_key="Actors")

        self._create_dropdown_field(
            "Def_EnabledState", f["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Enabled State"
        )

        return True

    def _show_loot_form(self, definition_json):
        """Render loot form (no recipe, simple fields)."""
        if not definition_json or not isinstance(definition_json, dict):
            return False

        lt = extract_loot_fields(definition_json)

        self._create_section_header("Loot Definition", "#E53935")
        self._create_text_field("Def_Name", lt["Name"], label="Row Name", readonly=True)

        self._create_text_field(
            "RequiredTags", ", ".join(lt["RequiredTags"]),
            label="Required Tags", autocomplete_key="LootTags"
        )
        self._create_text_field(
            "ItemHandle", lt["ItemHandle"],
            label="Item Handle", autocomplete_key="AllValues"
        )

        self._create_subsection_header("Drop Settings")
        self._create_text_field("DropChance", str(lt["DropChance"]),
                                label="Drop Chance (0-1)", width=200)

        qty_row = ctk.CTkFrame(self.form_content, fg_color="transparent")
        qty_row.pack(fill="x", pady=3)
        for col in range(2):
            qty_row.grid_columnconfigure(col, weight=1)
        for i, (key, label) in enumerate([
            ("MinQuantity", "Min Quantity"), ("MaxQuantity", "Max Quantity")
        ]):
            frame = ctk.CTkFrame(qty_row, fg_color="transparent")
            frame.grid(row=0, column=i, sticky="ew", padx=2)
            ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11),
                         width=80, anchor="w").pack(side="left")
            var = ctk.StringVar(value=str(lt[key]))
            self.form_vars[key] = var
            ctk.CTkEntry(frame, textvariable=var, width=80).pack(side="left", padx=2)

        self._create_dropdown_field(
            "Def_EnabledState", lt["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Enabled State"
        )

        return True

    # ---- Row data loading with cache ----

    def _load_row_data(self, row_name: str) -> dict | None:
        """Load a specific row from the secrets JSON files (first match)."""
        for path in [self._get_secrets_defs_path(), self._get_secrets_recipes_path()]:
            row = self._get_cached_row(path, row_name)
            if row:
                return row
        return None

    def _load_both_rows(self, row_name: str) -> tuple[dict | None, dict | None]:
        """Load both the definition row and recipe row for a given name."""
        def_row = self._get_cached_row(self._get_secrets_defs_path(), row_name)
        recipe_row = self._get_cached_row(self._get_secrets_recipes_path(), row_name)
        return def_row, recipe_row

    def _get_cached_row(self, path, row_name: str) -> dict | None:
        """Get a row by name from a JSON file, using cache."""
        if not path or not path.exists():
            return None

        cache_key = str(path)
        if cache_key not in self._json_row_cache:
            try:
                data = load_json(path)
                rows = {}
                for export in data.get("Exports", []):
                    table = export.get("Table", {})
                    for row in table.get("Data", []):
                        if isinstance(row, dict) and "Name" in row:
                            rows[row["Name"]] = row
                self._json_row_cache[cache_key] = rows
            except (json.JSONDecodeError, OSError):
                self._json_row_cache[cache_key] = {}

        return self._json_row_cache[cache_key].get(row_name)

    # ---- New-object template renderers ----
    # These render blank forms with game-accurate defaults. The field keys
    # match what extract_*_fields() returns so the save workflow is identical.

    def _render_new_construction_recipe(self, row_name_var=None):
        """Render blank construction recipe form with default values."""
        recipe = {
            "Name": "", "ResultConstructionHandle": "",
            "BuildProcess": "EBuildProcess::DualMode",
            "PlacementType": "EPlacementType::FreePlacement",
            "LocationRequirement": "EConstructionLocation::Base",
            "FoundationRule": "EFoundationRule::Never",
            "MonumentType": "EMonumentType::None",
            "bOnWall": False, "bOnFloor": True, "bPlaceOnWater": False,
            "bOverrideRotation": False, "bAllowRefunds": True,
            "bAutoFoundation": False, "bInheritAutoFoundationStability": False,
            "bOnlyOnVoxel": False, "bIsBlockedByNearbySettlementStones": False,
            "bIsBlockedByNearbyRavenConstructions": False,
            "MaxAllowedPenetrationDepth": -1.0, "RequireNearbyRadius": 300.0,
            "CameraStateOverridePriority": 5,
            "Materials": [], "DefaultRequiredConstructions": [],
            "DefaultUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
            "DefaultUnlocks_NumFragments": 1,
            "DefaultUnlocks_RequiredItems": [],
            "DefaultUnlocks_RequiredConstructions": [],
            "DefaultUnlocks_RequiredFragments": [],
            "bHasSandboxRequirementsOverride": False,
            "bHasSandboxUnlockOverride": False,
            "SandboxUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
            "SandboxUnlocks_NumFragments": 1,
            "SandboxUnlocks_RequiredItems": [],
            "SandboxUnlocks_RequiredConstructions": [],
            "SandboxUnlocks_RequiredFragments": [],
            "SandboxRequiredMaterials": [],
            "SandboxRequiredConstructions": [],
            "EnabledState": "ERowEnabledState::Live",
        }

        self._create_section_header("Construction Recipe", ("#E65100", "#FF9800"))

        if row_name_var is not None:
            self.form_vars["Name"] = row_name_var
        else:
            self._create_text_field("Name", recipe["Name"], label="Row Name")

        self._create_text_field(
            "ResultConstructionHandle", recipe["ResultConstructionHandle"],
            label="Result Construction", autocomplete_key="ResultConstructions"
        )

        row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        row1.pack(fill="x", pady=3)
        self._create_dropdown_field_inline(
            row1, "BuildProcess", recipe["BuildProcess"],
            self._get_options("Enum_BuildProcess", DEFAULT_BUILD_PROCESS)
        )
        self._create_dropdown_field_inline(
            row1, "PlacementType", recipe["PlacementType"],
            self._get_options("Enum_PlacementType", DEFAULT_PLACEMENT)
        )

        row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        row2.pack(fill="x", pady=3)
        self._create_dropdown_field_inline(
            row2, "LocationRequirement", recipe["LocationRequirement"],
            self._get_options("Enum_LocationRequirement", DEFAULT_LOCATION)
        )
        self._create_dropdown_field_inline(
            row2, "FoundationRule", recipe["FoundationRule"],
            self._get_options("Enum_FoundationRule", DEFAULT_FOUNDATION_RULE)
        )

        row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        row3.pack(fill="x", pady=3)
        self._create_dropdown_field_inline(
            row3, "MonumentType", recipe["MonumentType"],
            self._get_options("Enum_MonumentType", DEFAULT_MONUMENT_TYPE)
        )

        self._create_subsection_header("Placement Options")
        bool_row1 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_row1.pack(fill="x", pady=4)
        for bf in ["bOnWall", "bOnFloor", "bPlaceOnWater", "bOverrideRotation"]:
            self._create_checkbox_field(bool_row1, bf, recipe[bf])

        bool_row2 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_row2.pack(fill="x", pady=4)
        for bf in ["bAllowRefunds", "bAutoFoundation", "bInheritAutoFoundationStability", "bOnlyOnVoxel"]:
            self._create_checkbox_field(bool_row2, bf, recipe[bf])

        bool_row3 = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_row3.pack(fill="x", pady=4)
        for bf in ["bIsBlockedByNearbySettlementStones", "bIsBlockedByNearbyRavenConstructions"]:
            self._create_checkbox_field(bool_row3, bf, recipe[bf])

        self._create_subsection_header("Numeric Properties")
        self._create_text_field(
            "MaxAllowedPenetrationDepth", str(recipe["MaxAllowedPenetrationDepth"]),
            label="Max Penetration Depth", width=200
        )
        self._create_text_field(
            "RequireNearbyRadius", str(recipe["RequireNearbyRadius"]),
            label="Require Nearby Radius", width=200
        )
        self._create_text_field(
            "CameraStateOverridePriority", str(recipe["CameraStateOverridePriority"]),
            label="Camera Priority", width=200
        )

        self._render_materials_section(recipe)
        self._render_unlocks_section(recipe)
        self._render_sandbox_section(recipe)

        self._create_dropdown_field(
            "Recipe_EnabledState", recipe["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Recipe Enabled State"
        )

    def _render_new_construction_definition(self, row_name_var=None):
        """Render blank construction definition form."""
        construction = {
            "Name": "", "DisplayName": "", "Description": "",
            "Actor": "", "Icon": "", "Tags": [],
            "BackwardCompatibilityActors": [],
            "EnabledState": "ERowEnabledState::Live",
        }

        self._create_section_header("Construction Definition", "#4CAF50")

        if row_name_var is not None:
            self.form_vars["Construction_Name"] = row_name_var
        else:
            self._create_text_field("Construction_Name", construction["Name"], label="Row Name")

        self._create_text_field("DisplayName", construction["DisplayName"], label="Display Name")
        self._create_text_field("Description", construction["Description"])
        self._create_text_field("Actor", construction["Actor"],
                                label="Actor Path", autocomplete_key="Actors")
        self._create_text_field("Icon", "", label="Icon (Import Index)")
        self._create_dropdown_field(
            "Tags", "", self._get_options("Tags", []), label="Category Tag"
        )
        self._create_text_field(
            "BackwardCompatibilityActors", "",
            label="Backward Compat Actors", autocomplete_key="Actors"
        )
        self._create_dropdown_field(
            "Construction_EnabledState", construction["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Construction Enabled State"
        )

    def _render_new_item_recipe(self, row_name_var=None):
        """Render blank item recipe form (weapons, armor, tools)."""
        recipe = {
            "Name": "", "ResultItemHandle": "", "ResultItemCount": 1,
            "CraftTimeSeconds": 0.0, "bCanBePinned": True,
            "bNpcOnlyRecipe": False,
            "Materials": [], "DefaultRequiredConstructions": [],
            "DefaultUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
            "DefaultUnlocks_NumFragments": 1,
            "DefaultUnlocks_RequiredItems": [],
            "DefaultUnlocks_RequiredConstructions": [],
            "DefaultUnlocks_RequiredFragments": [],
            "bHasSandboxRequirementsOverride": False,
            "bHasSandboxUnlockOverride": False,
            "SandboxUnlocks_UnlockType": "EMorRecipeUnlockType::Manual",
            "SandboxUnlocks_NumFragments": 1,
            "SandboxUnlocks_RequiredItems": [],
            "SandboxUnlocks_RequiredConstructions": [],
            "SandboxUnlocks_RequiredFragments": [],
            "SandboxRequiredMaterials": [],
            "SandboxRequiredConstructions": [],
            "EnabledState": "ERowEnabledState::Live",
        }

        self._create_section_header("Item Recipe", ("#E65100", "#FF9800"))

        if row_name_var is not None:
            self.form_vars["Name"] = row_name_var
        else:
            self._create_text_field("Name", recipe["Name"], label="Row Name")

        self._create_text_field(
            "ResultItemHandle", recipe["ResultItemHandle"],
            label="Result Item", autocomplete_key="AllValues"
        )
        self._create_text_field(
            "ResultItemCount", str(recipe["ResultItemCount"]),
            label="Result Count", width=200
        )
        self._create_text_field(
            "CraftTimeSeconds", str(recipe["CraftTimeSeconds"]),
            label="Craft Time (s)", width=200
        )

        bool_frame = ctk.CTkFrame(self.form_content, fg_color="transparent")
        bool_frame.pack(fill="x", pady=4)
        self._create_checkbox_field(bool_frame, "bCanBePinned", recipe["bCanBePinned"])
        self._create_checkbox_field(bool_frame, "bNpcOnlyRecipe", recipe["bNpcOnlyRecipe"])

        self._render_materials_section(recipe)
        self._render_unlocks_section(recipe)
        self._render_sandbox_section(recipe)

        self._create_dropdown_field(
            "Recipe_EnabledState", recipe["EnabledState"],
            DEFAULT_ENABLED_STATE, label="Recipe Enabled State"
        )

    def _render_new_both(self):
        """Render construction recipe + definition with a single shared Row Name field."""
        shared_row_var = ctk.StringVar(value="")
        self.form_vars["_shared_row_name"] = shared_row_var

        self._create_subsection_header("Row Name (shared by both sections)")
        self._create_text_field("Name", "", label="Row Name")
        shared_row_var = self.form_vars["Name"]

        self._render_new_construction_recipe(row_name_var=shared_row_var)
        self._render_new_construction_definition(row_name_var=shared_row_var)

    # ---- Search/replace across form fields ----

    def _get_form_property_pairs(self) -> list[tuple[str, object, object]]:
        """Collect (property_name, label_widget, value_entry) triples from the form."""
        pairs: list[tuple[str, object, object]] = []
        if not self.form_scroll:
            return pairs
        for child in self.form_scroll.winfo_children():
            if not isinstance(child, ctk.CTkFrame):
                continue
            label_text = ""
            label_widget = None
            entry_widget = None
            for sub in child.winfo_children():
                if isinstance(sub, ctk.CTkLabel) and not label_text:
                    label_text = sub.cget("text").rstrip(":")
                    label_widget = sub
                elif isinstance(sub, ctk.CTkEntry):
                    try:
                        if sub.cget("state") != "disabled":
                            entry_widget = sub
                    except (ValueError, KeyError):
                        entry_widget = sub
            if label_text and entry_widget:
                pairs.append((label_text, label_widget, entry_widget))
        return pairs

    def _on_form_search_mode_change(self):
        """Update placeholder text when search mode changes."""
        mode = self._form_search_mode_var.get()
        if mode == SEARCH_PROPERTIES:
            self._form_search_entry.configure(placeholder_text="Search property...")
            self._form_replace_entry.configure(placeholder_text="Replace property...")
        elif mode == SEARCH_VALUES:
            self._form_search_entry.configure(placeholder_text="Search value...")
            self._form_replace_entry.configure(placeholder_text="Replace value...")
        else:
            self._form_search_entry.configure(placeholder_text="Search...")
            self._form_replace_entry.configure(placeholder_text="Replace...")
        self._form_search_index = -1
        self._form_search_matches = []

    def _on_form_search(self):
        """Find and highlight the next property or value matching the search text."""
        search_text = self._form_search_var.get()
        if not search_text:
            return
        pairs = self._get_form_property_pairs()
        if not pairs:
            return
        mode = self._form_search_mode_var.get()
        pairs_text = [(prop, entry.get()) for prop, _lbl, entry in pairs]
        self._form_search_matches = find_search_matches(pairs_text, search_text, mode)
        if not self._form_search_matches:
            self._form_search_index = -1
            self._set_status("No matches found")
            return
        next_idx = find_next_match(self._form_search_matches, self._form_search_index)
        if next_idx is None:
            return
        self._form_search_index = next_idx
        _, _lbl, entry = pairs[next_idx]
        entry.focus_set()
        entry.select_range(0, "end")
        self._set_status(
            f"Match {self._form_search_matches.index(next_idx) + 1} "
            f"of {len(self._form_search_matches)}"
        )

    def _on_form_replace(self):
        """Replace the current match using substring replacement."""
        search_text = self._form_search_var.get()
        replace_text = self._form_replace_var.get()
        if not search_text:
            return
        pairs = self._get_form_property_pairs()
        if not pairs or self._form_search_index < 0:
            self._on_form_search()
            return
        idx = self._form_search_index
        mode = self._form_search_mode_var.get()
        if idx < len(pairs):
            prop, label_w, entry = pairs[idx]
            val = entry.get()
            if mode == SEARCH_PROPERTIES and search_text.lower() in prop.lower():
                label_w.configure(text=substring_replace(prop, search_text, replace_text) + ":")
            elif mode == SEARCH_VALUES and search_text.lower() in val.lower():
                new_val = substring_replace(val, search_text, replace_text)
                entry.delete(0, "end")
                entry.insert(0, new_val)
            elif mode == SEARCH_BOTH:
                if search_text.lower() in prop.lower():
                    label_w.configure(text=substring_replace(prop, search_text, replace_text) + ":")
                if search_text.lower() in val.lower():
                    new_val = substring_replace(val, search_text, replace_text)
                    entry.delete(0, "end")
                    entry.insert(0, new_val)
        self._on_form_search()

    def _on_form_replace_all(self):
        """Replace all matches using substring replacement."""
        search_text = self._form_search_var.get()
        replace_text = self._form_replace_var.get()
        if not search_text:
            return
        pairs = self._get_form_property_pairs()
        mode = self._form_search_mode_var.get()
        count = 0
        for prop, label_w, entry in pairs:
            val = entry.get()
            if mode == SEARCH_PROPERTIES and search_text.lower() in prop.lower():
                label_w.configure(text=substring_replace(prop, search_text, replace_text) + ":")
                count += 1
            elif mode == SEARCH_VALUES and search_text.lower() in val.lower():
                new_val = substring_replace(val, search_text, replace_text)
                entry.delete(0, "end")
                entry.insert(0, new_val)
                count += 1
            elif mode == SEARCH_BOTH:
                replaced = False
                if search_text.lower() in prop.lower():
                    label_w.configure(text=substring_replace(prop, search_text, replace_text) + ":")
                    replaced = True
                if search_text.lower() in val.lower():
                    new_val = substring_replace(val, search_text, replace_text)
                    entry.delete(0, "end")
                    entry.insert(0, new_val)
                    replaced = True
                if replaced:
                    count += 1
        self._set_status(f"Replaced {count} matches" if count else "No matches found")

    # ---- Initial data loading and category switching ----

    def _initial_load(self):
        self._load_string_table()
        self._load_icon_paths()
        self._load_material_items()
        self._build_material_display_cache()
        self._load_category("buildings")

    def _build_material_display_cache(self):
        """Build cached material display names for FilterableComboBox."""
        self._cached_material_raw = set(self._material_items)
        self._cached_material_display = [
            self._format_material_display(m) for m in sorted(self._material_items)
        ]

    def _load_category(self, category: str):
        """Switch to a category: refresh cache, load row names, filter out base-game rows."""
        self.view_mode = category
        self._set_status(f"Loading {category}...")
        self._refresh_cache()

        recipe_names = self._get_names_from_file(self._get_cache_recipes_path())
        def_names = self._get_names_from_file(self._get_cache_defs_path())

        # Categories with recipes need matching names; flora/loot have definitions only
        if self.view_mode in ("buildings", "weapons", "armor", "tools", "items"):
            if recipe_names and def_names:
                matching = recipe_names & def_names
            elif def_names:
                matching = def_names
            else:
                matching = recipe_names or set()
        else:
            matching = def_names

        # Remove rows present in base-game output so only mod-added rows remain
        game_def_names = self._get_names_from_file(self._get_game_defs_path())
        game_recipe_names = self._get_names_from_file(self._get_game_recipes_path())
        game_names = game_def_names | game_recipe_names
        if game_names:
            before = len(matching)
            matching = matching - game_names
            stripped = before - len(matching)
            if stripped:
                logger.info("ObjectEditor: Stripped %d base-game rows, %d mod-only remain",
                            stripped, len(matching))

        self.secrets_items = {name: {"Name": name} for name in matching}
        self._populate_list(self.secrets_items)

        count = len(self.secrets_items)
        self._set_status(
            f"Found {count} {category} items" if count
            else f"No {category} items found in Secrets Source"
        )

    def _refresh_cache(self):
        """Copy Secrets Source JSON to cache dir for the active category."""
        self._json_row_cache.clear()
        cache_dir = self._get_cache_dir()

        if cache_dir.exists():
            for item in cache_dir.iterdir():
                if item.is_file() and item.suffix.lower() != ".ini":
                    item.unlink()

        cache_dir.mkdir(parents=True, exist_ok=True)

        src_recipes = self._get_secrets_recipes_path()
        cache_recipes = self._get_cache_recipes_path()
        if src_recipes and cache_recipes and src_recipes.exists():
            shutil.copy2(src_recipes, cache_recipes)

        src_defs = self._get_secrets_defs_path()
        cache_defs = self._get_cache_defs_path()
        if src_defs.exists():
            shutil.copy2(src_defs, cache_defs)

    def _on_refresh_click(self):
        self._load_category(self.view_mode)

    # ---- Path helpers: cache, secrets source, and base-game locations ----

    def _get_cache_dir(self) -> Path:
        return get_appdata_dir() / "cache" / "secrets" / (self.view_mode or "buildings")

    def _get_cache_recipes_path(self) -> Path | None:
        if self.view_mode in ("weapons", "armor", "tools", "items"):
            return self._get_cache_dir() / "DT_ItemRecipes.json"
        if self.view_mode == "buildings":
            return self._get_cache_dir() / "DT_ConstructionRecipes.json"
        return None

    def _get_cache_defs_path(self) -> Path:
        defs_map = {
            "buildings": "DT_Constructions.json",
            "weapons": "DT_Weapons.json",
            "armor": "DT_Armor.json",
            "tools": "DT_Tools.json",
            "items": "DT_Items.json",
            "flora": "DT_Moria_Flora.json",
            "loot": "DT_Loot.json",
        }
        return self._get_cache_dir() / defs_map.get(self.view_mode, "DT_Constructions.json")

    def _get_game_defs_path(self) -> Path:
        base = get_output_dir() / "jsondata" / "Moria" / "Content"
        defs_map = {
            "buildings": "Tech/Data/Building/DT_Constructions.json",
            "weapons": "Tech/Data/Items/DT_Weapons.json",
            "armor": "Tech/Data/Items/DT_Armor.json",
            "tools": "Tech/Data/Items/DT_Tools.json",
            "items": "Tech/Data/Items/DT_Items.json",
            "flora": "Tech/Data/Gameworld/DT_Moria_Flora.json",
            "loot": "Character/AI/DT_Loot.json",
        }
        return base / defs_map.get(self.view_mode, "Tech/Data/Building/DT_Constructions.json")

    def _get_game_recipes_path(self) -> Path | None:
        base = get_output_dir() / "jsondata" / "Moria" / "Content"
        if self.view_mode in ("weapons", "armor", "tools", "items"):
            return base / "Tech" / "Data" / "Items" / "DT_ItemRecipes.json"
        if self.view_mode == "buildings":
            return base / "Tech" / "Data" / "Building" / "DT_ConstructionRecipes.json"
        return None

    def _get_secrets_recipes_path(self) -> Path | None:
        base = get_new_secrets_jsondata_dir() / "Moria" / "Content"
        if self.view_mode in ("weapons", "armor", "tools", "items"):
            return base / "Tech" / "Data" / "Items" / "DT_ItemRecipes.json"
        if self.view_mode == "buildings":
            return base / "Tech" / "Data" / "Building" / "DT_ConstructionRecipes.json"
        return None

    def _get_secrets_defs_path(self) -> Path:
        base = get_new_secrets_jsondata_dir() / "Moria" / "Content"
        defs_map = {
            "buildings": "Tech/Data/Building/DT_Constructions.json",
            "weapons": "Tech/Data/Items/DT_Weapons.json",
            "armor": "Tech/Data/Items/DT_Armor.json",
            "tools": "Tech/Data/Items/DT_Tools.json",
            "items": "Tech/Data/Items/DT_Items.json",
            "flora": "Tech/Data/Gameworld/DT_Moria_Flora.json",
            "loot": "Character/AI/DT_Loot.json",
        }
        return base / defs_map.get(self.view_mode, "Tech/Data/Building/DT_Constructions.json")

    def _get_string_tables_dirs(self) -> list[Path]:
        """Return existing string table directories (base-game + New Secrets mod)."""
        candidates = [
            get_output_dir() / "jsondata" / "Moria" / "Content" / "Tech" / "Data" / "StringTables",
            get_new_secrets_jsondata_dir() / "Moria" / "Content" / "Mods" / "Tech" / "Data" / "StringTables",
            # Fallback to Secrets Source if New Secrets doesn't have string tables yet
            get_appdata_dir() / "Secrets Source" / "jsondata" / "Moria" / "Content" / "Mods" / "Tech" / "Data" / "StringTables",
        ]
        return [d for d in candidates if d.exists()]

    # ---- Data helpers: string table, name lookup, list population ----

    def _get_names_from_file(self, json_path: Path | None) -> set:
        if not json_path or not json_path.exists():
            return set()
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            names = set()
            for export in data.get("Exports", []):
                for row in export.get("Table", {}).get("Data", []):
                    if isinstance(row, dict) and "Name" in row:
                        names.add(row["Name"])
            return names
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read %s: %s", json_path, e)
            return set()

    def _load_string_table(self):
        """Parse string table JSONs to build tag -> display name mapping."""
        self.string_table = {}
        for st_dir in self._get_string_tables_dirs():
            for st_path in st_dir.glob("*.json"):
                try:
                    with open(st_path, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    exports = data.get("Exports", []) if isinstance(data, dict) else []
                    if exports:
                        table = exports[0].get("Table", {})
                        values = table.get("Value", [])
                        if isinstance(values, list):
                            for pair in values:
                                if isinstance(pair, list) and len(pair) == 2:
                                    key, val = pair
                                    if isinstance(key, str) and isinstance(val, str):
                                        parts = key.rsplit(".", 1)
                                        if len(parts) == 2:
                                            tag, field = parts
                                            if tag not in self.string_table:
                                                self.string_table[tag] = {}
                                            if field == "Name":
                                                self.string_table[tag]["name"] = val
                                            elif field == "Description":
                                                self.string_table[tag]["description"] = val

                    if isinstance(data, list):
                        for entry in data:
                            st = entry.get("StringTable", {})
                            for key, val in st.get("KeysToEntries", {}).items():
                                parts = key.rsplit(".", 1)
                                if len(parts) == 2:
                                    tag, field = parts
                                    if tag not in self.string_table:
                                        self.string_table[tag] = {}
                                    if field == "Name":
                                        self.string_table[tag]["name"] = val
                                    elif field == "Description":
                                        self.string_table[tag]["description"] = val
                except (json.JSONDecodeError, OSError):
                    pass

        logger.info("Loaded %d display names for Object Editor", len(self.string_table))

    def _lookup_game_name(self, internal_name: str) -> str:
        entry = self.string_table.get(internal_name)
        if entry and entry.get("name"):
            return entry["name"]
        return internal_name

    # ---- Left pane list population and filtering ----

    def _populate_list(self, items: dict):
        self.construction_check_vars.clear()

        if not items:
            self.building_list.clear()
            self.count_label.configure(text="0 items")
            return

        sorted_names = sorted(
            items.keys(), key=lambda n: self._lookup_game_name(n).lower()
        )

        list_items = []
        for name in sorted_names:
            check_var = ctk.BooleanVar(value=False)
            self.construction_check_vars[name] = check_var

            display_name = self._lookup_game_name(name)
            label_text = (
                f"{display_name} ({name})"
                if display_name != name else name
            )

            list_items.append({
                "key": name,
                "label_text": label_text,
                "eye_visible": True,
            })

        self.building_list.set_items(list_items, check_vars=self.construction_check_vars)
        self.count_label.configure(text=f"{len(list_items)} items")
        self._filter_list()

    def _filter_list(self):
        if not self.def_search_var:
            return
        filter_text = self.def_search_var.get().strip()
        visible, total = self.building_list.apply_filter(filter_text)
        if filter_text:
            self.count_label.configure(text=f"{visible} of {total} items")
        else:
            self.count_label.configure(text=f"{total} items")

    def _on_checkbox_toggle(self, key: str):
        pass

    # ---- Save operations ----
    # Existing items: read form_vars + _property_widgets, write back to JSON.
    # New items: collect form_vars + material_rows, create rows via object_templates.

    def _on_save(self):
        """Route save to either existing-item update or new-object creation."""
        if self.current_selected_name and not self._showing_new_form:
            self._save_existing_item()
            return
        template_type = self.template_type_var.get()
        if template_type in ("Construction", "Both"):
            self._save_construction()
        elif template_type == "Recipe":
            self._save_item_recipe()

    def _save_existing_item(self):
        """Find the row in definition and recipe files, apply edits, and write back."""
        row_name = self.current_selected_name
        saved_to = []

        for path in [self._get_secrets_defs_path(), self._get_secrets_recipes_path()]:
            if not path or not path.exists():
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read %s: %s", path, e)
                continue

            row_found = False
            for export in data.get("Exports", []):
                table = export.get("Table", {})
                for row in table.get("Data", []):
                    if isinstance(row, dict) and row.get("Name") == row_name:
                        self._apply_property_edits(row)
                        row_found = True
                        break
                if row_found:
                    break

            if row_found:
                try:
                    save_json(path, data)
                    saved_to.append(path.name)
                except OSError as e:
                    self._set_status(f"Error writing {path.name}: {e}")

        if saved_to:
            self._json_row_cache.clear()
            # Save individual row to Raw JSON directory
            for path in [self._get_secrets_defs_path(), self._get_secrets_recipes_path()]:
                if not path or not path.exists():
                    continue
                try:
                    row_data = self._get_row_by_name(path, row_name)
                    if row_data:
                        self._save_raw_json(row_name, row_data)
                except (json.JSONDecodeError, OSError):
                    pass
            self._set_status(f"Saved {row_name} to {', '.join(saved_to)}")
        else:
            self._set_status(f"Could not find {row_name} in New Secrets files")

    def _apply_property_edits(self, row: dict):
        """Write each _property_widgets entry back, converting to original type."""
        for pw in self._property_widgets:
            prop = pw["prop"]
            new_val = pw["var"].get()
            orig_type = pw["type"]
            if orig_type == "int":
                try:
                    prop["Value"] = int(new_val)
                except ValueError:
                    prop["Value"] = new_val
            elif orig_type == "float":
                try:
                    prop["Value"] = float(new_val)
                except ValueError:
                    prop["Value"] = new_val
            elif orig_type == "bool":
                prop["Value"] = new_val.lower() in ("true", "1", "yes")
            else:
                prop["Value"] = new_val

    @staticmethod
    def _save_raw_json(row_name: str, row: dict):
        """Save a single row's JSON to the Raw JSON directory."""
        raw_dir = get_new_secrets_raw_json_dir()
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"{row_name}.json"
        try:
            with open(raw_path, 'w', encoding='utf-8') as f:
                json.dump(row, f, indent=2, ensure_ascii=False)
            logger.info("Saved raw JSON: %s", raw_path.name)
        except OSError as e:
            logger.warning("Failed to save raw JSON for %s: %s", row_name, e)

    @staticmethod
    def _parse_material_name(display_text: str) -> str:
        """Extract internal name from 'Display Name (InternalName)' format."""
        if "(" in display_text and display_text.endswith(")"):
            return display_text[display_text.rindex("(") + 1:-1].strip()
        return display_text.strip()

    def _collect_materials(self) -> list[tuple[str, int]]:
        """Collect materials from structured form rows."""
        materials = []
        for row in self.material_rows:
            if row.get("removed"):
                continue
            mat_name = self._parse_material_name(row["material_var"].get())
            try:
                count = int(row["amount_var"].get())
            except ValueError:
                count = 1
            if mat_name and count > 0:
                materials.append((mat_name, count))
        return materials

    def _get_form_var(self, key: str, default: str = "") -> str:
        """Get a stripped string value from form_vars."""
        var = self.form_vars.get(key)
        if var is None:
            return default
        return var.get().strip()

    def _save_construction(self):
        """Create new construction rows in Architecture, Constructions, and Recipes JSON."""
        if not self._showing_new_form:
            self._set_status("Click 'New' first to create a construction")
            return

        row_name = self._get_form_var("Name")
        display_name = self._get_form_var("DisplayName")
        description = self._get_form_var("Description")
        actor = self._get_form_var("Actor")
        icon = self._get_form_var("Icon")

        if not row_name:
            self._set_status("Row Name is required")
            return

        materials = self._collect_materials()
        unlock_type = self._get_form_var(
            "DefaultUnlocks_UnlockType", "EMorRecipeUnlockType::Manual"
        )

        try:
            secrets_base = get_new_secrets_jsondata_dir() / "Moria" / "Content"

            arch_path = secrets_base / "Tech" / "Data" / "StringTables" / "Architecture.json"
            constructions_path = secrets_base / "Tech" / "Data" / "Building" / "DT_Constructions.json"
            recipes_path = secrets_base / "Tech" / "Data" / "Building" / "DT_ConstructionRecipes.json"

            for p, n in [
                (arch_path, "Architecture.json"),
                (constructions_path, "DT_Constructions.json"),
                (recipes_path, "DT_ConstructionRecipes.json"),
            ]:
                if not p.exists():
                    self._set_status(f"{n} not found in Secrets Source")
                    return

            arch_data = load_json(arch_path)
            constructions_data = load_json(constructions_path)
            recipes_data = load_json(recipes_path)

            existing = get_existing_row_names(constructions_data)
            unique_tag = gen_unique_tag(row_name, existing)

            category = self._get_form_var("Tags")
            if not icon:
                icon = f"/Game/Mods/Constructions/Icons/T_UI_BuildIcon_{unique_tag}"

            if display_name:
                add_string_table_entry(arch_data, unique_tag, display_name, description)
            create_construction_row(unique_tag, actor, category, icon, constructions_data)
            create_construction_recipe_row(
                unique_tag, category, materials, unlock_type, "", recipes_data
            )

            save_json(arch_path, arch_data)
            save_json(constructions_path, constructions_data)
            save_json(recipes_path, recipes_data)

            # Save raw JSON for the new construction and recipe rows
            constr_row = self._get_row_by_name(constructions_path, unique_tag)
            if constr_row:
                self._save_raw_json(unique_tag, constr_row)
            recipe_row = self._get_row_by_name(recipes_path, unique_tag)
            if recipe_row:
                self._save_raw_json(f"{unique_tag}_Recipe", recipe_row)

            self._set_status(f"Saved construction: {unique_tag}")
            self._json_row_cache.clear()
            self._load_category("buildings")

        except (OSError, json.JSONDecodeError) as e:
            logger.exception("Failed to save construction")
            self._set_status(f"Error saving: {e}")

    def _save_item_recipe(self):
        """Create a new item recipe row in DT_ItemRecipes.json."""
        if not self._showing_new_form:
            self._set_status("Click 'New' first to create an item recipe")
            return

        row_name = self._get_form_var("Name")
        result_item = self._get_form_var("ResultItemHandle")

        if not row_name:
            self._set_status("Row Name is required")
            return
        if not result_item:
            self._set_status("Result Item is required")
            return

        materials = self._collect_materials()

        try:
            secrets_base = get_new_secrets_jsondata_dir() / "Moria" / "Content"
            recipes_path = secrets_base / "Tech" / "Data" / "Items" / "DT_ItemRecipes.json"

            if not recipes_path.exists():
                self._set_status("DT_ItemRecipes.json not found in New Secrets")
                return

            recipes_data = load_json(recipes_path)

            item_prefix = result_item.split(".")[0] if "." in result_item else "Item"
            stations = []
            for key, var in self.form_vars.items():
                if key.startswith("CraftingStation_") and hasattr(var, 'get'):
                    try:
                        if var.get():
                            stations.append(key)
                    except (ValueError, TypeError):
                        pass

            unlock_type = self._get_form_var(
                "DefaultUnlocks_UnlockType", "EMorRecipeUnlockType::Manual"
            )

            create_item_recipe_row(
                row_name, item_prefix, stations, materials,
                unlock_type, "", recipes_data,
            )
            save_json(recipes_path, recipes_data)

            # Save raw JSON for the new recipe row
            recipe_row = self._get_row_by_name(recipes_path, row_name)
            if recipe_row:
                self._save_raw_json(row_name, recipe_row)

            self._set_status(f"Saved item recipe: {row_name}")
            self._json_row_cache.clear()
            cat_map = {"Armor": "armor", "Weapon": "weapons", "Tool": "tools"}
            self._load_category(cat_map.get(item_prefix, "items"))

        except (OSError, json.JSONDecodeError) as e:
            logger.exception("Failed to save item recipe")
            self._set_status(f"Error saving: {e}")

    # ---- Delete ----

    def _on_delete(self):
        """Remove the selected row from definition and recipe JSONs after confirmation."""
        if not self.current_selected_name:
            self._set_status("Select an item to delete")
            return

        row_name = self.current_selected_name
        display = self._lookup_game_name(row_name)

        confirm = ctk.CTkInputDialog(
            text=f"Type DELETE to confirm removal of:\n{display} ({row_name})",
            title="Confirm Delete",
        )
        result = confirm.get_input()
        if result != "DELETE":
            self._set_status("Delete cancelled")
            return

        deleted_from = []
        for path in [self._get_secrets_defs_path(), self._get_secrets_recipes_path()]:
            if not path or not path.exists():
                continue

            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue

            removed = False
            for export in data.get("Exports", []):
                table = export.get("Table", {})
                rows = table.get("Data", [])
                original_len = len(rows)
                table["Data"] = [
                    r for r in rows
                    if not (isinstance(r, dict) and r.get("Name") == row_name)
                ]
                if len(table["Data"]) < original_len:
                    removed = True

            if removed:
                try:
                    save_json(path, data)
                    deleted_from.append(path.name)
                except OSError as e:
                    logger.error("Failed to write %s: %s", path, e)

        if deleted_from:
            self._json_row_cache.clear()
            self._show_placeholder()
            self._load_category(self.view_mode)
            self._set_status(f"Deleted {row_name} from {', '.join(deleted_from)}")
        else:
            self._set_status(f"Could not find {row_name} in secrets files")

    # ---- Status bar ----

    def _set_status(self, message: str):
        if self.on_status_message:
            self.on_status_message(message)
        logger.info("ObjectEditor: %s", message)
