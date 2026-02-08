"""Import dialog for running retoc to import game files and convert to JSON.

This module scans all .def files in the Definitions directory to find
which game files are actually needed. It also checks for an optional
includes.xml file in the Definitions directory for additional files to import.
It then uses retoc to extract those specific files from the game (silently
skipping any that don't exist), and finally converts them to JSON using UAssetGUI.
"""

import logging
import shutil
import subprocess
import threading
import queue
import xml.etree.ElementTree as ET
from pathlib import Path
try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

import customtkinter as ctk

from src.config import get_utilities_dir, get_output_dir, get_game_install_path, get_appdata_dir, get_max_workers
from src.ui.shared_utils import (
    get_retoc_dir, get_jsondata_dir, get_files_to_convert, update_buildings_ini_from_json,
)


logger = logging.getLogger(__name__)


def check_retoc_output_exists() -> bool:
    """Check if retoc output directory exists and has files."""
    retoc_dir = get_output_dir() / "retoc"
    if not retoc_dir.exists():
        return False
    # Check if directory has any files
    try:
        return any(retoc_dir.iterdir())
    except OSError:
        return False


def scan_def_files_for_mod_paths() -> set[str]:
    """Scan all .def files in Definitions directory and extract mod file paths.

    Returns:
        Set of unique file paths (as they appear in the .def files, with .json extension)
    """
    definitions_dir = get_appdata_dir() / "Definitions"
    mod_paths = set()

    if not definitions_dir.exists():
        logger.warning("Definitions directory does not exist: %s", definitions_dir)
        return mod_paths

    # Find all .def files
    for def_file in definitions_dir.rglob("*.def"):
        try:
            tree = ET.parse(def_file)
            root = tree.getroot()

            # Find all <mod file="..."> elements
            for mod_element in root.findall('.//mod'):
                file_attr = mod_element.get('file', '').strip()
                if file_attr:
                    mod_paths.add(file_attr)

        except ET.ParseError as e:
            logger.warning("Failed to parse %s: %s", def_file.name, e)
        except OSError as e:
            logger.warning("Error reading %s: %s", def_file.name, e)

    logger.info("Found %d unique mod file paths from .def files", len(mod_paths))
    return mod_paths


def scan_includes_xml_for_mod_paths() -> set[str]:
    """Scan includes.xml in Definitions directory and extract mod file paths.

    The includes.xml file uses the same format as .def files with <mod file="..."> elements.
    Files listed here may or may not exist in the game, so callers should handle missing files.

    Returns:
        Set of unique file paths (as they appear in includes.xml, with .json extension)
    """
    definitions_dir = get_appdata_dir() / "Definitions"
    includes_file = definitions_dir / "includes.xml"
    mod_paths = set()

    if not includes_file.exists():
        logger.debug("includes.xml does not exist: %s", includes_file)
        return mod_paths

    try:
        tree = ET.parse(includes_file)
        root = tree.getroot()

        # Find all <mod file="..."> elements
        for mod_element in root.findall('.//mod'):
            file_attr = mod_element.get('file', '').strip()
            if file_attr:
                mod_paths.add(file_attr)

        logger.info("Found %d mod file paths from includes.xml", len(mod_paths))

    except ET.ParseError as e:
        logger.warning("Failed to parse includes.xml: %s", e)
    except OSError as e:
        logger.warning("Error reading includes.xml: %s", e)

    return mod_paths


def convert_json_path_to_uasset(json_path: str) -> str:
    """Convert a .json mod path to the corresponding .uasset game file path.

    Args:
        json_path: Path like "Moria\\Content\\Tech\\Data\\Building\\DT_Items.json"

    Returns:
        Path like "Moria\\Content\\Tech\\Data\\Building\\DT_Items.uasset"
    """
    # Normalize path separators
    normalized = json_path.replace('/', '\\')

    # Change extension from .json to .uasset
    if normalized.lower().endswith('.json'):
        normalized = normalized[:-5] + '.uasset'

    return normalized


def get_game_file_paths_to_import() -> list[str]:
    """Get the list of game file paths that need to be imported.

    Scans all .def files and includes.xml, returns the corresponding .uasset paths.

    Returns:
        List of unique .uasset file paths relative to game directory
    """
    # Get paths from .def files
    mod_paths = scan_def_files_for_mod_paths()

    # Also get paths from includes.xml (these may or may not exist in game)
    includes_paths = scan_includes_xml_for_mod_paths()
    mod_paths.update(includes_paths)

    # Convert each .json path to .uasset
    uasset_paths = set()
    for json_path in mod_paths:
        uasset_path = convert_json_path_to_uasset(json_path)
        uasset_paths.add(uasset_path)

    return sorted(uasset_paths)


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
    except OSError as e:
        return (False, f"Error: {source_file.name} - {str(e)}")


class ImportDialog(ctk.CTkToplevel):
    """Dialog showing progress of game file import and conversion."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Importing Game Files")
        self.geometry("550x220")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 550) // 2
        y = (self.winfo_screenheight() - 220) // 2
        self.geometry(f"550x220+{x}+{y}")

        # Result tracking
        self.result = False
        self.cancelled = False
        self.import_thread = None
        self.update_queue = queue.Queue()

        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Start import automatically
        self.after(100, self._start_import)

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        self.title_label = ctk.CTkLabel(
            main_frame,
            text="Importing Game Files",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(pady=(0, 10))

        # Status message
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Scanning .def files for required game files...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 5))

        # Current file label
        self.file_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.file_label.pack(pady=(0, 10))

        # Progress bar
        self.progress = ctk.CTkProgressBar(main_frame, mode="determinate", width=450)
        self.progress.pack(pady=(0, 10))
        self.progress.set(0)

        # Progress count label
        self.count_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=11)
        )
        self.count_label.pack(pady=(0, 10))

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            main_frame,
            text="Cancel",
            command=self._on_cancel,
            fg_color="#dc3545",
            hover_color="#c82333",
            width=100
        )
        self.cancel_btn.pack()

    def _start_import(self):
        """Start the import process in a background thread."""
        self.import_thread = threading.Thread(target=self._run_import_and_convert, daemon=True)
        self.import_thread.start()
        self._check_queue()

    def _check_queue(self):
        """Check the update queue for progress updates."""
        try:
            while True:
                msg_type, data = self.update_queue.get_nowait()

                if msg_type == "title":
                    self.title_label.configure(text=data)
                elif msg_type == "status":
                    self.status_label.configure(text=data)
                elif msg_type == "file":
                    self.file_label.configure(text=data)
                elif msg_type == "progress":
                    self.progress.set(data)
                elif msg_type == "count":
                    self.count_label.configure(text=data)
                elif msg_type == "done":
                    self.result = data
                    self._show_close_button()
                    return
                elif msg_type == "error":
                    self.status_label.configure(text=data, text_color="red")

        except queue.Empty:
            pass

        if not self.cancelled:
            self.after(100, self._check_queue)

    def _run_import_and_convert(self):
        """Run the full import and conversion process."""
        try:
            utilities_dir = get_utilities_dir()
            game_path = get_game_install_path()
            max_workers = get_max_workers()

            # Check prerequisites
            if not game_path:
                self.update_queue.put(("error", "Game install path not configured"))
                self.update_queue.put(("done", False))
                return

            retoc_exe = utilities_dir / "retoc.exe"
            uassetgui_exe = utilities_dir / "UAssetGUI.exe"
            retoc_output = get_retoc_dir()
            jsondata_output = get_jsondata_dir()

            if not retoc_exe.exists():
                self.update_queue.put(("error", "retoc.exe not found in utilities folder"))
                self.update_queue.put(("done", False))
                return

            if not uassetgui_exe.exists():
                self.update_queue.put(("error", "UAssetGUI.exe not found in utilities folder"))
                self.update_queue.put(("done", False))
                return

            paks_path = Path(game_path) / "Moria" / "Content" / "Paks"
            if not paks_path.exists():
                self.update_queue.put(("error", f"Paks directory not found at {paks_path}"))
                self.update_queue.put(("done", False))
                return

            # ========== PHASE 1: SCAN .DEF FILES ==========
            self.update_queue.put(("status", "Scanning .def files for required game files..."))
            files_to_import = get_game_file_paths_to_import()

            if not files_to_import:
                self.update_queue.put(("status", "No files to import - no .def files found"))
                self.update_queue.put(("done", True))
                return

            self.update_queue.put(("status", f"Found {len(files_to_import)} game files to import"))

            if self.cancelled:
                self.update_queue.put(("done", False))
                return

            # ========== PHASE 2: CLEAR DIRECTORIES ==========
            self.update_queue.put(("status", "Clearing output directories..."))

            if retoc_output.exists():
                shutil.rmtree(retoc_output, ignore_errors=True)
            retoc_output.mkdir(parents=True, exist_ok=True)

            if jsondata_output.exists():
                shutil.rmtree(jsondata_output, ignore_errors=True)
            jsondata_output.mkdir(parents=True, exist_ok=True)

            if self.cancelled:
                self.update_queue.put(("done", False))
                return

            # ========== PHASE 3: EXTRACT WITH RETOC ==========
            self.update_queue.put(("title", "Extracting Game Files"))
            total_files = len(files_to_import)
            import_success = 0
            import_errors = 0

            for i, file_path in enumerate(files_to_import):
                if self.cancelled:
                    self.update_queue.put(("done", False))
                    return

                file_name = Path(file_path).stem

                # Truncate for display
                display_name = file_name if len(file_name) <= 50 else file_name[:47] + "..."
                self.update_queue.put(("file", display_name))
                self.update_queue.put(("progress", i / total_files))
                self.update_queue.put(("count", f"Extracting {i + 1} / {total_files}"))

                cmd = f'"{retoc_exe}" to-legacy --version UE4_27 --filter "{file_name}" "{paks_path}" "{retoc_output}"'

                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        shell=True,
                        check=False,
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )

                    if result.returncode == 0:
                        import_success += 1
                    else:
                        import_errors += 1
                        logger.warning("Failed to extract %s: %s", file_path, result.stderr)

                except subprocess.TimeoutExpired:
                    import_errors += 1
                except OSError as e:
                    import_errors += 1
                    logger.warning("Error extracting %s: %s", file_path, e)

            self.update_queue.put(("progress", 1.0))
            self.update_queue.put(("status", f"Extracted {import_success} files ({import_errors} errors)"))

            if self.cancelled:
                self.update_queue.put(("done", False))
                return

            # ========== PHASE 4: CONVERT TO JSON ==========
            self.update_queue.put(("title", "Converting to JSON"))
            self.update_queue.put(("status", "Scanning for files to convert..."))
            self.update_queue.put(("progress", 0))

            uasset_files = get_files_to_convert()
            total_convert = len(uasset_files)

            if total_convert == 0:
                self.update_queue.put(("status", "No files to convert"))
                self.update_queue.put(("done", True))
                return

            self.update_queue.put(("status", f"Converting {total_convert} files using {max_workers} workers..."))

            converted = 0
            convert_errors = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        convert_file_to_json,
                        uassetgui_exe,
                        f,
                        retoc_output,
                        jsondata_output
                    ): f for f in uasset_files
                }

                for future in as_completed(futures):
                    if self.cancelled:
                        executor.shutdown(wait=False, cancel_futures=True)
                        self.update_queue.put(("done", False))
                        return

                    success, _ = future.result()
                    if success:
                        converted += 1
                    else:
                        convert_errors += 1

                    self.update_queue.put(("progress", (converted + convert_errors) / total_convert))
                    self.update_queue.put(("count", f"Converted {converted} / {total_convert} ({convert_errors} errors)"))

            # ========== PHASE 5: UPDATE BUILDINGS CACHE ==========
            self.update_queue.put(("status", "Updating buildings cache..."))
            ini_success, ini_message = update_buildings_ini_from_json()

            if ini_success:
                self.update_queue.put(("status", f"Complete! {converted} files converted. {ini_message}"))
            else:
                self.update_queue.put(("status", f"Complete! {converted} files converted."))

            self.update_queue.put(("file", ""))
            self.update_queue.put(("progress", 1.0))
            self.update_queue.put(("done", True))

        except OSError as e:
            logger.exception("Import/convert error")
            self.update_queue.put(("error", f"Error: {str(e)}"))
            self.update_queue.put(("done", False))

    def _show_close_button(self):
        """Update the cancel button to a close button."""
        self.cancel_btn.configure(
            text="Close",
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610"),
            command=self.destroy
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_cancel(self):
        """Handle cancel button click."""
        self.cancelled = True
        self.status_label.configure(text="Cancelling...")


def show_import_dialog(parent: ctk.CTk) -> bool:
    """Show the import dialog and wait for it to close.

    Args:
        parent: The parent window.

    Returns:
        True if import succeeded, False otherwise.
    """
    dialog = ImportDialog(parent)
    parent.wait_window(dialog)
    return dialog.result
