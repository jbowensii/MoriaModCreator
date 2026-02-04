"""Import dialog for running retoc to import game files.

This module scans all .def files in the Definitions directory to find
which game files are actually needed, then uses retoc to extract only
those specific files from the game.
"""

import logging
import subprocess
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import customtkinter as ctk

from src.config import get_utilities_dir, get_output_dir, get_game_install_path, get_appdata_dir


logger = logging.getLogger(__name__)


def check_retoc_output_exists() -> bool:
    """Check if retoc output directory exists and has files."""
    retoc_dir = get_output_dir() / "retoc"
    if not retoc_dir.exists():
        return False
    # Check if directory has any files
    try:
        return any(retoc_dir.iterdir())
    except Exception:
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
        except Exception as e:
            logger.warning("Error reading %s: %s", def_file.name, e)

    logger.info("Found %d unique mod file paths from .def files", len(mod_paths))
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

    Scans all .def files and returns the corresponding .uasset paths.

    Returns:
        List of unique .uasset file paths relative to game directory
    """
    mod_paths = scan_def_files_for_mod_paths()

    # Convert each .json path to .uasset
    uasset_paths = set()
    for json_path in mod_paths:
        uasset_path = convert_json_path_to_uasset(json_path)
        uasset_paths.add(uasset_path)

    return sorted(uasset_paths)


class ImportDialog(ctk.CTkToplevel):
    """Dialog showing progress of game file import."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Importing Game Files")
        self.geometry("500x200")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 200) // 2
        self.geometry(f"500x200+{x}+{y}")

        # Result tracking
        self.result = False
        self.process = None
        self.import_thread = None
        self.files_to_import = []
        self.current_file_index = 0
        self.success_count = 0
        self.error_count = 0
        self.error_message = ""

        self._create_widgets()

        # Prevent closing during import
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        # Start by scanning for files to import
        self.after(100, self._scan_and_start_import)

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configure grid
        main_frame.grid_columnconfigure(0, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Importing Game Files",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 10))

        # Status message
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Scanning .def files for required game files...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=1, column=0, pady=(0, 5))

        # Current file label
        self.file_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.file_label.grid(row=2, column=0, pady=(0, 10))

        # Progress bar
        self.progress = ctk.CTkProgressBar(main_frame, mode="determinate", width=450)
        self.progress.grid(row=3, column=0, pady=(0, 10))
        self.progress.set(0)

        # Progress count label
        self.count_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=11)
        )
        self.count_label.grid(row=4, column=0, pady=(0, 5))

    def _on_close_attempt(self):
        """Handle close button during import - do nothing."""
        return  # Intentionally ignore close during import

    def _scan_and_start_import(self):
        """Scan .def files and start the import process."""
        # Get list of files to import
        self.files_to_import = get_game_file_paths_to_import()

        if not self.files_to_import:
            self.status_label.configure(text="No files to import - no .def files found")
            self.progress.set(1)
            self._add_close_button()
            return

        self.status_label.configure(
            text=f"Found {len(self.files_to_import)} game files to import"
        )
        self.count_label.configure(text=f"0 / {len(self.files_to_import)}")

        # Start import in background thread
        self.import_thread = threading.Thread(target=self._run_import, daemon=True)
        self.import_thread.start()
        self._check_thread()

    def _run_import(self):
        """Run the retoc import for each file."""
        try:
            utilities_dir = get_utilities_dir()
            output_dir = get_output_dir()
            game_path = get_game_install_path()

            # Check if game path is configured
            if not game_path:
                self.result = False
                self.error_message = "Game install path not configured"
                return

            retoc_exe = utilities_dir / "retoc.exe"
            retoc_output = output_dir / "retoc"

            # Create output directory if it doesn't exist
            retoc_output.mkdir(parents=True, exist_ok=True)

            # Check if retoc exists
            if not retoc_exe.exists():
                self.result = False
                self.error_message = f"retoc.exe not found at {retoc_exe}"
                return

            # Build the paks path - retoc needs the Paks directory
            # game_path is the game install directory, we need Moria/Content/Paks
            paks_path = Path(game_path) / "Moria" / "Content" / "Paks"
            if not paks_path.exists():
                self.result = False
                self.error_message = f"Paks directory not found at {paks_path}"
                return

            # Import each file
            for i, file_path in enumerate(self.files_to_import):
                self.current_file_index = i

                # file_path is like "Moria\Content\Tech\Data\Building\DT_Items.uasset"
                # The filter should be the file name without extension for best matching
                file_name = Path(file_path).stem  # e.g., "DT_Items"

                # retoc extracts to .json, but our file_path has .uasset extension
                # Check for the json version of the output file
                json_path = str(file_path).replace('.uasset', '.json')
                dest_file = retoc_output / json_path

                # Skip if already exists
                if dest_file.exists():
                    self.success_count += 1
                    continue

                # Run retoc to extract this specific file
                # The filter matches against the asset name
                # Use shell=True and quote paths to handle special characters (like â„¢)
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
                        self.success_count += 1
                    else:
                        self.error_count += 1
                        logger.warning("Failed to extract %s: %s", file_path, result.stderr)

                except subprocess.TimeoutExpired:
                    self.error_count += 1
                    logger.warning("Timeout extracting %s", file_path)
                except Exception as e:
                    self.error_count += 1
                    logger.warning("Error extracting %s: %s", file_path, e)

            self.result = True

        except Exception as e:
            self.result = False
            self.error_message = str(e)
            logger.error("Import error: %s", e)

    def _check_thread(self):
        """Check if the import thread has completed and update progress."""
        if self.import_thread.is_alive():
            # Update progress
            if self.files_to_import:
                progress = self.current_file_index / len(self.files_to_import)
                self.progress.set(progress)
                self.count_label.configure(
                    text=f"{self.current_file_index} / {len(self.files_to_import)} "
                         f"({self.success_count} OK, {self.error_count} errors)"
                )

                # Show current file
                if self.current_file_index < len(self.files_to_import):
                    current_file = self.files_to_import[self.current_file_index]
                    # Truncate long paths
                    display_path = current_file
                    if len(display_path) > 60:
                        display_path = "..." + display_path[-57:]
                    self.file_label.configure(text=display_path)

            self.after(200, self._check_thread)
        else:
            self._import_complete()

    def _import_complete(self):
        """Handle import completion."""
        self.progress.set(1)

        if self.result:
            self.status_label.configure(
                text=f"Import completed: {self.success_count} files imported"
            )
            self.count_label.configure(
                text=f"{len(self.files_to_import)} total, "
                     f"{self.success_count} OK, {self.error_count} errors"
            )
            self.file_label.configure(text="")

            if self.error_count == 0:
                self.after(2000, self.destroy)
            else:
                self._add_close_button()
        else:
            self.status_label.configure(
                text=f"Import failed: {self.error_message}",
                text_color="red"
            )
            logger.error("Import failed: %s", self.error_message)
            self._add_close_button()

    def _add_close_button(self):
        """Add a close button and allow closing."""
        close_btn = ctk.CTkButton(
            self,
            text="Close",
            command=self.destroy,
            width=100
        )
        close_btn.pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.destroy)


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
