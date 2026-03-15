"""Unit tests for the build manager."""

import json
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
import tempfile
import shutil

from src.build_manager import BuildManager


class TestBuildManager:
    """Tests for BuildManager class."""

    def test_init_without_callback(self):
        """Test BuildManager initialization without progress callback."""
        manager = BuildManager()
        assert manager.progress_callback is None

    def test_init_with_callback(self):
        """Test BuildManager initialization with progress callback."""
        callback = Mock()
        manager = BuildManager(progress_callback=callback)
        assert manager.progress_callback == callback

    def test_report_progress_without_callback(self):
        """Test progress reporting without callback set."""
        manager = BuildManager()
        # Should not raise
        manager._report_progress("Test message", 0.5)

    def test_report_progress_with_callback(self):
        """Test progress reporting with callback set."""
        callback = Mock()
        manager = BuildManager(progress_callback=callback)
        manager._report_progress("Test message", 0.5)
        callback.assert_called_once_with("Test message", 0.5)


class TestApplyJsonChange:
    """Tests for _apply_json_change method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = BuildManager()

    def test_apply_change_to_default_export(self):
        """Test applying a change to a Default__ prefixed export."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObject_C",
                    "Data": [
                        {"Name": "TestProperty", "Value": 100}
                    ]
                }
            ]
        }

        self.manager._apply_json_change(json_data, "TestObject", "TestProperty", "200")

        assert json_data["Exports"][0]["Data"][0]["Value"] == 200

    def test_apply_change_to_nested_property(self):
        """Test applying a change to a nested property."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObject_C",
                    "Data": [
                        {
                            "Name": "OuterProperty",
                            "Value": [
                                {"Name": "InnerProperty", "Value": 50.0}
                            ]
                        }
                    ]
                }
            ]
        }

        self.manager._apply_json_change(
            json_data, "TestObject", "OuterProperty.InnerProperty", "75.5"
        )

        assert json_data["Exports"][0]["Data"][0]["Value"][0]["Value"] == 75.5

    def test_apply_change_no_exports(self):
        """Test applying a change when no Exports key exists."""
        json_data = {}
        # Should not raise
        self.manager._apply_json_change(json_data, "TestObject", "Property", "value")

    def test_apply_change_export_not_found(self):
        """Test applying a change when export is not found."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "OtherObject",
                    "Data": [{"Name": "Property", "Value": 100}]
                }
            ]
        }
        # Should not raise, but value unchanged
        self.manager._apply_json_change(json_data, "TestObject", "Property", "200")
        assert json_data["Exports"][0]["Data"][0]["Value"] == 100

    def test_apply_change_to_datatable_row(self):
        """Test applying a change to a DataTable format (Table.Data rows)."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_Items",
                    "Table": {
                        "Data": [
                            {
                                "Name": "Scrap",
                                "Value": [
                                    {"Name": "MaxStackSize", "Value": 99}
                                ]
                            },
                            {
                                "Name": "Wood",
                                "Value": [
                                    {"Name": "MaxStackSize", "Value": 99}
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        self.manager._apply_json_change(json_data, "Scrap", "MaxStackSize", "9999")

        # Scrap should be updated
        assert json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"] == 9999
        # Wood should remain unchanged
        assert json_data["Exports"][0]["Table"]["Data"][1]["Value"][0]["Value"] == 99

    def test_apply_change_datatable_nested_property(self):
        """Test applying a change to a nested property in DataTable format."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_Storage",
                    "Table": {
                        "Data": [
                            {
                                "Name": "Dwarf.Inventory",
                                "Value": [
                                    {
                                        "Name": "Dimensions",
                                        "Value": [
                                            {"Name": "Width", "Value": 8},
                                            {"Name": "Height", "Value": 4}
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        self.manager._apply_json_change(json_data, "Dwarf.Inventory", "Dimensions.Width", "12")

        assert json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"] == 12

    def test_apply_change_datatable_row_not_found(self):
        """Test applying a change when DataTable row is not found."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_Items",
                    "Table": {
                        "Data": [
                            {
                                "Name": "Scrap",
                                "Value": [
                                    {"Name": "MaxStackSize", "Value": 99}
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        # Should not raise, and Scrap should remain unchanged
        self.manager._apply_json_change(json_data, "NonExistentItem", "MaxStackSize", "9999")
        assert json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"] == 99

    def test_apply_change_prefers_objectname_over_datatable(self):
        """Test that ObjectName matching takes priority over DataTable format."""
        # This tests the case where both formats might match
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestItem_C",
                    "Data": [
                        {"Name": "MaxStackSize", "Value": 50}
                    ]
                },
                {
                    "ObjectName": "DT_Items",
                    "Table": {
                        "Data": [
                            {
                                "Name": "TestItem",
                                "Value": [
                                    {"Name": "MaxStackSize", "Value": 99}
                                ]
                            }
                        ]
                    }
                }
            ]
        }

        self.manager._apply_json_change(json_data, "TestItem", "MaxStackSize", "9999")

        # ObjectName match should be updated (priority)
        assert json_data["Exports"][0]["Data"][0]["Value"] == 9999
        # DataTable should remain unchanged (fallback not used)
        assert json_data["Exports"][1]["Table"]["Data"][0]["Value"][0]["Value"] == 99


class TestSetNestedPropertyValue:
    """Tests for _set_nested_property_value method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = BuildManager()

    def test_set_float_value(self):
        """Test setting a float value."""
        data = [{"Name": "FloatProp", "Value": 1.0}]
        self.manager._set_nested_property_value(data, "FloatProp", "2.5")
        assert data[0]["Value"] == 2.5

    def test_set_int_value(self):
        """Test setting an integer value."""
        data = [{"Name": "IntProp", "Value": 10}]
        self.manager._set_nested_property_value(data, "IntProp", "20")
        assert data[0]["Value"] == 20

    def test_set_bool_value_true(self):
        """Test setting a boolean value to true."""
        data = [{"Name": "BoolProp", "Value": False}]  # Old value is bool
        self.manager._set_nested_property_value(data, "BoolProp", "true")
        assert data[0]["Value"] is True

    def test_set_bool_value_false(self):
        """Test setting a boolean value to false."""
        data = [{"Name": "BoolProp", "Value": True}]  # Old value is bool
        self.manager._set_nested_property_value(data, "BoolProp", "no")
        assert data[0]["Value"] is False

    def test_set_string_value(self):
        """Test setting a string value."""
        data = [{"Name": "StringProp", "Value": "old"}]
        self.manager._set_nested_property_value(data, "StringProp", "new")
        assert data[0]["Value"] == "new"

    def test_empty_data(self):
        """Test with empty data list."""
        data = []
        # Should not raise
        self.manager._set_nested_property_value(data, "Property", "value")

    def test_empty_property_path(self):
        """Test with empty property path."""
        data = [{"Name": "Property", "Value": 100}]
        # Should not raise, value unchanged
        self.manager._set_nested_property_value(data, "", "200")
        assert data[0]["Value"] == 100

    def test_property_not_found(self):
        """Test when property is not found."""
        data = [{"Name": "OtherProperty", "Value": 100}]
        # Should not raise
        self.manager._set_nested_property_value(data, "Property", "200")
        assert data[0]["Value"] == 100

    def test_array_index_simple(self):
        """Test array indexing with bracket notation."""
        data = [
            {
                "Name": "StageDataList",
                "Value": [
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 0}
                    ]},
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 180}
                    ]},
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 0}
                    ]}
                ]
            }
        ]
        # Change Stage 2 (index 1) progression points
        path = "StageDataList[1].MonumentProgressonPointsNeeded"
        self.manager._set_nested_property_value(data, path, "100")
        # Stage 2 should be updated
        assert data[0]["Value"][1]["Value"][0]["Value"] == 100
        # Stage 1 and 3 should remain unchanged
        assert data[0]["Value"][0]["Value"][0]["Value"] == 0
        assert data[0]["Value"][2]["Value"][0]["Value"] == 0

    def test_array_index_out_of_bounds(self):
        """Test array indexing with out of bounds index."""
        data = [
            {
                "Name": "StageDataList",
                "Value": [
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 0}
                    ]}
                ]
            }
        ]
        # Index 5 is out of bounds - should not raise, value unchanged
        path = "StageDataList[5].MonumentProgressonPointsNeeded"
        self.manager._set_nested_property_value(data, path, "100")
        assert data[0]["Value"][0]["Value"][0]["Value"] == 0

    def test_array_index_multiple_levels(self):
        """Test array indexing with multiple array indices."""
        data = [
            {
                "Name": "StageDataList",
                "Value": [
                    {"Name": "StageDataList", "Value": [
                        {"Name": "StageBuildItems", "Value": [
                            {"Name": "StageBuildItems", "Value": [
                                {"Name": "Count", "Value": 100}
                            ]},
                            {"Name": "StageBuildItems", "Value": [
                                {"Name": "Count", "Value": 20}
                            ]}
                        ]}
                    ]}
                ]
            }
        ]
        # Change the count of the second build item in stage 1
        self.manager._set_nested_property_value(
            data,
            "StageDataList[0].StageBuildItems[1].Count",
            "50"
        )
        assert data[0]["Value"][0]["Value"][0]["Value"][1]["Value"][0]["Value"] == 50
        # First item unchanged
        assert data[0]["Value"][0]["Value"][0]["Value"][0]["Value"][0]["Value"] == 100

    def test_wildcard_array_index(self):
        """Test [*] wildcard expands to all array elements."""
        data = [
            {
                "Name": "StageDataList",
                "Value": [
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 0}
                    ]},
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 180}
                    ]},
                    {"Name": "StageDataList", "Value": [
                        {"Name": "MonumentProgressonPointsNeeded", "Value": 260}
                    ]}
                ]
            }
        ]
        # Wildcard should change ALL stages
        path = "StageDataList[*].MonumentProgressonPointsNeeded"
        self.manager._set_nested_property_value(data, path, "0")
        assert data[0]["Value"][0]["Value"][0]["Value"] == 0
        assert data[0]["Value"][1]["Value"][0]["Value"] == 0
        assert data[0]["Value"][2]["Value"][0]["Value"] == 0

    def test_dict_style_property(self):
        """Test setting a property in dict-style format (like RichCurveKey)."""
        data = [
            {
                "Name": "FloatCurve",
                "Value": [
                    {
                        "Name": "Keys",
                        "Value": [
                            {"Name": "Keys", "Value": [
                                {"Name": "Keys", "Value": {"Time": 0.0, "Value": 90.0}}
                            ]}
                        ]
                    }
                ]
            }
        ]
        # Set the Time value inside the dict - path is FloatCurve.Keys[0].Keys.Time
        # FloatCurve -> Keys array -> [0] -> struct with Name=Keys -> Value is dict with Time
        self.manager._set_nested_property_value(data, "FloatCurve.Keys[0].Keys.Time", "100")
        assert data[0]["Value"][0]["Value"][0]["Value"][0]["Value"]["Time"] == 100.0


class TestApplyJsonChangeNone:
    """Tests for _apply_json_change with NONE item."""

    def setup_method(self):
        """Set up test fixtures."""
        self.manager = BuildManager()

    def test_none_applies_to_all_datatable_rows(self):
        """Test NONE applies change to all DataTable rows."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_SettlementLevelData",
                    "Table": {
                        "Data": [
                            {
                                "Name": "1",
                                "Value": [{"Name": "LevelData", "Value": [
                                    {"Name": "MaxNpcsAllowed", "Value": 5}
                                ]}]
                            },
                            {
                                "Name": "2",
                                "Value": [{"Name": "LevelData", "Value": [
                                    {"Name": "MaxNpcsAllowed", "Value": 7}
                                ]}]
                            },
                            {
                                "Name": "3",
                                "Value": [{"Name": "LevelData", "Value": [
                                    {"Name": "MaxNpcsAllowed", "Value": 9}
                                ]}]
                            }
                        ]
                    }
                }
            ]
        }

        self.manager._apply_json_change(json_data, "NONE", "LevelData.MaxNpcsAllowed", "40")

        # All rows should be updated
        assert json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"] == 40
        assert json_data["Exports"][0]["Table"]["Data"][1]["Value"][0]["Value"][0]["Value"] == 40
        assert json_data["Exports"][0]["Table"]["Data"][2]["Value"][0]["Value"][0]["Value"] == 40

    def test_none_applies_to_single_asset(self):
        """Test NONE applies change to single asset export."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Curve_Test",
                    "Data": [
                        {"Name": "FloatCurve", "Value": [{"Name": "TestProp", "Value": 100}]}
                    ]
                }
            ]
        }

        self.manager._apply_json_change(json_data, "NONE", "FloatCurve.TestProp", "200")

        assert json_data["Exports"][0]["Data"][0]["Value"][0]["Value"] == 200

    def test_none_with_wildcard_and_dict_style(self):
        """Test NONE with wildcard [*] and dict-style property access (curve files)."""
        # Simulates the structure of Curve_AdmiringTreasurePiles_Noble.json
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Curve_Test",
                    "Data": [
                        {
                            "Name": "FloatCurve",
                            "Value": [
                                {
                                    "Name": "Keys",
                                    "Value": [
                                        {"Name": "Keys", "Value": [
                                            {"Name": "Keys", "Value": {
                                                "Time": 0.0, "Value": 90.0
                                            }}
                                        ]},
                                        {"Name": "Keys", "Value": [
                                            {"Name": "Keys", "Value": {
                                                "Time": 10.0, "Value": 90.0
                                            }}
                                        ]},
                                        {"Name": "Keys", "Value": [
                                            {"Name": "Keys", "Value": {
                                                "Time": 41.0, "Value": 180.0
                                            }}
                                        ]}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            ]
        }

        # Change all Time values to 1800 using NONE and wildcard
        self.manager._apply_json_change(json_data, "NONE", "FloatCurve.Keys[*].Keys.Time", "1800")

        keys = json_data["Exports"][0]["Data"][0]["Value"][0]["Value"]
        assert keys[0]["Value"][0]["Value"]["Time"] == 1800.0
        assert keys[1]["Value"][0]["Value"]["Time"] == 1800.0
        assert keys[2]["Value"][0]["Value"]["Time"] == 1800.0


class TestBuildProcess:
    """Integration tests for the build process."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BuildManager()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_build_with_no_files(self):
        """Test build with no definition files."""
        success, message = self.manager.build("TestMod", [])
        assert success is False
        assert "No definition files selected" in message

    @patch('src.build_manager.get_output_dir')
    @patch('src.build_manager.get_default_mymodfiles_dir')
    @patch('src.build_manager.get_utilities_dir')
    def test_build_missing_source_file(
        self,
        mock_utilities,
        mock_mymodfiles,
        mock_output
    ):
        """Test build when source JSON file is missing."""
        # Set up mocks
        mock_output.return_value = Path(self.temp_dir) / 'output'
        mock_mymodfiles.return_value = Path(self.temp_dir) / 'mymodfiles'
        mock_utilities.return_value = Path(self.temp_dir) / 'utilities'

        # Create utilities directory with mock executables
        utilities_dir = Path(self.temp_dir) / 'utilities'
        utilities_dir.mkdir(parents=True)
        (utilities_dir / 'UAssetGUI.exe').touch()
        (utilities_dir / 'retoc.exe').touch()

        # Create a definition file
        def_dir = Path(self.temp_dir) / 'definitions'
        def_dir.mkdir(parents=True)
        def_file = def_dir / 'test.def'
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>Test</description>
    <mod file="\\Moria\\Content\\Test.json">
        <change item="TestItem" property="Value" value="100" />
    </mod>
</definition>''', encoding='utf-8')

        success, _msg = self.manager.build("TestMod", [def_file])
        assert success is False


class TestNormalizeSecretsPath:
    """Tests for _normalize_secrets_path static method."""

    def test_normal_path(self):
        """Test normalizing a normal (non-secrets) path."""
        result = BuildManager._normalize_secrets_path(
            r'\Moria\Content\Tech\Data\Building\DT_Constructions.json'
        )
        assert result == 'Moria/Content/Tech/Data/Building/DT_Constructions.json'

    def test_secrets_path_with_jsondata(self):
        """Test normalizing a secrets path with jsondata."""
        result = BuildManager._normalize_secrets_path(
            r'Secrets Source\jsondata\Moria\Content\Test.json'
        )
        assert result == 'Moria/Content/Test.json'

    def test_secrets_path_without_jsondata(self):
        """Test normalizing a secrets path without jsondata."""
        result = BuildManager._normalize_secrets_path(
            r'Secrets Source/SomeFile.json'
        )
        assert result == 'SomeFile.json'

    def test_forward_slashes(self):
        """Test path with forward slashes."""
        result = BuildManager._normalize_secrets_path(
            'Secrets Source/jsondata/Building/DT_X.json'
        )
        assert result == 'Building/DT_X.json'

    def test_leading_slashes_stripped(self):
        """Test leading slashes are stripped."""
        result = BuildManager._normalize_secrets_path('/Moria/Content/Test.json')
        assert result == 'Moria/Content/Test.json'


class TestConvertValue:
    """Tests for _convert_value method."""

    def setup_method(self):
        self.manager = BuildManager()

    def test_convert_bool_true(self):
        """Test converting to bool true."""
        assert self.manager._convert_value(False, 'true') is True
        assert self.manager._convert_value(False, '1') is True
        assert self.manager._convert_value(False, 'yes') is True

    def test_convert_bool_false(self):
        """Test converting to bool false."""
        assert self.manager._convert_value(True, 'false') is False
        assert self.manager._convert_value(True, '0') is False
        assert self.manager._convert_value(True, 'no') is False

    def test_convert_float(self):
        """Test converting to float."""
        assert self.manager._convert_value(1.0, '2.5') == 2.5
        assert self.manager._convert_value(0.0, '100') == 100.0

    def test_convert_float_invalid(self):
        """Test converting invalid string to float returns string."""
        assert self.manager._convert_value(1.0, 'not_a_number') == 'not_a_number'

    def test_convert_int(self):
        """Test converting to int."""
        assert self.manager._convert_value(10, '20') == 20
        assert self.manager._convert_value(0, '9999') == 9999

    def test_convert_int_from_float_string(self):
        """Test converting float string to int (truncates)."""
        assert self.manager._convert_value(10, '20.7') == 20

    def test_convert_int_invalid(self):
        """Test converting invalid string to int returns string."""
        assert self.manager._convert_value(10, 'not_a_number') == 'not_a_number'

    def test_convert_string(self):
        """Test converting string to string."""
        assert self.manager._convert_value('old', 'new') == 'new'

    def test_bool_before_int(self):
        """Test that bool is checked before int (bool is subclass of int)."""
        # This is the critical edge case: isinstance(True, int) is True
        assert self.manager._convert_value(True, 'false') is False
        assert self.manager._convert_value(False, 'true') is True


class TestFindItemData:
    """Tests for _find_item_data method."""

    def setup_method(self):
        self.manager = BuildManager()

    def test_find_by_objectname_default(self):
        """Test finding item by Default__ ObjectName."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObj_C",
                    "Data": [{"Name": "Prop", "Value": 1}]
                }
            ]
        }
        result = self.manager._find_item_data(json_data, "TestObj")
        assert result is not None
        assert result[0]["Name"] == "Prop"

    def test_find_by_exact_objectname(self):
        """Test finding item by exact ObjectName."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "TestObj",
                    "Data": [{"Name": "Prop", "Value": 1}]
                }
            ]
        }
        result = self.manager._find_item_data(json_data, "TestObj")
        assert result is not None

    def test_find_in_datatable(self):
        """Test finding item in DataTable format."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_Items",
                    "Table": {
                        "Data": [
                            {"Name": "Scrap", "Value": [{"Name": "Stack", "Value": 99}]}
                        ]
                    }
                }
            ]
        }
        result = self.manager._find_item_data(json_data, "Scrap")
        assert result is not None
        assert result[0]["Name"] == "Stack"

    def test_find_not_found(self):
        """Test returns None when item not found."""
        json_data = {
            "Exports": [
                {"ObjectName": "OtherObj", "Data": []}
            ]
        }
        result = self.manager._find_item_data(json_data, "NonExistent")
        assert result is None


class TestAddPropertyToJson:
    """Tests for _add_property_to_json method."""

    def setup_method(self):
        self.manager = BuildManager()

    def test_add_property_to_export(self):
        """Test adding a property to an export."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObj_C",
                    "Data": [{"Name": "ExistingProp", "Value": 1}]
                }
            ]
        }
        prop_json = json.dumps({"Name": "NewProp", "Value": 42})
        self.manager._add_property_to_json(json_data, "TestObj", prop_json)

        data = json_data["Exports"][0]["Data"]
        assert len(data) == 2
        assert data[1]["Name"] == "NewProp"

    def test_add_property_already_exists(self):
        """Test adding a property that already exists does nothing."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObj_C",
                    "Data": [{"Name": "ExistingProp", "Value": 1}]
                }
            ]
        }
        prop_json = json.dumps({"Name": "ExistingProp", "Value": 99})
        self.manager._add_property_to_json(json_data, "TestObj", prop_json)

        data = json_data["Exports"][0]["Data"]
        assert len(data) == 1
        assert data[0]["Value"] == 1  # Original value unchanged

    def test_add_property_invalid_json(self):
        """Test adding property with invalid JSON string."""
        json_data = {
            "Exports": [
                {"ObjectName": "Default__TestObj_C", "Data": []}
            ]
        }
        # Should not raise
        self.manager._add_property_to_json(json_data, "TestObj", "not valid json")

    def test_add_property_missing_name(self):
        """Test adding property without Name field."""
        json_data = {
            "Exports": [
                {"ObjectName": "Default__TestObj_C", "Data": []}
            ]
        }
        prop_json = json.dumps({"Value": 42})
        self.manager._add_property_to_json(json_data, "TestObj", prop_json)
        assert len(json_data["Exports"][0]["Data"]) == 0

    def test_add_property_no_exports(self):
        """Test adding property when no Exports key."""
        json_data = {}
        prop_json = json.dumps({"Name": "NewProp", "Value": 42})
        # Should not raise
        self.manager._add_property_to_json(json_data, "TestObj", prop_json)

    def test_add_property_with_parent_path(self):
        """Test adding property with nested parent path from change."""
        json_data = {
            "Exports": [
                {
                    "ObjectName": "Default__TestObj_C",
                    "Data": [
                        {
                            "Name": "PrimaryDrop",
                            "Value": [
                                {"Name": "ExistingChild", "Value": 1}
                            ]
                        }
                    ]
                }
            ]
        }
        prop_json = json.dumps({"Name": "DropRate", "Value": 0.5})
        self.manager._add_property_to_json(
            json_data, "TestObj", prop_json, "PrimaryDrop.DropRate"
        )

        primary_drop = json_data["Exports"][0]["Data"][0]["Value"]
        assert len(primary_drop) == 2
        assert primary_drop[1]["Name"] == "DropRate"


class TestGameplayTags:
    """Tests for _remove_gameplay_tag and _add_gameplay_tag methods."""

    def setup_method(self):
        self.manager = BuildManager()
        self.json_data = {
            "Exports": [
                {
                    "ObjectName": "DT_Storage",
                    "Table": {
                        "Data": [
                            {
                                "Name": "Dwarf.Inventory",
                                "Value": [
                                    {
                                        "Name": "ExcludeItems",
                                        "Value": [
                                            {
                                                "Name": "GameplayTags",
                                                "Value": ["Item.Brew", "Item.Food", "Item.Key"]
                                            }
                                        ]
                                    },
                                    {
                                        "Name": "AllowedItems",
                                        "Value": [
                                            {
                                                "Name": "GameplayTags",
                                                "Value": ["Item.Tool"]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                }
            ]
        }

    def test_remove_existing_tag(self):
        """Test removing an existing tag."""
        self.manager._remove_gameplay_tag(
            self.json_data, "Dwarf.Inventory", "ExcludeItems", "Item.Brew"
        )
        tags = self.json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        assert "Item.Brew" not in tags
        assert "Item.Food" in tags

    def test_remove_nonexistent_tag(self):
        """Test removing a tag that doesn't exist (no error)."""
        self.manager._remove_gameplay_tag(
            self.json_data, "Dwarf.Inventory", "ExcludeItems", "Item.NotHere"
        )
        tags = self.json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        assert len(tags) == 3  # Unchanged

    def test_remove_tag_wrong_item(self):
        """Test removing tag from non-existent item."""
        self.manager._remove_gameplay_tag(
            self.json_data, "NonExistent", "ExcludeItems", "Item.Brew"
        )
        # Original unchanged
        tags = self.json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        assert "Item.Brew" in tags

    def test_remove_tag_no_exports(self):
        """Test removing tag from data with no Exports."""
        self.manager._remove_gameplay_tag({}, "Item", "ExcludeItems", "Tag")

    def test_add_new_tag(self):
        """Test adding a new tag."""
        self.manager._add_gameplay_tag(
            self.json_data, "Dwarf.Inventory", "ExcludeItems", "Item.NewTag"
        )
        tags = self.json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        assert "Item.NewTag" in tags

    def test_add_duplicate_tag(self):
        """Test adding a tag that already exists (no duplicate)."""
        self.manager._add_gameplay_tag(
            self.json_data, "Dwarf.Inventory", "ExcludeItems", "Item.Brew"
        )
        tags = self.json_data["Exports"][0]["Table"]["Data"][0]["Value"][0]["Value"][0]["Value"]
        assert tags.count("Item.Brew") == 1

    def test_add_tag_no_exports(self):
        """Test adding tag to data with no Exports."""
        self.manager._add_gameplay_tag({}, "Item", "ExcludeItems", "Tag")


class TestSyncNamemap:
    """Tests for _sync_namemap static method."""

    def test_adds_missing_name_property(self):
        """Test adds NamePropertyData values to NameMap."""
        json_data = {
            "NameMap": ["ExistingName"],
            "Exports": [
                {
                    "Data": [
                        {"$type": "NamePropertyData", "Name": "Test", "Value": "NewName"}
                    ]
                }
            ]
        }
        BuildManager._sync_namemap(json_data)
        assert "NewName" in json_data["NameMap"]

    def test_adds_missing_enum_property(self):
        """Test adds EnumPropertyData values and types to NameMap."""
        json_data = {
            "NameMap": [],
            "Exports": [
                {
                    "Data": [
                        {
                            "$type": "EnumPropertyData",
                            "Name": "BuildProcess",
                            "Value": "EBuildProcess::DualMode",
                            "EnumType": "EBuildProcess"
                        }
                    ]
                }
            ]
        }
        BuildManager._sync_namemap(json_data)
        assert "EBuildProcess::DualMode" in json_data["NameMap"]
        assert "EBuildProcess" in json_data["NameMap"]

    def test_does_not_duplicate(self):
        """Test does not add duplicates."""
        json_data = {
            "NameMap": ["AlreadyHere"],
            "Exports": [
                {
                    "Data": [
                        {"$type": "NamePropertyData", "Name": "X", "Value": "AlreadyHere"}
                    ]
                }
            ]
        }
        BuildManager._sync_namemap(json_data)
        assert json_data["NameMap"].count("AlreadyHere") == 1

    def test_no_namemap(self):
        """Test handles missing NameMap gracefully."""
        json_data = {"Exports": [{"Data": []}]}
        # Should not raise
        BuildManager._sync_namemap(json_data)

    def test_namemap_not_list(self):
        """Test handles non-list NameMap."""
        json_data = {"NameMap": "not_a_list", "Exports": []}
        BuildManager._sync_namemap(json_data)

    def test_adds_missing_text_property_data(self):
        """Test syncs TextPropertyData TableId and Value FNames."""
        json_data = {
            "NameMap": ["ExistingName"],
            "Exports": [{
                "Data": [{
                    "$type": "UAssetAPI.PropertyTypes.Objects.TextPropertyData, UAssetAPI",
                    "Name": "DisplayName",
                    "HistoryType": "StringTableEntry",
                    "TableId": "/Game/Mods/Tech/Data/StringTables/ST_Mod_Items.ST_Mod_Items",
                    "Value": "Armor.BearGuild.Gloves.Name"
                }]
            }]
        }
        BuildManager._sync_namemap(json_data)
        nm = json_data["NameMap"]
        assert "DisplayName" in nm
        assert "/Game/Mods/Tech/Data/StringTables/ST_Mod_Items.ST_Mod_Items" in nm
        assert "Armor.BearGuild.Gloves.Name" in nm


class TestCleanBuildDirectories:
    """Tests for _clean_build_directories method."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BuildManager()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.build_manager.get_default_mymodfiles_dir')
    def test_cleans_existing_dirs(self, mock_mymodfiles):
        """Test cleaning existing build directories."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        mod_dir = Path(self.temp_dir) / 'TestMod'

        # Create build directories
        (mod_dir / 'jsonfiles').mkdir(parents=True)
        (mod_dir / 'jsonfiles' / 'test.json').write_text('{}', encoding='utf-8')
        (mod_dir / 'uasset').mkdir(parents=True)
        (mod_dir / 'finalmod').mkdir(parents=True)

        self.manager._clean_build_directories('TestMod')

        assert not (mod_dir / 'jsonfiles').exists()
        assert not (mod_dir / 'uasset').exists()
        assert not (mod_dir / 'finalmod').exists()

    @patch('src.build_manager.get_default_mymodfiles_dir')
    def test_cleans_nonexistent_dirs(self, mock_mymodfiles):
        """Test cleaning when directories don't exist."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        # Should not raise
        self.manager._clean_build_directories('TestMod')


class TestCreateZip:
    """Tests for _create_zip method."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.manager = BuildManager()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        # Clean up any created zip
        zip_path = Path.home() / 'Downloads' / 'ZipTestMod.zip'
        if zip_path.exists():
            zip_path.unlink()

    @patch('src.build_manager.get_default_mymodfiles_dir')
    def test_create_zip_success(self, mock_mymodfiles):
        """Test creating a zip file successfully."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        mod_dir = Path(self.temp_dir) / 'ZipTestMod' / 'finalmod' / 'ZipTestMod_P'
        mod_dir.mkdir(parents=True)
        (mod_dir / 'test.utoc').write_text('data', encoding='utf-8')
        (mod_dir / 'test.ucas').write_text('data', encoding='utf-8')

        result = self.manager._create_zip('ZipTestMod')
        assert result is not None
        assert result.exists()
        assert result.suffix == '.zip'

        # Verify contents
        with zipfile.ZipFile(result, 'r') as zf:
            names = zf.namelist()
            assert any('test.utoc' in n for n in names)
            assert any('test.ucas' in n for n in names)

    @patch('src.build_manager.get_default_mymodfiles_dir')
    def test_create_zip_missing_dir(self, mock_mymodfiles):
        """Test creating zip when mod_P directory doesn't exist."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        result = self.manager._create_zip('NonExistentMod')
        assert result is None
