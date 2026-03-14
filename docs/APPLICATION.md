# Moria MOD Creator — Application Documentation

**Version:** 2.2.0
**Author:** John B Owens II
**Create DEF functionality by:** Sqitey
**Framework:** Python 3.10+ / CustomTkinter
**Target Game:** The Lord of the Rings: Return to Moria (UE4.27)

---

## Table of Contents

1. [Application Overview](#1-application-overview)
2. [Entry Point and Startup](#2-entry-point-and-startup)
3. [Configuration System](#3-configuration-system)
4. [Main Window](#4-main-window)
5. [Definition Management](#5-definition-management)
6. [Build Pipeline](#6-build-pipeline)
7. [Buildings / Constructions View](#7-buildings--constructions-view)
8. [Object Editor View](#8-object-editor-view)
9. [Create DEF View](#9-create-def-view)
10. [Import System](#10-import-system)
11. [Custom Widgets](#11-custom-widgets)
12. [Object Templates](#12-object-templates)
13. [Data Formats](#13-data-formats)
14. [Directory Layout](#14-directory-layout)
15. [Test Suite](#15-test-suite)
16. [Build and Release](#16-build-and-release)

---

## 1. Application Overview

Moria MOD Creator is a desktop tool for creating and managing mods for *Return to Moria*. It provides a GUI for:

- Browsing and selecting `.def` XML definition files that describe mod changes
- Editing game DataTable properties via structured forms
- Building mods from definitions into installable `.pak` files
- Creating new game objects (constructions, weapons, armor, tools)
- Comparing modded vs original game files to auto-generate `.def` files

The application operates on UAssetAPI-exported JSON representations of Unreal Engine DataTable assets. The build pipeline converts edited JSON back to `.uasset` format and packages it using `retoc`.

### Source File Summary

| Area | Files | Lines | Description |
|------|-------|-------|-------------|
| Core | 6 | ~2,540 | Config, constants, build manager, definition manager, object templates |
| UI | 19 | ~24,800 | Main window, views, dialogs, custom widgets |
| Tests | 6 | ~3,990 | 275 tests covering all core modules |
| Scripts | 5 | ~800 | Build, release, signing, cleanup utilities |

---

## 2. Entry Point and Startup

**File:** `main.py`

Startup sequence:
1. Configure logging (console at WARNING, file at WARNING, src.* at INFO)
2. Check for existing config; if missing, show first-run `ConfigDialog`
3. Apply color scheme from config (dark/light/system)
4. Enable debug mode if configured (upgrades file logging to DEBUG)
5. Create `MainWindow` and enter the CTk event loop

Log file location: `%APPDATA%/MoriaMODCreator/MoriaMODCreator.log`

---

## 3. Configuration System

**File:** `src/config.py` (440 lines)

Manages application settings stored in `%APPDATA%/MoriaMODCreator/config.ini`.

### Key Functions
- `get_appdata_dir()` — Returns the AppData directory, creating it if needed
- `get_output_dir()` — Returns the output directory for built mods
- `get_game_install_path()` — Reads the game installation path from config
- `get_color_scheme()` / `apply_color_scheme()` — Theme management
- `get_debug_mode()` — Check if verbose logging is enabled
- `config_exists()` — Whether first-run setup has completed

### Settings Stored
- Game installation path (Epic Games directory)
- Utilities directory (UAssetGUI, retoc, FModel)
- Color scheme preference
- Debug mode flag
- Custom paths for mod files

---

## 4. Main Window

**File:** `src/ui/main_window.py` (4,515 lines)

Split-pane layout that serves as the primary interface.

### Left Pane — Definitions Browser
- Tree of `.def` files organized by category (14 categories under `Definitions/`)
- Checkboxes to select which definitions to include in a build
- Checkbox states persist per-mod via `DefinitionManager`
- Filter/search bar for quick lookup

### Right Pane — JSON Data Editor
- Virtual-scrolled property list showing the DataTable fields from selected `.def` files
- Inline editing of values with type detection (int, float, bool, string, enum)
- Search and replace across property names and values
- Batch rendering mode for viewing multiple definitions at once

### Toolbar
- **Build Mod** — Triggers the full build pipeline
- **Import** — Opens the combined import dialog
- **Advanced** — Switches to Buildings view, Object Editor, or Create DEF view
- **Settings** — Opens config dialog
- **About** — Shows version and credits

### Modes
- **Novice** — Simplified interface with pre-built mod files
- **Advanced** — Full access to definition editing, buildings view, object editor, Create DEF

---

## 5. Definition Management

**File:** `src/definition_manager.py` (272 lines)

Handles `.def` XML files and their selection state.

### .def File Format
```xml
<root>
  <description>Human-readable description</description>
  <author>Author name</author>
  <mod file="relative/path/to/DT_Something.json">
    <add_imports>[{"ObjectName": "..."}]</add_imports>
    <add_row name="RowName">{ JSON row data }</add_row>
    <change item="RowName" property="PropertyPath" value="NewValue" />
    <delete item="RowName" property="ContainerProp" value="ValueToRemove" />
    <change item="RowName" property="ContainerProp" value="TagToAdd">
      <add_property item="RowName">{ JSON property }</add_property>
    </change>
  </mod>
</root>
```

### DefinitionManager Class
- Tracks per-mod checkbox states in `checkbox_states.ini`
- Path encoding: `\` → `|`, `:` → `~` for INI key compatibility
- `parse_definition()` — Extracts description, author, mod target, and changes
- `get_all_selected_definitions()` — Returns checked `.def` file paths for building

---

## 6. Build Pipeline

**File:** `src/build_manager.py` (1,236 lines)

Three-phase pipeline that converts `.def` files into a packaged mod.

### Phase A — Assemble Base Files
Copy non-secrets source JSON files into the `jsonfiles/` working directory.

### Phase B — Overlay Secrets
Copy secrets manifest files (from Secrets Source) on top of assembled files.

### Phase C — Apply Definition Changes
For each selected `.def` file, parse the XML and apply operations to the target JSON:
- `<add_row>` — Insert or replace a DataTable row
- `<add_imports>` — Add import entries (avoiding duplicates)
- `<change>` — Modify a property value in a row
- `<change>` with `<add_property>` — Ensure a property exists, then set its value
- `<delete>` — Remove a value from a GameplayTagContainer or array

### Post-Processing
- Convert modified JSON back to `.uasset` via UAssetGUI CLI
- Package using `retoc` to create the final `.pak`/`.ucas`/`.utoc` IoStore files
- Create a distributable ZIP in the output directory

### GameplayTagContainer Handling
The build manager detects GameplayTagContainer properties at runtime by checking `$type`, `StructType`, and inner `Value` array markers. This allows `<delete>` and `<change>` to work generically on any tag container, not just hardcoded property names.

---

## 7. Buildings / Constructions View

**Files:** `src/ui/buildings_view.py` (7,050 lines), `src/ui/constructions_view.py` (6,894 lines)

These views provide the Advanced tab for browsing and editing construction/secret data.

### Layout
- **Left pane:** Category tabs (Buildings, Weapons, Armor, Tools, Items, Flora, Loot) with virtual-scrolled item lists
- **Right pane:** Structured forms for the selected item, with sections for recipe properties, definition properties, materials, unlocks, and sandbox overrides

### Field Extraction
Each category has an `extract_*_fields()` function that flattens the nested UAssetAPI JSON into a simple dictionary:
- `extract_recipe_fields()` — Construction recipes (placement, materials, unlocks)
- `extract_construction_fields()` — Construction definitions (actor, icon, tags)
- `extract_weapon_fields()` — Weapon stats (damage, speed, durability)
- `extract_armor_fields()` — Armor stats (damage reduction, protection)
- `extract_tool_fields()` — Tool stats (carve hits, mining rate)
- `extract_item_fields()` — Generic item properties
- `extract_flora_fields()` — Flora/farming properties
- `extract_loot_fields()` — Loot table entries
- `extract_item_recipe_fields()` — Item crafting recipes

### Shared Components
- `AutocompleteEntry` — Text entry with suggestion dropdown
- `FieldTooltip` — Hover tooltips with field descriptions from `FIELD_DESCRIPTIONS`
- `FilterableComboBox` — Type-to-filter dropdown for enum/material selection

### Secrets Tab Workflow
1. Scan Secrets Source JSON for mod-added rows (not in base game)
2. Display mod-only items in the left pane
3. On click, extract fields from the row's `Value[]` property array
4. Render structured form with appropriate widgets per field type
5. On save, write modified values back to the Secrets Source JSON

---

## 8. Object Editor View

**File:** `src/ui/object_editor_view.py` (~2,550 lines)

Advanced tab for creating and editing DataTable objects in the Secrets Source.

### Architecture
Two-pane layout identical to the Secrets tab, but focused on object creation:

**Left pane:** Browsable list of mod-only items for the active category. Base-game rows are filtered out by comparing Secrets Source names against `output/jsondata/` names.

**Right pane:** Structured form rendered by per-category methods (`_show_buildings_form`, `_show_weapon_form`, etc.). Each method uses `extract_*_fields()` to flatten JSON, then renders using shared form helpers.

### Form System
All form fields are created by shared helper methods that store variables in `self.form_vars`:
- `_create_text_field()` — Labeled text entry (with optional autocomplete)
- `_create_dropdown_field()` — Labeled FilterableComboBox
- `_create_checkbox_field()` — Boolean checkbox with tooltip
- `_create_section_header()` — Colored section divider
- `_create_subsection_header()` — Gray subsection label

Material rows are dynamically managed via `_add_structured_material_row()` / `_remove_structured_material_row()`, with lazy frame packing (the container only appears when materials exist).

### New Object Creation
The "New" button renders blank forms with game-accurate defaults:
- **Construction:** Recipe section + Definition section (two forms)
- **Recipe:** Item recipe section only
- **Both:** Shared Row Name field + Construction Recipe + Construction Definition

On save, the form values are collected from `self.form_vars` and `self.material_rows`, then passed to `object_templates` functions to inject rows into Secrets Source JSON files.

### Save Workflow
- **Existing items:** `_apply_property_edits()` writes `_property_widgets` values back to the JSON row's `Value[]` array, converting types (int, float, bool, string)
- **New constructions:** Creates rows in `Architecture.json`, `DT_Constructions.json`, and `DT_ConstructionRecipes.json`
- **New item recipes:** Creates a row in `DT_ItemRecipes.json`

### Data Flow
```
Secrets Source JSON → _load_both_rows() → extract_*_fields() → form_vars
                                                                    ↓
                                                              User edits
                                                                    ↓
form_vars → _apply_property_edits() / _save_construction() → Secrets Source JSON
```

---

## 9. Create DEF View

**File:** `src/ui/def_creator_view.py` (1,239 lines)

Generates `.def` files by comparing modded vs original game files.

### Workflow
1. User selects two directories: modded game files and original game files
2. Auto-converts `.uasset` files to JSON using UAssetGUI
3. Matches files by name between both directories
4. For each matched pair, walks the UAssetAPI JSON structure recursively
5. Detects differences at the property level:
   - Value changes → `<change>` elements
   - New properties → `<change>` with `<add_property>`
   - Removed tags from GameplayTagContainers → `<delete>` elements
   - Added tags → `<change>` with tag value
6. Groups changes and generates one `.def` XML file per property group
7. Shows preview/edit window before saving

### Category Detection
Uses a mapping from DataTable filenames to definition categories:
```
DT_Constructions → Building
DT_Weapons → Items
DT_Armor → Items
DT_Storage → Storage
DT_Loot → Loot
DT_Moria_Flora → Flora
```
Falls back to prefix matching for `GE_*` → Buffs, `Curve_*` → Buffs, `Properties_*` → Ores.

### Comparison Algorithm
Handles all UAssetAPI property types:
- **Primitives** (int, float, bool, string) — Direct value comparison
- **ArrayPropertyData / SetPropertyData** — Element-by-element comparison
- **StructPropertyData** — Recursive descent into nested Value arrays
- **GameplayTagContainerPropertyData** — Set comparison of tag string lists, reporting individual additions and removals
- **Generic fallback** — JSON serialization comparison for unhandled types

---

## 10. Import System

### Combined Import Dialog
**File:** `src/ui/combined_import_dialog.py` (841 lines)

Chains game-file import with secrets import into a seamless flow:
1. Extract game assets using `retoc` (IoStore → legacy format)
2. Convert `.uasset` to JSON using UAssetGUI
3. Extract secrets-specific assets
4. Generate manifest files for the build pipeline

### Secrets Import Dialog
**File:** `src/ui/secrets_import_dialog.py` (811 lines)

Handles IoStore extraction specifically for mod ("Secrets") content:
- Detects `.ucas`/`.utoc` files in the game directory
- Runs `retoc to-legacy` with the game's `global.ucas`/`global.utoc` for name resolution
- Converts extracted `.uasset` files to JSON
- Outputs to `Secrets Source/` in AppData

### Import Construction Dialog
**File:** `src/ui/import_construction_dialog.py` (773 lines)

Browse `DT_Constructions.json` to select specific items and generate `.def` files for them.

---

## 11. Custom Widgets

### FilterableComboBox
**File:** `src/ui/filterable_combobox.py` (337 lines)

Drop-in replacement for `CTkComboBox` with type-to-filter functionality:
- Text entry with dropdown arrow button
- Typing filters the option list case-insensitively
- Keyboard navigation (Up/Down/Enter/Escape)
- Scrollable popup for long option lists

### VirtualScrollList
**File:** `src/ui/virtual_scroll_list.py` (390 lines)

Efficient rendering for lists with thousands of items:
- Only renders rows visible in the viewport
- Recycles row widgets as the user scrolls
- Supports checkboxes, click handlers, and filtering
- `height` must be set in the constructor (not `.place()`) for CTk + Python 3.14 compatibility

### HTMLTextRenderer
**File:** `src/ui/html_text_renderer.py` (176 lines)

Renders a subset of HTML into `CTkTextbox`:
- Supported tags: `h1`-`h3`, `p`, `b`/`strong`, `i`/`em`, `ul`, `li`, `br`, `table`/`tr`/`td`
- Uses `tk.Text` tags for formatting

---

## 12. Object Templates

**File:** `src/object_templates.py` (546 lines)

Ported from TobiIchiro/RtoM-Moding-Tool. Creates new DataTable rows by deep-copying JSON templates and modifying properties.

### Key Functions
- `load_json()` / `save_json()` — File I/O with encoding handling
- `gen_unique_tag(base_tag, existing)` — Appends A-Z suffix to avoid name collisions
- `get_existing_row_names(data)` — Extracts all row `Name` values from a DataTable
- `add_string_table_entry()` — Adds display name/description to Architecture.json
- `create_construction_row()` — Creates a row in DT_Constructions.json
- `create_construction_recipe_row()` — Creates a row in DT_ConstructionRecipes.json
- `create_item_recipe_row()` — Creates a row in DT_ItemRecipes.json

Templates are loaded from `docs/templates/` as JSON files.

---

## 13. Data Formats

### UAssetAPI JSON Structure
Game DataTable files exported by UAssetGUI have this structure:
```json
{
  "Imports": [ { "ObjectName": "...", "ClassPackage": "..." } ],
  "Exports": [
    {
      "ObjectName": "Default__DT_Something",
      "Table": {
        "Data": [
          {
            "Name": "RowName",
            "Value": [
              { "Name": "PropertyName", "$type": "TypeName", "Value": ... },
              ...
            ]
          }
        ]
      }
    }
  ]
}
```

### Property Types
- **IntPropertyData** — `"Value": 42`
- **FloatPropertyData** — `"Value": 3.14`
- **BoolPropertyData** — `"Value": true`
- **StrPropertyData / NamePropertyData** — `"Value": "string"`
- **EnumPropertyData** — `"Value": "EEnumType::EnumValue"`
- **ArrayPropertyData** — `"Value": [ ... ]` with typed elements
- **StructPropertyData** — `"Value": [ { nested properties } ]`
- **GameplayTagContainerPropertyData** — `"Value": ["Tag.Name1", "Tag.Name2"]`
- **SoftObjectPropertyData** — `"Value": "/Game/Path/To/Asset"`

### .def XML Format
See [Section 5: Definition Management](#5-definition-management) for the full element reference.

### Prebuilt .ini Format
```ini
[ModInfo]
description = Mod description
author = Author name

[Paths]
category|filename = true

[Settings]
key = value
```

---

## 14. Directory Layout

### Project Structure
```
Moria MOD Creator/
├── main.py                     Entry point
├── src/
│   ├── build_manager.py        Build pipeline
│   ├── config.py               Configuration management
│   ├── constants.py            Project-wide constants
│   ├── definition_manager.py   .def file and checkbox state management
│   ├── object_templates.py     DataTable row creation templates
│   └── ui/
│       ├── main_window.py      Primary application window
│       ├── buildings_view.py   Buildings/Secrets tab
│       ├── constructions_view.py Constructions tab
│       ├── object_editor_view.py Object Editor tab
│       ├── def_creator_view.py   Create DEF tab
│       ├── combined_import_dialog.py  Import workflow
│       ├── secrets_import_dialog.py   Secrets extraction
│       ├── import_construction_dialog.py  Construction import
│       ├── import_dialog.py    Import helpers
│       ├── config_dialog.py    Settings dialog
│       ├── about_dialog.py     About dialog (version source)
│       ├── mod_name_dialog.py  Mod project management
│       ├── construction_name_dialog.py  Construction selector
│       ├── shared_utils.py     Shared utilities
│       ├── filterable_combobox.py  Type-to-filter dropdown
│       ├── virtual_scroll_list.py  Virtual scrolling widget
│       ├── json_convert_dialog.py  JSON conversion progress
│       ├── utility_check_dialog.py Utility verification
│       └── html_text_renderer.py   HTML rendering
├── docs/
│   ├── definitions/            115 reference .def files (14 categories)
│   ├── prebuilt modfiles/      18 prebuilt mod .ini files
│   ├── templates/              JSON templates for object creation
│   ├── New Objects/            Building template data
│   ├── Secrets Source/         Secrets extraction source
│   ├── changeconstructions/    Construction change sets
│   ├── changesecrets/          Secrets change sets
│   └── utilities/              retoc, UAssetGUI, FModel, ZenTools
├── scripts/
│   ├── build_release.py        Full release pipeline
│   ├── cleanup_appdata.py      AppData cleanup utility
│   ├── sign_executable.py      Code signing (SSL.com eSigner)
│   └── refactor_object_editor.py  Refactoring utility
├── tests/                      275 tests across 6 files
├── installer/
│   └── MoriaMODCreator.iss     Inno Setup installer script
└── release/                    Build output directory
```

### AppData Directory (`%APPDATA%/MoriaMODCreator/`)
```
├── config.ini                  Application settings
├── MoriaMODCreator.log         Application log
├── Definitions/                User .def files (14 category subdirs)
├── prebuilt modfiles/          Prebuilt mod .ini files
├── Secrets Source/             Extracted secrets JSON
│   └── jsondata/Moria/Content/ UAssetAPI JSON files
├── cache/
│   ├── constructions/          Cached construction JSON
│   ├── game/                   Cached base-game JSON
│   └── secrets/                Cached secrets JSON per category
├── changeconstructions/        Construction change definitions
├── changesecrets/              Secrets change definitions
├── mymodfiles/                 User mod projects
├── New Objects/                Object creation data
├── utilities/                  Build tool executables
└── output/                     Built mod output
    └── jsondata/               Base-game exported JSON
```

---

## 15. Test Suite

275 tests across 6 test files, all using pytest.

| File | Tests | Coverage Area |
|------|-------|---------------|
| `test_build_manager.py` | 70 | Build phases, progress callbacks, .def processing |
| `test_config.py` | 54 | Path helpers, color schemes, settings, validation |
| `test_definition_manager.py` | 35 | .def parsing, checkbox states, INI persistence |
| `test_shared_utils.py` | 29 | Directory helpers, file conversion, JSON updates |
| `test_buildings_view.py` | 23 | Field extraction, JSON parsing, form rendering |
| `test_main_window.py` | 64 | XML parsing, value lookup, search/replace, version |

Run tests: `python -m pytest tests/ -q`

---

## 16. Build and Release

**Script:** `scripts/build_release.py`

Full release pipeline:
1. PyInstaller → `release/MoriaMODCreator.exe`
2. Code sign the executable (SSL.com eSigner)
3. Create 7 ZIP bundles from `docs/` directory:
   - `Definitions.zip`, `prebuilt_modfiles.zip`, `SecretsSource.zip`
   - `NewObjects.zip`, `utilities.zip`
   - `changeconstructions.zip`, `changesecrets.zip`
4. Inno Setup → `release/MoriaMODCreator_Setup_v{VERSION}.exe`
5. Code sign the installer

Version is sourced from `about_dialog.APP_VERSION` and must also be updated in `installer/MoriaMODCreator.iss`.
