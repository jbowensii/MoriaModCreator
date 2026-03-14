"""Refactor object_editor_view.py to use structured form rendering like buildings_view.py."""
import re

FILE = r"c:\Users\johnb\OneDrive\Documents\Projects\Moria MOD Creator\src\ui\object_editor_view.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add imports from buildings_view at the top (after existing imports)
old_import = "from src.ui.filterable_combobox import FilterableComboBox"
new_import = """from src.ui.buildings_view import (
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
from src.ui.filterable_combobox import FilterableComboBox"""
content = content.replace(old_import, new_import)

# 2. Add form_vars, cached_options, material_rows, etc. to __init__
old_init = """        # Editor form state
        self._material_rows = []
        self._station_vars = {}
        self._property_widgets = []  # List of (label, value_widget) for JSON display
        self._showing_new_form = False  # True when a blank template form is shown"""
new_init = """        # Editor form state
        self._material_rows = []
        self._station_vars = {}
        self._property_widgets = []  # List of (label, value_widget) for JSON display
        self._showing_new_form = False  # True when a blank template form is shown

        # Structured form state (mirrors Secrets tab)
        self.form_vars = {}
        self.form_content = None  # Will be set during widget creation
        self.material_rows: list[dict] = []
        self.sandbox_material_rows: list[dict] = []
        self.materials_frame = None
        self.sandbox_materials_frame = None
        self.cached_options: dict = {}
        self._cached_material_display: list[str] = []
        self._cached_material_raw: set[str] = set()"""
content = content.replace(old_init, new_init)

# 3. Replace the scrollable form area setup so form_content is created
old_scroll = """        # Row 2: Scrollable form area
        self.form_scroll = ctk.CTkScrollableFrame(
            self.form_container, fg_color="transparent"
        )
        self.form_scroll.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        # Placeholder
        self._show_placeholder()"""
new_scroll = """        # Row 2: Scrollable form area
        self.form_scroll = ctk.CTkScrollableFrame(
            self.form_container, fg_color="transparent"
        )
        self.form_scroll.grid(row=2, column=0, sticky="nsew", padx=5, pady=5)

        # form_content frame inside scroll (same pattern as Secrets tab)
        self.form_content = ctk.CTkFrame(self.form_scroll, fg_color="transparent")

        # Placeholder
        self._show_placeholder()"""
content = content.replace(old_scroll, new_scroll)

# 4. Update _clear_form_widgets to also clear form_content
old_clear = """    def _clear_form_widgets(self):
        for widget in self.form_scroll.winfo_children():
            widget.destroy()
        self._material_rows.clear()
        self._station_vars.clear()
        self._property_widgets.clear()"""
new_clear = """    def _clear_form_widgets(self):
        for widget in self.form_scroll.winfo_children():
            widget.destroy()
        # Re-create form_content frame
        self.form_content = ctk.CTkFrame(self.form_scroll, fg_color="transparent")
        self._material_rows.clear()
        self._station_vars.clear()
        self._property_widgets.clear()
        self.form_vars.clear()
        self.material_rows.clear()
        self.sandbox_material_rows.clear()"""
content = content.replace(old_clear, new_clear)

# 5. Replace _on_item_click to use structured form rendering
old_item_click = '''    def _on_item_click(self, key: str):
        """Load the selected item\'s JSON data into the right pane."""
        self.current_selected_name = key
        self._showing_new_form = False
        self._clear_form_widgets()
        if self._search_bar:
            self._search_bar.grid()

        # Load both definition and recipe rows
        def_row, recipe_row = self._load_both_rows(key)
        if not def_row and not recipe_row:
            ctk.CTkLabel(
                self.form_scroll,
                text=f"Could not find row data for: {key}",
                font=ctk.CTkFont(size=13),
                text_color="gray",
            ).pack(pady=20, padx=15)
            return

        # Display header with item name
        display_name = self._lookup_game_name(key)
        header_text = f"{display_name}" if display_name != key else key
        if display_name != key:
            header_text += f"  ({key})"

        ctk.CTkLabel(
            self.form_scroll, text=header_text,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=15, pady=(10, 2), anchor="w")

        # Separator
        ctk.CTkFrame(
            self.form_scroll, height=2, fg_color=("gray70", "gray30")
        ).pack(fill="x", padx=15, pady=(2, 10))

        # Render recipe section (if exists \xe2\x80\x94 flora and loot have no recipes)
        if recipe_row and self.view_mode not in ("flora", "loot"):
            self._render_section_header(
                self._get_recipe_section_label(),
                fg_color=("#E65100", "#FF9800"),
            )
            self._render_row_properties(recipe_row)

        # Render definition section (if exists)
        if def_row:
            self._render_section_header(
                self._get_def_section_label(),
                fg_color=self._get_def_section_color(),
            )
            self._render_row_properties(def_row)

        self._set_status(f"Loaded: {display_name}")'''

new_item_click = '''    def _on_item_click(self, key: str):
        """Load the selected item\'s JSON data into the right pane."""
        self.current_selected_name = key
        self._showing_new_form = False
        self._clear_form_widgets()
        if self._search_bar:
            self._search_bar.grid()

        # Load both definition and recipe rows
        def_row, recipe_row = self._load_both_rows(key)
        if not def_row and not recipe_row:
            ctk.CTkLabel(
                self.form_scroll,
                text=f"Could not find row data for: {key}",
                font=ctk.CTkFont(size=13),
                text_color="gray",
            ).pack(pady=20, padx=15)
            return

        # Show form_content
        self.form_content.pack(fill="both", expand=True)

        # Display header with item name
        display_name = self._lookup_game_name(key)
        header_text = f"{display_name}" if display_name != key else key
        if display_name != key:
            header_text += f"  ({key})"

        ctk.CTkLabel(
            self.form_content, text=header_text,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(fill="x", padx=15, pady=(10, 2), anchor="w")

        # Separator
        ctk.CTkFrame(
            self.form_content, height=2, fg_color=("gray70", "gray30")
        ).pack(fill="x", padx=15, pady=(2, 10))

        # Dispatch to per-category structured form renderer
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

        self._set_status(f"Loaded: {display_name}")'''

content = content.replace(old_item_click, new_item_click)

# 6. Replace the old section label methods and generic renderers with structured ones
# Find the block from _get_recipe_section_label through _render_property and replace
old_renderers_start = "    def _get_recipe_section_label(self) -> str:"
old_renderers_end = """            elif isinstance(v, dict):
                    self._render_property(parent, {"Name": k, "Value": v}, depth + 1)

        elif value is None:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=(left_pad, 15), pady=1)

            ctk.CTkLabel(
                row, text=f"{prop_name}:", width=220, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left")

            ctk.CTkLabel(
                row, text="null", text_color="gray",
                font=ctk.CTkFont(size=12),
            ).pack(side="left")"""

# Find the exact positions
start_pos = content.find(old_renderers_start)
end_pos = content.find(old_renderers_end)
if start_pos == -1 or end_pos == -1:
    print("ERROR: Could not find renderer block to replace")
    import sys; sys.exit(1)
end_pos += len(old_renderers_end)

new_renderers = '''    # ------------------------------------------------------------------
    # Structured form helpers (mirrors Secrets tab in buildings_view.py)
    # ------------------------------------------------------------------

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
            row_frame, text="\\u2715", width=28, height=28,
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
            row_frame, text="\\u2715", width=28, height=28,
            fg_color="#f44336", hover_color="#d32f2f",
            command=lambda rf=row_frame: self._remove_sandbox_material_row(rf)
        ).pack(side="right", padx=5, pady=5)

        self.sandbox_material_rows.append({
            "frame": row_frame,
            "material_var": mat_var,
            "amount_var": amount_var
        })

    def _add_new_sandbox_material_row(self):
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

    # ------------------------------------------------------------------
    # Per-category form renderers (mirrors Secrets tab exactly)
    # ------------------------------------------------------------------

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

        return True'''

content = content[:start_pos] + new_renderers + content[end_pos:]

# 7. Also remove the old _render_section_header that was used for colored bars
# It was between _get_def_section_color and _render_row_properties — now replaced above

# 8. Update _initial_load to also build material display cache
old_initial_load = """    def _initial_load(self):
        self._load_string_table()
        self._load_icon_paths()
        self._load_material_items()
        self._load_category("buildings")"""
new_initial_load = """    def _initial_load(self):
        self._load_string_table()
        self._load_icon_paths()
        self._load_material_items()
        self._build_material_display_cache()
        self._load_category("buildings")

    def _build_material_display_cache(self):
        \"\"\"Build cached material display names for FilterableComboBox.\"\"\"
        self._cached_material_raw = set(self._material_items)
        self._cached_material_display = [
            self._format_material_display(m) for m in sorted(self._material_items)
        ]"""
content = content.replace(old_initial_load, new_initial_load)

# 9. Update _save_existing_item to also check form_vars (structured form)
old_save = """    def _on_save(self):
        # If editing an existing item, save property edits back to JSON
        if self.current_selected_name and self._property_widgets:
            self._save_existing_item()
            return"""
new_save = """    def _on_save(self):
        # If editing an existing item, save property edits back to JSON
        if self.current_selected_name and not self._showing_new_form:
            self._save_existing_item()
            return"""
content = content.replace(old_save, new_save)

# 10. Update _show_placeholder to not pack form_content
old_placeholder = """    def _show_placeholder(self):
        self._clear_form_widgets()
        self.current_selected_name = None
        self._showing_new_form = False
        if self._search_bar:
            self._search_bar.grid_remove()
        ctk.CTkLabel(
            self.form_scroll,
            text=(
                "Select a category, then click an item to view/edit its JSON.\\n\\n"
                "Or select a template type and click 'New' to create a new object."
            ),
            font=ctk.CTkFont(size=14),
            text_color="gray",
            justify="center",
        ).pack(expand=True, pady=100)"""
new_placeholder = """    def _show_placeholder(self):
        self._clear_form_widgets()
        self.current_selected_name = None
        self._showing_new_form = False
        if self._search_bar:
            self._search_bar.grid_remove()
        ctk.CTkLabel(
            self.form_scroll,
            text=(
                "Select a category, then click an item to view/edit its JSON.\\n\\n"
                "Or select a template type and click 'New' to create a new object."
            ),
            font=ctk.CTkFont(size=14),
            text_color="gray",
            justify="center",
        ).pack(expand=True, pady=100)
        # form_content is destroyed and re-created in _clear_form_widgets
        # but placeholder goes directly on form_scroll, not form_content"""
content = content.replace(old_placeholder, new_placeholder)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

print("Refactoring complete!")
