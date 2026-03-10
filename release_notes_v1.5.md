# Moria MOD Creator v1.5

## Create DEF Tab (New)

A new **Create DEF** tab under Advanced mode enables automatic generation of `.def` definition files from IoStore mods.

### IoStore Extraction Pipeline
- **Automatic extraction**: Detects `.ucas`/`.utoc` IoStore mod files and runs the full conversion pipeline (retoc to-legacy → UAssetGUI tojson)
- **Persistent output**: Extraction outputs are saved to `retoc/` and `jsondata/` subdirectories inside the Modded Files Folder (not a temp directory), so results persist for inspection
- **Global file resolution**: Automatically copies the game's `global.ucas`/`global.utoc` for retoc name resolution

### Comparison & DEF Generation
- **JSON diff comparison**: Compares modded JSON against vanilla game JSON to identify changes
- **Automatic .def creation**: Generates properly formatted `.def` XML files with correct `<change>`, `<add_property>`, and CDATA structures
- **Smart category detection**: Uses the last path component (e.g., "Effects" from `Moria\Content\Items\Effects\DT_ItemTint.json`) for category assignment
- **Batch save**: "Save All .def Files" writes definitions to the Definitions directory and generates a prebuilt `.ini` file

### UI
- **Larger fonts**: Log and Preview textboxes use doubled font size (22pt) for readability
- **Detailed logging**: Full path logging for all save operations

## New Mod Content

- **More Wardrobe Colors**: Added 5 definition files for the "More Wardrobe Colors" mod (Effects category) and prebuilt `.ini` file
  - DT_ItemTint: EnabledState, Icon, RequiredMaterials, TintColor, TintName

## Docs Cleanup

- **Removed legacy directory**: Deleted `docs/Ready Made Mods/` (replaced by `docs/prebuilt modfiles/`)
- **Updated installer zips**: All 7 installer zip bundles regenerated with current content

## Build Pipeline Fix

- **Dynamic installer version**: `build_release.py` now reads the installer version from `about_dialog.py` instead of using a hardcoded value

## Credits

- **Create DEF functionality by Sqitey** — added to the About dialog credits
- Co-Authored-By: Claude Opus 4.6

---

**Full Changelog**: https://github.com/jbowensii/MoriaModCreator/compare/v1.1...v1.5
