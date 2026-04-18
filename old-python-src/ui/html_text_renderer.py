"""Simple HTML-to-CTkTextbox renderer using stdlib html.parser.

Supports a limited subset of HTML tags: h1-h3, p, b/strong, i/em, ul, li,
br, table/tr/td. Renders formatted text into a CTkTextbox using tk.Text tags.
"""

from html.parser import HTMLParser

import customtkinter as ctk

HEADING_TAGS = {"h1", "h2", "h3"}
TABLE_TAGS = {"table", "tr", "td", "th"}


class HTMLToTextRenderer(HTMLParser):
    """Renders simple HTML into a CTkTextbox with styled text tags."""

    def __init__(self, textbox: ctk.CTkTextbox):
        super().__init__()
        self.textbox = textbox
        self._tag_stack: list[str] = []
        self._in_ul = False
        self._in_table = False
        self._td_count = 0  # track columns within a row
        self._configure_tags()

    def _get_fg_color(self) -> str:
        """Get the current foreground color from the textbox theme."""
        try:
            return self.textbox._textbox.cget("foreground")  # pylint: disable=protected-access
        except Exception:  # pylint: disable=broad-except
            return "white"

    def _configure_tags(self):
        """Configure text tags for formatting on the underlying tk.Text widget."""
        text_widget = self.textbox._textbox  # pylint: disable=protected-access
        font_family = "Segoe UI Emoji"
        fg = self._get_fg_color()

        text_widget.tag_configure(
            "h1", font=(font_family, 36, "bold"),
            foreground=fg, spacing1=16, spacing3=8
        )
        text_widget.tag_configure(
            "h2", font=(font_family, 32, "bold"),
            foreground=fg, spacing1=16, spacing3=8
        )
        text_widget.tag_configure(
            "h3", font=(font_family, 28, "bold"),
            foreground=fg, spacing1=16, spacing3=8
        )
        text_widget.tag_configure(
            "bold", font=(font_family, 26, "bold"),
            foreground=fg
        )
        text_widget.tag_configure(
            "italic", font=(font_family, 26, "italic"),
            foreground=fg
        )
        text_widget.tag_configure(
            "bold_italic", font=(font_family, 26, "bold italic"),
            foreground=fg
        )
        text_widget.tag_configure(
            "body", font=(font_family, 26),
            foreground=fg
        )
        text_widget.tag_configure(
            "bullet", font=(font_family, 26),
            foreground=fg, lmargin1=40, lmargin2=70
        )

    def render(self, html_content: str):
        """Clear the textbox and render the HTML content."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self._tag_stack = []
        self._in_ul = False
        self._in_table = False
        self._td_count = 0
        self._configure_tags()
        self.feed(html_content)
        self.textbox.configure(state="disabled")

    def handle_starttag(self, tag, attrs):
        if tag in HEADING_TAGS:
            self._tag_stack.append(tag)
        elif tag in ("b", "strong"):
            self._tag_stack.append("b")
        elif tag in ("i", "em"):
            self._tag_stack.append("i")
        elif tag == "p":
            self._tag_stack.append("p")
        elif tag == "ul":
            self._in_ul = True
        elif tag == "li":
            text_widget = self.textbox._textbox  # pylint: disable=protected-access
            start = text_widget.index("end-1c")
            self.textbox.insert("end", "\u2022  ")
            end = text_widget.index("end-1c")
            text_widget.tag_add("bullet", start, end)
            self._tag_stack.append("li")
        elif tag == "br":
            self.textbox.insert("end", "\n")
        elif tag == "table":
            self._in_table = True
        elif tag == "tr":
            self._td_count = 0
        elif tag in ("td", "th"):
            if self._td_count > 0:
                self.textbox.insert("end", "    ")
            self._td_count += 1
            if tag == "th":
                self._tag_stack.append("b")

    def handle_endtag(self, tag):
        if tag in HEADING_TAGS and tag in self._tag_stack:
            self._tag_stack.remove(tag)
            self.textbox.insert("end", "\n")
        elif tag in ("b", "strong") and "b" in self._tag_stack:
            self._tag_stack.remove("b")
        elif tag in ("i", "em") and "i" in self._tag_stack:
            self._tag_stack.remove("i")
        elif tag == "p" and "p" in self._tag_stack:
            self._tag_stack.remove("p")
            self.textbox.insert("end", "\n")
        elif tag == "ul":
            self._in_ul = False
        elif tag == "li" and "li" in self._tag_stack:
            self._tag_stack.remove("li")
            self.textbox.insert("end", "\n")
        elif tag == "table":
            self._in_table = False
            self.textbox.insert("end", "\n")
        elif tag == "tr":
            self.textbox.insert("end", "\n")
        elif tag == "th" and "b" in self._tag_stack:
            self._tag_stack.remove("b")

    def handle_data(self, data):
        # Skip pure whitespace between tags
        if not data.strip():
            return
        tags = self._get_current_tags()
        text_widget = self.textbox._textbox  # pylint: disable=protected-access
        start = text_widget.index("end-1c")
        self.textbox.insert("end", data)
        end = text_widget.index("end-1c")
        for t in tags:
            text_widget.tag_add(t, start, end)

    def _get_current_tags(self) -> list[str]:
        """Determine which formatting tags apply based on the current tag stack."""
        tags = []
        has_bold = "b" in self._tag_stack
        has_italic = "i" in self._tag_stack

        # Check for any heading tag
        for heading in HEADING_TAGS:
            if heading in self._tag_stack:
                tags.append(heading)
                break
        else:
            if has_bold and has_italic:
                tags.append("bold_italic")
            elif has_bold:
                tags.append("bold")
            elif has_italic:
                tags.append("italic")
            else:
                tags.append("body")

        if "li" in self._tag_stack:
            tags.append("bullet")

        return tags
