"""Import dialog for running retoc to import game files."""

import subprocess
import threading

import customtkinter as ctk

from src.config import get_utilities_dir, get_output_dir, get_game_install_path


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


class ImportDialog(ctk.CTkToplevel):
    """Dialog showing progress of game file import."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Importing Game Files")
        self.geometry("450x150")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 450) // 2
        y = (self.winfo_screenheight() - 150) // 2
        self.geometry(f"450x150+{x}+{y}")

        # Result tracking
        self.result = False
        self.process = None
        self.import_thread = None

        self._create_widgets()

        # Prevent closing during import
        self.protocol("WM_DELETE_WINDOW", self._on_close_attempt)

        # Start the import process
        self.after(100, self._start_import)

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
        title_label.grid(row=0, column=0, pady=(0, 15))

        # Status message
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Running retoc.exe to extract game files...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.grid(row=1, column=0, pady=(0, 10))

        # Progress bar (indeterminate)
        self.progress = ctk.CTkProgressBar(main_frame, mode="indeterminate", width=400)
        self.progress.grid(row=2, column=0, pady=(0, 10))
        self.progress.start()

    def _on_close_attempt(self):
        """Handle close button during import - do nothing."""
        return  # Intentionally ignore close during import

    def _start_import(self):
        """Start the import process in a background thread."""
        self.import_thread = threading.Thread(target=self._run_retoc, daemon=True)
        self.import_thread.start()
        self._check_thread()

    def _run_retoc(self):
        """Run the retoc command."""
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

            # Build the command
            cmd = [
                str(retoc_exe),
                "to-legacy",
                "--version", "UE4_27",
                str(game_path),
                str(retoc_output)
            ]

            # Run the command
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            stdout, stderr = self.process.communicate()

            if self.process.returncode == 0:
                self.result = True
            else:
                self.result = False
                self.error_message = stderr.decode('utf-8', errors='replace') if stderr else "Unknown error"

        except Exception as e:
            self.result = False
            self.error_message = str(e)

    def _check_thread(self):
        """Check if the import thread has completed."""
        if self.import_thread.is_alive():
            self.after(100, self._check_thread)
        else:
            self._import_complete()

    def _import_complete(self):
        """Handle import completion."""
        self.progress.stop()

        if self.result:
            self.status_label.configure(text="Import completed successfully!")
            self.after(1500, self.destroy)
        else:
            self.status_label.configure(
                text=f"Import failed: {getattr(self, 'error_message', 'Unknown error')}",
                text_color="red"
            )
            # Add a close button
            close_btn = ctk.CTkButton(
                self,
                text="Close",
                command=self.destroy,
                width=100
            )
            close_btn.pack(pady=10)
            # Allow closing now
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
