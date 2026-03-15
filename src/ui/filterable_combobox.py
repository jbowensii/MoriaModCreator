"""Filterable combobox widget for single-value selection with type-to-filter.

Provides a text entry with a dropdown arrow button that shows a scrollable
list of options. Typing in the entry filters the list case-insensitively.
Clicking the arrow button shows all options. Keyboard navigation
(Up/Down/Enter/Escape) is fully supported.

This is a drop-in replacement for CTkComboBox, using the same
variable/values constructor API.

Layout:
    [  Entry (text input, expands)  ][ ▾ ]   <- arrow button (28px)
    +---------------------------------+
    |  Option 1                       |      <- popup (CTkToplevel)
    |  Option 2                       |         with scrollable frame
    |  ...                            |
    +---------------------------------+
"""

import tkinter as tk

import customtkinter as ctk


class FilterableComboBox(ctk.CTkFrame):
    """Entry widget with filterable dropdown for single-value selection.

    Features:
        - Filters options as user types (case-insensitive partial match)
        - Shows all options on arrow button click or Down arrow key
        - Keyboard navigation: Up/Down to move, Enter to select, Escape to close
        - Scrollable popup for large option lists (e.g., 100+ materials)
        - Popup auto-positions below entry; flips above if near screen bottom

    Args:
        parent: Parent widget.
        variable: StringVar bound to the entry text (read/write).
        values: List of option strings to display in the dropdown.
        width: Total widget width in pixels (default 350).

    Example:
        var = ctk.StringVar(value="")
        combo = FilterableComboBox(parent, variable=var,
                                   values=["Stone", "Iron", "Wood"])
        combo.pack()
    """

    MAX_VISIBLE = 30       # Max items shown before scrolling kicks in
    DROPDOWN_GAP = 4       # Pixels between entry bottom and popup top

    def __init__(self, parent, variable: ctk.StringVar, values: list[str],
                 width: int = 350, **kwargs):
        # CTkFrame doesn't accept 'command', so strip it if passed
        kwargs.pop('command', None)
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.variable = variable
        self.all_values = list(values) if values else []
        self.dropdown_visible = False
        self.dropdown_window = None       # CTkToplevel popup (created on demand)
        self.scroll_frame = None          # Scrollable frame inside popup
        self.current_matches = []         # Filtered option list
        self.selected_index = -1          # Keyboard highlight index (-1 = none)
        self.item_buttons = []            # CTkButton refs in the popup
        self._closing = False             # Guard against re-entrant hide

        # --- Entry widget (fills remaining space) ---
        entry_width = max(width - 28, 100)
        self.entry = ctk.CTkEntry(self, textvariable=variable,
                                  width=entry_width)
        self.entry.pack(side="left", fill="x", expand=True)

        # --- Arrow button (fixed 28px) ---
        self.arrow_btn = ctk.CTkButton(
            self, text="\u25be", width=28, height=28,
            fg_color="transparent",
            hover_color=("gray80", "gray35"),
            text_color=("gray10", "gray90"),
            command=self._toggle_dropdown
        )
        self.arrow_btn.pack(side="left")

        # --- Bind keyboard/focus events to the entry ---
        self.entry.bind("<KeyRelease>", self._on_key_release)
        self.entry.bind("<Down>", self._on_down_arrow)
        self.entry.bind("<Up>", self._on_up_arrow)
        self.entry.bind("<Return>", self._on_enter)
        self.entry.bind("<Escape>", self._on_escape)

        # Close dropdown when user clicks elsewhere in the app
        self._click_bind_id = None

    # -----------------------------------------------------------------------
    #  Public API
    # -----------------------------------------------------------------------

    def get(self) -> str:
        """Get the current entry value."""
        return self.variable.get()

    def set(self, value: str):
        """Set the entry value programmatically."""
        self.variable.set(value)

    def update_values(self, new_values: list[str]):
        """Replace the list of available dropdown options."""
        self.all_values = list(new_values) if new_values else []

    # -----------------------------------------------------------------------
    #  Event handlers
    # -----------------------------------------------------------------------

    def _on_key_release(self, event):
        """Filter and show dropdown as the user types.

        Ignores navigation keys (handled by their own bindings).
        Filters case-insensitively using partial "contains" matching.
        """
        if event.keysym in ("Return", "Tab", "Escape", "Up", "Down"):
            return

        text = self.variable.get().strip()
        if text:
            # Show options containing the typed text (case-insensitive)
            self.current_matches = [
                v for v in self.all_values if text.lower() in v.lower()
            ][:self.MAX_VISIBLE]
        else:
            # Empty text -> show all options
            self.current_matches = self.all_values[:self.MAX_VISIBLE]

        if self.current_matches:
            self._show_dropdown()
        else:
            self._hide_dropdown()

    def _toggle_dropdown(self):
        """Arrow button click: toggle dropdown open/closed."""
        if self.dropdown_visible:
            self._hide_dropdown()
        else:
            self.current_matches = self.all_values[:self.MAX_VISIBLE]
            if self.current_matches:
                self._show_dropdown()
            self.entry.focus_set()

    def _on_escape(self, _event=None):
        """Close dropdown on Escape key without changing the value."""
        if self.dropdown_visible:
            self._hide_dropdown()
            return "break"
        return None

    # -----------------------------------------------------------------------
    #  Dropdown popup management
    # -----------------------------------------------------------------------

    def _show_dropdown(self):
        """Create or update the dropdown popup window.

        On first call, creates a CTkToplevel with overrideredirect (no
        window decorations) containing a CTkScrollableFrame. On subsequent
        calls, just rebuilds the option buttons.
        """
        if self.dropdown_window:
            self._update_listbox()
            return

        # Create the popup toplevel (borderless, always on top)
        self.dropdown_window = ctk.CTkToplevel(self)
        self.dropdown_window.withdraw()
        self.dropdown_window.overrideredirect(True)
        self.dropdown_window.attributes("-topmost", True)

        # Scrollable frame holds the option buttons
        popup_height = min(len(self.current_matches) * 30 + 10, 350)
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.dropdown_window,
            fg_color=("gray95", "gray20"),
            height=popup_height - 6
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=1, pady=1)

        self.item_buttons = []
        self._update_listbox()
        self._position_dropdown()
        self.dropdown_window.deiconify()
        self.dropdown_visible = True
        self.selected_index = -1

        # Bind a global click handler to close when clicking outside
        root = self.winfo_toplevel()
        self._click_bind_id = root.bind("<Button-1>", self._on_global_click, add="+")
        self.dropdown_window.bind("<Button-1>", lambda e: "break")

    def _update_listbox(self):
        """Rebuild option buttons inside the scrollable frame.

        Destroys existing buttons and creates new ones for the current
        filtered matches. Each button selects its option on click.
        """
        for btn in self.item_buttons:
            btn.destroy()
        self.item_buttons = []

        for match in self.current_matches:
            btn = ctk.CTkButton(
                self.scroll_frame,
                text=match,
                anchor="w",
                height=28,
                corner_radius=0,
                fg_color="transparent",
                hover_color=("gray80", "gray35"),
                text_color=("gray10", "gray90"),
                command=lambda m=match: self._select_item(m)
            )
            btn.pack(fill="x")
            self.item_buttons.append(btn)

        self._position_dropdown()

    def _position_dropdown(self):
        """Position the popup below the entry, flipping above if near
        the bottom edge of the screen.
        """
        if not self.dropdown_window:
            return

        x = self.entry.winfo_rootx()
        y = (self.entry.winfo_rooty()
             + self.entry.winfo_height()
             + self.DROPDOWN_GAP)
        width = max(self.winfo_width(), 300)
        height = min(len(self.current_matches) * 30 + 10, 350)

        # Flip above the entry if popup would go off-screen
        screen_height = self.winfo_screenheight()
        if y + height > screen_height - 50:
            y = self.entry.winfo_rooty() - height - self.DROPDOWN_GAP

        self.dropdown_window.geometry(f"{width}x{height}+{x}+{y}")

    def _hide_dropdown(self, _event=None):
        """Destroy the dropdown popup and reset state.

        Uses a _closing guard to prevent re-entrant calls (can happen
        if destroy triggers focus events that call hide again).
        """
        if self._closing:
            return
        self._closing = True
        try:
            # Remove global click binding
            if self._click_bind_id:
                try:
                    self.winfo_toplevel().unbind("<Button-1>", self._click_bind_id)
                except (tk.TclError, ValueError):
                    pass
                self._click_bind_id = None
            if self.dropdown_window:
                self.dropdown_window.destroy()
                self.dropdown_window = None
                self.scroll_frame = None
                self.item_buttons = []
            self.dropdown_visible = False
            self.selected_index = -1
        finally:
            self._closing = False

    # -----------------------------------------------------------------------
    #  Selection
    # -----------------------------------------------------------------------

    def _select_item(self, item: str):
        """Set the variable to the selected item and close the dropdown."""
        self.variable.set(item)
        self._hide_dropdown()
        self.entry.focus_set()

    # -----------------------------------------------------------------------
    #  Keyboard navigation
    # -----------------------------------------------------------------------

    def _on_down_arrow(self, _event):
        """Move highlight down one item, or open dropdown if closed."""
        if not self.dropdown_visible or not self.current_matches:
            self.current_matches = self.all_values[:self.MAX_VISIBLE]
            if self.current_matches:
                self._show_dropdown()
            return "break"

        self.selected_index = min(
            self.selected_index + 1, len(self.current_matches) - 1)
        self._highlight_selection()
        return "break"

    def _on_up_arrow(self, _event):
        """Move highlight up one item."""
        if not self.dropdown_visible or not self.current_matches:
            return None
        self.selected_index = max(self.selected_index - 1, 0)
        self._highlight_selection()
        return "break"

    def _on_enter(self, _event):
        """Select the currently highlighted item on Enter key."""
        if (self.dropdown_visible
                and 0 <= self.selected_index < len(self.current_matches)):
            self._select_item(self.current_matches[self.selected_index])
            return "break"
        self._hide_dropdown()
        return None

    def _highlight_selection(self):
        """Update button colors to show which item is keyboard-selected."""
        for i, btn in enumerate(self.item_buttons):
            if i == self.selected_index:
                btn.configure(fg_color=("gray75", "gray40"))
            else:
                btn.configure(fg_color="transparent")

    # -----------------------------------------------------------------------
    #  Focus management
    # -----------------------------------------------------------------------

    def _on_global_click(self, event):
        """Close dropdown when user clicks outside the combobox and popup."""
        if not self.dropdown_visible:
            return

        # Check if click is on our entry or arrow button
        try:
            clicked = event.widget
            # Walk up from clicked widget to see if it's part of us
            widget = clicked
            while widget is not None:
                if widget is self or widget is self.dropdown_window:
                    return  # Click is inside our widget tree — keep open
                widget = widget.master
        except (AttributeError, TypeError):
            pass

        # Click was outside — close
        self._hide_dropdown()
