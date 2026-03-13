"""Unit tests for main_window module — non-GUI helper methods.

Tests cover:
- Definition XML parsing (title, author, description, changes)
- Original value lookup from game data
- Mod file path extraction
- Search/replace property-based semantics (card pairs)
- Version info
"""

import json
import tempfile
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — these replicate the logic of main_window methods so we can unit-
# test them without instantiating the full GUI.  Each test class documents
# which main_window method it mirrors.
# ---------------------------------------------------------------------------

def _parse_definition_title(file_path: Path) -> str:
    """Mirror of MainWindow._get_definition_title."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        title_elem = root.find('title')
        if title_elem is not None and title_elem.text:
            return title_elem.text.strip()
    except (ET.ParseError, OSError):
        pass
    return file_path.stem


def _parse_definition_author(file_path: Path) -> str:
    """Mirror of MainWindow._get_definition_author."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        author_elem = root.find('author')
        if author_elem is not None and author_elem.text:
            return author_elem.text.strip()
    except (ET.ParseError, OSError):
        pass
    return ""


def _parse_definition_description(file_path: Path) -> str:
    """Mirror of MainWindow._get_definition_description."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        desc_elem = root.find('description')
        if desc_elem is not None and desc_elem.text:
            return desc_elem.text.strip()
    except (ET.ParseError, OSError):
        pass
    return ""


def _parse_definition_changes(file_path: Path) -> list[dict]:
    """Mirror of MainWindow._get_definition_changes."""
    changes = []
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        for change_elem in root.iter('change'):
            item = change_elem.get('item', '')
            prop = change_elem.get('property', '')
            value = change_elem.get('value', '')
            if item and prop:
                change_data = {'item': item, 'property': prop, 'value': value}
                add_prop = change_elem.find('add_property')
                if add_prop is not None and add_prop.text:
                    json_text = add_prop.text.strip()
                    change_data['add_property_json'] = json_text
                    try:
                        prop_json = json.loads(json_text)
                        change_data['add_property'] = True
                        change_data['add_property_item'] = add_prop.get('item', '')
                        change_data['add_property_name'] = prop_json.get('Name', '')
                        change_data['add_property_default'] = str(prop_json.get('Value', ''))
                        change_data['add_property_type'] = (
                            prop_json.get('$type', '')
                            .split('.')[-1]
                            .replace('Data, UAssetAPI', '')
                            .strip()
                            .rstrip(',')
                        )
                    except (json.JSONDecodeError, AttributeError):
                        change_data['add_property'] = True
                changes.append(change_data)
        for delete_elem in root.iter('delete'):
            item = delete_elem.get('item', '')
            prop = delete_elem.get('property', '')
            value = delete_elem.get('value', '')
            if item and prop:
                changes.append({
                    'item': item, 'property': prop, 'value': value,
                    'is_delete': True,
                })
    except (ET.ParseError, OSError):
        pass
    return sorted(changes, key=lambda x: x['item'].lower())


def _get_mod_file_path(file_path: Path) -> str | None:
    """Mirror of MainWindow._get_mod_file_path."""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        mod_elem = root.find('mod')
        if mod_elem is not None:
            return mod_elem.get('file', '')
    except (ET.ParseError, OSError):
        pass
    return None


def _get_original_value(game_data: dict | None, item_name: str,
                        property_path: str) -> str | None:
    """Mirror of MainWindow._get_original_value."""
    import re as _re
    if not game_data or not item_name or not property_path:
        return None
    try:
        item_data = None
        name_variations = [
            f"Default__{item_name}_C", f"Default__{item_name}",
            item_name, f"{item_name}_C",
        ]
        for name_variant in name_variations:
            for export in game_data.get('Exports', []):
                if export.get('ObjectName', '') == name_variant:
                    data = export.get('Data', [])
                    if isinstance(data, list):
                        item_data = data
                        break
            if item_data:
                break

        if item_data is None:
            try:
                table_data = game_data['Exports'][0]['Table']['Data']
                for row in table_data:
                    if row.get('Name') == item_name:
                        value_array = row.get('Value', [])
                        if isinstance(value_array, list):
                            item_data = value_array
                        break
            except (KeyError, IndexError, TypeError):
                pass

        if not item_data:
            return None

        parts = []
        for segment in property_path.split('.'):
            match = _re.match(r'^(\w+)(?:\[(\d+)\])?$', segment)
            if match:
                parts.append((match.group(1), int(match.group(2)) if match.group(2) is not None else None))
            else:
                parts.append((segment, None))

        current = item_data
        for name, index in parts:
            if isinstance(current, list):
                found = False
                for entry in current:
                    if isinstance(entry, dict) and entry.get('Name') == name:
                        current = entry.get('Value')
                        if index is not None and isinstance(current, list):
                            if 0 <= index < len(current):
                                indexed = current[index]
                                current = indexed.get('Value') if isinstance(indexed, dict) and 'Value' in indexed else indexed
                            else:
                                return None
                        found = True
                        break
                if not found:
                    return None
            elif isinstance(current, dict):
                if name in current:
                    current = current[name]
                    if index is not None and isinstance(current, list):
                        if 0 <= index < len(current):
                            indexed = current[index]
                            current = indexed.get('Value') if isinstance(indexed, dict) and 'Value' in indexed else indexed
                        else:
                            return None
                elif 'Value' in current:
                    current = current['Value']
                    continue
                else:
                    return None
            else:
                return None

        return str(current) if current is not None else None
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _write_def(temp_dir: Path, name: str, content: str) -> Path:
    p = temp_dir / f"{name}.def"
    p.write_text(content, encoding='utf-8')
    return p


# ===========================================================================
# Test classes
# ===========================================================================


class TestDefinitionTitle:
    """Tests for _get_definition_title logic."""

    def test_basic_title(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><title>Hello World</title></definition>')
        assert _parse_definition_title(p) == "Hello World"

    def test_title_with_whitespace(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><title>  Spaced  </title></definition>')
        assert _parse_definition_title(p) == "Spaced"

    def test_missing_title_returns_stem(self, temp_dir):
        p = _write_def(temp_dir, "MyMod", '<definition></definition>')
        assert _parse_definition_title(p) == "MyMod"

    def test_empty_title_returns_stem(self, temp_dir):
        p = _write_def(temp_dir, "Fallback", '<definition><title></title></definition>')
        assert _parse_definition_title(p) == "Fallback"

    def test_invalid_xml_returns_stem(self, temp_dir):
        p = _write_def(temp_dir, "Bad", 'not xml at all')
        assert _parse_definition_title(p) == "Bad"

    def test_missing_file_returns_stem(self, temp_dir):
        p = temp_dir / "Ghost.def"
        assert _parse_definition_title(p) == "Ghost"


class TestDefinitionAuthor:
    """Tests for _get_definition_author logic."""

    def test_basic_author(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><author>John</author></definition>')
        assert _parse_definition_author(p) == "John"

    def test_missing_author(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition></definition>')
        assert _parse_definition_author(p) == ""

    def test_empty_author(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><author></author></definition>')
        assert _parse_definition_author(p) == ""

    def test_author_with_whitespace(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><author>  Trimmed  </author></definition>')
        assert _parse_definition_author(p) == "Trimmed"


class TestDefinitionDescription:
    """Tests for _get_definition_description logic."""

    def test_basic_description(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><description>A mod</description></definition>')
        assert _parse_definition_description(p) == "A mod"

    def test_missing_description(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition></definition>')
        assert _parse_definition_description(p) == ""

    def test_empty_description(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><description></description></definition>')
        assert _parse_definition_description(p) == ""


class TestDefinitionChanges:
    """Tests for _get_definition_changes logic."""

    def test_single_change(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change item="Item.Stone" property="MaxStackSize" value="999"/>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 1
        assert changes[0]['item'] == 'Item.Stone'
        assert changes[0]['property'] == 'MaxStackSize'
        assert changes[0]['value'] == '999'

    def test_multiple_changes_sorted(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change item="Zebra" property="P1" value="V1"/>
                <change item="Apple" property="P2" value="V2"/>
                <change item="Banana" property="P3" value="V3"/>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 3
        assert changes[0]['item'] == 'Apple'
        assert changes[1]['item'] == 'Banana'
        assert changes[2]['item'] == 'Zebra'

    def test_delete_element(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <delete item="Enemy.Goblin" property="Tags" value="Enemy.Type.Melee"/>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 1
        assert changes[0]['is_delete'] is True
        assert changes[0]['item'] == 'Enemy.Goblin'
        assert changes[0]['property'] == 'Tags'
        assert changes[0]['value'] == 'Enemy.Type.Melee'

    def test_change_with_add_property(self, temp_dir):
        add_prop_json = json.dumps({
            "$type": "IntPropertyData, UAssetAPI",
            "Name": "NewField",
            "Value": 42,
        })
        p = _write_def(temp_dir, "T", f'''<definition>
            <mod file="test.json">
                <change item="Item.X" property="SomeField" value="10">
                    <add_property>{add_prop_json}</add_property>
                </change>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 1
        c = changes[0]
        assert c['add_property'] is True
        assert c['add_property_name'] == 'NewField'
        assert c['add_property_default'] == '42'
        assert 'IntProperty' in c['add_property_type']

    def test_change_with_invalid_add_property_json(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change item="Item.X" property="P" value="V">
                    <add_property>not valid json</add_property>
                </change>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 1
        assert changes[0]['add_property'] is True

    def test_skip_change_without_item(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change property="P" value="V"/>
            </mod>
        </definition>''')
        assert _parse_definition_changes(p) == []

    def test_skip_change_without_property(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change item="I" value="V"/>
            </mod>
        </definition>''')
        assert _parse_definition_changes(p) == []

    def test_mixed_changes_and_deletes(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="test.json">
                <change item="Item.A" property="P1" value="V1"/>
                <delete item="Item.B" property="Tags" value="tag1"/>
                <change item="Item.C" property="P2" value="V2"/>
            </mod>
        </definition>''')
        changes = _parse_definition_changes(p)
        assert len(changes) == 3
        # Sorted by item
        assert changes[0]['item'] == 'Item.A'
        assert changes[1]['item'] == 'Item.B'
        assert changes[1].get('is_delete') is True
        assert changes[2]['item'] == 'Item.C'

    def test_empty_def(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition></definition>')
        assert _parse_definition_changes(p) == []

    def test_invalid_xml(self, temp_dir):
        p = _write_def(temp_dir, "T", 'garbage')
        assert _parse_definition_changes(p) == []


class TestGetModFilePath:
    """Tests for _get_mod_file_path logic."""

    def test_basic_mod_path(self, temp_dir):
        p = _write_def(temp_dir, "T", '''<definition>
            <mod file="\\Moria\\Content\\Items\\DT_Items.json"/>
        </definition>''')
        assert _get_mod_file_path(p) == "\\Moria\\Content\\Items\\DT_Items.json"

    def test_no_mod_element(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition></definition>')
        assert _get_mod_file_path(p) is None

    def test_invalid_xml(self, temp_dir):
        p = _write_def(temp_dir, "T", 'bad xml')
        assert _get_mod_file_path(p) is None

    def test_mod_without_file_attr(self, temp_dir):
        p = _write_def(temp_dir, "T", '<definition><mod></mod></definition>')
        assert _get_mod_file_path(p) == ""


class TestGetOriginalValue:
    """Tests for _get_original_value — game JSON traversal."""

    def test_none_game_data(self):
        assert _get_original_value(None, "Item.X", "P") is None

    def test_empty_item_name(self):
        assert _get_original_value({"Exports": []}, "", "P") is None

    def test_empty_property_path(self):
        assert _get_original_value({"Exports": []}, "Item.X", "") is None

    def test_export_format_direct_match(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "MaxStackSize", "Value": 999}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "MaxStackSize") == "999"

    def test_export_format_default_prefix(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Default__Item.Stone",
                "Data": [
                    {"Name": "Weight", "Value": 1.5}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "Weight") == "1.5"

    def test_datatable_format(self):
        game_data = {
            "Exports": [{
                "Table": {
                    "Data": [
                        {"Name": "Item.Stone", "Value": [
                            {"Name": "MaxStackSize", "Value": 500}
                        ]}
                    ]
                }
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "MaxStackSize") == "500"

    def test_datatable_item_not_found(self):
        game_data = {
            "Exports": [{
                "Table": {
                    "Data": [
                        {"Name": "Item.Wood", "Value": [
                            {"Name": "MaxStackSize", "Value": 100}
                        ]}
                    ]
                }
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "MaxStackSize") is None

    def test_property_not_found(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "Weight", "Value": 1.0}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "NonExistent") is None

    def test_indexed_property(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "Materials", "Value": [
                        {"Value": "Iron"},
                        {"Value": "Copper"},
                        {"Value": "Gold"},
                    ]}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "Materials[1]") == "Copper"

    def test_indexed_out_of_range(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "Materials", "Value": [
                        {"Value": "Iron"},
                    ]}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "Materials[5]") is None

    def test_nested_property_path(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "Stats", "Value": [
                        {"Name": "Damage", "Value": 25}
                    ]}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "Stats.Damage") == "25"

    def test_empty_exports(self):
        assert _get_original_value({"Exports": []}, "Item.X", "P") is None

    def test_string_value(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "DisplayName", "Value": "Stone Block"}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "DisplayName") == "Stone Block"

    def test_boolean_value(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": [
                    {"Name": "bStackable", "Value": True}
                ]
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "bStackable") == "True"

    def test_malformed_game_data(self):
        assert _get_original_value({"Exports": [{"ObjectName": "X"}]}, "X", "P") is None

    def test_export_data_not_list(self):
        game_data = {
            "Exports": [{
                "ObjectName": "Item.Stone",
                "Data": "not a list"
            }]
        }
        assert _get_original_value(game_data, "Item.Stone", "P") is None


class TestVersionInfo:
    """Tests for version constants."""

    def test_version_is_2_0_0(self):
        from src.ui.about_dialog import APP_VERSION
        assert APP_VERSION == "2.0.0"

    def test_app_name(self):
        from src.ui.about_dialog import APP_NAME
        assert APP_NAME == "Moria MOD Creator"

    def test_app_author(self):
        from src.ui.about_dialog import APP_AUTHOR
        assert APP_AUTHOR == "John B Owens II"

    def test_github_url(self):
        from src.ui.about_dialog import GITHUB_URL
        assert "github.com" in GITHUB_URL


class TestSearchReplaceSemantics:
    """Test the property-based search/replace logic.

    These test the pure algorithmic logic that search matches property names
    and replace sets the value — mirroring the card_property_pairs approach
    in main_window.py.
    """

    @staticmethod
    def _simulate_search(pairs: list[tuple[str, str]], search_text: str,
                         start_index: int = -1) -> int | None:
        """Simulate _on_card_search: find next property match index."""
        if not search_text or not pairs:
            return None
        matches = [
            i for i, (prop, _) in enumerate(pairs)
            if search_text.lower() in prop.lower()
        ]
        if not matches:
            return None
        start = start_index + 1
        for idx in matches:
            if idx >= start:
                return idx
        return matches[0]  # wrap

    @staticmethod
    def _simulate_replace_all(pairs: list[tuple[str, str]], search_text: str,
                              replace_text: str) -> list[tuple[str, str]]:
        """Simulate _on_card_replace_all: replace values of matching properties."""
        result = []
        for prop, val in pairs:
            if search_text.lower() in prop.lower():
                result.append((prop, replace_text))
            else:
                result.append((prop, val))
        return result

    def test_search_finds_property(self):
        pairs = [("MaxStackSize", "100"), ("Weight", "1.0"), ("MaxHP", "500")]
        idx = self._simulate_search(pairs, "Max")
        assert idx == 0

    def test_search_case_insensitive(self):
        pairs = [("maxstacksize", "100"), ("Weight", "1.0")]
        idx = self._simulate_search(pairs, "MAX")
        assert idx == 0

    def test_search_no_match(self):
        pairs = [("Weight", "1.0"), ("Height", "2.0")]
        idx = self._simulate_search(pairs, "Damage")
        assert idx is None

    def test_search_wraps_around(self):
        pairs = [("MaxA", "1"), ("MaxB", "2"), ("Other", "3")]
        # Start after last match (index 1), should wrap to 0
        idx = self._simulate_search(pairs, "Max", start_index=1)
        assert idx == 0

    def test_search_advances(self):
        pairs = [("MaxA", "1"), ("MaxB", "2"), ("MaxC", "3")]
        idx = self._simulate_search(pairs, "Max", start_index=0)
        assert idx == 1

    def test_search_empty_text(self):
        pairs = [("A", "1")]
        assert self._simulate_search(pairs, "") is None

    def test_search_empty_pairs(self):
        assert self._simulate_search([], "test") is None

    def test_replace_all_matching_properties(self):
        pairs = [("MaxA", "10"), ("Weight", "1.0"), ("MaxB", "20")]
        result = self._simulate_replace_all(pairs, "Max", "999")
        assert result[0] == ("MaxA", "999")
        assert result[1] == ("Weight", "1.0")  # unchanged
        assert result[2] == ("MaxB", "999")

    def test_replace_all_no_match(self):
        pairs = [("Weight", "1.0"), ("Height", "2.0")]
        result = self._simulate_replace_all(pairs, "Damage", "999")
        assert result == pairs

    def test_replace_all_case_insensitive(self):
        pairs = [("maxstack", "5"), ("MAXHP", "100")]
        result = self._simulate_replace_all(pairs, "max", "0")
        assert result[0][1] == "0"
        assert result[1][1] == "0"

    def test_replace_all_empty_replacement(self):
        pairs = [("MaxStack", "100")]
        result = self._simulate_replace_all(pairs, "Max", "")
        assert result[0][1] == ""

    def test_replace_sets_full_value_not_substring(self):
        """Replace should SET the value, not do text substitution within it."""
        pairs = [("MaxStackSize", "100")]
        result = self._simulate_replace_all(pairs, "MaxStackSize", "999")
        assert result[0] == ("MaxStackSize", "999")

    def test_partial_property_match(self):
        """Search 'Stack' should match 'MaxStackSize'."""
        pairs = [("MaxStackSize", "100"), ("Weight", "1.0")]
        idx = self._simulate_search(pairs, "Stack")
        assert idx == 0


class TestFormPropertyPairs:
    """Test the property-pairs extraction logic used in buildings/constructions views.

    This mirrors _get_form_property_pairs which walks CTkFrame children looking
    for label+entry pairs.
    """

    @staticmethod
    def _extract_pairs(label_entry_data: list[tuple[str, str, bool]]) -> list[tuple[str, str]]:
        """Simulate extraction: each tuple is (label_text, entry_value, is_disabled).

        Returns (property_name, value) pairs, excluding disabled entries.
        """
        pairs = []
        for label_text, value, disabled in label_entry_data:
            prop = label_text.rstrip(":")
            if not disabled:
                pairs.append((prop, value))
        return pairs

    def test_strips_colon_from_label(self):
        data = [("MaxStackSize:", "100", False)]
        pairs = self._extract_pairs(data)
        assert pairs[0][0] == "MaxStackSize"

    def test_excludes_disabled_entries(self):
        data = [
            ("Name:", "ReadOnly", True),
            ("Weight:", "1.0", False),
        ]
        pairs = self._extract_pairs(data)
        assert len(pairs) == 1
        assert pairs[0][0] == "Weight"

    def test_empty_form(self):
        assert self._extract_pairs([]) == []

    def test_multiple_fields(self):
        data = [
            ("A:", "1", False),
            ("B:", "2", False),
            ("C:", "3", False),
        ]
        pairs = self._extract_pairs(data)
        assert len(pairs) == 3
        assert [p[0] for p in pairs] == ["A", "B", "C"]
