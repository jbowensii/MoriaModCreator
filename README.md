# Moria MOD Creator

A desktop application for creating mods for **Lord of the Rings: Return to Moria**.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Version](https://img.shields.io/badge/Version-1.1-orange.svg)

## Overview

Moria MOD Creator simplifies the process of modding Return to Moria by providing a graphical interface to:
- Import and extract game files
- Convert game assets to editable JSON format
- Create mod definitions that specify what values to change
- Edit Buildings, Constructions, and Secrets with dedicated tabs
- Build complete mod packages ready for use

## Features

- **Novice / Advanced UI Modes** - Simplified card-based mod builder for beginners, full editor for power users
- **Buildings Tab** - Edit item properties, stack sizes, durability, loot tables, and more
- **Constructions Tab** - Edit construction recipes, costs, building properties
- **Secrets Tab** - Edit secrets and hidden game content
- **File Import** - Import game files using FModel integration
- **JSON Conversion** - Convert `.uasset` files to editable JSON format using UAssetGUI
- **Mod Definition Editor** - Create and manage `.def` files that define mod changes
- **Build System** - Process definitions, modify JSON, convert back to game format, and package as a zip
- **Prebuilt Mods** - 16 ready-made mods replicating popular Nexus mods
- **Filterable Dropdowns** - Type-to-filter combo boxes for quick item selection
- **Combined Import** - Import constructions and secrets from game data with one dialog

## Installation

### Windows Installer (Recommended)

Download the latest `MoriaMODCreator_Setup_v1.1.exe` from [GitHub Releases](https://github.com/jbowensii/MoriaModCreator/releases). The installer bundles all required utilities and definition files.

### From Source

1. Clone the repository:
   ```bash
   git clone https://github.com/jbowensii/MoriaModCreator.git
   cd MoriaModCreator
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Place required utilities in `%APPDATA%\MoriaMODCreator\utilities\`

5. Run the application:
   ```bash
   python main.py
   ```

## Requirements

- Python 3.10 or higher
- Windows OS
- The following utilities (placed in `%APPDATA%\MoriaMODCreator\utilities\`):
  - [UAssetGUI](https://github.com/atenfyr/UAssetGUI) - For JSON/uasset conversion
  - [retoc](https://github.com/trumank/retoc) - For creating zen format packages
  - [FModel](https://fmodel.app/) - For extracting game files (optional, for import feature)
  - [ZenTools](https://github.com/WistfulHopes/ZenTools-UE4) - For UE4 zen packaging

## Usage

### Getting Started

1. **Import Game Files** - Click the Import button to extract game files using FModel
2. **Convert to JSON** - Convert the extracted `.uasset` files to JSON format
3. **Create a Mod** - Use "My Mods" dropdown to create a new mod project
4. **Add Definitions** - Create `.def` files or use the built-in tabs to edit values
5. **Build** - Click Build to process your mod and create a ready-to-use zip file

### Mod Definition Files (.def)

Definition files are XML files that specify what changes to make to game data:

```xml
<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>Makes mining song buff last longer</description>
    <author>YourName</author>
    <mod file="\Moria\Content\Character\Shared\Effects\GE_MiningSong_CompleteBuff.json">
        <object name="GE_MiningSong_CompleteBuff">
            <change property="DurationMagnitude.ScalableFloatMagnitude.Value" value="1800" />
        </object>
    </mod>
</definition>
```

### Build Output

When you click Build, the application:
1. Copies and modifies JSON files based on your definitions
2. Converts JSON back to `.uasset` format
3. Packages assets into zen format (`.utoc`/`.ucas`/`.pak`)
4. Creates a zip file in your Downloads folder

## Project Structure

```
MoriaModCreator/
├── main.py                          # Application entry point
├── requirements.txt                 # Python dependencies
├── assets/                          # Icons and images
│   ├── icons/
│   └── images/
├── src/
│   ├── build_manager.py             # Build pipeline logic
│   ├── config.py                    # Configuration management
│   ├── constants.py                 # Application constants
│   ├── definition_manager.py        # .def file handling
│   └── ui/
│       ├── main_window.py           # Main application window
│       ├── buildings_view.py        # Buildings tab
│       ├── constructions_view.py    # Constructions tab
│       ├── about_dialog.py          # Help/About dialog
│       ├── config_dialog.py         # Settings dialog
│       ├── import_dialog.py         # File import dialog
│       ├── combined_import_dialog.py # Combined import dialog
│       ├── secrets_import_dialog.py # Secrets import dialog
│       ├── import_construction_dialog.py # Construction import
│       ├── json_convert_dialog.py   # JSON conversion dialog
│       ├── mod_name_dialog.py       # Mod naming dialog
│       ├── filterable_combobox.py   # Type-to-filter dropdown
│       ├── shared_utils.py          # Shared UI utilities
│       ├── html_text_renderer.py    # HTML rendering
│       └── utility_check_dialog.py  # Utility validation
├── tests/                           # Test suite (211 tests)
├── scripts/                         # Build and release scripts
├── helpers/                         # Developer utility scripts
├── installer/                       # Inno Setup script and zip bundles
└── docs/                            # Documentation and example mods
    ├── definitions/                 # Reference .def files
    └── Ready Made Mods/             # 14 pre-built example mods
```

## Data Directories

The application stores data in `%APPDATA%\MoriaMODCreator\`:

| Directory | Purpose |
|-----------|---------|
| `Definitions/` | Global definition files |
| `mymodfiles/` | Per-mod project files |
| `cache/` | Cached game JSON (constructions, game, secrets) |
| `changeconstructions/` | Construction change definitions and build intermediates |
| `changesecrets/` | Secret change definitions and build intermediates |
| `prebuilt modfiles/` | Pre-configured mod .ini files |
| `New Objects/` | Custom object/NPC definitions |
| `Secrets Source/` | Secrets .def source files |
| `utilities/` | External tools (UAssetGUI, retoc, FModel, ZenTools) |
| `output/` | Build output files |

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

Bug reports: https://github.com/jbowensii/MoriaModCreator/issues

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [UAssetGUI](https://github.com/atenfyr/UAssetGUI) - For uasset/JSON conversion
- [retoc](https://github.com/trumank/retoc) - For zen format packaging
- [FModel](https://fmodel.app/) - For game file extraction
- [ZenTools](https://github.com/WistfulHopes/ZenTools-UE4) - For UE4 zen packaging
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern UI framework

## Disclaimer

This tool is for personal use only. Always respect the game's terms of service and the rights of the developers.
