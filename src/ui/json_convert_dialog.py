"""JSON conversion dialog for converting uasset files to JSON."""

import logging
import shutil
import subprocess
import threading
import queue
from pathlib import Path
try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

import customtkinter as ctk

from src.config import get_utilities_dir, get_max_workers
from src.ui.shared_utils import (
    get_retoc_dir, get_jsondata_dir, get_files_to_convert, update_buildings_ini_from_json,
)
from src.ui.utility_check_dialog import find_utility


logger = logging.getLogger(__name__)


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

            # Clear existing jsondata output directory for fresh conversion
            if jsondata_dir.exists():
                logger.info("Clearing existing jsondata output directory")
                shutil.rmtree(jsondata_dir, ignore_errors=True)

            # Create output directory
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
                logger.warning("Buildings INI update: %s", ini_message)

            self.update_queue.put(("done", True))

        except OSError as e:
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
