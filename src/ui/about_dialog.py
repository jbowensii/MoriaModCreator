"""Help About dialog for Moria MOD Creator."""

import configparser
import re
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from src.config import get_appdata_dir

# Application info
APP_NAME = "Moria MOD Creator"
APP_VERSION = "2.5.0"
APP_DATE = "March 2026"
APP_AUTHOR = "John B Owens II"
GITHUB_URL = "https://github.com/jbowensii/MoriaModCreator"
LICENSE_URL = "https://github.com/jbowensii/MoriaModCreator?tab=MIT-1-ov-file#"


def _collect_contributors() -> list[str]:
    """Collect unique contributor names from prebuilt mod INI files.

    Reads the Authors field from [ModInfo] in each INI, splits by comma,
    strips parenthetical notes, deduplicates, and returns sorted list.
    """
    prebuilt_dir = get_appdata_dir() / 'prebuilt modfiles'
    authors = set()

    if not prebuilt_dir.exists():
        return []

    for ini_file in prebuilt_dir.glob('*.ini'):
        try:
            config = configparser.ConfigParser()
            config.read(ini_file, encoding='utf-8')
            raw = config.get('ModInfo', 'Authors', fallback='')
            for part in raw.split(','):
                # Remove anything in parentheses and strip whitespace
                name = re.sub(r'\([^)]*\)', '', part).strip()
                if name:
                    authors.add(name)
        except (configparser.Error, OSError):
            continue

    return sorted(authors, key=str.lower)


class AboutDialog(ctk.CTkToplevel):
    """About dialog showing application information with tabbed content."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)
        self._about_btn = None
        self._disclaimer_btn = None
        self._credits_btn = None
        self._text_frame = None
        self._overlay_image = None

        # Make this dialog modal
        self.transient(parent)
        self.grab_set()

        # Set application icon
        from src.ui.shared_utils import get_assets_dir  # pylint: disable=import-outside-toplevel
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center the dialog on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 900) // 2
        y = (self.winfo_screenheight() - 550) // 2
        self.geometry(f"900x550+{x}+{y}")

        # Load images
        self._load_images()

        # Current active tab
        self._active_tab = "about"

        self._create_widgets()

        # Handle window close button
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Bind resize event
        self.bind("<Configure>", self._on_resize)

    def _load_images(self):
        """Load overlay image (Mereak Firmaxe with transparency)."""
        assets_path = Path(__file__).parent.parent.parent / "assets" / "images"

        # Load overlay image (Mereak Firmaxe) - preserving transparency
        overlay_path = assets_path / "Mereak Firmaxe.png"
        if overlay_path.exists():
            img = Image.open(overlay_path).convert("RGBA")
            # Flip horizontally so character faces toward the text (right)
            self._overlay_image_pil = img.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        else:
            self._overlay_image_pil = None

    def _create_widgets(self):
        """Create the dialog widgets."""
        # Main container - uses theme colors
        self._container = ctk.CTkFrame(self)
        self._container.pack(fill="both", expand=True)

        # LEFT SIDE: Image frame (fixed width), tight to lower left
        self._image_frame = ctk.CTkFrame(
            self._container,
            width=440,
            fg_color="transparent"
        )
        self._image_frame.pack(side="left", fill="y", padx=0, pady=0)
        self._image_frame.pack_propagate(False)  # Keep fixed width

        # Image label inside image frame, aligned to bottom-left
        self._overlay_label = ctk.CTkLabel(
            self._image_frame,
            text="",
            fg_color="transparent"
        )
        self._overlay_label.pack(side="bottom", anchor="sw", padx=0, pady=0)

        # RIGHT SIDE: Content frame with buttons and scrollable text (fixed width)
        self._content_frame = ctk.CTkFrame(
            self._container,
            width=450,
            fg_color="transparent"
        )
        self._content_frame.pack(side="right", fill="y", padx=(5, 10), pady=10)
        self._content_frame.pack_propagate(False)  # Keep fixed width

        # Create content inside content frame
        self._create_content()

    def _create_content(self):
        """Create the content inside the content frame."""
        # Button bar at top
        btn_frame = ctk.CTkFrame(self._content_frame, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(0, 10))

        # About button first
        self._about_btn = ctk.CTkButton(
            btn_frame,
            text="About",
            width=80,
            fg_color="#c01c28",
            hover_color="#a01020",
            command=lambda: self._show_tab("about")
        )
        self._disclaimer_btn = ctk.CTkButton(
            btn_frame,
            text="Disclaimer",
            width=80,
            fg_color="#c01c28",
            hover_color="#a01020",
            command=lambda: self._show_tab("disclaimer")
        )
        self._credits_btn = ctk.CTkButton(
            btn_frame,
            text="Credits",
            width=80,
            fg_color="#c01c28",
            hover_color="#a01020",
            command=lambda: self._show_tab("credits")
        )

        # Pack tab buttons
        self._about_btn.pack(side="left", padx=(0, 5))
        self._disclaimer_btn.pack(side="left", padx=5)
        self._credits_btn.pack(side="left", padx=5)

        # Close button on the right
        close_btn = ctk.CTkButton(
            btn_frame,
            text="Close",
            command=self._on_close,
            width=80,
            fg_color="#c01c28",
            hover_color="#a01020"
        )
        close_btn.pack(side="right")

        # Content area (scrollable)
        self._text_frame = ctk.CTkScrollableFrame(
            self._content_frame,
            width=450,
            fg_color="transparent"
        )
        self._text_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Show about tab by default
        self._show_tab("about")

    def _show_tab(self, tab_name: str):
        """Switch to the specified tab."""
        self._active_tab = tab_name

        # Update button colors
        active_color = "#1a5fb4"
        inactive_color = "gray50"

        if self._about_btn:
            self._about_btn.configure(
                fg_color=active_color if tab_name == "about" else inactive_color
            )
        if self._disclaimer_btn:
            self._disclaimer_btn.configure(
                fg_color=active_color if tab_name == "disclaimer" else inactive_color
            )
        if self._credits_btn:
            self._credits_btn.configure(
                fg_color=active_color if tab_name == "credits" else inactive_color
            )

        # Clear current content
        if self._text_frame:
            for widget in self._text_frame.winfo_children():
                widget.destroy()

        # Show appropriate content
        if tab_name == "disclaimer":
            self._show_disclaimer_content()
        elif tab_name == "about":
            self._show_about_content()
        elif tab_name == "credits":
            self._show_credits_content()

    def _show_disclaimer_content(self):
        """Display the disclaimer content."""
        title = ctk.CTkLabel(
            self._text_frame,
            text="DISCLAIMER OF WARRANTY",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#c01c28"
        )
        title.pack(pady=(10, 20))

        disclaimer_text = (
            "Software is provided \"as is,\" without warranties of any kind, "
            "express or implied. Users accept all risks associated with using "
            "the software, including its quality, performance, and accuracy.\n\n"
            "⚠️  Mods can be dangerous!\n\n"
            "Please backup your game and character files often.\n\n"
            "If you use mods, do not report game or system crashes to the "
            "game developers.\n\n"
            "Thank you for understanding."
        )

        content = ctk.CTkLabel(
            self._text_frame,
            text=disclaimer_text,
            font=ctk.CTkFont(size=13),
            justify="left",
            wraplength=350
        )
        content.pack(pady=10, padx=10)

    def _show_about_content(self):
        """Display the about information."""
        # App name
        name_label = ctk.CTkLabel(
            self._text_frame,
            text=APP_NAME,
            font=ctk.CTkFont(size=22, weight="bold")
        )
        name_label.pack(pady=(10, 5))

        # Version and date
        version_label = ctk.CTkLabel(
            self._text_frame,
            text=f"Version {APP_VERSION}  •  {APP_DATE}",
            font=ctk.CTkFont(size=14)
        )
        version_label.pack(pady=5)

        # Author
        author_label = ctk.CTkLabel(
            self._text_frame,
            text=f"Created by {APP_AUTHOR}",
            font=ctk.CTkFont(size=13)
        )
        author_label.pack(pady=(10, 2))

        # Create DEF credit
        def_credit_label = ctk.CTkLabel(
            self._text_frame,
            text="Create DEF functionality by Sqitey",
            font=ctk.CTkFont(size=13)
        )
        def_credit_label.pack(pady=(2, 10))

        # Separator
        sep = ctk.CTkFrame(self._text_frame, height=2, fg_color="gray50")
        sep.pack(fill="x", padx=20, pady=15)

        # GitHub link
        github_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
        github_frame.pack(pady=5)

        github_icon = ctk.CTkLabel(
            github_frame,
            text="📦 GitHub Repository:",
            font=ctk.CTkFont(size=12)
        )
        github_icon.pack(side="left")

        github_link = ctk.CTkLabel(
            github_frame,
            text=GITHUB_URL,
            font=ctk.CTkFont(size=11),
            text_color="#3584e4",
            cursor="hand2"
        )
        github_link.pack(side="left", padx=(5, 0))
        github_link.bind("<Button-1>", lambda e: self._open_url(GITHUB_URL))

        # License link
        license_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
        license_frame.pack(pady=5)

        license_icon = ctk.CTkLabel(
            license_frame,
            text="📄 MIT License:",
            font=ctk.CTkFont(size=12)
        )
        license_icon.pack(side="left")

        license_link = ctk.CTkLabel(
            license_frame,
            text="View License",
            font=ctk.CTkFont(size=11, underline=True),
            text_color="#3584e4",
            cursor="hand2"
        )
        license_link.pack(side="left", padx=(5, 0))
        license_link.bind("<Button-1>", lambda e: self._open_url(LICENSE_URL))

        # Description
        desc_label = ctk.CTkLabel(
            self._text_frame,
            text=(
                "\nA tool for creating and managing mods for\n"
                "Lord of the Rings: Return to Moria"
            ),
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        desc_label.pack(pady=15)

    def _show_credits_content(self):
        """Display the credits information with clickable links."""
        title = ctk.CTkLabel(
            self._text_frame,
            text="Credits & Acknowledgments",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title.pack(pady=(10, 20))

        # Community contributors - dynamically collected from prebuilt mod INI files
        contributors = _collect_contributors()

        community_label = ctk.CTkLabel(
            self._text_frame,
            text="Community Contributors:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        community_label.pack(anchor="w", padx=10, pady=(0, 5))

        if contributors:
            for name in contributors:
                contrib_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
                contrib_frame.pack(anchor="w", padx=20, pady=1)

                bullet = ctk.CTkLabel(contrib_frame, text="•", font=ctk.CTkFont(size=12))
                bullet.pack(side="left")

                ctk.CTkLabel(
                    contrib_frame,
                    text=name,
                    font=ctk.CTkFont(size=12),
                ).pack(side="left", padx=(5, 0))
        else:
            ctk.CTkLabel(
                self._text_frame,
                text="No prebuilt mod files found",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            ).pack(anchor="w", padx=20, pady=5)

        # Separator
        sep1 = ctk.CTkFrame(self._text_frame, height=1, fg_color="gray50")
        sep1.pack(fill="x", padx=10, pady=(15, 5))

        # Third-Party Tools header
        tools_header = ctk.CTkLabel(
            self._text_frame,
            text="Third-Party Tools:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        tools_header.pack(anchor="w", padx=10, pady=(10, 5))

        # Tool links
        tools = [
            ("FModel", "UE4/UE5 asset viewer", "https://fmodel.app/"),
            ("UAssetGUI", "Unreal Engine asset editor", "https://github.com/atenfyr/UAssetGUI"),
            ("retoc", "Table of contents rebuilder", "https://github.com/trumank/retoc/releases"),
            ("ZenTools", "Zen asset tools", "https://github.com/WistfulHopes/ZenTools-UE4"),
        ]

        for name, desc, url in tools:
            tool_frame = ctk.CTkFrame(self._text_frame, fg_color="transparent")
            tool_frame.pack(anchor="w", padx=20, pady=2)

            bullet = ctk.CTkLabel(tool_frame, text="•", font=ctk.CTkFont(size=12))
            bullet.pack(side="left")

            tool_link = ctk.CTkLabel(
                tool_frame,
                text=f"{name}",
                font=ctk.CTkFont(size=12, underline=True),
                text_color="#3584e4",
                cursor="hand2"
            )
            tool_link.pack(side="left", padx=(5, 0))
            tool_link.bind("<Button-1>", lambda e, u=url: self._open_url(u))

            desc_label = ctk.CTkLabel(
                tool_frame,
                text=f" - {desc}",
                font=ctk.CTkFont(size=12)
            )
            desc_label.pack(side="left")

        # Separator
        sep2 = ctk.CTkFrame(self._text_frame, height=1, fg_color="gray50")
        sep2.pack(fill="x", padx=10, pady=(15, 5))

        # Libraries header
        libs_header = ctk.CTkLabel(
            self._text_frame,
            text="Libraries:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        libs_header.pack(anchor="w", padx=10, pady=(10, 5))

        libraries_text = (
            "• CustomTkinter - Modern UI toolkit\n"
            "• Pillow - Image processing\n"
            "• Python - Programming language"
        )

        libs_label = ctk.CTkLabel(
            self._text_frame,
            text=libraries_text,
            font=ctk.CTkFont(size=12),
            justify="left"
        )
        libs_label.pack(anchor="w", padx=20, pady=5)

    def _open_url(self, url: str):
        """Open a URL in the default browser."""
        import webbrowser
        webbrowser.open(url)

    def _on_resize(self, event=None):
        """Handle window resize to update images."""
        if event and event.widget == self:
            self.update_images()

    def update_images(self):
        """Update overlay image - use 50% of original size."""
        try:
            # Force geometry update
            self.update_idletasks()

            # Update overlay image at 50% of original size
            if self._overlay_image_pil:
                orig_w, orig_h = self._overlay_image_pil.size

                # Use 50% of original size
                new_w = orig_w // 2
                new_h = orig_h // 2

                self._overlay_image = ctk.CTkImage(
                    light_image=self._overlay_image_pil,
                    dark_image=self._overlay_image_pil,
                    size=(new_w, new_h)
                )
                self._overlay_label.configure(image=self._overlay_image)

        except OSError:
            pass  # Ignore errors during resize

    def _on_close(self):
        """Handle close button click."""
        self.destroy()


def show_about_dialog(parent: ctk.CTk) -> None:
    """Show the about dialog.

    Args:
        parent: The parent window.
    """
    dialog = AboutDialog(parent)
    # Trigger initial image update after window is displayed
    dialog.after(100, dialog.update_images)
    parent.wait_window(dialog)
