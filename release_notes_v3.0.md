# Moria MOD Creator v3.0.0

**Release date:** April 2026
**Previous release:** [v2.10.0](https://github.com/jbowensii/MoriaModCreator/releases/tag/v2.10.0) (April 6, 2026)

v3.0.0 is a **major release**: the entire application has been rewritten from Python / CustomTkinter to C# / WPF / .NET 10. The Python implementation is archived (not deleted) under `old-python-src/` for reference. The new build is faster, native, self-contained, and no longer requires a Python runtime.

---

## Highlights

- **Full C# / WPF rewrite on .NET 10** — native Windows app, no Python or CustomTkinter required
- **Feature parity with Python across all Advanced tabs** — Mod Builder, Change Secrets, Change Constructions, Create DEF
- **Self-contained installer** — single `.exe` bundled with the .NET runtime; no prerequisites
- **Hardened security** — zip-slip guard on all archive extraction; path-traversal validation on user-entered prefixes
- **Structured logging** — all services + ViewModels log through `ILogger`, output captured to `%APPDATA%\MoriaMODCreator\MoriaMODCreator.log`
- **Global crash handling** — unhandled exceptions on any thread (UI, background, unobserved Task) surface a copy-to-clipboard crash dialog instead of silent termination
- **Signed executable + installer** — SSL.com code-signing on both binaries

---

## New features vs v2.10.0

### Advanced UI

- **Create DEF tab** — added **Description**, **Change Note**, and **Include Comments** fields (Python parity). The `changeNote` attribute is only applied to `<change>` elements (not `<delete>`). Layout rewritten as a single centered scrollable column matching the Python reference.
- **Change Secrets / Change Constructions** — prefix dialog split into two mode-specific dialogs with combobox-of-existing + "Or new prefix" text entry + Delete/Set/Cancel buttons (Python parity). Path-traversal validation on Create; defense-in-depth path-boundary check on Delete; combobox selection cleared after removal.
- **Mod Builder (Definitions view)** — `<add_property>` elements are now correctly nested inside `<change>` with JSON text content, matching the Python `build_manager` schema. Previous C# output was self-consistent but incompatible with the Python build pipeline.
- **Object Editor** — new view-model infrastructure for creating secrets-source items (8 categories: Buildings, Weapons, Armor, Tools, Flora, Loot, Items, Ores). Shared `FormBuilder` helpers extracted from `BuildingsViewModel`. The toolbar button is **intentionally hidden in v3.0.0 pending final UX review** — the view, VM, commands, and DI wiring are all in place; flip `Visibility="Collapsed"` → `"Visible"` in `MainWindow.xaml` to re-enable.
- **All TextBox inputs** — support `Tag`-driven watermark/placeholder text via a dark-themed custom ControlTemplate.
- **Dropdowns** — global dark `ComboBox` ControlTemplate with `PART_EditableTextBox`, type-to-filter, and "click to open" behavior.

### Platform & build

- **.NET 10** target framework (`net10.0-windows`)
- **Self-contained single-file publish** — `dotnet publish -c Release -r win-x64 --self-contained true /p:PublishSingleFile=true`
- **New solution layout** — C# source at `src/`, solution file `MoriaMODCreator.slnx` at repo root
- **Archived Python** — moved to `old-python-src/` for historical reference
- **Version metadata** — `<Version>3.0.0</Version>` baked into the exe's file-version properties (Windows Explorer shows it correctly)

### Diagnostics

- **Structured logging** in `BuildingsViewModel` and `ObjectEditorViewModel` — silent `catch { }` blocks in material-section parsing and dropdown-option scanning are now `_logger.LogWarning` calls that capture the exception and context.
- **ImportService `.def` parse failures** now log via `XmlException` / `IOException` rather than being silently dropped.

### Safety

- **Zip-slip / path-traversal** hardening in `ImportService.ExtractGitHubJsonFiles` and `ExtractCompanionPaksFromNexusZip` via a new `SafeCombine` helper. Entries containing `..\` segments or absolute paths are rejected.
- **Prefix dialog validation** — rejects names with invalid filename chars, `..`, or rooted paths. Delete verifies the resolved path stays within the Secrets/Constructions root before removing.

---

## Fixes

- **Display name resolution** — `CategoryDataService.ResolveDisplayName` correctly extracts `DisplayName` when the value is a plain string (previous `is JsonNode` check always failed since `ExtractPropertyValue` returns `string` for `TextPropertyData`).
- **Diff output** — `DiffService.FormatValue` no longer emits raw JSON blobs for struct / SoftObject array elements. Extracts `RowName` from DataTableRowHandle structs, `AssetName` from SoftObjectPath, `CultureInvariantString` from FText, and falls back to a `k=v, k=v` summary.
- **Tag extraction** — `ObjectTemplateService.ExtractTagNames` tolerates wrapped `NamePropertyData` entries (used to crash with `GetValue<string>()` on non-string tokens when loading Tools/Weapons).
- **Float / Int parsing** — safe extraction with typed fallbacks to `ToString()` for `"None"`-string values that previously crashed form rendering.
- **WPF ComboBox dropdown** — fully dark-themed via custom ControlTemplate (WPF system-color overrides don't propagate to the default ComboBox popup).

---

## Internal / developer-facing

- **Test coverage**: 158 xUnit tests covering services, ViewModels, converters, extraction, round-trip schemas, prefix validation
- **Static analysis**: builds clean at `AnalysisLevel=latest-all` (0 warnings, 0 errors) — suppression rationale documented inline in `src/.globalconfig`
- **Format**: `dotnet format --verify-no-changes` clean
- **Extracted `FormBuilder`** in `src/MoriaMODCreator/ViewModels/FormBuilder.cs` — shared form-field builders used by both Buildings and Object Editor view models

---

## Breaking changes

- **Python app no longer shipped.** The `.exe` in the installer is C#/WPF, not PyInstaller. If you had scripts or shortcuts pointing at the old `MoriaMODCreator.exe` PyInstaller output, they continue to work because the filename is unchanged — but the Python source tree is no longer at `src/`, it's at `old-python-src/`.
- **Minimum OS**: Windows 10 1809+ (required by .NET 10). Windows 7/8 users on the Python build are not supported by v3.0.0.

---

## Known limitations

- **Create/Edit Secret button is hidden** pending final UX review (see above). All underlying code is preserved.
- **Mod Builder right-pane Search & Replace bar** — present in Python, not yet in C# (tracked for v3.1).
- **Form builder duplication** — ~500 lines shared between `BuildingsViewModel` and `ObjectEditorViewModel` tracked as tech debt; planned `CategoryFormBuilder` extraction in v3.1.

---

## Install & upgrade

- Run `MoriaMODCreator_Setup_v3.0.0.exe` — installs to `%LOCALAPPDATA%\Programs\Moria MOD Creator\` (no admin required)
- First launch extracts bundled Definitions / Secrets Source / Utilities / prebuilt mod files into `%APPDATA%\MoriaMODCreator\`
- Existing `%APPDATA%\MoriaMODCreator\` data from v2.x is preserved — your mods, prefixes, and edits continue working

---

## Acknowledgments

Original Python implementation: John B Owens II (Mereak Firmaxe)
C# rewrite: collaborative effort
Create DEF feature: Sqitey (retained from Python)

🤖 Release prepared with [Claude Code](https://claude.com/claude-code)
