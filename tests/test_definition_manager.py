"""Unit tests for the definition manager."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from src.definition_manager import DefinitionManager


class TestDefinitionManager:
    """Tests for DefinitionManager class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_without_mod_name(self):
        """Test initialization without mod name."""
        manager = DefinitionManager()
        assert manager.mod_name is None
        assert manager._checkbox_states == {}

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_init_with_mod_name(self, mock_mymodfiles):
        """Test initialization with mod name."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        manager = DefinitionManager(mod_name="TestMod")
        assert manager.mod_name == "TestMod"

    def test_get_saved_state_empty(self):
        """Test getting saved state when empty."""
        manager = DefinitionManager()
        result = manager.get_saved_state(Path("test/path.def"))
        assert result is False

    def test_set_and_get_state(self):
        """Test setting and getting state."""
        manager = DefinitionManager()
        test_path = Path("C:/test/path.def")
        
        manager.set_state(test_path, True)
        assert manager.get_saved_state(test_path) is True
        
        manager.set_state(test_path, False)
        assert manager.get_saved_state(test_path) is False

    def test_get_saved_state_case_insensitive(self):
        """Test case-insensitive path matching."""
        manager = DefinitionManager()
        manager._checkbox_states["C:\\Test\\Path.def"] = True
        
        # Should match with different case
        result = manager.get_saved_state(Path("c:\\test\\path.def"))
        assert result is True


class TestParseDefinition:
    """Tests for parse_definition static method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_valid_definition(self):
        """Test parsing a valid definition file."""
        def_file = Path(self.temp_dir) / "test.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>Test Description</description>
    <author>Test Author</author>
    <mod file="\\Moria\\Content\\Test.json">
        <change item="TestItem" property="TestProp" value="100" />
    </mod>
</definition>''')
        
        result = DefinitionManager.parse_definition(def_file)
        
        assert result is not None
        assert result['description'] == "Test Description"
        assert result['author'] == "Test Author"
        assert result['mod_file'] == "\\Moria\\Content\\Test.json"
        assert len(result['changes']) == 1
        assert result['changes'][0]['item'] == "TestItem"
        assert result['changes'][0]['property'] == "TestProp"
        assert result['changes'][0]['value'] == "100"

    def test_parse_minimal_definition(self):
        """Test parsing a minimal definition file."""
        def_file = Path(self.temp_dir) / "minimal.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <mod file="\\Test.json">
    </mod>
</definition>''')
        
        result = DefinitionManager.parse_definition(def_file)
        
        assert result is not None
        assert result['description'] == ""
        assert result['author'] == ""
        assert result['mod_file'] == "\\Test.json"
        assert len(result['changes']) == 0

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML."""
        def_file = Path(self.temp_dir) / "invalid.def"
        def_file.write_text("not valid xml <><><")
        
        result = DefinitionManager.parse_definition(def_file)
        assert result is None

    def test_parse_nonexistent_file(self):
        """Test parsing a non-existent file."""
        result = DefinitionManager.parse_definition(Path("/nonexistent/file.def"))
        assert result is None


class TestGetDescription:
    """Tests for get_description static method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_description_found(self):
        """Test getting description when present."""
        def_file = Path(self.temp_dir) / "test.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>My Test Description</description>
</definition>''')
        
        result = DefinitionManager.get_description(def_file)
        assert result == "My Test Description"

    def test_get_description_empty(self):
        """Test getting description when empty."""
        def_file = Path(self.temp_dir) / "test.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
</definition>''')
        
        result = DefinitionManager.get_description(def_file)
        assert result == ""

    def test_get_description_invalid_file(self):
        """Test getting description from invalid file."""
        result = DefinitionManager.get_description(Path("/nonexistent.def"))
        assert result == ""


class TestGetAuthor:
    """Tests for get_author static method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_author_found(self):
        """Test getting author when present."""
        def_file = Path(self.temp_dir) / "test.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <author>John Doe</author>
</definition>''')
        
        result = DefinitionManager.get_author(def_file)
        assert result == "John Doe"

    def test_get_author_empty(self):
        """Test getting author when empty."""
        def_file = Path(self.temp_dir) / "test.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
</definition>''')
        
        result = DefinitionManager.get_author(def_file)
        assert result == ""


class TestGetAllSelectedDefinitions:
    """Tests for get_all_selected_definitions method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_selected_empty(self):
        """Test getting selected definitions when empty."""
        manager = DefinitionManager()
        result = manager.get_all_selected_definitions()
        assert result == []

    def test_get_selected_with_files(self):
        """Test getting selected definitions with files."""
        manager = DefinitionManager()
        
        # Create test files
        def_file1 = Path(self.temp_dir) / "test1.def"
        def_file2 = Path(self.temp_dir) / "test2.def"
        def_file1.touch()
        def_file2.touch()
        
        manager.set_state(def_file1, True)
        manager.set_state(def_file2, False)
        
        result = manager.get_all_selected_definitions()
        assert len(result) == 1
        assert def_file1 in result

    def test_get_selected_ignores_directories(self):
        """Test that directories are ignored."""
        manager = DefinitionManager()
        
        # Create test directory
        test_dir = Path(self.temp_dir) / "subdir"
        test_dir.mkdir()
        
        manager._checkbox_states[str(test_dir)] = True
        
        result = manager.get_all_selected_definitions()
        assert result == []

    def test_get_selected_ignores_nonexistent(self):
        """Test that non-existent files are ignored."""
        manager = DefinitionManager()
        manager._checkbox_states["/nonexistent/file.def"] = True
        
        result = manager.get_all_selected_definitions()
        assert result == []
