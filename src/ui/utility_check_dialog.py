"""Utility check dialog for verifying required executables."""

from pathlib import Path

import customtkinter as ctk

from src.config import get_utilities_dir


REQUIRED_UTILITIES = ["retoc.exe", "UAssetGUI.exe", "FModel.exe"]


def find_utility(utilities_dir: Path, name: str) -> Path | None:
    """Find a utility file with case-insensitive matching."""
    # Try exact match first
    exact_path = utilities_dir / name
    if exact_path.exists():
        return exact_path
    # Try case-insensitive search
    name_lower = name.lower()
    for file in utilities_dir.iterdir():
        if file.name.lower() == name_lower:
            return file
    return None


def check_utilities_exist() -> bool:
    """Check if all required utilities exist in the utilities directory."""
    utilities_dir = get_utilities_dir()
    if not utilities_dir.exists():
        return False
    for util in REQUIRED_UTILITIES:
        if find_utility(utilities_dir, util) is None:
            return False
    return True


def get_missing_utilities() -> list[str]:
    """Get a list of missing utility files."""
    utilities_dir = get_utilities_dir()
    if not utilities_dir.exists():
        return REQUIRED_UTILITIES.copy()
    missing = []
    for util in REQUIRED_UTILITIES:
        if find_utility(utilities_dir, util) is None:
            missing.append(util)
    return missing


class UtilityCheckDialog(ctk.CTkToplevel):
    """Dialog prompting user to install required utilities."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Missing Utilities")
        self.geometry("500x250")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 250) // 2
        self.geometry(f"500x250+{x}+{y}")

        # Result tracking
        self.result = False

        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configure grid
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=1)

        # Warning message
        utilities_dir = get_utilities_dir()

        title_label = ctk.CTkLabel(
            main_frame,
            text="Required Utilities Not Found",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, pady=(0, 15))

        message = (
            "Please place the following files in the utilities directory:\n\n"
            "  - RETOC.EXE\n"
            "  - UassetGUI.exe\n"
            "  - FModel.exe\n\n"
            f"Directory: {utilities_dir}"
        )

        message_label = ctk.CTkLabel(
            main_frame,
            text=message,
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        message_label.grid(row=1, column=0, sticky="w")

        # Status label for showing retest results
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.status_label.grid(row=2, column=0, pady=(10, 0))

        # Button frame at bottom
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", pady=(15, 0))
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        # Cancel button (red) - lower left
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="CANCEL",
            command=self._on_cancel,
            fg_color="#dc3545",
            hover_color="#c82333",
            text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=36
        )
        cancel_btn.grid(row=0, column=0, sticky="w")

        # Retest button (green) - lower right
        retest_btn = ctk.CTkButton(
            button_frame,
            text="RETEST",
            command=self._on_retest,
            fg_color="#28a745",
            hover_color="#218838",
            text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=120,
            height=36
        )
        retest_btn.grid(row=0, column=1, sticky="e")

    def _on_cancel(self):
        """Handle cancel button click."""
        self.result = False
        self.destroy()

    def _on_retest(self):
        """Handle retest button click."""
        if check_utilities_exist():
            self.result = True
            self.destroy()
        else:
            missing = get_missing_utilities()
            self.status_label.configure(
                text=f"Still missing: {', '.join(missing)}",
                text_color="red"
            )


def show_utility_check_dialog(parent: ctk.CTk) -> bool:
    """Show the utility check dialog and wait for it to close.

    Args:
        parent: The parent window.

    Returns:
        True if utilities are found, False if user cancelled.
    """
    dialog = UtilityCheckDialog(parent)
    parent.wait_window(dialog)
    return dialog.result
