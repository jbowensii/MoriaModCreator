"""JSON conversion dialog for converting uasset files to JSON."""

import configparser
import json
import logging
import subprocess
import threading
import queue
from collections import defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import customtkinter as ctk

from src.config import get_output_dir, get_utilities_dir, get_appdata_dir
from src.ui.utility_check_dialog import find_utility


logger = logging.getLogger(__name__)

from src.config import get_max_workers

# File extensions to convert
UASSET_EXTENSIONS = {".uasset", ".umap"}

# Buildings cache filename
BUILDINGS_CACHE_FILENAME = "buildings_cache.ini"


def get_retoc_dir() -> Path:
    """Get the retoc output directory."""
    return get_output_dir() / "retoc"


def get_jsondata_dir() -> Path:
    """Get the JSON data output directory."""
    return get_output_dir() / "jsondata"


def get_buildings_cache_path() -> Path:
    """Get path to buildings INI cache file."""
    return get_appdata_dir() / "New Objects" / "Build" / BUILDINGS_CACHE_FILENAME


def update_buildings_ini_from_json() -> tuple[bool, str]:
    """Scan DT_ConstructionRecipes.json and update the buildings INI cache.

    This reads the game's JSON file and adds values to the buildings INI file,
    ensuring no duplicates per section.

    Returns:
        Tuple of (success, message)
    """
    # Path to the DT_ConstructionRecipes.json
    recipes_path = (get_jsondata_dir() / 'Moria' / 'Content' / 'Tech' / 'Data'
                    / 'Building' / 'DT_ConstructionRecipes.json')

    if not recipes_path.exists():
        return (False, f"DT_ConstructionRecipes.json not found at {recipes_path}")

    try:
        # Load the JSON file
        with open(recipes_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Collect values from NameMap
        collected = defaultdict(set)
        name_map = data.get('NameMap', [])

        for name in name_map:
            # Skip system names
            if name.startswith('/') or name.startswith('$'):
                continue
            if name in ('ArrayProperty', 'BoolProperty', 'IntProperty', 'FloatProperty',
                        'StructProperty', 'ObjectProperty', 'EnumProperty', 'NameProperty',
                        'TextProperty', 'SoftObjectProperty', 'ByteProperty', 'StrProperty',
                        'None', 'Object', 'Class', 'Package', 'Default__DataTable',
                        'DataTable', 'ScriptStruct', 'BlueprintGeneratedClass', 'RowStruct',
                        'RowName', 'ArrayIndex', 'IsZero', 'PropertyTagFlags', 'Value'):
                continue

            # Categorize by pattern
            if name.startswith('E') and '::' in name:
                # Enum value
                enum_type = name.split('::')[0]
                collected[f'Enum_{enum_type}'].add(name)
            elif name.startswith('UI.') and 'Category' in name:
                collected['Tags'].add(name)
            elif name.startswith('Item.'):
                collected['Items'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Ore.'):
                collected['Ores'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Consumable.'):
                collected['Consumables'].add(name)
                collected['Materials'].add(name)
            elif name.startswith('Tool.'):
                collected['Tools'].add(name)
            elif name.startswith('Decoration'):
                collected['Decorations'].add(name)
            elif name.endswith('_Fragment'):
                collected['Fragments'].add(name)
                collected['UnlockRequiredFragments'].add(name)
            elif name.startswith('b') and len(name) > 1 and name[1].isupper():
                # Boolean property name - skip
                pass
            elif name.startswith('Mor'):
                # Moria type name - skip
                pass
            elif name.startswith('/Game/'):
                # Asset path
                collected['Actors'].add(name)
            elif '_' in name and not name.startswith('Default'):
                # Likely a construction/building name
                if name[0].isupper():
                    collected['Constructions'].add(name)
                    collected['ResultConstructions'].add(name)
            elif name and name[0].isupper() and not name.startswith('Default'):
                # Could be a construction name
                collected['Constructions'].add(name)

        # Load existing INI file if it exists
        cache_path = get_buildings_cache_path()
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        if cache_path.exists():
            config.read(cache_path, encoding='utf-8')

        # Merge new values with existing, ensuring no duplicates
        total_added = 0
        for section, new_values in collected.items():
            # Get existing values for this section
            existing_values = set()
            if config.has_section(section):
                existing_str = config.get(section, 'values', fallback='')
                existing_values = {v.strip() for v in existing_str.split('|') if v.strip()}
            else:
                config.add_section(section)

            # Merge and deduplicate
            merged = existing_values | new_values
            total_added += len(new_values - existing_values)

            # Save back as sorted, pipe-separated values
            config.set(section, 'values', '|'.join(sorted(merged)))

        # Write the updated INI file
        with open(cache_path, 'w', encoding='utf-8') as f:
            config.write(f)

        logger.info(f"Updated buildings cache: added {total_added} new values to {len(collected)} sections")
        return (True, f"Updated buildings cache with {total_added} new values")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse DT_ConstructionRecipes.json: {e}")
        return (False, f"JSON parse error: {e}")
    except Exception as e:
        logger.error(f"Error updating buildings INI: {e}")
        return (False, f"Error: {e}")


def check_jsondata_exists() -> bool:
    """Check if JSON data directory exists and has files."""
    jsondata_dir = get_jsondata_dir()
    if not jsondata_dir.exists():
        return False
    # Check if there's at least one JSON file
    try:
        next(jsondata_dir.rglob("*.json"))
        return True
    except StopIteration:
        return False


def get_files_to_convert() -> list[Path]:
    """Get list of uasset/umap files that need conversion."""
    retoc_dir = get_retoc_dir()
    if not retoc_dir.exists():
        return []

    files = []
    for ext in UASSET_EXTENSIONS:
        files.extend(retoc_dir.rglob(f"*{ext}"))
    return files


def convert_file_to_json(
    uassetgui_path: Path,
    source_file: Path,
    retoc_dir: Path,
    jsondata_dir: Path,
) -> tuple[bool, str]:
    """Convert a single uasset file to JSON.

    Args:
        uassetgui_path: Path to UAssetGUI.exe
        source_file: Path to the source uasset file
        retoc_dir: Base retoc directory
        jsondata_dir: Base JSON output directory

    Returns:
        Tuple of (success, message)
    """
    try:
        # Calculate relative path and destination
        rel_path = source_file.relative_to(retoc_dir)
        dest_file = jsondata_dir / rel_path.with_suffix(".json")

        # Create destination directory if needed
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        # Skip if already converted
        if dest_file.exists():
            return (True, f"Skipped (exists): {rel_path}")

        # Run UAssetGUI tojson command
        cmd = [
            str(uassetgui_path),
            "tojson",
            str(source_file),
            str(dest_file),
            "VER_UE4_27"
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )

        if result.returncode == 0 and dest_file.exists():
            return (True, f"Converted: {rel_path}")
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            return (False, f"Failed: {rel_path} - {error_msg}")

    except subprocess.TimeoutExpired:
        return (False, f"Timeout: {source_file.name}")
    except Exception as e:
        return (False, f"Error: {source_file.name} - {str(e)}")


class JsonConvertDialog(ctk.CTkToplevel):
    """Dialog for converting uasset files to JSON."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Converting to JSON")
        self.geometry("550x200")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 550) // 2
        y = (self.winfo_screenheight() - 200) // 2
        self.geometry(f"550x200+{x}+{y}")

        # Result tracking
        self.result = False
        self.cancelled = False
        self.conversion_thread = None
        self.update_queue = queue.Queue()

        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Start conversion automatically
        self.after(100, self._start_conversion)

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Converting Game Data to JSON",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.pack(pady=(0, 15))

        # Status message
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Preparing conversion...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(main_frame, width=400)
        self.progress_bar.pack(pady=(0, 10))
        self.progress_bar.set(0)

        # Progress text (X of Y files)
        self.progress_text = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.progress_text.pack(pady=(0, 15))

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            main_frame,
            text="CANCEL",
            command=self._on_cancel,
            fg_color="#dc3545",
            hover_color="#c82333",
            text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=36
        )
        self.cancel_btn.pack()

    def _start_conversion(self):
        """Start the conversion process in a background thread."""
        self.conversion_thread = threading.Thread(target=self._run_conversion, daemon=True)
        self.conversion_thread.start()
        self._check_queue()

    def _check_queue(self):
        """Check the update queue for progress updates."""
        try:
            while True:
                msg_type, data = self.update_queue.get_nowait()

                if msg_type == "status":
                    self.status_label.configure(text=data)
                elif msg_type == "progress":
                    current, total = data
                    if total > 0:
                        self.progress_bar.set(current / total)
                        self.progress_text.configure(text=f"{current} of {total} files")
                elif msg_type == "done":
                    self.result = data
                    self.destroy()
                    return
                elif msg_type == "error":
                    self.status_label.configure(text=data, text_color="red")

        except queue.Empty:
            pass

        if not self.cancelled:
            self.after(100, self._check_queue)

    def _run_conversion(self):
        """Run the conversion process (called in background thread)."""
        try:
            # Find UAssetGUI
            utilities_dir = get_utilities_dir()
            uassetgui_path = find_utility(utilities_dir, "UAssetGUI.exe")

            if not uassetgui_path:
                self.update_queue.put(("error", "UAssetGUI.exe not found!"))
                self.update_queue.put(("done", False))
                return

            # Get files to convert
            self.update_queue.put(("status", "Scanning for files..."))
            files = get_files_to_convert()

            if not files:
                self.update_queue.put(("status", "No files to convert"))
                self.update_queue.put(("done", True))
                return

            total_files = len(files)
            max_workers = get_max_workers()
            self.update_queue.put(
                ("status", f"Converting {total_files} files using {max_workers} parallel processes...")
            )
            self.update_queue.put(("progress", (0, total_files)))

            retoc_dir = get_retoc_dir()
            jsondata_dir = get_jsondata_dir()
            jsondata_dir.mkdir(parents=True, exist_ok=True)

            completed = 0
            failed = 0

            # Use ThreadPoolExecutor for parallel processing
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all conversion tasks
                future_to_file = {
                    executor.submit(
                        convert_file_to_json,
                        uassetgui_path,
                        f,
                        retoc_dir,
                        jsondata_dir
                    ): f for f in files
                }

                # Process completed tasks
                for future in as_completed(future_to_file):
                    if self.cancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.update_queue.put(("done", False))
                        return

                    success, _ = future.result()
                    completed += 1
                    if not success:
                        failed += 1

                    self.update_queue.put(("progress", (completed, total_files)))

                    # Update status periodically
                    if completed % 10 == 0 or completed == total_files:
                        self.update_queue.put(
                            ("status", f"Converted {completed}/{total_files} files ({failed} failed)")
                        )

            # Done with file conversion
            if failed > 0:
                self.update_queue.put(("status", f"Completed with {failed} failures"))
            else:
                self.update_queue.put(("status", "Conversion complete!"))

            # Update buildings INI cache from the converted JSON
            self.update_queue.put(("status", "Updating buildings cache..."))
            ini_success, ini_message = update_buildings_ini_from_json()
            if ini_success:
                self.update_queue.put(("status", f"Done! {ini_message}"))
            else:
                logger.warning(f"Buildings INI update: {ini_message}")

            self.update_queue.put(("done", True))

        except Exception as e:
            self.update_queue.put(("error", f"Error: {str(e)}"))
            self.update_queue.put(("done", False))

    def _on_cancel(self):
        """Handle cancel button click."""
        self.cancelled = True
        self.result = False
        self.destroy()


def show_json_convert_dialog(parent: ctk.CTk) -> bool:
    """Show the JSON conversion dialog and wait for it to close.

    Args:
        parent: The parent window.

    Returns:
        True if conversion completed, False if user cancelled.
    """
    dialog = JsonConvertDialog(parent)
    parent.wait_window(dialog)
    return dialog.result
