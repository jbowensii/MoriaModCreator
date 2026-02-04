"""Construction Name dialog for Moria MOD Creator.

This dialog allows users to:
1. Select an existing construction pack from %AppData%/MoriaMODCreator/Constructions/
2. Create a new construction pack with a custom name
3. Load the selected constructions from a pack's INI file
"""

import configparser

import customtkinter as ctk

from src.config import get_constructions_dir


class ConstructionNameDialog(ctk.CTkToplevel):
    """Dialog for selecting or creating a construction pack name."""

    def __init__(self, parent: ctk.CTk, current_name: str = ""):
        super().__init__(parent)

        self.title("My Construction Pack")
        self.geometry("500x480")
        self.resizable(False, False)

        # Result - will be set if Apply is clicked
        # Returns tuple: (pack_name, list_of_construction_names) or None
        self.result = None

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 480) // 2
        self.geometry(f"500x480+{x}+{y}")

        self._current_name = current_name
        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _get_existing_packs(self) -> list[tuple[str, int]]:
        """Get list of existing construction pack directories with their construction count.

        Returns:
            List of tuples: (pack_name, construction_count)
        """
        constructions_dir = get_constructions_dir()
        if not constructions_dir.exists():
            return []

        packs = []
        for item in sorted(constructions_dir.iterdir()):
            if item.is_dir():
                # Count constructions in pack (from INI file)
                ini_file = item / f"{item.name}.ini"
                if ini_file.exists():
                    config = configparser.ConfigParser()
                    try:
                        config.read(ini_file, encoding='utf-8')
                        count = len(config.options('Constructions')) if config.has_section('Constructions') else 0
                    except Exception:
                        count = 0
                else:
                    count = 0
                packs.append((item.name, count))
        return packs

    def _load_pack_constructions(self, pack_name: str) -> list[str]:
        """Load the list of construction names from a pack's INI file.

        Args:
            pack_name: Name of the construction pack

        Returns:
            List of construction names from the INI file
        """
        # Strip .ini extension if included
        if pack_name.lower().endswith('.ini'):
            pack_name = pack_name[:-4]

        constructions_dir = get_constructions_dir()
        ini_file = constructions_dir / pack_name / f"{pack_name}.ini"

        if not ini_file.exists():
            return []

        config = configparser.ConfigParser()
        try:
            config.read(ini_file, encoding='utf-8')
            if config.has_section('Constructions'):
                # Each option name is a construction name, value is '1' for selected
                return [name for name in config.options('Constructions')
                        if config.get('Constructions', name) == '1']
        except Exception:
            pass

        return []

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
            text="Select or create a construction pack to manage\nyour custom building collections.",
            font=ctk.CTkFont(size=12),
            text_color="gray",
            justify="left"
        )
        header_label.grid(row=0, column=0, sticky="w", pady=(0, 15))

        # Existing packs section
        existing_label = ctk.CTkLabel(
            main_frame,
            text="Existing Construction Packs:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        existing_label.grid(row=1, column=0, sticky="w", pady=(0, 5))

        # Scrollable frame for existing packs list
        self.packs_list_frame = ctk.CTkScrollableFrame(
            main_frame,
            height=180
        )
        self.packs_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        # Populate existing packs
        existing_packs = self._get_existing_packs()
        if existing_packs:
            for pack_name, count in existing_packs:
                pack_frame = ctk.CTkFrame(self.packs_list_frame, fg_color="transparent")
                pack_frame.pack(fill="x", pady=2)

                pack_btn = ctk.CTkButton(
                    pack_frame,
                    text=pack_name,
                    fg_color="transparent",
                    hover_color=("gray75", "gray25"),
                    text_color=("gray10", "gray90"),
                    anchor="w",
                    command=lambda m=pack_name: self._select_existing_pack(m)
                )
                pack_btn.pack(side="left", fill="x", expand=True)

                count_label = ctk.CTkLabel(
                    pack_frame,
                    text=f"({count} constructions)",
                    text_color="gray",
                    font=ctk.CTkFont(size=11)
                )
                count_label.pack(side="right", padx=5)
        else:
            no_packs_label = ctk.CTkLabel(
                self.packs_list_frame,
                text="No existing construction packs found.\nCreate a new one below.",
                text_color="gray"
            )
            no_packs_label.pack(pady=20)

        # Pack name section
        new_pack_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        new_pack_frame.grid(row=3, column=0, sticky="sew", pady=(10, 0))
        new_pack_frame.grid_columnconfigure(1, weight=1)

        new_label = ctk.CTkLabel(
            new_pack_frame,
            text="Pack Name:",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        new_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.name_var = ctk.StringVar(value=self._current_name)
        self.name_entry = ctk.CTkEntry(
            new_pack_frame,
            textvariable=self.name_var,
            font=ctk.CTkFont(size=14),
            placeholder_text="Enter pack name..."
        )
        self.name_entry.grid(row=0, column=1, sticky="ew")

        # Info text
        info_label = ctk.CTkLabel(
            main_frame,
            text="Selecting an existing pack will load its saved construction selections.\n"
                 "Creating a new pack will start with no selections.",
            font=ctk.CTkFont(size=11),
            text_color="gray",
            justify="left"
        )
        info_label.grid(row=4, column=0, sticky="w", pady=(10, 0))

        # Button frame at bottom
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.grid(row=5, column=0, sticky="ew", pady=(15, 0))

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

        # Apply button (purple, right)
        apply_btn = ctk.CTkButton(
            button_frame,
            text="Apply",
            fg_color="#9C27B0",  # Purple to match constructions theme
            hover_color="#7B1FA2",
            text_color="white",
            font=ctk.CTkFont(weight="bold"),
            width=100,
            command=self._on_apply
        )
        apply_btn.pack(side="right")

        # Bind Enter key to apply
        self.name_entry.bind("<Return>", lambda e: self._on_apply())

    def _select_existing_pack(self, pack_name: str):
        """Select an existing pack from the list - populate the pack name field."""
        self.name_var.set(pack_name)
        self.name_entry.focus_set()

    def _on_cancel(self):
        """Handle Cancel button click."""
        self.result = None
        self.destroy()

    def _on_apply(self):
        """Handle Apply button click - create or load construction pack."""
        pack_name = self.name_var.get().strip()

        # Strip .ini extension if user included it
        if pack_name.lower().endswith('.ini'):
            pack_name = pack_name[:-4]

        if not pack_name:
            # Show error - name required
            self.name_entry.configure(border_color="red")
            return

        # Validate pack name (no invalid characters)
        invalid_chars = '<>:"/\\|?*'
        if any(c in pack_name for c in invalid_chars):
            self.name_entry.configure(border_color="red")
            return

        # Get or create the pack directory
        constructions_dir = get_constructions_dir()
        pack_dir = constructions_dir / pack_name

        try:
            # Create pack directory if it doesn't exist
            pack_dir.mkdir(parents=True, exist_ok=True)

            # Check if INI file exists (named same as directory)
            ini_file = pack_dir / f"{pack_name}.ini"

            # Load existing constructions or create empty list
            if ini_file.exists():
                constructions = self._load_pack_constructions(pack_name)
            else:
                # Create empty INI file
                constructions = []
                config = configparser.ConfigParser()
                config.add_section('Constructions')
                with open(ini_file, 'w', encoding='utf-8') as f:
                    config.write(f)

            # Set result and close - return tuple of (name, constructions_list)
            self.result = (pack_name, constructions)
            self.destroy()

        except OSError as e:
            # Show error in entry
            self.name_entry.configure(border_color="red")
            print(f"Error creating construction pack directory: {e}")


def save_construction_pack(pack_name: str, selected_constructions: list[str]) -> bool:
    """Save the list of selected constructions to a pack's INI file.

    Args:
        pack_name: Name of the construction pack
        selected_constructions: List of construction names that are selected

    Returns:
        True if saved successfully, False otherwise
    """
    # Strip .ini extension if included
    if pack_name.lower().endswith('.ini'):
        pack_name = pack_name[:-4]

    constructions_dir = get_constructions_dir()
    pack_dir = constructions_dir / pack_name
    ini_file = pack_dir / f"{pack_name}.ini"

    try:
        pack_dir.mkdir(parents=True, exist_ok=True)

        config = configparser.ConfigParser()
        config.add_section('Constructions')

        for name in selected_constructions:
            config.set('Constructions', name, '1')

        with open(ini_file, 'w', encoding='utf-8') as f:
            config.write(f)

        return True
    except Exception as e:
        print(f"Error saving construction pack: {e}")
        return False


def show_construction_name_dialog(parent: ctk.CTk, current_name: str = "") -> tuple[str, list[str]] | None:
    """Show the construction name dialog and return the result.

    Args:
        parent: Parent window.
        current_name: Current pack name to pre-fill.

    Returns:
        Tuple of (pack_name, list_of_construction_names) if Apply was clicked,
        None if cancelled.
    """
    dialog = ConstructionNameDialog(parent, current_name)
    dialog.wait_window()
    return dialog.result
