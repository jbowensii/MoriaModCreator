"""Construction Name dialog for Moria MOD Creator.

This dialog allows users to:
1. Select an existing .def file from %AppData%/MoriaMODCreator/Definitions/Building/
2. Create a new .def filename for building definitions
3. The selected name populates the text field used by the Build button
"""

import customtkinter as ctk

from src.config import get_appdata_dir


def _get_definitions_building_dir():
    """Get the Definitions/Building directory, creating it if needed."""
    defs_dir = get_appdata_dir() / 'Definitions' / 'Building'
    defs_dir.mkdir(parents=True, exist_ok=True)
    return defs_dir


class ConstructionNameDialog(ctk.CTkToplevel):
    """Dialog for selecting or creating a .def filename for building definitions."""

    def __init__(self, parent: ctk.CTk, current_name: str = ""):
        super().__init__(parent)

        self.title("My Construction")
        self.geometry("500x420")
        self.resizable(False, False)

        # Result - will be set if Apply is clicked
        # Returns the filename (without .def extension) or None
        self.result = None

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 420) // 2
        self.geometry(f"500x420+{x}+{y}")

        self._current_name = current_name
        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _get_existing_def_files(self) -> list[str]:
        """Get list of existing .def files in Definitions/Building.

        Returns:
            List of filenames (without .def extension), sorted alphabetically.
        """
        defs_dir = _get_definitions_building_dir()
        return sorted(
            f.stem for f in defs_dir.glob("*.def") if f.is_file()
        )

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configure grid
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)

        # Header
        header_label = ctk.CTkLabel(
            main_frame,
            text="Select an existing definition or create a new one.\n"
                 "The Build button will save to this filename.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="left"
        )
        header_label.grid(row=0, column=0, sticky="w", pady=(0, 15))

        # Existing files section
        existing_label = ctk.CTkLabel(
            main_frame,
            text="Existing Definitions:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        existing_label.grid(row=1, column=0, sticky="w", pady=(0, 5))

        # Scrollable frame for existing files list
        self.files_list_frame = ctk.CTkScrollableFrame(
            main_frame,
            height=180
        )
        self.files_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        # Populate existing files
        existing_files = self._get_existing_def_files()
        if existing_files:
            for filename in existing_files:
                file_frame = ctk.CTkFrame(self.files_list_frame, fg_color="transparent")
                file_frame.pack(fill="x", pady=2)

                file_btn = ctk.CTkButton(
                    file_frame,
                    text=filename,
                    fg_color="transparent",
                    hover_color=("gray75", "gray25"),
                    text_color=("gray10", "gray90"),
                    anchor="w",
                    command=lambda n=filename: self._select_existing_file(n)
                )
                file_btn.pack(side="left", fill="x", expand=True)

                ext_label = ctk.CTkLabel(
                    file_frame,
                    text=".def",
                    text_color="gray",
                    font=ctk.CTkFont(size=11)
                )
                ext_label.pack(side="right", padx=5)
        else:
            no_files_label = ctk.CTkLabel(
                self.files_list_frame,
                text="No existing .def files found.\nCreate a new one below.",
                text_color="gray"
            )
            no_files_label.pack(pady=20)

        # Filename entry section
        name_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        name_frame.grid(row=3, column=0, sticky="sew", pady=(10, 0))
        name_frame.grid_columnconfigure(1, weight=1)

        new_label = ctk.CTkLabel(
            name_frame,
            text="Filename:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        new_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.name_var = ctk.StringVar(value=self._current_name)
        self.name_entry = ctk.CTkEntry(
            name_frame,
            textvariable=self.name_var,
            font=ctk.CTkFont(size=14),
            placeholder_text="Enter definition name..."
        )
        self.name_entry.grid(row=0, column=1, sticky="ew")

        def_ext_label = ctk.CTkLabel(
            name_frame,
            text=".def",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        def_ext_label.grid(row=0, column=2, padx=(5, 0))

        # Button frame at bottom
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.grid(row=4, column=0, sticky="ew", pady=(15, 0))

        # Cancel button (red, left)
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            fg_color="#F44336",
            hover_color="#D32F2F",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._on_cancel
        )
        cancel_btn.pack(side="left")

        # Apply button (purple, right)
        apply_btn = ctk.CTkButton(
            button_frame,
            text="Apply",
            fg_color="#9C27B0",
            hover_color="#7B1FA2",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._on_apply
        )
        apply_btn.pack(side="right")

        # Bind Enter key to apply
        self.name_entry.bind("<Return>", lambda e: self._on_apply())

    def _select_existing_file(self, filename: str):
        """Select an existing .def file from the list."""
        self.name_var.set(filename)
        self.name_entry.focus_set()

    def _on_cancel(self):
        """Handle Cancel button click."""
        self.result = None
        self.destroy()

    def _on_apply(self):
        """Handle Apply button click - return the selected filename."""
        name = self.name_var.get().strip()

        # Strip .def extension if user included it
        if name.lower().endswith('.def'):
            name = name[:-4]

        if not name:
            self.name_entry.configure(border_color="red")
            return

        # Validate filename (no invalid characters)
        invalid_chars = '<>:"/\\|?*'
        if any(c in name for c in invalid_chars):
            self.name_entry.configure(border_color="red")
            return

        self.result = name
        self.destroy()


def show_construction_name_dialog(parent: ctk.CTk, current_name: str = "") -> str | None:
    """Show the construction name dialog and return the result.

    Args:
        parent: Parent window.
        current_name: Current name to pre-fill.

    Returns:
        The selected filename (without .def extension) if Apply was clicked,
        None if cancelled.
    """
    dialog = ConstructionNameDialog(parent, current_name)
    dialog.wait_window()
    return dialog.result
