"""Mod Name dialog for Moria MOD Creator."""

import logging
import shutil
from pathlib import Path
from src.ui.shared_utils import get_assets_dir

import customtkinter as ctk

from src.config import get_default_mymodfiles_dir

logger = logging.getLogger(__name__)


class _ConfirmDeleteDialog(ctk.CTkToplevel):
    """Confirmation dialog for deleting a mod."""

    def __init__(self, parent, mod_name: str):
        super().__init__(parent)

        self.title("Confirm Delete")
        self.geometry("380x150")
        self.resizable(False, False)
        self.result = False

        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        self.update_idletasks()
        x = (self.winfo_screenwidth() - 380) // 2
        y = (self.winfo_screenheight() - 150) // 2
        self.geometry(f"380x150+{x}+{y}")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            main_frame,
            text=f"Delete mod '{mod_name}' and all its files?",
            font=ctk.CTkFont(size=14),
            wraplength=340
        ).pack(pady=(0, 20))

        btn_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(
            btn_frame, text="Cancel",
            fg_color="#F44336", hover_color="#D32F2F",
            text_color="white", font=ctk.CTkFont(weight="bold"),
            width=100, command=self._on_cancel
        ).pack(side="left")

        ctk.CTkButton(
            btn_frame, text="OK",
            fg_color="#4CAF50", hover_color="#388E3C",
            text_color="white", font=ctk.CTkFont(weight="bold"),
            width=100, command=self._on_ok
        ).pack(side="right")

    def _on_cancel(self):
        self.result = False
        self.destroy()

    def _on_ok(self):
        self.result = True
        self.destroy()


class ModNameDialog(ctk.CTkToplevel):
    """Dialog for selecting or creating a mod name."""

    def __init__(self, parent: ctk.CTk, current_name: str = ""):
        super().__init__(parent)

        self.title("My Mod Name")
        self.geometry("450x420")
        self.resizable(False, False)

        # Result - will be set if Apply is clicked
        self.result = None

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 450) // 2
        y = (self.winfo_screenheight() - 420) // 2
        self.geometry(f"450x420+{x}+{y}")

        self._current_name = current_name
        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _get_existing_mods(self) -> list[str]:
        """Get list of existing mod directories."""
        mymodfiles_dir = get_default_mymodfiles_dir()
        if not mymodfiles_dir.exists():
            return []

        mods = []
        for item in sorted(mymodfiles_dir.iterdir()):
            if item.is_dir():
                mods.append(item.name)
        return mods

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configure grid
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # Existing mods section
        existing_label = ctk.CTkLabel(
            main_frame,
            text="Existing Mods:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        existing_label.grid(row=0, column=0, sticky="w", pady=(0, 5))

        # Scrollable frame for existing mods list
        self.mods_list_frame = ctk.CTkScrollableFrame(
            main_frame,
            height=150
        )
        self.mods_list_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))

        # Populate existing mods
        self._refresh_mod_list()

        # Mod name section
        new_mod_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        new_mod_frame.grid(row=2, column=0, sticky="sew", pady=(10, 0))
        new_mod_frame.grid_columnconfigure(1, weight=1)

        new_label = ctk.CTkLabel(
            new_mod_frame,
            text="Mod Name:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        new_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.name_var = ctk.StringVar(value=self._current_name)
        self.name_entry = ctk.CTkEntry(
            new_mod_frame,
            textvariable=self.name_var,
            font=ctk.CTkFont(size=14),
            placeholder_text="Enter mod name..."
        )
        self.name_entry.grid(row=0, column=1, sticky="ew")

        # Button frame at bottom
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.grid(row=3, column=0, sticky="ew", pady=(15, 0))

        # Cancel button (red, left)
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            fg_color="#F44336",  # Red
            hover_color="#D32F2F",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._on_cancel
        )
        cancel_btn.pack(side="left")

        # Apply button (green, right)
        apply_btn = ctk.CTkButton(
            button_frame,
            text="Apply",
            fg_color="#4CAF50",  # Green
            hover_color="#388E3C",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._on_apply
        )
        apply_btn.pack(side="right")

        # Bind Enter key to apply
        self.name_entry.bind("<Return>", lambda e: self._on_apply())

    def _refresh_mod_list(self):
        """Refresh the mod list display."""
        for widget in self.mods_list_frame.winfo_children():
            widget.destroy()

        existing_mods = self._get_existing_mods()
        if existing_mods:
            for mod_name in existing_mods:
                row = ctk.CTkFrame(self.mods_list_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)

                mod_btn = ctk.CTkButton(
                    row,
                    text=mod_name,
                    fg_color="transparent",
                    hover_color=("gray75", "gray25"),
                    text_color=("gray10", "gray90"),
                    anchor="w",
                    command=lambda m=mod_name: self._select_existing_mod(m)
                )
                mod_btn.pack(side="left", fill="x", expand=True)

                delete_btn = ctk.CTkButton(
                    row,
                    text="\U0001F5D1",
                    width=28, height=28,
                    fg_color="#F44336",
                    hover_color="#D32F2F",
                    text_color="white",
                    font=ctk.CTkFont(size=14),
                    command=lambda m=mod_name: self._confirm_delete_mod(m)
                )
                delete_btn.pack(side="right", padx=(5, 0))
        else:
            ctk.CTkLabel(
                self.mods_list_frame,
                text="No existing mods found",
                text_color="gray"
            ).pack(pady=10)

    def _confirm_delete_mod(self, mod_name: str):
        """Show confirmation dialog before deleting a mod."""
        confirm = _ConfirmDeleteDialog(self, mod_name)
        confirm.wait_window()
        if confirm.result:
            mod_dir = get_default_mymodfiles_dir() / mod_name
            if mod_dir.exists():
                logger.info("Deleting mod directory: %s", mod_dir)
                shutil.rmtree(mod_dir)
            # Clear selection if the deleted mod was selected
            if self.name_var.get() == mod_name:
                self.name_var.set("")
            self._refresh_mod_list()

    def _select_existing_mod(self, mod_name: str):
        """Select an existing mod from the list - populate the mod name field."""
        self.name_var.set(mod_name)
        self.name_entry.focus_set()

    def _on_cancel(self):
        """Handle Cancel button click."""
        self.result = None
        self.destroy()

    def _on_apply(self):
        """Handle Apply button click - create mod directory structure for new mod."""
        mod_name = self.name_var.get().strip()

        if not mod_name:
            logger.warning("Mod name dialog: empty name submitted")
            self.name_entry.configure(border_color="red")
            return

        # Validate mod name (no invalid characters)
        invalid_chars = '<>:"/\\|?*'
        if any(c in mod_name for c in invalid_chars):
            logger.warning("Mod name dialog: invalid characters in name '%s'", mod_name)
            self.name_entry.configure(border_color="red")
            return

        # Create the mod directory structure
        mymodfiles_dir = get_default_mymodfiles_dir()
        mod_dir = mymodfiles_dir / mod_name

        try:
            # Create main mod directory
            mod_dir.mkdir(parents=True, exist_ok=True)

            # Create subdirectories
            (mod_dir / "jsonfiles").mkdir(exist_ok=True)
            (mod_dir / "finalmod").mkdir(exist_ok=True)

            logger.debug("Created mod directory structure: %s", mod_dir)

            # Set result and close
            self.result = mod_name
            self.destroy()

        except OSError as e:
            logger.error("Error creating mod directory '%s': %s", mod_dir, e)
            self.name_entry.configure(border_color="red")


def show_mod_name_dialog(parent: ctk.CTk, current_name: str = "") -> str | None:
    """Show the mod name dialog and return the result.

    Args:
        parent: Parent window.
        current_name: Current mod name to pre-fill.

    Returns:
        The mod name if Apply was clicked, None if cancelled.
    """
    dialog = ModNameDialog(parent, current_name)
    dialog.wait_window()
    return dialog.result
