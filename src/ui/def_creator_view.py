"""Create DEF view — generates .def files by comparing modded vs original game files.

Algorithm:
1. User selects two folders: modded game files and original game files
2. Auto-converts any .uasset files to JSON using UAssetGUI
3. Matches files by name between both folders
4. For each matched pair, parses the UAssetAPI JSON (Exports[0].Table.Data[])
5. Walks each row's Value property list recursively, comparing primitives,
   arrays, and structs to find differences
6. Groups differences by leaf property name (e.g. all MaxStackSize changes)
7. Generates one .def XML file per property group per JSON file
8. Shows a preview/edit window; user can edit before saving
"""

import json
import logging
import os
import subprocess
import threading
from pathlib import Path

import customtkinter as ctk

from src.config import get_utilities_dir
from src.constants import UE_VERSION, UASSETGUI_EXE
from src.ui.shared_utils import get_jsondata_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure diff logic (no UI dependency, testable)
# ---------------------------------------------------------------------------


def _format_value(val):
    """Format a property value for display in .def XML."""
    if isinstance(val, bool):
        return "True" if val else "False"
    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str(val)


def _extract_context(props_list, prop_name):
    """Try to find a meaningful context label (e.g. item name) near the property."""
    relevant = ("Count", "Cost", "MinPrice", "MaxPrice", "Amount")
    if not any(r in prop_name for r in relevant):
        return None

    context_keys = ("Item", "Resource", "Material", "ItemTemplate", "ItemTag", "Tag")
    for prop in props_list:
        if not isinstance(prop, dict):
            continue
        name = prop.get("Name", "")
        if name not in context_keys:
            continue
        val = prop.get("Value")
        if isinstance(val, dict):
            for key in ("AssetPath", "ObjectName", "TagName", "Name"):
                if key in val:
                    inner = val[key]
                    if isinstance(inner, dict) and "AssetName" in inner:
                        asset = inner["AssetName"]
                        return asset.split("/")[-1].split(".")[0]
                    if isinstance(inner, str):
                        return inner
        elif isinstance(val, str):
            return val
    return None


def _compare_properties(mod_props, orig_props, current_path=""):
    """Recursively compare two UAssetAPI property lists and return changes."""
    changes = []
    if not (isinstance(mod_props, list) and isinstance(orig_props, list)):
        return changes

    orig_dict = {}
    for o in orig_props:
        if isinstance(o, dict) and "Name" in o:
            orig_dict[o["Name"]] = o

    for m in mod_props:
        if not isinstance(m, dict):
            continue

        type_str = m.get("$type", "")
        if "Name" not in m:
            continue

        prop_name = m["Name"]
        new_path = f"{current_path}.{prop_name}" if current_path else prop_name
        o = orig_dict.get(prop_name)

        if not o:
            # New property added by the mod
            val = m.get("Value")
            str_val = _format_value(val) if not isinstance(val, (list, dict)) else ""
            changes.append({
                "type": "add",
                "property": new_path,
                "value": str_val,
                "old_value": "New Property",
                "context": None,
                "json_data": json.dumps(m, indent=2),
            })
            continue

        if "ArrayPropertyData" in type_str:
            m_list = m.get("Value", [])
            o_list = o.get("Value", [])
            for i in range(max(len(m_list), len(o_list))):
                arr_path = f"{new_path}[{i}]"
                m_val = m_list[i] if i < len(m_list) else None
                o_val = o_list[i] if i < len(o_list) else None
                if m_val and not o_val:
                    if isinstance(m_val, dict) and "Value" in m_val:
                        changes.extend(_compare_properties(
                            m_val.get("Value", []), [], arr_path
                        ))
                elif m_val and o_val:
                    if isinstance(m_val, dict) and isinstance(o_val, dict):
                        changes.extend(_compare_properties(
                            m_val.get("Value", []),
                            o_val.get("Value", []),
                            arr_path,
                        ))
        elif "StructPropertyData" in type_str:
            changes.extend(_compare_properties(
                m.get("Value", []), o.get("Value", []), new_path
            ))
        else:
            primitive_types = (
                "IntPropertyData", "BoolPropertyData", "FloatPropertyData",
                "EnumPropertyData", "NamePropertyData", "StrPropertyData",
                "BytePropertyData", "TextPropertyData",
            )
            if any(pt in type_str for pt in primitive_types):
                m_val = m.get("Value")
                o_val = o.get("Value")
                if m_val != o_val:
                    context = _extract_context(orig_props, prop_name)
                    changes.append({
                        "type": "change",
                        "property": new_path,
                        "value": _format_value(m_val),
                        "old_value": _format_value(o_val),
                        "context": context,
                    })
    return changes


def find_differences(orig_data, mod_data):
    """Compare two DataTable Data arrays and return all differences."""
    differences = []
    orig_dict = {item.get("Name"): item for item in orig_data}

    for mod_item in mod_data:
        item_name = mod_item.get("Name")
        orig_item = orig_dict.get(item_name)
        orig_props = orig_item.get("Value", []) if orig_item else []

        diffs = _compare_properties(mod_item.get("Value", []), orig_props)
        for diff in diffs:
            diff["item"] = item_name
            differences.append(diff)
    return differences


def group_diffs_by_property(differences):
    """Group differences by their leaf property name."""
    grouped = {}
    for diff in differences:
        prop_key = diff["property"].split(".")[-1].split("[")[0]
        grouped.setdefault(prop_key, []).append(diff)
    return grouped


def generate_def_xml(diffs, mod_path, title, author, description,
                     change_note="", include_comments=False):
    """Generate a .def XML string from a list of differences.

    Args:
        diffs: List of diff dicts (item, property, value, old_value, type, etc.)
        mod_path: Relative path to the mod JSON file
        title: Mod title
        author: Mod author
        description: Mod description
        change_note: Default change note
        include_comments: Whether to include XML comments for each change
    """
    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<definition>",
        f"  <title>{title}</title>",
        f"  <author>{author}</author>",
        f"  <description>{description}</description>",
        f'  <mod file="{mod_path}">',
    ]

    for diff in diffs:
        if include_comments:
            item_info = diff["item"]
            if diff.get("context"):
                item_info += f": {diff['context']}"
            old_text = "Added" if diff.get("type") == "add" else f"was {diff['old_value']}"
            comment = f"{change_note} - {item_info}" if change_note else item_info
            lines.append(f"    <!--  {comment} ({old_text})  -->")

        if diff.get("type") == "add":
            lines.append(f'    <change item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}">')
            lines.append(f'      <add_property item="{diff["item"]}">'
                         f'<![CDATA[{diff.get("json_data", "")}]]>'
                         f'</add_property>')
            lines.append('    </change>')
        else:
            lines.append(f'    <change item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}" />')

    lines.append("  </mod>")
    lines.append("</definition>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


class DefCreatorView(ctk.CTkFrame):
    """Advanced-mode view for generating .def files from modded vs original game files."""

    def __init__(self, parent, on_status_message=None, on_back=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_status = on_status_message
        self._on_back = on_back

        self._mod_folder = ""
        self._orig_folder = ""
        self._generated_files: dict[str, str] = {}  # {filename: xml_content}
        self._include_comments = ctk.BooleanVar(value=False)
        self._scan_thread = None
        self._current_preview_file = None

        # Entry widgets (created in _create_ui)
        self._mod_entry = None
        self._orig_entry = None
        self._title_entry = None
        self._author_entry = None
        self._desc_entry = None
        self._note_entry = None

        self._create_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _create_ui(self):
        """Build the full Create DEF interface."""
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Scrollable container
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll.grid_columnconfigure(1, weight=1)

        row = 0

        # --- Title ---
        title = ctk.CTkLabel(
            scroll, text="Create DEF Files",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=("#333", "#ddd"),
        )
        title.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 5))
        row += 1

        subtitle = ctk.CTkLabel(
            scroll,
            text="Compare modded game files against originals to generate .def definition files.",
            text_color="gray",
        )
        subtitle.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 15))
        row += 1

        # --- Section: Folder Selection ---
        row = self._create_section_header(scroll, "Folder Selection", "#FF9800", row)

        ctk.CTkLabel(scroll, text="Modded Files Folder:", anchor="w", width=160).grid(
            row=row, column=0, sticky="w", pady=3
        )
        self._mod_entry = ctk.CTkEntry(scroll, placeholder_text="Select folder with modded .json or .uasset files...")
        self._mod_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=3)
        ctk.CTkButton(scroll, text="Browse...", width=90, command=self._browse_mod_folder).grid(
            row=row, column=2, pady=3
        )
        row += 1

        ctk.CTkLabel(scroll, text="Original Files Folder:", anchor="w", width=160).grid(
            row=row, column=0, sticky="w", pady=3
        )
        self._orig_entry = ctk.CTkEntry(scroll, placeholder_text="Select folder with original game .json files...")
        # Default to the jsondata output directory from settings
        default_orig = get_jsondata_dir()
        if default_orig.exists():
            self._orig_entry.insert(0, str(default_orig))
            self._orig_folder = str(default_orig)
        self._orig_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=3)
        ctk.CTkButton(scroll, text="Browse...", width=90, command=self._browse_orig_folder).grid(
            row=row, column=2, pady=3
        )
        row += 1

        # --- Section: Metadata ---
        row = self._create_section_header(scroll, "DEF File Metadata", "#4CAF50", row)

        for label_text, attr_name, default, placeholder in [
            ("Title:", "_title_entry", "My Mod", "Enter mod title..."),
            ("Author:", "_author_entry", "", "Enter author name..."),
            ("Description:", "_desc_entry", "", "Enter mod description..."),
            ("Change Note:", "_note_entry", "", "Default note for each change (optional)..."),
        ]:
            ctk.CTkLabel(scroll, text=label_text, anchor="w", width=160).grid(
                row=row, column=0, sticky="w", pady=3
            )
            entry = ctk.CTkEntry(scroll, placeholder_text=placeholder)
            if default:
                entry.insert(0, default)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
            # Assign to pre-declared instance attribute
            if attr_name == "_title_entry":
                self._title_entry = entry
            elif attr_name == "_author_entry":
                self._author_entry = entry
            elif attr_name == "_desc_entry":
                self._desc_entry = entry
            elif attr_name == "_note_entry":
                self._note_entry = entry
            row += 1

        # Comments checkbox
        cb = ctk.CTkCheckBox(
            scroll,
            text="Include comments in generated .def files",
            variable=self._include_comments,
        )
        cb.grid(row=row, column=0, columnspan=3, sticky="w", pady=(5, 10))
        row += 1

        # --- Action Buttons ---
        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        row += 1

        ctk.CTkButton(
            btn_frame, text="Scan & Compare",
            width=160, height=36,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._scan_and_compare,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Save All .def Files",
            width=160, height=36,
            fg_color=("#1565C0", "#0D47A1"),
            hover_color=("#0D47A1", "#082D69"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_all_files,
        ).pack(side="left", padx=(0, 10))

        # --- Section: Log ---
        row = self._create_section_header(scroll, "Log", "#2196F3", row)

        self._log_box = ctk.CTkTextbox(scroll, height=160, font=ctk.CTkFont(family="Consolas", size=11))
        self._log_box.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._log_box.configure(state="disabled")
        row += 1

        # --- Section: Preview ---
        row = self._create_section_header(scroll, "Preview / Edit", "#9C27B0", row)

        preview_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        preview_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        preview_frame.grid_columnconfigure(0, weight=1)
        row += 1

        # File selector
        selector_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        selector_row.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(selector_row, text="File:", width=40).pack(side="left")
        self._file_selector = ctk.CTkComboBox(
            selector_row, values=["(no files generated yet)"],
            command=self._on_file_selected, width=500,
        )
        self._file_selector.pack(side="left", fill="x", expand=True, padx=5)

        self._file_count_label = ctk.CTkLabel(selector_row, text="0 files", text_color="gray")
        self._file_count_label.pack(side="right", padx=5)

        self._preview_box = ctk.CTkTextbox(
            preview_frame, height=350,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._preview_box.pack(fill="both", expand=True)

        self._current_preview_file = None

    def _create_section_header(self, parent, text, color, row):
        """Create a colored section header label and separator line."""
        header = ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        )
        header.grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 2))
        row += 1
        sep = ctk.CTkFrame(parent, height=2, fg_color=color)
        sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        row += 1
        return row

    # ------------------------------------------------------------------
    # Folder browsing
    # ------------------------------------------------------------------

    def _browse_mod_folder(self):
        folder = ctk.filedialog.askdirectory(title="Select Modded Files Folder")
        if folder:
            self._mod_folder = folder
            self._mod_entry.delete(0, "end")
            self._mod_entry.insert(0, folder)

    def _browse_orig_folder(self):
        folder = ctk.filedialog.askdirectory(title="Select Original Game Files Folder")
        if folder:
            self._orig_folder = folder
            self._orig_entry.delete(0, "end")
            self._orig_entry.insert(0, folder)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, msg):
        """Append a message to the log textbox (thread-safe)."""
        def _append():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", msg + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        if threading.current_thread() is threading.main_thread():
            _append()
        else:
            self.after(0, _append)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _set_status(self, msg):
        if self._on_status:
            self._on_status(msg)

    # ------------------------------------------------------------------
    # UAssetGUI conversion
    # ------------------------------------------------------------------

    def _get_uassetgui_path(self) -> Path | None:
        """Find UAssetGUI.exe in the utilities directory."""
        utils_dir = get_utilities_dir()
        path = utils_dir / UASSETGUI_EXE
        if path.exists():
            return path
        return None

    def _convert_uassets(self, folder: str) -> int:
        """Convert .uasset files in folder to JSON. Returns count converted."""
        gui_path = self._get_uassetgui_path()
        if not gui_path:
            self._log("[WARNING] UAssetGUI.exe not found — skipping .uasset conversion.")
            return 0

        kwargs = {}
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            kwargs["startupinfo"] = startupinfo
            kwargs["creationflags"] = 0x08000000

        converted = 0
        for root_dir, _, files in os.walk(folder):
            files_lower = {f.lower() for f in files}
            for f in files:
                if not f.lower().endswith(".uasset"):
                    continue
                base = os.path.splitext(f)[0]
                if (base + ".json").lower() in files_lower:
                    continue
                uasset_path = os.path.join(root_dir, f)
                json_path = os.path.join(root_dir, base + ".json")
                self._log(f"  Converting: {f}")
                try:
                    subprocess.run(
                        [str(gui_path), "tojson", uasset_path, json_path, UE_VERSION],
                        check=True, timeout=30, capture_output=True, **kwargs,
                    )
                    converted += 1
                except subprocess.TimeoutExpired:
                    self._log(f"  [ERROR] Timeout converting {f}")
                except subprocess.CalledProcessError as e:
                    self._log(f"  [ERROR] Failed to convert {f}: {e}")
        return converted

    # ------------------------------------------------------------------
    # Scan & Compare
    # ------------------------------------------------------------------

    def _scan_and_compare(self):
        """Main action: convert, compare, and generate .def previews."""
        mod_folder = self._mod_entry.get().strip()
        orig_folder = self._orig_entry.get().strip()

        if not mod_folder or not orig_folder:
            self._log("[ERROR] Please select both Modded and Original folders.")
            return
        if not os.path.isdir(mod_folder) or not os.path.isdir(orig_folder):
            self._log("[ERROR] One or both folder paths are invalid.")
            return
        if os.path.abspath(mod_folder) == os.path.abspath(orig_folder):
            self._log("[ERROR] Modded and Original folders cannot be the same.")
            return

        if self._scan_thread and self._scan_thread.is_alive():
            self._log("[WARNING] Scan already in progress.")
            return

        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(mod_folder, orig_folder),
            daemon=True,
        )
        self._scan_thread.start()

    def _scan_worker(self, mod_folder, orig_folder):
        """Background worker for scan & compare."""
        self._clear_log()
        self._log("--- Starting Scan & Compare ---")

        # Step 1: convert .uasset to JSON
        self._log("[INFO] Converting .uasset files in modded folder...")
        converted = self._convert_uassets(mod_folder)
        self._log(f"[INFO] Converted {converted} .uasset file(s).")

        # Step 2: index original files
        self._log("[INFO] Scanning original folder...")
        orig_map = {}
        for root_dir, _, files in os.walk(orig_folder):
            for f in files:
                if f.lower().endswith(".json"):
                    full = os.path.join(root_dir, f)
                    rel = os.path.relpath(full, orig_folder).replace("/", "\\")
                    orig_map[f.lower()] = {"full": full, "rel": rel, "name": f}
        self._log(f"[INFO] Found {len(orig_map)} original .json file(s).")

        # Step 3: compare
        title = self._title_entry.get().strip() or "My Mod"
        author = self._author_entry.get().strip() or "Author"
        description = self._desc_entry.get().strip()
        change_note = self._note_entry.get().strip()
        include_comments = self._include_comments.get()

        files_to_save = {}
        matched = 0
        total_diffs = 0

        self._log("[INFO] Comparing modded files against originals...")

        for root_dir, _, files in os.walk(mod_folder):
            for mod_file in files:
                if not mod_file.lower().endswith(".json"):
                    continue
                orig_info = orig_map.get(mod_file.lower())
                if not orig_info:
                    continue

                matched += 1
                mod_path = os.path.join(root_dir, mod_file)

                try:
                    with open(orig_info["full"], "r", encoding="utf-8") as f:
                        orig_json = json.load(f)
                    with open(mod_path, "r", encoding="utf-8") as f:
                        mod_json = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    self._log(f"  [ERROR] {mod_file}: {e}")
                    continue

                orig_data = orig_json.get("Exports", [{}])[0].get("Table", {}).get("Data", [])
                mod_data = mod_json.get("Exports", [{}])[0].get("Table", {}).get("Data", [])

                if not orig_data or not mod_data:
                    continue

                differences = find_differences(orig_data, mod_data)
                if not differences:
                    self._log(f"  [MATCH] {mod_file} — no differences.")
                    continue

                self._log(f"  [DIFF] {mod_file} — {len(differences)} change(s).")
                total_diffs += len(differences)

                grouped = group_diffs_by_property(differences)
                json_base = mod_file[:-5]  # strip .json

                for prop_key, diff_group in grouped.items():
                    safe_key = "".join(c for c in prop_key if c.isalnum() or c in ("_", "-"))
                    def_name = f"{json_base}_{safe_key}"
                    mod_title = f"{title} - {json_base} ({prop_key})"

                    xml = generate_def_xml(
                        diff_group, orig_info["rel"],
                        mod_title, author, description,
                        change_note, include_comments,
                    )
                    files_to_save[f"{def_name}.def"] = xml

        self._log(f"\n[INFO] Matched {matched} file(s), found {total_diffs} total difference(s).")
        self._log(f"[INFO] Generated {len(files_to_save)} .def file(s).")

        # Update UI on main thread
        self.after(0, lambda: self._update_preview(files_to_save))

    def _update_preview(self, files_to_save):
        """Update the generated files and preview selector."""
        self._generated_files = files_to_save
        self._current_preview_file = None

        if files_to_save:
            sorted_names = sorted(files_to_save.keys())
            self._file_selector.configure(values=sorted_names)
            self._file_selector.set(sorted_names[0])
            self._file_count_label.configure(text=f"{len(sorted_names)} file(s)")
            self._on_file_selected(sorted_names[0])
            self._set_status(f"Generated {len(sorted_names)} .def file(s)")
        else:
            self._file_selector.configure(values=["(no files generated)"])
            self._file_selector.set("(no files generated)")
            self._file_count_label.configure(text="0 files")
            self._preview_box.delete("1.0", "end")
            self._set_status("No differences found")

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _on_file_selected(self, filename):
        """Show the selected file's content in the preview editor."""
        # Save edits to the previously viewed file
        if self._current_preview_file and self._current_preview_file in self._generated_files:
            self._generated_files[self._current_preview_file] = self._preview_box.get("1.0", "end-1c")

        self._current_preview_file = filename
        content = self._generated_files.get(filename, "")
        self._preview_box.delete("1.0", "end")
        self._preview_box.insert("1.0", content)

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_all_files(self):
        """Save all generated .def files to a user-selected folder."""
        # Save any pending edits
        if self._current_preview_file and self._current_preview_file in self._generated_files:
            self._generated_files[self._current_preview_file] = self._preview_box.get("1.0", "end-1c")

        if not self._generated_files:
            self._log("[WARNING] No .def files to save. Run Scan & Compare first.")
            return

        save_dir = ctk.filedialog.askdirectory(title="Select folder to save .def files")
        if not save_dir:
            return

        saved = 0
        for filename, content in self._generated_files.items():
            try:
                filepath = os.path.join(save_dir, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                saved += 1
            except OSError as e:
                self._log(f"[ERROR] Could not save {filename}: {e}")

        self._log(f"[INFO] Saved {saved} .def file(s) to {save_dir}")
        self._set_status(f"Saved {saved} .def files to {save_dir}")

        # Open the folder on Windows
        try:
            os.startfile(save_dir)
        except (AttributeError, OSError):
            pass
