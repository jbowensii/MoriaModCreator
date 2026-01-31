"""Unit tests for the build manager."""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
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
</definition>''')
        
        success, message = self.manager.build("TestMod", [def_file])
        assert success is False
