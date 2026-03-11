"""Initial configuration dialog for Moria MOD Creator."""

import logging
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

logger = logging.getLogger(__name__)

from src.config import (
    get_available_install_options,
    load_config,
    save_config,
    get_default_utilities_dir,
    get_default_output_dir,
    get_default_mymodfiles_dir,
    get_default_definitions_dir,
    get_game_install_path,
    get_utilities_dir,
    get_output_dir,
    get_mymodfiles_dir,
    get_definitions_dir,
    get_color_scheme,
    get_max_workers,
    get_debug_mode,
    COLOR_SCHEMES,
    DEFAULT_COLOR_SCHEME,
)


class ConfigDialog(ctk.CTkToplevel):
    """Configuration dialog for first-run setup."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Configuration")
        self.geometry("825x510")
        self.resizable(False, False)

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 825) // 2
        y = (self.winfo_screenheight() - 510) // 2
        self.geometry(f"825x510+{x}+{y}")

        # Result tracking
        self.result = False

        # Get available install options
        self.install_options = get_available_install_options()
        self.option_names = [opt[0] for opt in self.install_options]
        self.option_paths = {opt[0]: opt[1] for opt in self.install_options}

        # Load saved install type to restore dropdown selection
        saved_config = load_config()
        self.saved_install_type = saved_config.get('Game', 'install_type', fallback='')

        # Track paths — use saved values if they exist, else defaults
        self.game_path = ctk.StringVar()
        self.custom_game_path = ""
        if self.saved_install_type == "Custom":
            self.custom_game_path = get_game_install_path() or ""
        self.utilities_path = ctk.StringVar(value=str(get_utilities_dir()))
        self.output_path = ctk.StringVar(value=str(get_output_dir()))
        self.mymodfiles_path = ctk.StringVar(value=str(get_mymodfiles_dir()))
        self.definitions_path = ctk.StringVar(value=str(get_definitions_dir()))
        self.color_scheme = ctk.StringVar(value=get_color_scheme())
        self.max_workers = ctk.StringVar(value=str(get_max_workers()))
        self.debug_mode = ctk.StringVar(value="1" if get_debug_mode() else "0")

        self._create_widgets()
        logger.debug("Config dialog created (%dx%d)", 825, 510)

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main frame with padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configure grid
        main_frame.grid_columnconfigure(1, weight=1)

        row = 0

        # Game Install Path
        label = ctk.CTkLabel(main_frame, text="Game Install Path:", font=ctk.CTkFont(size=13))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(0, 5))

        game_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        game_frame.grid(row=row, column=1, columnspan=2, sticky="ew", pady=(0, 5))
        game_frame.grid_columnconfigure(0, weight=1)

        self.game_dropdown = ctk.CTkComboBox(
            game_frame,
            values=self.option_names,
            command=self._on_game_dropdown_change,
            width=200,
            state="readonly"
        )
        self.game_dropdown.grid(row=0, column=0, sticky="w")

        self.game_browse_btn = ctk.CTkButton(
            game_frame, text="Browse...", command=self._on_game_browse, width=80
        )
        self.game_browse_btn.grid(row=0, column=1, padx=(10, 0))
        self.game_browse_btn.grid_remove()

        row += 1

        # Game path display
        self.game_path_label = ctk.CTkLabel(
            main_frame, text="", font=ctk.CTkFont(size=10),
            text_color="gray", wraplength=775, justify="left"
        )
        self.game_path_label.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 15))

        # Set initial dropdown value — restore saved install type if available
        if self.saved_install_type and self.saved_install_type in self.option_names:
            self.game_dropdown.set(self.saved_install_type)
            self._on_game_dropdown_change(self.saved_install_type)
        elif self.option_names:
            self.game_dropdown.set(self.option_names[0])
            self._update_game_path_display(self.option_names[0])

        row += 1

        # Utilities Directory
        self._create_dir_row(main_frame, row, "Utilities Directory:", self.utilities_path, self._on_utilities_browse)
        row += 1

        # Output Directory
        self._create_dir_row(
            main_frame, row, "Output Directory:", self.output_path, self._on_output_browse)
        row += 1

        # My MOD Files Directory
        self._create_dir_row(
            main_frame, row, "My MOD Files Directory:",
            self.mymodfiles_path, self._on_mymodfiles_browse)
        row += 1

        # MOD Definitions Directory
        self._create_dir_row(
            main_frame, row, "MOD Definitions Directory:",
            self.definitions_path, self._on_definitions_browse)
        row += 1

        # Color Scheme
        label = ctk.CTkLabel(main_frame, text="Color Scheme:", font=ctk.CTkFont(size=13))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=(15, 5))

        self.color_dropdown = ctk.CTkComboBox(
            main_frame,
            values=COLOR_SCHEMES,
            variable=self.color_scheme,
            width=400,
            state="readonly"
        )
        self.color_dropdown.grid(row=row, column=1, sticky="w", pady=(15, 5))

        row += 1

        # Max Workers for parallel processing
        label = ctk.CTkLabel(main_frame, text="Parallel Processes:", font=ctk.CTkFont(size=13))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)

        self.workers_dropdown = ctk.CTkComboBox(
            main_frame,
            values=[str(i) for i in range(1, 11)],
            variable=self.max_workers,
            width=80,
            state="readonly"
        )
        self.workers_dropdown.grid(row=row, column=1, sticky="w", pady=5)

        workers_hint = ctk.CTkLabel(
            main_frame, text="(Number of parallel processes for JSON conversion)",
            font=ctk.CTkFont(size=10), text_color="gray"
        )
        workers_hint.grid(row=row, column=2, sticky="w", padx=(10, 0), pady=5)

        row += 1

        # Debug Mode
        label = ctk.CTkLabel(main_frame, text="Debug Mode:", font=ctk.CTkFont(size=13))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)

        self.debug_switch = ctk.CTkSwitch(
            main_frame,
            text="",
            variable=self.debug_mode,
            onvalue="1",
            offvalue="0",
            width=46
        )
        self.debug_switch.grid(row=row, column=1, sticky="w", pady=5)

        debug_hint = ctk.CTkLabel(
            main_frame, text="(Enable verbose logging for troubleshooting)",
            font=ctk.CTkFont(size=10), text_color="gray"
        )
        debug_hint.grid(row=row, column=2, sticky="w", padx=(10, 0), pady=5)

        row += 1

        # Spacer
        main_frame.grid_rowconfigure(row, weight=1)
        row += 1

        # Button frame at bottom
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
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

        # Save & Continue button (green) - lower right
        self.save_btn = ctk.CTkButton(
            button_frame,
            text="SAVE & CONTINUE",
            command=self._on_save,
            fg_color="#28a745",
            hover_color="#218838",
            text_color="white",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=150,
            height=36
        )
        self.save_btn.grid(row=0, column=1, sticky="e")

    def _create_dir_row(self, parent, row: int, label_text: str, path_var: ctk.StringVar, browse_command):
        """Create a directory selection row."""
        label = ctk.CTkLabel(parent, text=label_text, font=ctk.CTkFont(size=13))
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)

        entry = ctk.CTkEntry(parent, textvariable=path_var, width=550)
        entry.grid(row=row, column=1, sticky="ew", pady=5)

        browse_btn = ctk.CTkButton(parent, text="Browse...", command=browse_command, width=80)
        browse_btn.grid(row=row, column=2, padx=(10, 0), pady=5)

    def _on_game_dropdown_change(self, selection: str):
        """Handle game dropdown selection change."""
        self._update_game_path_display(selection)

        if selection == "Custom":
            self.game_browse_btn.grid()
        else:
            self.game_browse_btn.grid_remove()

    def _update_game_path_display(self, selection: str):
        """Update the game path display label."""
        if selection == "Custom":
            if self.custom_game_path:
                self.game_path_label.configure(
                    text=f"{self.custom_game_path}  (select the game root folder, e.g. ...\\ReturnToMoria)",
                    text_color="gray")
                self.game_path.set(self.custom_game_path)
            else:
                self.game_path_label.configure(
                    text="Select the game root folder (e.g. C:\\...\\ReturnToMoria — not the Paks folder)",
                    text_color="gray")
                self.game_path.set("")
        else:
            path = self.option_paths.get(selection, "")
            self.game_path_label.configure(text=path, text_color="gray")
            self.game_path.set(path)

    def _on_game_browse(self):
        """Handle game browse button click."""
        folder = filedialog.askdirectory(title="Select Game Installation Folder", mustexist=True)
        if folder:
            self.custom_game_path = folder
            self.game_path_label.configure(text=folder, text_color="gray")
            self.game_path.set(folder)

    def _on_utilities_browse(self):
        """Handle utilities browse button click."""
        self._browse_for_dir(self.utilities_path, "Select Utilities Directory")

    def _on_output_browse(self):
        """Handle output browse button click."""
        self._browse_for_dir(self.output_path, "Select Output Directory")

    def _on_mymodfiles_browse(self):
        """Handle My MOD Files browse button click."""
        self._browse_for_dir(self.mymodfiles_path, "Select My MOD Files Directory")

    def _on_definitions_browse(self):
        """Handle MOD Definitions browse button click."""
        self._browse_for_dir(self.definitions_path, "Select MOD Definitions Directory")

    def _browse_for_dir(self, path_var: ctk.StringVar, title: str):
        """Browse for a directory and update the path variable."""
        initial_dir = path_var.get() if Path(path_var.get()).exists() else None
        folder = filedialog.askdirectory(title=title, initialdir=initial_dir)
        if folder:
            path_var.set(folder)

    def _on_cancel(self):
        """Handle cancel button click."""
        logger.debug("User cancelled config dialog")
        self.result = False
        self.destroy()

    def _on_save(self):
        """Handle save button click."""
        game_path = self.game_path.get()
        if not game_path:
            logger.warning("Save attempted with no game path selected")
            self.game_path_label.configure(text="Please select a valid game path!", text_color="red")
            return

        if not Path(game_path).exists():
            logger.warning("Save attempted with non-existent game path: %s", game_path)
            self.game_path_label.configure(text=f"Path does not exist: {game_path}", text_color="red")
            return

        install_type = self.game_dropdown.get()
        logger.debug("Saving config - install=%s, game=%s, workers=%s, debug=%s",
                      install_type, game_path, self.max_workers.get(), self.debug_mode.get())

        save_config(
            game_install_path=game_path,
            install_type=install_type,
            utilities_dir=self.utilities_path.get(),
            output_dir=self.output_path.get(),
            mymodfiles_dir=self.mymodfiles_path.get(),
            definitions_dir=self.definitions_path.get(),
            color_scheme=self.color_scheme.get(),
            max_workers=int(self.max_workers.get()),
            debug=self.debug_mode.get() == "1"
        )

        self.result = True
        self.destroy()


def show_config_dialog(parent: ctk.CTk) -> bool:
    """Show the configuration dialog and wait for it to close.

    Args:
        parent: The parent window.

    Returns:
        True if configuration was saved, False if cancelled.
    """
    dialog = ConfigDialog(parent)
    parent.wait_window(dialog)
    return dialog.result
