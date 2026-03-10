# Moria MOD Creator v1.2

## Performance Improvements

- **Fast form display**: Clicking items in the left pane now loads the right pane form significantly faster. Form rendering is deferred so the list highlight updates immediately, and the form is hidden during widget reconstruction to eliminate intermediate repaints.
- **JSON row caching**: Game data JSON files are parsed once and cached in memory. Subsequent item clicks do a simple dict lookup instead of re-reading large files from disk. Cache is automatically invalidated on refresh.

## Virtual Scroll List

- **Fixed blank list display**: Resolved a Python 3.14 + CustomTkinter incompatibility where `height` and `width` arguments passed to `.place()` caused a `ValueError`. Widget dimensions are now set at construction time.
- **Full viewport coverage**: The secrets/constructions list now fills the available height instead of showing only 5 items.
- **Eliminated white bar**: Background color of the viewport frame now syncs with the canvas to match the current theme.

## Import Pipeline Fixes

- **GitHub ZIP cleanup**: The upfront cleanup phase now removes ALL ZIP files from Secrets Source, including the GitHub ZIP. Previously the GitHub ZIP was skipped, causing stale data on re-import.
- **Consistent ZIP cleanup**: Both the combined import dialog and the Advanced path use the same cleanup logic.

## UI Improvements

- **Blank prefix on startup**: The "Change Secrets" and "Change Constructions" text fields now start empty until the user explicitly selects a prefix, instead of auto-loading the last used value.
- **Always-fresh cache on tab switch**: Clicking category tabs (Buildings, Weapons, Armor, etc.) in both Advanced Secrets and Advanced Constructions now always refreshes the cache from source files.
- **DLC content support**: Added DLC brew buff duration and book buff definition files (community contribution by Letimineur).

## Code Quality

- **Pylint score**: 9.97/10 (up from 9.77)
- **All 211 tests passing**
- **Removed unused imports and overly broad exception handling**
- **Updated in-code documentation for accuracy**
