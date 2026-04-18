# Moria MOD Creator

A native Windows desktop application for creating mods for **Lord of the Rings: Return to Moria**.

![.NET](https://img.shields.io/badge/.NET-10-512BD4.svg)
![Framework](https://img.shields.io/badge/WPF-Windows-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Version](https://img.shields.io/badge/Version-3.0.0-orange.svg)

## Overview

Moria MOD Creator simplifies the process of modding Return to Moria by providing a graphical interface to:
- Import and extract game files (FModel / retoc integration)
- Convert game assets to editable JSON format (UAssetGUI)
- Create mod definitions that specify what values to change
- Edit Buildings, Constructions, Secrets, and Definitions through dedicated tabs
- Build complete mod packages ready for use

> **v3.0.0** is a ground-up rewrite from Python / CustomTkinter to C# / WPF / .NET 10. Faster, native, self-contained — no Python runtime required. The Python implementation is preserved for reference at `old-python-src/`.

## Features

- **Novice / Advanced UI Modes** — card-based mod builder for beginners, full editor for power users
- **Mod Builder (Definitions)** — browse and toggle definition files, edit individual changes with original-value lookup
- **Change Secrets / Change Constructions** — edit recipes, stats, materials, unlocks, tags across 8 categories (Buildings, Weapons, Armor, Tools, Flora, Loot, Items, Ores)
- **Create DEF** — compare modded vs vanilla assets and auto-generate `.def` XML files with metadata, per-change notes, and optional inline comments
- **Import** — extract game files via FModel, convert `.uasset` → JSON via UAssetGUI
- **Build System** — scan definitions → apply changes to JSON → convert back to `.uasset` → package to `.pak`/`.utoc`/`.ucas` → zip
- **Prebuilt Mods** — 18 ready-made mod templates bundled with the installer
- **Global dark theme** — custom WPF ControlTemplates on every control (ComboBox, TextBox watermark, etc.)
- **Structured logging** — `%APPDATA%\MoriaMODCreator\MoriaMODCreator.log`
- **Global crash handling** — unhandled exceptions show a copy-to-clipboard dialog instead of silent termination
- **Signed binaries** — exe + installer signed via SSL.com eSigner

## Installation

### Windows Installer (Recommended)

Download `MoriaMODCreator_Setup_v3.0.0.exe` from the [latest GitHub release](https://github.com/jbowensii/MoriaModCreator/releases/latest). The installer:

- Deploys the signed `MoriaMODCreator.exe` to `%LOCALAPPDATA%\Programs\Moria MOD Creator\`
- Extracts bundled Definitions / Secrets Source / prebuilt mods / utilities to `%APPDATA%\MoriaMODCreator\`
- Creates Start Menu shortcuts (desktop shortcut optional)
- No admin required
- No .NET runtime required — the exe is self-contained

### From Source

```bash
git clone https://github.com/jbowensii/MoriaModCreator.git
cd MoriaModCreator
dotnet build MoriaMODCreator.slnx
dotnet run --project src/MoriaMODCreator/MoriaMODCreator.csproj
```

To produce a release build identical to the installer's:

```bash
dotnet publish src/MoriaMODCreator/MoriaMODCreator.csproj \
    -c Release -r win-x64 --self-contained true \
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true \
    -p:DebugType=None -p:DebugSymbols=false \
    -o release/publish
```

The published exe appears at `release/publish/MoriaMODCreator.exe`.

## Requirements

- **Windows 10 1809+ or Windows 11** (required by .NET 10)
- External utilities (bundled in the installer, or placed manually in `%APPDATA%\MoriaMODCreator\utilities\`):
  - [UAssetGUI](https://github.com/atenfyr/UAssetGUI) — `.uasset` ↔ JSON conversion
  - [retoc](https://github.com/trumank/retoc) — zen-format packaging
  - [FModel](https://fmodel.app/) — game file extraction (optional)
  - [ZenTools](https://github.com/WistfulHopes/ZenTools-UE4) — UE4 zen packaging

For source development: **.NET 10 SDK**.

## Usage

### Getting Started

1. **Import Game Files** — toolbar "Import" button uses FModel to extract `.pak` / `.ucas` / `.utoc` from the installed game
2. **Pick or create a mod** — "Mod Name" button opens the mod picker
3. **Edit** — use the Mod Builder to edit raw `.def` files, or Change Secrets / Change Constructions to visually edit item properties
4. **Build** — "Build" button processes your mod and writes a ready-to-use zip to your Downloads folder

### Mod Definition Files (`.def`)

`.def` files are XML files describing changes to game data:

```xml
<?xml version="1.0" encoding="utf-8"?>
<definition>
    <title>Longer Mining Song Buff</title>
    <author>YourName</author>
    <description>Makes mining song buff last longer</description>
    <mod file="\Moria\Content\Character\Shared\Effects\GE_MiningSong_CompleteBuff.json">
        <change item="GE_MiningSong_CompleteBuff"
                property="DurationMagnitude.ScalableFloatMagnitude.Value"
                value="1800"
                note="balance pass"/>
    </mod>
</definition>
```

Create DEF can generate these automatically by diffing a modded file against the vanilla original.

### Build Output

Clicking **Build**:

1. Scans your selected definitions and loads the targeted JSON files
2. Applies each `<change>` / `<delete>` / `<add_property>` to the corresponding JSON
3. Converts the patched JSON back to `.uasset` via UAssetGUI
4. Packages the result into `.pak` / `.utoc` / `.ucas` via retoc
5. Zips the mod into `%USERPROFILE%\Downloads\{ModName}.zip`

## Project Structure

```
MoriaModCreator/
├── MoriaMODCreator.slnx              # .NET solution file
├── src/                              # C# source (the standard build)
│   ├── .globalconfig                 # Roslyn analyzer config
│   ├── MoriaMODCreator/              # WPF app
│   │   ├── App.xaml / MainWindow.xaml
│   │   ├── Models/                   # Constants, FormField, ModDefinition, PrebuiltMod
│   │   ├── Services/                 # BuildService, ImportService, CategoryDataService,
│   │   │                             #   DiffService, ObjectTemplateService, etc.
│   │   ├── ViewModels/               # NoviceVM, DefinitionsVM, BuildingsVM, DefCreatorVM,
│   │   │                             #   ObjectEditorVM, FormBuilder (shared helpers)
│   │   ├── Views/                    # XAML views + Dialogs
│   │   ├── Converters/               # FormFieldTemplateSelector, StringToBrush, etc.
│   │   └── Resources/                # DarkTheme.xaml (full custom ControlTemplates)
│   └── MoriaMODCreator.Tests/        # xUnit test suite (158 tests)
├── old-python-src/                   # Archived Python implementation (not built)
├── installer/
│   ├── MoriaMODCreator.iss           # Inno Setup script
│   └── *.zip                         # Bundled assets (7 zips: Definitions, Utilities, etc.)
├── docs/                             # Reference definitions + example mods
├── release/                          # Build output (exe + signed installer)
└── release_notes_v3.0.md             # This release's notes
```

## Data Directories

The application stores data in `%APPDATA%\MoriaMODCreator\`:

| Directory | Purpose |
|-----------|---------|
| `Definitions/` | Global definition files (115 .def files in 14 categories) |
| `mymodfiles/` | Per-mod project files (build intermediates) |
| `cache/` | Cached game JSON (constructions, game, secrets) |
| `changeconstructions/` | Construction change definitions and build intermediates |
| `changesecrets/` | Secret change definitions and build intermediates |
| `prebuilt modfiles/` | 18 pre-configured mod `.ini` files |
| `New Objects/` | Custom object/NPC definitions |
| `Secrets Source/` | Secrets `.def` source files |
| `utilities/` | External tools (UAssetGUI, retoc, FModel, ZenTools) |
| `output/` | Build output files |
| `MoriaMODCreator.log` | Application log (structured `ILogger` output) |

## Development

### Tests

```bash
dotnet test MoriaMODCreator.slnx
```

158 xUnit tests cover services, view models, converters, diff round-trips, prefix validation, and more.

### Static Analysis

```bash
dotnet build MoriaMODCreator.slnx -p:AnalysisLevel=latest-all
```

The project builds clean at `latest-all` (the strictest Roslyn analyzer setting) with 0 warnings / 0 errors. Suppression rationale for each disabled rule is documented inline in `src/.globalconfig`.

### Format

```bash
dotnet format MoriaMODCreator.slnx --verify-no-changes
```

## Release Pipeline

1. Bump `AppVersion` in `src/MoriaMODCreator/Models/Constants.cs`, `<Version>` in the `.csproj`, and `#define MyAppVersion` in `installer/MoriaMODCreator.iss`
2. `dotnet publish` (see "From Source" above) → copy `release/publish/MoriaMODCreator.exe` to `release/MoriaMODCreator.exe`
3. Sign the exe via SSL.com eSigner
4. Compile the installer: `ISCC.exe installer/MoriaMODCreator.iss` (Inno Setup 6)
5. Sign the installer
6. Tag + GitHub release:
   ```bash
   git tag -a v3.0.0 -m "..."
   git push origin v3.0.0
   gh release create v3.0.0 release/MoriaMODCreator_Setup_v3.0.0.exe \
       --title "Moria MOD Creator v3.0.0" --notes-file release_notes_v3.0.md
   ```

## Contributing

Contributions are welcome. Please open an issue or pull request at https://github.com/jbowensii/MoriaModCreator.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgments

- Original Python implementation and ongoing design: **John B Owens II** (Mereak Firmaxe)
- "Create DEF" feature: **Sqitey**
- [UAssetGUI](https://github.com/atenfyr/UAssetGUI) — uasset/JSON conversion
- [retoc](https://github.com/trumank/retoc) — zen format packaging
- [FModel](https://fmodel.app/) — game file extraction
- [ZenTools](https://github.com/WistfulHopes/ZenTools-UE4) — UE4 zen packaging
- [.NET Community Toolkit MVVM](https://github.com/CommunityToolkit/dotnet) — MVVM source generators

## Disclaimer

This tool is for personal use only. Always respect the game's terms of service and the rights of the developers.
