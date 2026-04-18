"""Virtual scrolling list widget for efficient rendering of large item lists.

Instead of creating thousands of widgets (one per item), this widget only
renders the rows visible in the viewport and recycles them as the user scrolls.
"""

import logging
import tkinter as tk

import customtkinter as ctk

logger = logging.getLogger(__name__)


class VirtualScrollList(ctk.CTkFrame):
    """A virtualized scrollable list that only renders visible rows.

    Uses a plain tk.Canvas with row frames placed directly via create_window.
    The canvas scroll region covers all items; only visible rows get widgets.

    Data model:
        Items stored as list of dicts with 'key', 'label_text', 'eye_visible'.
        Checkbox state is read/written via an external ``check_vars`` dict
        of ``{key: BooleanVar}`` so existing code continues to work.

    Callbacks:
        on_item_click(key)        – user clicked a row label
        on_checkbox_toggle(key)   – user toggled a checkbox
    """

    ROW_HEIGHT = 44
    CHECKBOX_WIDTH = 28
    EYE_WIDTH = 24
    FONT_SIZE = 14

    def __init__(
        self,
        parent,
        on_item_click=None,
        on_checkbox_toggle=None,
        eye_icons=None,
        check_vars: dict | None = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self._on_item_click = on_item_click
        self._on_checkbox_toggle = on_checkbox_toggle

        # External BooleanVar dict — shared with parent view
        self._check_vars: dict = check_vars or {}

        # Eye icons: (visible_icon, hidden_icon)
        self._eye_visible_icon = eye_icons[0] if eye_icons else None
        self._eye_hidden_icon = eye_icons[1] if eye_icons else None
        self._show_eyes = bool(eye_icons)

        # Data
        self._all_items: list[dict] = []
        self._filtered_indices: list[int] = []
        self._key_to_index: dict = {}
        self._selected_key = None
        self._filter_text = ""

        # Tk canvas + scrollbar
        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._scrollbar = ctk.CTkScrollbar(self, command=self._on_scrollbar)
        self._canvas.configure(yscrollcommand=self._on_canvas_scroll)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # Row widget pool — each row has a canvas window id
        self._row_pool: list[dict] = []
        self._pool_size = 0

        # Match theme background
        self._sync_bg()

        # Events
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_scroll(self._canvas)

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------

    def _sync_bg(self):
        """Match canvas bg to CTk theme."""
        mode = ctk.get_appearance_mode()
        bg = "#2b2b2b" if mode == "Dark" else "#f0f0f0"
        self._canvas.configure(bg=bg)

    # ------------------------------------------------------------------
    # Scroll binding helpers
    # ------------------------------------------------------------------

    def _bind_scroll(self, widget):
        """Bind mousewheel to a widget."""
        widget.bind("<MouseWheel>", self._on_mousewheel)

    def _on_scrollbar(self, *args):
        """Handle scrollbar drag — scroll canvas and redraw."""
        self._canvas.yview(*args)
        self._redraw()

    def _on_canvas_scroll(self, first, last):
        """Called by canvas when scroll position changes — update scrollbar."""
        self._scrollbar.set(first, last)

    def _on_mousewheel(self, event):
        """Scroll by 2 rows per wheel tick and redraw."""
        total_height = len(self._filtered_indices) * self.ROW_HEIGHT
        if total_height <= 0:
            return "break"
        delta = int(-1 * (event.delta / 120))
        fraction = (2 * self.ROW_HEIGHT * delta) / total_height
        current = self._canvas.yview()[0]
        new_pos = max(0.0, min(1.0, current + fraction))
        self._canvas.yview_moveto(new_pos)
        self._redraw()
        return "break"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_items(self, items: list[dict], check_vars: dict | None = None):
        """Replace all items and redraw."""
        if check_vars is not None:
            self._check_vars = check_vars

        self._all_items = []
        self._key_to_index.clear()

        for i, item in enumerate(items):
            entry = {
                'key': item['key'],
                'label_text': item['label_text'],
                'eye_visible': item.get('eye_visible', True),
            }
            self._all_items.append(entry)
            self._key_to_index[item['key']] = i

        # Reset all bound keys so rows get fully rebound
        for row in self._row_pool:
            row['bound_key'] = None

        self._apply_filter_internal(self._filter_text)
        self._canvas.yview_moveto(0)

    def clear(self):
        """Remove all items."""
        self._all_items.clear()
        self._filtered_indices.clear()
        self._key_to_index.clear()
        self._selected_key = None
        self._filter_text = ""
        self._hide_all_rows()
        self._update_scroll_region()

    def get_item_count(self) -> int:
        return len(self._all_items)

    def get_visible_count(self) -> int:
        return len(self._filtered_indices)

    def set_selected(self, key):
        self._selected_key = key
        self._redraw()

    def get_selected(self):
        return self._selected_key

    def set_eye_visible(self, key, visible: bool):
        idx = self._key_to_index.get(key)
        if idx is not None:
            self._all_items[idx]['eye_visible'] = visible
            self._redraw()

    def update_eye_icons(self, eye_icons):
        if eye_icons:
            self._eye_visible_icon = eye_icons[0]
            self._eye_hidden_icon = eye_icons[1]
            self._show_eyes = True
        else:
            self._show_eyes = False
        self._redraw()

    def apply_filter(self, filter_text: str) -> tuple[int, int]:
        self._filter_text = filter_text
        self._apply_filter_internal(filter_text)
        return len(self._filtered_indices), len(self._all_items)

    def scroll_to_key(self, key):
        try:
            filtered_pos = self._filtered_indices.index(
                self._key_to_index[key]
            )
        except (KeyError, ValueError):
            return
        total = len(self._filtered_indices)
        if total == 0:
            return
        self._canvas.yview_moveto(filtered_pos / total)

    def scroll_to_top(self):
        self._canvas.yview_moveto(0)

    def redraw(self):
        self._redraw()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _apply_filter_internal(self, filter_text: str):
        ft = filter_text.lower().strip()
        self._filtered_indices = [
            i for i, item in enumerate(self._all_items)
            if not ft or ft in item['label_text'].lower()
        ]
        self._update_scroll_region()
        self._redraw()

    def _update_scroll_region(self):
        total_height = max(1, len(self._filtered_indices) * self.ROW_HEIGHT)
        canvas_width = self._canvas.winfo_width() or 300
        self._canvas.configure(scrollregion=(0, 0, canvas_width, total_height))

    def _on_canvas_configure(self, event):
        needed = (event.height // self.ROW_HEIGHT) + 3
        if needed != self._pool_size:
            self._rebuild_pool(needed)
            self._pool_size = needed
        self._update_scroll_region()
        self._redraw()

    def _rebuild_pool(self, count: int):
        # Remove excess
        while len(self._row_pool) > count:
            row = self._row_pool.pop()
            self._canvas.delete(row['win_id'])
            row['frame'].destroy()

        # Add new
        while len(self._row_pool) < count:
            row = self._create_row()
            self._row_pool.append(row)

    def _create_row(self) -> dict:
        frame = ctk.CTkFrame(self._canvas, fg_color="transparent",
                             height=self.ROW_HEIGHT)
        frame.pack_propagate(False)

        checkbox = ctk.CTkCheckBox(frame, text="", width=self.CHECKBOX_WIDTH)
        checkbox.pack(side="left", padx=(4, 0))

        label = ctk.CTkLabel(
            frame, text="", anchor="w", cursor="hand2",
            text_color=("gray10", "#E8E8E8"),
            font=ctk.CTkFont(size=self.FONT_SIZE),
        )
        label.pack(side="left", fill="x", expand=True, padx=8, pady=6)

        eye_label = ctk.CTkLabel(frame, text="", width=self.EYE_WIDTH)
        eye_label.pack(side="right", padx=(0, 5))

        # Place off-screen initially; create_window gives us an id to move later
        canvas_width = self._canvas.winfo_width() or 300
        win_id = self._canvas.create_window(
            0, -100, window=frame, anchor="nw",
            width=canvas_width, height=self.ROW_HEIGHT
        )

        # Bind mousewheel on all child widgets
        for w in (frame, label, eye_label, checkbox):
            self._bind_scroll(w)

        return {
            'frame': frame,
            'checkbox': checkbox,
            'label': label,
            'eye_label': eye_label,
            'win_id': win_id,
            'bound_key': None,
            '_prev_selected': None,
            '_prev_checked': None,
            '_prev_eye': None,
        }

    def _hide_all_rows(self):
        for row in self._row_pool:
            self._canvas.coords(row['win_id'], 0, -100)

    def _redraw(self):
        if not self._filtered_indices:
            self._hide_all_rows()
            return

        canvas_height = self._canvas.winfo_height()
        if canvas_height <= 1:
            return

        canvas_width = self._canvas.winfo_width() or 300
        total_items = len(self._filtered_indices)

        y_top = self._canvas.canvasy(0)
        first_visible = max(0, int(y_top // self.ROW_HEIGHT))
        first_visible = min(first_visible, max(0, total_items - 1))

        last_visible = min(
            first_visible + (canvas_height // self.ROW_HEIGHT) + 3,
            total_items
        )

        pool_idx = 0
        for fi in range(first_visible, last_visible):
            if pool_idx >= len(self._row_pool):
                break

            item_idx = self._filtered_indices[fi]
            item = self._all_items[item_idx]
            row = self._row_pool[pool_idx]

            self._bind_row(row, item)

            # Position directly on canvas at the item's absolute Y
            y = fi * self.ROW_HEIGHT
            self._canvas.coords(row['win_id'], 0, y)
            self._canvas.itemconfigure(row['win_id'],
                                       width=canvas_width,
                                       height=self.ROW_HEIGHT)

            pool_idx += 1

        # Hide unused pool rows
        for i in range(pool_idx, len(self._row_pool)):
            self._canvas.coords(self._row_pool[i]['win_id'], 0, -100)

    def _bind_row(self, row: dict, item: dict):
        key = item['key']
        is_selected = (key == self._selected_key)

        check_var = self._check_vars.get(key)
        checked = check_var.get() if check_var else False
        eye_vis = item['eye_visible']

        key_changed = (row['bound_key'] != key)
        sel_changed = (row['_prev_selected'] != is_selected)
        chk_changed = (row['_prev_checked'] != checked)
        eye_changed = (row['_prev_eye'] != eye_vis)

        if not (key_changed or sel_changed or chk_changed or eye_changed):
            return

        if key_changed or sel_changed:
            if key_changed:
                row['label'].configure(text=item['label_text'])
            if is_selected:
                row['frame'].configure(fg_color=("#d0e8ff", "#1a4a6e"))
                row['label'].configure(text_color=("#0066cc", "#66b3ff"))
            else:
                row['frame'].configure(fg_color="transparent")
                row['label'].configure(text_color=("gray10", "#E8E8E8"))

        if key_changed:
            cb = row['checkbox']
            cb.configure(command=lambda k=key: self._handle_checkbox(k))
            row['label'].bind("<Button-1>", lambda e, k=key: self._handle_click(k))
            row['frame'].bind("<Button-1>", lambda e, k=key: self._handle_click(k))
            row['label'].bind("<Enter>", lambda e, k=key, lbl=row['label']: self._handle_hover(k, lbl, True))
            row['label'].bind("<Leave>", lambda e, k=key, lbl=row['label']: self._handle_hover(k, lbl, False))

        if key_changed or chk_changed:
            cb = row['checkbox']
            if checked and not cb.get():
                cb.select()
            elif not checked and cb.get():
                cb.deselect()

        if key_changed or eye_changed:
            if self._show_eyes and self._eye_visible_icon and self._eye_hidden_icon:
                icon = self._eye_visible_icon if eye_vis else self._eye_hidden_icon
                row['eye_label'].configure(image=icon)
            else:
                row['eye_label'].configure(image="", text="")

        row['bound_key'] = key
        row['_prev_selected'] = is_selected
        row['_prev_checked'] = checked
        row['_prev_eye'] = eye_vis

    def _handle_click(self, key):
        self._selected_key = key
        self._redraw()
        if self._on_item_click:
            self._on_item_click(key)

    def _handle_checkbox(self, key):
        check_var = self._check_vars.get(key)
        if check_var:
            check_var.set(not check_var.get())
        if self._on_checkbox_toggle:
            self._on_checkbox_toggle(key)

    def _handle_hover(self, key, label, entering: bool):
        if key == self._selected_key:
            return
        if entering:
            label.configure(text_color="#4CAF50")
        else:
            label.configure(text_color=("gray10", "#E8E8E8"))
