# Moria MOD Creator v2.5.0

Release covering all changes from v1.5 through v2.5.0.

## Object Editor (New — Advanced Tab)

A full **Create/Edit Secret** tab for creating and editing DataTable objects directly in the Secrets Source JSON files.

### Two-Pane Layout
- **Left pane**: Browsable list of mod-only items per category (buildings, weapons, armor, tools, items, flora, loot) with type-to-filter search
- **Right pane**: Structured forms matching the Secrets tab layout with labeled fields, dropdowns, checkboxes, and material rows
- Base-game rows are automatically filtered out so only user-added objects appear

### Per-Category Structured Forms
- **Buildings**: Construction Recipe (placement, materials, unlocks, sandbox) + Construction Definition (actor, icon, tags)
- **Weapons**: Item Recipe + Weapon Definition (damage, speed, durability, armor pen, stamina/energy cost, repair cost)
- **Armor**: Item Recipe + Armor Definition (damage reduction, protection, repair cost)
- **Tools**: Item Recipe + Tool Definition (durability, carve hits, mining rate, stamina/energy cost, repair cost)
- **Items**: Item Recipe + generic Item Definition (portability, stack size, trade value)
- **Flora**: Flora Definition only (growth timing, drop amounts, farming properties)
- **Loot**: Loot Definition only (drop chance, quantity range, required tags)

### New Object Creation
- **Template dropdown**: Construction, Recipe, or Both
- **Construction**: Renders blank recipe + definition forms with game-accurate defaults
- **Recipe**: Blank item recipe form for weapons, armor, tools
- **Both**: Shared Row Name field linked between construction recipe and definition sections
- On save, rows are injected into Secrets Source JSON files (Architecture, Constructions, Recipes)

### Editing and Management
- Click any item to view/edit its properties in structured forms
- Save writes edited values back to JSON with type conversion (int, float, bool, string)
- Delete with confirmation (type DELETE to confirm)
- Display names resolved from string table JSON files

## Search and Replace

- **Search bar** added to Mod Builder, Secrets, Constructions, and Object Editor right panes
- **Three modes**: Search by Property names, Values, or Both via dropdown
- **Substring replacement**: Replace matches within values (not full-value overwrite)
- **Replace All**: Batch replace across all visible fields
- Shared logic centralized in `shared_utils.py`

## Create DEF Improvements

### GameplayTagContainer Support
- Comparison algorithm now detects `GameplayTagContainerPropertyData` changes (previously silently skipped)
- Properly handles individual tag additions and removals within containers like `ExcludeItems` and `AllowedItems`
- Set-based comparison: reports each added/removed tag individually

### Full .def Syntax
- `<delete>` elements for tag removals from containers
- `<change>` elements for value modifications and tag additions
- `<change>` with `<add_property>` for adding new properties
- Handles `SetPropertyData` alongside `ArrayPropertyData`
- Generic fallback for unhandled property types

### Category Detection Fix
- Category now derived from DataTable filename (e.g., `DT_Storage` -> `Storage`) instead of parent directory path (which was always "Items")
- Complete mapping for 20+ DataTable names plus prefix fallbacks (`GE_*` -> Buffs, `Curve_*` -> Buffs, `Properties_*` -> Ores)

## Build Manager Enhancements

- `<delete>` handling widened to work on all GameplayTagContainer properties (not just hardcoded `ExcludeItems`/`AllowedItems`)
- Runtime detection of GameplayTagContainers via `$type`, `StructType`, and inner `Value` markers
- `_is_gameplay_tag_container()` method replaces hardcoded property name checks

## UI Improvements

- **Batch rendering**: 8 cards at a time with font caching for Mod Builder performance
- **Original Value field**: Non-editable field showing the original value in Mod Builder change cards
- **Material rows**: Lazy frame packing — empty materials section takes no space, expands on first "+ Add Material" click
- **Button ordering**: Create/Edit Secret positioned between Secrets and Constructions tabs

## Code Quality

- **Dead code removal**: ~500 lines of unused methods removed across buildings_view, constructions_view, and object_editor_view
- **Removed unused imports**: 7 unused imports cleaned up
- **Narrowed exception handling**: Bare `except` catches replaced with specific exception types
- **Pylint score**: 9.84/10 on object_editor_view, 9.97/10 on other modules
- **Comments overhaul**: Redundant comments stripped, replaced with workflow-focused documentation
- **Application documentation**: New `docs/APPLICATION.md` — comprehensive 16-section technical reference

## Test Suite

- **275 tests** across 6 test files, all passing
- 64 new tests added in `test_main_window.py`: definition XML parsing, original value lookup, search/replace semantics, version validation

## Credits

- Created by John B Owens II
- Create DEF functionality by Sqitey
- Co-Authored-By: Claude Opus 4.6

---

**Full Changelog**: https://github.com/jbowensii/MoriaModCreator/compare/v1.5...v2.5.0
