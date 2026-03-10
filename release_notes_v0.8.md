# Moria MOD Creator v0.8 Beta

## 🎨 Card-Based Mod Builder UI

The Mod Builder tab's right pane has been completely redesigned with a modern card-based interface that better handles complex definition structures.

### New Features
- **Card Layout**: Each change is displayed as a dedicated card with clear type badges
- **Visual Change Types**: Color-coded badges distinguish between CHANGE, ADD PROPERTY, and DELETE operations
- **Inline Editing**: Edit item names, properties, and values directly in the card
- **JSON Editor**: Full JSON editor for `<add_property>` structures with syntax highlighting
- **Improved Readability**: Better organization of complex definition data

### Benefits
- More intuitive for working with multi-element definitions
- Proper display of nested JSON structures
- Clear visual separation between different types of changes
- Easier to understand what each `.def` file will do

## 🪨 Ore Definition Files

Added 35 individual ore definition files for modding voxel drop rates.

### Included Files
All ore types from the game now have dedicated `.def` files:
- Precious gems (Adamant, Amethyst, Diamond, Emerald, Ruby, Sapphire, etc.)
- Metals (Copper, Gold, Iron, Mithril, Silver, Tin, etc.)
- Stone types (Granite, Marble, Obsidian, etc.)
- Special materials (Star Metal, Sun Stone, Resin, etc.)

### Features
- Each file adds `DropRate` property to ore voxel properties
- Uses `<add_property>` XML element for missing properties
- CDATA-wrapped JSON for proper property structures
- Ready-to-use examples for ore drop rate modification

## 🔧 XML `<add_property>` Support

Full support for the new `<add_property>` XML element in definition files.

### Implementation
- **Build Pipeline**: Automatically adds missing properties to JSON files during build
- **UI Display**: Card-based view shows add_property metadata and JSON structure
- **Validation**: Parses and validates property JSON before applying
- **Idempotent**: Safe to run multiple times - won't duplicate properties

### Helper Script
New `helpers/patch_ore_droprates.py` utility:
- Patches ore `Properties_*.json` files to add missing `DropRate` property
- Dry-run mode to preview changes
- Patched 11 ore files that were missing the property

## 🎯 UI Improvements

- **Font Size**: Reduced Mod Builder table font from 20pt to 16pt for better readability
- **Cleaner Layout**: Simplified save button area, removed search (cards are self-contained)
- **Better Scrolling**: Smooth scrolling through card list

## 🔨 Technical Changes

- Updated `_get_definition_changes()` to extract `add_property` metadata
- New `_setup_card_based_view()` replaces table view
- Card-based save functionality with XML generation
- Improved CDATA handling in XML output
- Enhanced build manager to apply `<add_property>` elements

## 📦 Files Changed
- 57 files modified
- 4,356 insertions, 132 deletions
- Version bumped to 0.8 Beta

## 🙏 Credits
Co-Authored-By: Claude Sonnet 4.5

---

**Full Changelog**: https://github.com/jbowensii/MoriaModCreator/compare/v0.7...v0.8
