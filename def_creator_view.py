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
import shutil
import subprocess
import tempfile
import threading
import re
from pathlib import Path

import customtkinter as ctk

from src.config import (
    get_utilities_dir, get_game_install_path, get_default_definitions_dir,
    get_prebuilt_modfiles_dir,
)
from src.constants import UE_VERSION, RETOC_UE_VERSION, UASSETGUI_EXE, RETOC_EXE
from src.ui.shared_utils import get_jsondata_dir, get_retoc_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pure diff logic (no UI dependency, testable)
# ---------------------------------------------------------------------------

def _extract_uasset_data(json_obj):
    """Smartly extracts Data from a UAssetAPI JSON object."""
    exports = json_obj.get("Exports", [])
    
    # 1. Standardní DataTable
    for exp in exports:
        if "Table" in exp and "Data" in exp["Table"]:
            return exp["Table"]["Data"]
            
    # 2. CurveTable Export
    for exp in exports:
        if exp.get("$type", "").startswith("CurveTableExport"):
            data = exp.get("Data")
            if isinstance(data, list):
                return data
            
    # 3. Samostatné assety (DataAsset, CurveFloat atd.)
    for exp in exports:
        if "Data" in exp and isinstance(exp["Data"], list):
            obj_name = exp.get("ObjectName", "DefaultAsset")
            if obj_name.startswith("Default__"):
                obj_name = obj_name.replace("Default__", "")
            return [{"Name": obj_name, "Value": exp["Data"]}]
            
    return None

def _format_value(val):
    """Format a property value for display in .def XML."""
    if isinstance(val, bool):
        return "True" if val else "False"
    
    str_val = str(val)
    if str_val.startswith('+'):
        try:
            num = float(str_val)
            if num.is_integer():
                return str(int(num))
            return str(num)
        except ValueError:
            pass

    if isinstance(val, float) and val.is_integer():
        return str(int(val))
    return str_val

def _extract_context(props_list, prop_name=""):
    """Try to find a meaningful context label (e.g. item name) near the property."""
    context_keys = (
        "Item", "Resource", "Material", "ItemTemplate", "ItemTag", 
        "Tag", "GameplayTag", "DropItem", "ResultItem", "Reward", "Loot"
    )
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

        # --- TADY ZAČÍNÁ TA ZMĚNĚNÁ ČÁST ---
        is_missing = (o is None)
        is_null = (isinstance(o, dict) and o.get("Value") is None)

        if is_missing or is_null:
            val = m.get("Value")
            str_val = _format_value(val) if not isinstance(val, (list, dict)) else ""
            
            # Všechno, co chybí nebo je null, přidáme rovnou jako <add_property> i s JSONem
            changes.append({
                "type": "add",
                "property": new_path,
                "value": str_val,
                "old_value": "New Property (was null)",
                "context": _extract_context(orig_props, prop_name),
                "json_data": json.dumps(m, indent=2),
            })
            continue
        # --- TADY ZMĚNĚNÁ ČÁST KONČÍ ---

        # (Zde u tebe v kódu normálně pokračují další věci jako elif "ArrayPropertyData" atd. - ty tam samozřejmě nech)

        if "GameplayTagContainerPropertyData" in type_str:
            container_prop = current_path.split(".")[-1] if current_path else prop_name
            m_tags = m.get("Value", [])
            o_tags = o.get("Value", [])
            if m_tags != o_tags:
                m_set = set(m_tags) if isinstance(m_tags, list) else set()
                o_set = set(o_tags) if isinstance(o_tags, list) else set()
                removed = o_set - m_set
                added = m_set - o_set
                for tag in sorted(removed):
                    changes.append({
                        "type": "delete",
                        "property": container_prop,
                        "value": tag,
                        "old_value": tag,
                        "context": _extract_context(orig_props, prop_name),
                    })
                for tag in sorted(added):
                    changes.append({
                        "type": "add_tag",
                        "property": container_prop,
                        "value": tag,
                        "old_value": "(new tag)",
                        "context": _extract_context(orig_props, prop_name),
                    })
        elif "ArrayPropertyData" in type_str or "SetPropertyData" in type_str:
            m_list = m.get("Value", []) or []
            o_list = o.get("Value", []) or []
            for i in range(max(len(m_list), len(o_list))):
                arr_path = f"{new_path}[{i}]"
                m_val = m_list[i] if i < len(m_list) else None
                o_val = o_list[i] if i < len(o_list) else None
                
                if m_val and not o_val:
                    if isinstance(m_val, dict):
                        added_context = _extract_context(m_val.get("Value", []))
                        changes.append({
                            "type": "add",
                            "property": new_path,
                            "value": "",
                            "old_value": "Added to Array",
                            "context": added_context,
                            "json_data": json.dumps(m_val, indent=2)
                        })
                elif not m_val and o_val:
                    if isinstance(o_val, dict):
                        o_name = o_val.get("Name", f"[{i}]")
                        o_display = o_val.get("Value", o_name)
                        removed_context = _extract_context(o_val.get("Value", []))
                        changes.append({
                            "type": "remove",
                            "property": arr_path,
                            "value": "(removed)",
                            "old_value": _format_value(o_display) if not isinstance(o_display, (list, dict)) else o_name,
                            "context": removed_context,
                        })
                elif m_val and o_val:
                    if isinstance(m_val, dict) and isinstance(o_val, dict):
                        changes.extend(_compare_properties(
                            m_val.get("Value", []), o_val.get("Value", []), arr_path
                        ))
        elif "StructPropertyData" in type_str:
            m_val = m.get("Value", []) or []
            o_val = o.get("Value", []) or []
            if isinstance(m_val, list) and isinstance(o_val, list):
                changes.extend(_compare_properties(m_val, o_val, new_path))
            elif isinstance(m_val, dict) and isinstance(o_val, dict):
                for k in set(m_val.keys()).union(o_val.keys()):
                    if k in ("$type", "Name"): continue
                    v_m = m_val.get(k)
                    v_o = o_val.get(k)
                    if v_m != v_o:
                        changes.append({
                            "type": "change",
                            "property": f"{new_path}.{k}",
                            "value": _format_value(v_m) if not isinstance(v_m, (list, dict)) else str(v_m)[:100],
                            "old_value": _format_value(v_o) if not isinstance(v_o, (list, dict)) else str(v_o)[:100],
                            "context": _extract_context(orig_props, prop_name),
                        })
        else:
            primitive_types = (
                "IntPropertyData", "BoolPropertyData", "FloatPropertyData",
                "EnumPropertyData", "NamePropertyData", "StrPropertyData",
                "BytePropertyData", "TextPropertyData",
                "ObjectPropertyData", "SoftObjectPropertyData",
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
            else:
                m_val = m.get("Value")
                o_val = o.get("Value")
                if m_val != o_val:
                    if isinstance(m_val, list) and isinstance(o_val, list):
                        for i in range(max(len(m_val), len(o_val))):
                            sub_m = m_val[i] if i < len(m_val) else None
                            sub_o = o_val[i] if i < len(o_val) else None
                            if isinstance(sub_m, dict) and isinstance(sub_o, dict):
                                if "Value" in sub_m and isinstance(sub_m["Value"], list):
                                    changes.extend(_compare_properties(
                                        sub_m.get("Value", []),
                                        sub_o.get("Value", []),
                                        f"{new_path}[{i}]",
                                    ))
                                else:
                                    for k in set(sub_m.keys()).union(sub_o.keys()):
                                        if k in ("$type", "Name"): continue
                                        v_m = sub_m.get(k)
                                        v_o = sub_o.get(k)
                                        if v_m != v_o:
                                            changes.append({
                                                "type": "change",
                                                "property": f"{new_path}[{i}].{k}",
                                                "value": _format_value(v_m) if not isinstance(v_m, (list, dict)) else str(v_m)[:100],
                                                "old_value": _format_value(v_o) if not isinstance(v_o, (list, dict)) else str(v_o)[:100],
                                                "context": _extract_context(orig_props, prop_name),
                                            })
                            elif sub_m != sub_o:
                                changes.append({
                                    "type": "change",
                                    "property": f"{new_path}[{i}]",
                                    "value": _format_value(sub_m) if sub_m is not None else "(removed)",
                                    "old_value": _format_value(sub_o) if sub_o is not None else "(new)",
                                    "context": _extract_context(orig_props, prop_name),
                                })
                    elif isinstance(m_val, dict) and isinstance(o_val, dict):
                        for k in set(m_val.keys()).union(o_val.keys()):
                            if k in ("$type", "Name"): continue
                            v_m = m_val.get(k)
                            v_o = o_val.get(k)
                            if v_m != v_o:
                                changes.append({
                                    "type": "change",
                                    "property": f"{new_path}.{k}",
                                    "value": _format_value(v_m) if not isinstance(v_m, (list, dict)) else str(v_m)[:100],
                                    "old_value": _format_value(v_o) if not isinstance(v_o, (list, dict)) else str(v_o)[:100],
                                    "context": _extract_context(orig_props, prop_name),
                                })
                    else:
                        changes.append({
                            "type": "change",
                            "property": new_path,
                            "value": _format_value(m_val) if not isinstance(m_val, (list, dict)) else str(m_val)[:100],
                            "old_value": _format_value(o_val) if not isinstance(o_val, (list, dict)) else str(o_val)[:100],
                            "context": _extract_context(orig_props, prop_name),
                        })
    return changes

def find_differences(orig_data, mod_data):
    differences = []
    orig_dict = {item.get("Name"): item for item in orig_data}
    mod_dict = {item.get("Name"): item for item in mod_data}

    for mod_item in mod_data:
        item_name = mod_item.get("Name")
        orig_item = orig_dict.get(item_name)
        orig_props = orig_item.get("Value", []) if orig_item else []

        diffs = _compare_properties(mod_item.get("Value", []), orig_props)
        for diff in diffs:
            diff["item"] = item_name
            
            differences.append(diff)

    for orig_item in orig_data:
        item_name = orig_item.get("Name")
        if item_name and item_name not in mod_dict:
            differences.append({
                "type": "remove",
                "item": item_name,
                "property": "(entire row)",
                "value": "(deleted)",
                "old_value": "Row existed in original",
                "context": None,
            })

    return differences

def group_diffs_by_property(differences):
    grouped = {}
    for diff in differences:
        prop_key = diff["property"].split(".")[-1].split("[")[0]
        grouped.setdefault(prop_key, []).append(diff)
    return grouped

def _get_existing_description(base_filename):
    """Najde description v existujícím .ini/.def (včetně podadresářů)."""
    import xml.etree.ElementTree as ET

    if not base_filename:
        return None

    def _read_ini_description(ini_file: Path):
        try:
            content = ini_file.read_text(encoding="utf-8")
            match = re.search(r"(?im)^\s*Description\s*=\s*(.+?)\s*$", content)
            if match:
                return match.group(1).strip()
        except OSError:
            return None
        return None

    def _read_def_description(def_file: Path):
        try:
            tree = ET.parse(def_file)
            desc_el = tree.getroot().find("description")
            if desc_el is not None and desc_el.text:
                return desc_el.text.strip()
        except (OSError, ET.ParseError):
            return None
        return None

    # 1) Preferujeme .def podle jména (typické pro per-file descriptions).
    defs_dir = get_default_definitions_dir()
    if defs_dir.exists():
        for def_file in defs_dir.rglob(f"{base_filename}.def"):
            desc = _read_def_description(def_file)
            if desc:
                return desc

    # 2) Fallback na .ini stejného jména (mod-level description).
    prebuilt_dir = get_prebuilt_modfiles_dir()
    for search_dir in (prebuilt_dir, defs_dir):
        if search_dir.exists():
            ini_file = search_dir / f"{base_filename}.ini"
            if ini_file.exists():
                desc = _read_ini_description(ini_file)
                if desc:
                    return desc
    return None

def generate_def_xml(diffs, mod_path, title, author, description,
                    change_note="", include_comments=False, base_filename=""):
    
    # Zkusíme najít starý popis, pokud nebyl zadán nový nebo pokud chceme prioritu
    existing_desc = _get_existing_description(base_filename) if base_filename else None
    final_description = existing_desc if existing_desc else description

    lines = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        "<definition>",
        f"  <title>{title}</title>",
        f"  <author>{author}</author>",
        f"  <description>{final_description}</description>", # Použijeme nalezený nebo původní
        f'  <mod file="{mod_path}">',
    ]
    
    for diff in diffs:
        diff_type = diff.get("type", "change")

        if include_comments:
            item_info = diff["item"]
            if diff.get("context"):
                item_info += f": {diff['context']}"
            if diff_type == "add":
                old_text = "Added"
            elif diff_type == "delete":
                old_text = f"Delete tag {diff['value']}"
            elif diff_type == "add_tag":
                old_text = f"Add tag {diff['value']}"
            elif diff_type == "remove":
                old_text = "Removed"
            else:
                old_text = f"was {diff['old_value']}"
            comment = f"{change_note} - {item_info}" if change_note else item_info
            lines.append(f"    <!--  {comment} ({old_text})  -->")

        if diff_type == "delete":
            lines.append(f'    <delete item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}" />')
        elif diff_type == "add_tag":
            lines.append(f'    <change item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}" />')
        elif diff_type == "add":
            lines.append(f'    <change item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}">')
            lines.append(f'      <add_property item="{diff["item"]}">'
                         f'<![CDATA[{diff.get("json_data", "")}]]>'
                         f'</add_property>')
            lines.append('    </change>')
        elif diff_type == "remove":
            lines.append(f'    <!-- ROW DELETED: {diff["item"]} '
                         f'property="{diff["property"]}" -->')
        else:
            lines.append(f'    <change item="{diff["item"]}" '
                         f'property="{diff["property"]}" '
                         f'value="{diff["value"]}" />')

    lines.append("  </mod>")
    lines.append("</definition>")
    return "\n".join(lines)

def _detect_category(mod_file_path: str) -> str:
    normalized = mod_file_path.replace("\\", "/")
    filename = normalized.rsplit("/", 1)[-1]
    basename = filename.rsplit(".", 1)[0]
    _CATEGORY_MAP = {
        "DT_Armor": "Items", "DT_Consumables": "Items", "DT_ConstructionRecipes": "Building",
        "DT_Constructions": "Building", "DT_ConstructionStabilities": "Building",
        "DT_Items": "Items", "DT_ItemRecipes": "Items", "DT_ItemTint": "Effects",
        "DT_Loot": "Loot", "DT_MonumentData": "Monuments", "DT_Moria_Flora": "Flora",
        "DT_Ores": "Items", "DT_RecipeBundles": "Trade", "DT_SettlementLevelData": "Settlement",
        "DT_Storage": "Storage", "DT_Tools": "Items", "DT_TradeGoods": "Trade",
        "DT_Weapons": "Items", "DT_WorldLevelData": "Settlement",
    }
    if basename in _CATEGORY_MAP: return _CATEGORY_MAP[basename]
    for prefix, category in _CATEGORY_MAP.items():
        if basename.startswith(prefix): return category
    if basename.startswith("GE_") or basename.startswith("Curve_"): return "Buffs"
    if basename.startswith("Properties_"): return "Ores"
    parts = [p for p in normalized.split("/") if p]
    if len(parts) >= 2: return parts[-2]
    return "Misc"

def generate_ini_content(title, author, description, category_files):
    lines = [
        "[ModInfo]", f"Title = {title}", f"Authors = {author}", 
        f"Description = {description}", "", "[Paths]",
    ]
    for category, filenames in sorted(category_files.items()):
        cat_lower = category.lower()
        for fname in sorted(filenames):
            lines.append(f"{cat_lower}|{fname.lower()} = true")
        lines.append(f"{cat_lower} = true")
    lines.append("")
    lines.append("[Settings]")
    lines.append("include_secrets = False")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# INI Editor Popup Window (with HTML Helpers & Split Fields)
# ---------------------------------------------------------------------------

class IniEditorWindow(ctk.CTkToplevel):
    """Popup window to edit the generated .ini file with split fields and HTML helpers."""
    def __init__(self, parent, ini_path: Path):
        super().__init__(parent)
        self.title(f"Edit Mod Configuration: {ini_path.name}")
        self.geometry("900x700")
        self.ini_path = ini_path
        self.rest_content = ""  # Sem si schováme [Paths] a [Settings]

        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        info_text = "Edit your mod's metadata. The technical paths are safely hidden and will be saved automatically."
        ctk.CTkLabel(self, text=info_text, font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, pady=(10, 5), padx=10, sticky="w"
        )

        # --- Mod Info Sekce (Title a Author) ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        ctk.CTkLabel(header_frame, text="Mod Name:", width=80, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.title_entry = ctk.CTkEntry(header_frame, width=300)
        self.title_entry.pack(side="left", padx=5)

        ctk.CTkLabel(header_frame, text="Author:", width=60, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(20, 0))
        self.author_entry = ctk.CTkEntry(header_frame, width=300)
        self.author_entry.pack(side="left", padx=5)

        # --- HTML Helper Toolbar (Lišta pro Description) ---
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.grid(row=2, column=0, sticky="ew", padx=10, pady=(15, 5))

        ctk.CTkLabel(toolbar, text="Description:", width=80, anchor="w", font=ctk.CTkFont(weight="bold")).pack(side="left")

        helpers = [
            ("Header 1", "<h1>", "</h1>"),
            ("Header 2", "<h2>", "</h2>"),
            ("Bold", "<b>", "</b>"),
            ("Italic", "<i>", "</i>"),
            ("Underline", "<u>", "</u>"),
            ("Paragraph", "<p>", "</p>"),
            ("Line Break", "<br>", ""),
        ]

        for text, open_tag, close_tag in helpers:
            ctk.CTkButton(
                toolbar, text=text, width=80, height=24,
                command=lambda o=open_tag, c=close_tag: self._wrap_text(o, c)
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            toolbar, text="Insert Table", width=100, height=24, fg_color="#1565C0",
            command=self._insert_table_template
        ).pack(side="left", padx=(15, 2))

        # --- Textový Editor pro Description ---
        self.desc_textbox = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=14))
        self.desc_textbox.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)

        # --- Spodní ovládací tlačítka ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=4, column=0, pady=10)

        ctk.CTkButton(
            btn_frame, text="Save & Close", fg_color="#2E7D32", hover_color="#1B5E20", 
            command=self._save_ini
        ).pack(side="left", padx=10)
        
        ctk.CTkButton(
            btn_frame, text="Cancel (Discard)", fg_color="#C62828", hover_color="#b71c1c", 
            command=self.destroy
        ).pack(side="left", padx=10)

        # --- Načtení dat ze souboru ---
        self._load_ini_data()


    def _load_ini_data(self):
        """Robustnější načítání, které zvládne text hned za rovnítkem i bez odsazení."""
        try:
            with open(self.ini_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            desc_lines = []
            rest_lines = []
            in_desc = False
            in_rest = False

            for line in lines:
                stripped = line.strip()

                # Detekce technických sekcí - vše odtud dolů schováme
                if stripped.startswith("[Paths]") or stripped.startswith("[Settings]"):
                    in_rest = True
                    in_desc = False

                if in_rest:
                    rest_lines.append(line)
                    continue

                # Čtení názvu a autora
                if stripped.startswith("Title") and "=" in stripped:
                    self.title_entry.insert(0, stripped.split("=", 1)[1].strip())
                    continue
                elif stripped.startswith("Authors") and "=" in stripped:
                    self.author_entry.insert(0, stripped.split("=", 1)[1].strip())
                    continue

                # Čtení Description
                if stripped.startswith("Description") and "=" in stripped:
                    in_desc = True
                    val = stripped.split("=", 1)[1].strip()
                    if val:
                        desc_lines.append(val)
                    continue
                
                # Pokud jsme v sekci popisu a řádek nezačíná novou sekcí []
                # přidáme ho do popisu (i když není odsazený mezerami)
                if in_desc and not stripped.startswith("["):
                    # Pokud narazíme na prázdný řádek, přidáme ho taky
                    desc_lines.append(stripped)

            # Vložení popisu do textboxu (spojíme řádky)
            self.desc_textbox.insert("1.0", "\n".join(desc_lines))
            # Uložení zbytku souboru
            self.rest_content = "".join(rest_lines)

        except Exception as e:
            self.desc_textbox.insert("1.0", f"Chyba při načítání souboru:\n{e}")

    # --- Pomocné funkce pro HTML ---
    
    def _wrap_text(self, open_tag, close_tag):
        """Obalí výběr nebo funguje jako tupý vkladač začátku/konce."""
        # Získáme přístup k textovému poli
        txt = self.desc_textbox._textbox
        
        # 1. Pokusíme se o obalení vybraného textu
        try:
            start = txt.index("sel.first")
            end = txt.index("sel.last")
            sel_text = txt.get(start, end)
            
            txt.delete(start, end)
            txt.insert(start, f"{open_tag}{sel_text}{close_tag}")
            
            # Vrátíme označení na text uvnitř tagů
            new_start = txt.index(f"{start} + {len(open_tag)}c")
            new_end = txt.index(f"{new_start} + {len(sel_text)}c")
            txt.tag_add("sel", new_start, new_end)
            self.desc_textbox.focus_set()
            return # Hotovo, končíme
        except:
            # Pokud není výběr, pokračujeme k vkládání tagů
            pass

        # 2. Scénář bez výběru (Přepínač/Vkladač)
        cursor = txt.index("insert")
        
        # Pokud tag nemá konec (Line Break), prostě ho vložíme
        if not close_tag:
            txt.insert(cursor, open_tag)
        else:
            # Zjistíme, co je před kurzorem (posledních 100 znaků na řádku)
            line_content = txt.get("insert linestart", "insert")
            
            # Pokud už tam otevírací tag je a není tam uzavírací, dáme uzavírací
            if open_tag in line_content and close_tag not in line_content.split(open_tag)[-1]:
                txt.insert(cursor, close_tag)
            else:
                # Jinak vložíme otevírací
                txt.insert(cursor, open_tag)
        
        self.desc_textbox.focus_set()
    def _insert_table_template(self):
        table_html = (
            '\n<table cellpadding="6" cellspacing="0" border="0">\n'
            '<tr>\n'
            '<td><b>Category</b></td>\n'
            '<td><b>Value</b></td>\n'
            '</tr>\n'
            '<tr>\n'
            '<td>Item 1</td>\n'
            '<td>999</td>\n'
            '</tr>\n'
            '</table>\n'
        )
        cursor = self.desc_textbox.index("insert")
        self.desc_textbox.insert(cursor, table_html)

    # --- Ukládání ---

    def _save_ini(self):
        """Sestaví INI zpátky dohromady, naformátuje popis a uloží ho."""
        title = self.title_entry.get().strip()
        author = self.author_entry.get().strip()
        raw_desc = self.desc_textbox.get("1.0", "end-1c")

        # Automatické formátování popisu (odsazení o 4 mezery)
        formatted_desc_lines = []
        for line in raw_desc.splitlines():
            stripped = line.strip()
            if stripped == "":
                formatted_desc_lines.append("")
            else:
                formatted_desc_lines.append("    " + stripped)
        
        desc_final = "\n".join(formatted_desc_lines)

        # Poskládání finálního souboru
        final_content = (
            f"[ModInfo]\n"
            f"Title = {title}\n"
            f"Authors = {author}\n"
            f"Description =\n{desc_final}\n\n"
            f"{self.rest_content}"
        )

        try:
            with open(self.ini_path, "w", encoding="utf-8") as f:
                f.write(final_content)
            self.destroy()
        except Exception as e:
            self.desc_textbox.insert("end", f"\n\n[ERROR SAVING]: {e}")


class DefCreatorView(ctk.CTkFrame):
    """Advanced-mode view for generating .def files from modded vs original game files."""

    def __init__(self, parent, on_status_message=None, on_back=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_status = on_status_message
        self._on_back = on_back

        self._mod_folder = ""
        self._orig_folder = ""
        self._generated_files: dict[str, str] = {}
        self._generated_categories: dict[str, str] = {}
        self._include_comments = ctk.BooleanVar(value=False)
        self._scan_thread = None
        self._current_preview_file = None

        self._mod_entry = None
        self._orig_entry = None
        self._title_entry = None
        self._author_entry = None
        self._desc_entry = None
        self._note_entry = None
        
        self._found_properties = []
        self._create_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _create_ui(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll.grid_columnconfigure(1, weight=1)

        row = 0

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

        row = self._create_section_header(scroll, "Folder Selection", ("#E65100", "#FF9800"), row)

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
        default_orig = get_jsondata_dir()
        if default_orig.exists():
            self._orig_entry.insert(0, str(default_orig))
            self._orig_folder = str(default_orig)
        self._orig_entry.grid(row=row, column=1, sticky="ew", padx=5, pady=3)
        ctk.CTkButton(scroll, text="Browse...", width=90, command=self._browse_orig_folder).grid(
            row=row, column=2, pady=3
        )
        row += 1

        row = self._create_section_header(scroll, "DEF File Metadata", "#4CAF50", row)

        for label_text, attr_name, default, placeholder in [
            ("Title:", "_title_entry", "My Mod", "Enter mod title..."),
            ("Author:", "_author_entry", "", "Enter author name..."),
            ("Description:", "_desc_entry", "", "Enter mod description..."),
        ]:
            ctk.CTkLabel(scroll, text=label_text, anchor="w", width=160).grid(
                row=row, column=0, sticky="w", pady=3
            )
            entry = ctk.CTkEntry(scroll, placeholder_text=placeholder)
            if default:
                entry.insert(0, default)
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
            
            if attr_name == "_title_entry": self._title_entry = entry
            elif attr_name == "_author_entry": self._author_entry = entry
            elif attr_name == "_desc_entry": self._desc_entry = entry
            row += 1

        cb = ctk.CTkCheckBox(
            scroll,
            text="Include comments in generated .def files",
            variable=self._include_comments,
        )
        cb.grid(row=row, column=0, columnspan=3, sticky="w", pady=(5, 10))
        row += 1

        btn_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(5, 10))
        row += 1

        ctk.CTkButton(
            btn_frame, text="Scan & Compare",
            width=140, height=36,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._scan_and_compare,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Save All .def Files",
            width=140, height=36,
            fg_color=("#1565C0", "#0D47A1"),
            hover_color=("#0D47A1", "#082D69"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save_all_files,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Edit Existing .ini",
            width=140, height=36,
            fg_color=("#F57C00", "#E65100"),  # Oranžová barva pro odlišení
            hover_color=("#E65100", "#BF360C"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._edit_existing_ini,
        ).pack(side="left", padx=(0, 10))

        # Uložíme si tlačítko do self.edit_def_btn, abychom ho mohli měnit
        self.edit_def_btn = ctk.CTkButton(
            btn_frame, text="Edit Existing .def",
            width=140, height=36,
            fg_color=("#8E24AA", "#6A1B9A"),  # Původní fialová
            hover_color=("#6A1B9A", "#4A148C"),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._handle_edit_def_click, # Změníme na obslužnou funkci
        )
        self.edit_def_btn.pack(side="left", padx=(0, 10))

        # Pomocná proměnná pro sledování cesty k externímu souboru
        self._current_external_def_path = None

        row = self._create_section_header(scroll, "Log", "#2196F3", row)

        self._log_box = ctk.CTkTextbox(scroll, height=160, font=ctk.CTkFont(family="Consolas", size=14))
        self._log_box.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self._log_box.configure(state="disabled")
        row += 1

        # --- SEKCE PRO DESCRIPTION EDITOR ---
        row = self._create_section_header(scroll, "Step 2: Assign Descriptions", "#E91E63", row)
        
        self._desc_editor_frame = ctk.CTkFrame(scroll, fg_color=("#dbdbdb", "#2b2b2b"))
        self._desc_editor_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=10, padx=5)
        row += 1
        
        edit_row = ctk.CTkFrame(self._desc_editor_frame, fg_color="transparent")
        edit_row.pack(fill="x", padx=10, pady=10)
        
        # Přidej parametr 'command', který zavolá naši novou funkci
        self._prop_selector = ctk.CTkComboBox(
            edit_row, 
            values=["(Scan first...)"], 
            width=200,
            command=self._on_property_selected  # <--- Tohle je klíčové
        )
        self._prop_selector.pack(side="left", padx=5)
        
        self._desc_entry_field = ctk.CTkEntry(edit_row, placeholder_text="Type description here...", width=400)
        self._desc_entry_field.pack(side="left", fill="x", expand=True, padx=5)
        
        self._apply_btn = ctk.CTkButton(edit_row, text="Apply to All", width=100, fg_color="#1565C0", command=self._apply_description)
        self._apply_btn.pack(side="left", padx=5)

        # --- Section: Preview / Edit ---
        row = self._create_section_header(scroll, "Preview / Edit", "#9C27B0", row)

        preview_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        preview_frame.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        preview_frame.grid_columnconfigure(0, weight=1)
        row += 1

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
            font=ctk.CTkFont(family="Consolas", size=14),
        )
        self._preview_box.pack(fill="both", expand=True)
        self._current_preview_file = None

    def _create_section_header(self, parent, text, color, row):
        header = ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        )
        header.grid(row=row, column=0, columnspan=3, sticky="w", pady=(15, 2))
        row += 1
        sep = ctk.CTkFrame(parent, height=2, fg_color=color)
        sep.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        return row + 1

    def _browse_mod_folder(self):
        folder = ctk.filedialog.askdirectory(title="Select Modded Files Folder")
        if folder:
            folder = os.path.normpath(folder)
            self._mod_folder = folder
            self._mod_entry.delete(0, "end")
            self._mod_entry.insert(0, folder)

    def _browse_orig_folder(self):
        folder = ctk.filedialog.askdirectory(title="Select Original Game Files Folder")
        if folder:
            folder = os.path.normpath(folder)
            self._orig_folder = folder
            self._orig_entry.delete(0, "end")
            self._orig_entry.insert(0, folder)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, msg):
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
        utils_dir = get_utilities_dir()
        path = utils_dir / UASSETGUI_EXE
        if path.exists():
            return path
        return None

    def _convert_uassets(self, folder: str) -> int:
        gui_path = self._get_uassetgui_path()
        if not gui_path:
            self._log(f"[WARNING] {UASSETGUI_EXE} not found — skipping .uasset conversion.")
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

    def _import_single_file(self, json_filename: str) -> Path | None:
        game_install = get_game_install_path()
        if not game_install:
            self._log(f"  [ERROR] Game install path not configured — cannot import {json_filename}")
            return None

        utils_dir = get_utilities_dir()
        retoc_exe = utils_dir / RETOC_EXE
        uassetgui_exe = utils_dir / UASSETGUI_EXE

        if not retoc_exe.exists():
            self._log(f"  [ERROR] {RETOC_EXE} not found — cannot import {json_filename}")
            return None
        if not uassetgui_exe.exists():
            self._log(f"  [ERROR] {UASSETGUI_EXE} not found — cannot import {json_filename}")
            return None

        paks_path = Path(game_install) / "Moria" / "Content" / "Paks"
        if not paks_path.exists():
            self._log(f"  [ERROR] Game Paks folder not found at {paks_path}")
            return None

        retoc_dir = get_retoc_dir()
        jsondata_dir = get_jsondata_dir()
        retoc_dir.mkdir(parents=True, exist_ok=True)
        jsondata_dir.mkdir(parents=True, exist_ok=True)

        file_stem = Path(json_filename).stem
        self._log(f"  [IMPORT] Extracting {file_stem} from game files...")

        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

        game_paks_temp = tempfile.mkdtemp(prefix="game_paks_")
        try:
            for ext in (".pak", ".ucas", ".utoc"):
                src = paks_path / f"Moria-WindowsNoEditor{ext}"
                if src.exists():
                    shutil.copy2(str(src), game_paks_temp)
            for gname in ("global.ucas", "global.utoc"):
                src = paks_path / gname
                if src.exists():
                    shutil.copy2(str(src), game_paks_temp)
        except OSError as e:
            self._log(f"  [ERROR] Failed to prepare temp paks dir: {e}")
            shutil.rmtree(game_paks_temp, ignore_errors=True)
            return None

        cmd = f'"{retoc_exe}" to-legacy --version {RETOC_UE_VERSION} --filter "{file_stem}" "{game_paks_temp}" "{retoc_dir}"'
        try:
            subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", 
                errors="replace", timeout=120, shell=True, check=False, **kwargs,
            )
        except subprocess.TimeoutExpired:
            self._log(f"  [ERROR] retoc timed out for {file_stem}")
            return None
        finally:
            shutil.rmtree(game_paks_temp, ignore_errors=True)

        extracted = list(retoc_dir.rglob(f"{file_stem}.uasset"))
        if not extracted:
            self._log(f"  [ERROR] No .uasset found after retoc extraction for {file_stem}")
            return None

        source_file = extracted[0]
        self._log(f"  [IMPORT] Converting {file_stem}.uasset to JSON...")

        rel_path = source_file.relative_to(retoc_dir)
        dest_file = jsondata_dir / rel_path.with_suffix(".json")
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                [str(uassetgui_exe), "tojson", str(source_file), str(dest_file), UE_VERSION],
                capture_output=True, text=True, encoding="utf-8", errors="replace", 
                timeout=60, check=True, **kwargs,
            )
        except subprocess.TimeoutExpired:
            self._log(f"  [ERROR] UAssetGUI timed out for {file_stem}")
            return None
        except subprocess.CalledProcessError as e:
            self._log(f"  [ERROR] UAssetGUI failed for {file_stem}: {e}")
            return None

        if dest_file.exists():
            self._log(f"  [IMPORT] Successfully imported {dest_file.name}")
            return dest_file

        self._log(f"  [ERROR] JSON file not created for {file_stem}")
        return None

    def _extract_iostore_mod(self, mod_folder: str) -> str | None:
        mod_path = Path(mod_folder)
        utoc_files = list(mod_path.glob("*.utoc"))
        if not utoc_files:
            return None

        self._log("[INFO] Detected IoStore mod pak (.ucas/.utoc) — extracting...")

        game_install = get_game_install_path()
        if not game_install:
            self._log("[ERROR] Game install path not configured — cannot extract IoStore mod.")
            return None

        paks_path = Path(game_install) / "Moria" / "Content" / "Paks"
        global_ucas = paks_path / "global.ucas"
        global_utoc = paks_path / "global.utoc"

        if not global_ucas.exists() or not global_utoc.exists():
            self._log("[ERROR] global.ucas/global.utoc not found in game Paks dir — extraction will fail.")
            return None

        utils_dir = get_utilities_dir()
        retoc_exe = utils_dir / RETOC_EXE
        uassetgui_exe = utils_dir / UASSETGUI_EXE

        if not retoc_exe.exists() or not uassetgui_exe.exists():
            self._log(f"[ERROR] Missing tools ({RETOC_EXE} or {UASSETGUI_EXE}) — cannot extract.")
            return None

        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0x08000000

        retoc_dir = mod_path / "retoc"
        jsondata_dir = mod_path / "jsondata"

        for out_dir in (retoc_dir, jsondata_dir):
            if out_dir.exists():
                self._log(f"  Deleting existing {out_dir.name}/ directory...")
                shutil.rmtree(out_dir)

        retoc_dir.mkdir()
        jsondata_dir.mkdir()

        temp_paks = tempfile.mkdtemp(prefix="defcreator_paks_")
        try:
            for ext in ("*.pak", "*.ucas", "*.utoc"):
                for f in mod_path.glob(ext):
                    shutil.copy2(str(f), temp_paks)
            shutil.copy2(str(global_ucas), temp_paks)
            shutil.copy2(str(global_utoc), temp_paks)

            self._log("[INFO] Running retoc to-legacy...")
            cmd = f'"{retoc_exe}" to-legacy --version {RETOC_UE_VERSION} "{temp_paks}" "{retoc_dir}"'
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", 
                errors="replace", timeout=300, shell=True, check=False, **kwargs,
            )

            if result.returncode != 0:
                self._log(f"  [ERROR] retoc failed: {result.stderr.strip()}")
                return None

            uasset_files = list(retoc_dir.rglob("*.uasset"))
            if not uasset_files:
                self._log("  [ERROR] No .uasset files produced by retoc.")
                return None

            self._log(f"[INFO] Found {len(uasset_files)} .uasset files. Converting to JSON...")
            converted = 0
            for uasset in uasset_files:
                rel = uasset.relative_to(retoc_dir)
                json_dest = jsondata_dir / rel.with_suffix(".json")
                json_dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(
                        [str(uassetgui_exe), "tojson", str(uasset), str(json_dest), UE_VERSION],
                        capture_output=True, text=True, encoding="utf-8", errors="replace", 
                        timeout=60, check=True, **kwargs,
                    )
                    if json_dest.exists():
                        converted += 1
                except subprocess.TimeoutExpired:
                    self._log(f"  [WARNING] Timeout converting {uasset.name}")
                except Exception as e:
                    self._log(f"  [WARNING] Failed converting {uasset.name}: {e}")

            if converted == 0:
                self._log("  [ERROR] No files were successfully converted to JSON.")
                return None

            self._log(f"[INFO] Successfully prepared {converted} JSON files from IoStore mod.")
            return str(jsondata_dir)

        except Exception as e:
            self._log(f"  [ERROR] Unexpected error during extraction: {e}")
            return None
        finally:
            shutil.rmtree(temp_paks, ignore_errors=True)

    # ------------------------------------------------------------------
    # Scan & Compare
    # ------------------------------------------------------------------

    def _scan_and_compare(self):
        mod_folder = self._mod_entry.get().strip()
        orig_folder = self._orig_entry.get().strip()

        if not mod_folder or not orig_folder:
            self._log("[ERROR] Please select both Modded and Original folders.")
            return
        if os.path.abspath(mod_folder) == os.path.abspath(orig_folder):
            self._log("[ERROR] Modded and Original folders cannot be the same.")
            return
        if self._scan_thread and self._scan_thread.is_alive():
            self._log("[WARNING] Scan already in progress.")
            return

        comments_enabled = bool(self._include_comments.get())
        title_val = self._title_entry.get().strip() or "My Mod"
        author_val = self._author_entry.get().strip() or "Author"
        desc_val = self._desc_entry.get().strip()
        note_val = ""

        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(mod_folder, orig_folder, comments_enabled, title_val, author_val, desc_val, note_val),
            daemon=True,
        )
        self._scan_thread.start()

    def _scan_worker(self, mod_folder, orig_folder, include_comments, title, author, description, change_note):
        self._clear_log()
        self._log("--- Starting Scan & Compare ---")
        ini_desc = _get_existing_description(title)
        if ini_desc:
            description = ini_desc
            self._log(f"[INFO] Loaded existing .ini description for mod '{title}'.")

        iostore_json_dir = self._extract_iostore_mod(mod_folder)
        if iostore_json_dir:
            mod_folder = iostore_json_dir
            self._log(f"[INFO] Using extracted mod JSON files from: {mod_folder}")

        self._log("[INFO] Converting .uasset files in modded folder...")
        converted = self._convert_uassets(mod_folder)
        self._log(f"[INFO] Converted {converted} .uasset file(s).")

        self._log("[INFO] Scanning original folder...")
        orig_map = {}
        for root_dir, _, files in os.walk(orig_folder):
            for f in files:
                if f.lower().endswith(".json"):
                    full = os.path.join(root_dir, f)
                    rel = os.path.relpath(full, orig_folder).replace("/", "\\")
                    orig_map[f.lower()] = {"full": full, "rel": rel, "name": f}

        files_to_save = {}
        categories = {}
        matched = 0
        total_diffs = 0

        self._log("[INFO] Comparing modded files against originals...")

        for root_dir, _, files in os.walk(mod_folder):
            for mod_file in files:
                if not mod_file.lower().endswith(".json"):
                    continue

                orig_info = orig_map.get(mod_file.lower())

                if not orig_info:
                    self._log(f"  [WARNING] No original found for {mod_file} — attempting auto-import...")
                    imported_path = self._import_single_file(mod_file)
                    if imported_path and imported_path.exists():
                        rel = os.path.relpath(str(imported_path), orig_folder).replace("/", "\\")
                        orig_info = {"full": str(imported_path), "rel": rel, "name": imported_path.name}
                        orig_map[mod_file.lower()] = orig_info
                    else:
                        self._log(f"  [ERROR] Could not import original for {mod_file} — skipping.")
                        continue

                matched += 1
                mod_path = os.path.join(root_dir, mod_file)

                try:
                    with open(orig_info["full"], "r", encoding="utf-8") as f:
                        orig_json = json.load(f)
                    with open(mod_path, "r", encoding="utf-8") as f:
                        mod_json = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    self._log(f"  [ERROR] Failed to load JSON for {mod_file}: {e}")
                    continue

                orig_data = _extract_uasset_data(orig_json)
                mod_data = _extract_uasset_data(mod_json)

                if orig_data is None or mod_data is None:
                    self._log(f"  [WARNING] Could not parse UAssetAPI format in {mod_file}")
                    continue

                differences = find_differences(orig_data, mod_data)

                if not differences:
                    continue

                self._log(f"  [DIFF] {mod_file} — {len(differences)} change(s).")
                total_diffs += len(differences)

                grouped = group_diffs_by_property(differences)
                json_base = mod_file[:-5]
                category = _detect_category(orig_info["rel"])

                for prop_key, diff_group in grouped.items():
                    safe_key = "".join(c for c in prop_key if c.isalnum() or c in ("_", "-"))
                    def_name = f"{json_base}_{safe_key}"
                    mod_title = f"{title} - {json_base} ({prop_key})"

                    # --- NOVÁ ČÁST: Získání existujícího popisu ---
                    # def_name je jméno souboru bez přípony .def
                    found_desc = _get_existing_description(def_name)
                    
                    # Pokud jsme popis našli, použijeme ho, jinak necháme ten z UI
                    current_desc = found_desc if found_desc else description
                    # ----------------------------------------------

                    xml = generate_def_xml(
                        diff_group, orig_info["rel"],
                        mod_title, author, current_desc,
                        change_note, include_comments,
                        base_filename=def_name # <-- TOHLE JE DŮLEŽITÉ
                    )
                    files_to_save[f"{def_name}.def"] = xml
                    categories[f"{def_name}.def"] = category

        self._log(f"\n[INFO] Matched {matched} file(s), found {total_diffs} total difference(s).")
        self._log(f"[INFO] Generated {len(files_to_save)} .def file(s).")

        # AKTUALIZACE SEZNAMU VLASTNOSTÍ PRO COMBOBOX
        all_props_found = set()
        for fname in files_to_save.keys():
            # Získáme název vlastnosti z konce (např. DT_Items_MaxStackSize.def -> MaxStackSize)
            p_name = fname.split('_')[-1].replace('.def', '')
            all_props_found.add(p_name)
            
        sorted_list = sorted(list(all_props_found))
        
        # Aktualizace přes GUI vlákno
        self.after(0, lambda: self._prop_selector.configure(values=sorted_list))
        if sorted_list:
            self.after(0, lambda: self._prop_selector.set(sorted_list[0]))

        # Aktualizace Preview
        self.after(0, lambda: self._update_preview(files_to_save, categories))


    def _update_preview(self, files_to_save, categories=None):
        """Update the file selector and preview box on the main thread."""
        self._generated_files = files_to_save
        self._generated_categories = categories or {}
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
            self._desc_entry_field.delete(0, "end")
            self._set_status("No differences found")

    def _extract_description_from_xml(self, xml_text):
        """Extract <description> text from DEF XML preview content."""
        if not xml_text:
            return ""
        match = re.search(r"<description>(.*?)</description>", xml_text, flags=re.DOTALL | re.IGNORECASE)
        if not match:
            return ""
        return match.group(1).strip()

    def _on_file_selected(self, filename):
        if self._current_preview_file and self._current_preview_file in self._generated_files:
            self._generated_files[self._current_preview_file] = self._preview_box.get("1.0", "end-1c")
        
        self._current_preview_file = filename
        content = self._generated_files.get(filename, "")
        
        self._preview_box.delete("1.0", "end")
        self._preview_box.insert("1.0", content)
        self._desc_entry_field.delete(0, "end")
        self._desc_entry_field.insert(0, self._extract_description_from_xml(content))

    def _save_all_files(self):
        """Save generated definitions and generate a .ini for the mod."""
        if self._current_preview_file and self._current_preview_file in self._generated_files:
            self._generated_files[self._current_preview_file] = self._preview_box.get("1.0", "end-1c")

        if not self._generated_files:
            self._log("[WARNING] No .def files to save. Run Scan & Compare first.")
            return

        self._log("\n--- Saving .def Files ---")
        defs_dir = get_default_definitions_dir()
        defs_dir.mkdir(parents=True, exist_ok=True)
        self._log(f"[INFO] Definitions directory: {defs_dir}")

        title = self._title_entry.get().strip() or "My Mod"
        author = self._author_entry.get().strip() or "Author"
        description = self._desc_entry.get().strip()

        saved = 0
        category_files = {}

        for filename, content in self._generated_files.items():
            category = self._generated_categories.get(filename, "Misc")
            cat_dir = defs_dir / category
            cat_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = cat_dir / filename
            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                saved += 1
                self._log(f"  [SAVE] {filepath.relative_to(defs_dir.parent)}")
                category_files.setdefault(category, []).append(filename)
            except OSError as e:
                self._log(f"  [ERROR] Could not save {filename}: {e}")

        prebuilt_dir = get_prebuilt_modfiles_dir()
        prebuilt_dir.mkdir(parents=True, exist_ok=True)
        
        ini_content = generate_ini_content(title, author, description, category_files)
        ini_path = prebuilt_dir / f"{title}.ini"
        try:
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(ini_content)
            self._log(f"  [SAVE] {ini_path}")
        except OSError as e:
            self._log(f"  [ERROR] Could not save .ini file: {e}")

        self._log(f"\n[INFO] Done! {saved} .def file(s) + 1 .ini saved.")
        self._set_status(f"Saved {saved} .def files + .ini")

        # ---> TOTO JE NOVÁ ČÁST: Otevření editoru <---
        if ini_path.exists():
            IniEditorWindow(self, ini_path)

    def _apply_description(self):
        """Vezme text z políčka a přepíše jím <description> v XML (100% přesná shoda vlastnosti)."""
        import re
        sel = self._prop_selector.get()
        txt = self._desc_entry_field.get().strip()
        
        if sel in ["(Scan first...)", ""] or not txt:
            self._log("[WARNING] Please select a property and enter a description.")
            return

        # 1. Uložíme aktuální náhled, ať nepřijdeme o ruční úpravy
        current_file = self._file_selector.get()
        if self._current_preview_file and self._current_preview_file in self._generated_files:
            self._generated_files[self._current_preview_file] = self._preview_box.get("1.0", "end-1c")

        count = 0
        
        # 2. Projdeme všechny soubory a zkontrolujeme přesně jejich vlastnost
        for filename, xml in self._generated_files.items():
            # Vezmeme název souboru (např. DT_Items_Value.def)
            # Rozdělíme ho podle '_' a vezmeme úplně poslední část ('Value.def')
            # Odstraníme '.def', takže nám zbyde čistě jen 'Value'
            file_prop = filename.split('_')[-1].replace('.def', '')
            
            # Pokud se tato vlastnost PŘESNĚ shoduje s tvým výběrem:
            if file_prop.lower() == sel.lower():
                # Nahrazení tagu description
                new_xml = re.sub(r'<description>.*?</description>', f'<description>{txt}</description>', xml, flags=re.DOTALL)
                self._generated_files[filename] = new_xml
                count += 1
        
        # 3. Zpětné propsání do editoru
        if count > 0:
            self._log(f"[OK] Applied description to {count} files matching exactly '{sel}'.")
            
            if current_file in self._generated_files:
                self._preview_box.delete("1.0", "end")
                self._preview_box.insert("1.0", self._generated_files[current_file])
        else:
            self._log(f"[WARNING] No files found matching exactly '{sel}'.")

    def _on_property_selected(self, selected_prop):
        """Když se nahoře vybere vlastnost, najde PRVNÍ PŘESNĚ odpovídající soubor a zobrazí ho."""
        if selected_prop in ["(Scan first...)", ""] or not self._generated_files:
            return

        # Seřadíme názvy souborů, aby byl výběr vždy stejný
        for filename in sorted(self._generated_files.keys()):
            # PŘESNÁ LOGIKA: 
            # 1. Rozdělíme název podle podtržítek (split)
            # 2. Vezmeme poslední část ([-1]) -> např. 'Value.def'
            # 3. Odstraníme koncovku '.def'
            file_prop = filename.split('_')[-1].replace('.def', '')
            
            # Teď porovnáme, jestli se to PŘESNĚ shoduje s tím, co jsi vybral v menu
            if file_prop.lower() == selected_prop.lower():
                # 1. Nastavíme spodní selector na tento soubor
                self._file_selector.set(filename)
                # 2. Zavoláme načtení obsahu do editoru
                self._on_file_selected(filename)
                
                # Našli jsme ten pravý, můžeme skončit
                break

    def _edit_existing_ini(self):
        """Otevře dialog pro výběr existujícího INI souboru a načte ho do editoru."""
        from src.config import get_prebuilt_modfiles_dir
        
        prebuilt_dir = get_prebuilt_modfiles_dir()
        
        # Ujistíme se, že složka existuje, jinak ji vytvoříme (aby dialog nespadl)
        prebuilt_dir.mkdir(parents=True, exist_ok=True)
        
        # Otevřeme okno pro výběr souboru
        file_path = ctk.filedialog.askopenfilename(
            title="Select .ini file to edit",
            initialdir=str(prebuilt_dir),
            filetypes=[("INI Files", "*.ini"), ("All Files", "*.*")]
        )
        
        if file_path:
            # Pokud uživatel vybral soubor, otevřeme tvůj existující editor s HTML prvky
            from pathlib import Path
            IniEditorWindow(self, Path(file_path))

    def _edit_existing_def(self):
        """Otevře dialog pro výběr existujícího .def souboru, vymaže aktuální práci a načte ho."""
        from src.config import get_default_definitions_dir
        import os
        
        defs_dir = get_default_definitions_dir()
        defs_dir.mkdir(parents=True, exist_ok=True)
        
        # Otevřeme okno pro výběr souboru
        file_path = ctk.filedialog.askopenfilename(
            title="Select .def file to edit",
            initialdir=str(defs_dir),
            filetypes=[("DEF Files", "*.def"), ("All Files", "*.*")]
        )
        
        if file_path:
            try:
                # Přečteme obsah souboru
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                filename = os.path.basename(file_path)
                
                # ---> NOVÉ: VYMAZÁNÍ PŘEDCHOZÍ PRÁCE <---
                self._generated_files.clear()
                self._generated_categories.clear()
                self._current_preview_file = None
                
                # Vyčistíme i ten růžový vybírací seznam vlastností, protože starý sken už neplatí
                self._prop_selector.configure(values=["(Scan first...)"])
                self._prop_selector.set("(Scan first...)")
                # ----------------------------------------

                # Přidáme načtený soubor do čisté paměti aplikace
                self._generated_files[filename] = content
                self._generated_categories[filename] = "Misc"

                # Aktualizujeme rozevírací seznam souborů nad editorem
                self._file_selector.configure(values=[filename])
                
                # Vybereme ho a zobrazíme rovnou v editoru
                self._file_selector.set(filename)
                self._on_file_selected(filename)
                
                # --- NOVÁ LOGIKA PŘEPNUTÍ ---
                self._current_external_def_path = file_path # Uložíme si cestu pro uložení
                self.edit_def_btn.configure(
                    text="Save .def",
                    fg_color=("#4A148C", "#310D5E"), # Tmavší fialová pro "Save" režim
                    hover_color=("#310D5E", "#1A0633")
                )
                
                self._file_count_label.configure(text="Editing external file")
                self._log(f"\n[INFO] Loaded for editing: {filename}")
                
            except Exception as e:
                self._log(f"[ERROR] Could not load .def file: {e}")

    def _handle_edit_def_click(self):
        """Rozhodne, zda soubor otevřít nebo uložit na základě stavu tlačítka."""
        if self._current_external_def_path is None:
            self._edit_existing_def()
        else:
            self._save_external_def()

    def _save_external_def(self):
        """Uloží změny zpět do původního souboru a vrátí tlačítko do původního stavu."""
        if not self._current_external_def_path:
            return

        try:
            # Získáme aktuální text z editoru
            content = self._preview_box.get("1.0", "end-1c")
            
            with open(self._current_external_def_path, "w", encoding="utf-8") as f:
                f.write(content)
            
            self._log(f"[OK] Changes saved back to: {os.path.basename(self._current_external_def_path)}")

            # --- RESET TLAČÍTKA ---
            self._current_external_def_path = None
            self.edit_def_btn.configure(
                text="Edit Existing .def",
                fg_color=("#8E24AA", "#6A1B9A"),
                hover_color=("#6A1B9A", "#4A148C")
            )
        except Exception as e:
            self._log(f"[ERROR] Failed to save external def: {e}")

