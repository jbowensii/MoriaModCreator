"""Unit tests for the definition manager."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil
import configparser

from src.definition_manager import DefinitionManager
from src.constants import CHECKBOX_STATES_FILE, CHECKBOX_STATES_SECTION


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


class TestCheckboxStatePersistence:
    """Tests for loading and saving checkbox states to INI."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_get_checkbox_ini_path_with_mod(self, mock_mymodfiles):
        """Test getting checkbox INI path with mod name."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        manager = DefinitionManager(mod_name="TestMod")
        
        ini_path = manager.get_checkbox_ini_path()
        assert ini_path.parent.name == "TestMod"
        assert ini_path.name == CHECKBOX_STATES_FILE

    def test_get_checkbox_ini_path_without_mod(self):
        """Test getting checkbox INI path without mod name."""
        manager = DefinitionManager()
        
        ini_path = manager.get_checkbox_ini_path()
        assert ini_path == Path()

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_load_checkbox_states_from_file(self, mock_mymodfiles):
        """Test loading checkbox states from existing file."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        
        # Create mod directory and INI file
        mod_dir = Path(self.temp_dir) / "TestMod"
        mod_dir.mkdir(parents=True)
        ini_file = mod_dir / CHECKBOX_STATES_FILE
        ini_file.write_text(f'''[{CHECKBOX_STATES_SECTION}]
C~|Test|Path|file.def = true
''')
        
        manager = DefinitionManager(mod_name="TestMod")
        
        # Path should be reconstructed with : and \
        assert manager.get_saved_state(Path("C:\\Test\\Path\\file.def")) is True

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_save_checkbox_states_to_file(self, mock_mymodfiles):
        """Test saving checkbox states to file."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        
        # Create mod directory
        mod_dir = Path(self.temp_dir) / "TestMod"
        mod_dir.mkdir(parents=True)
        
        manager = DefinitionManager(mod_name="TestMod")
        manager.set_state(Path("C:\\Test\\Path\\file.def"), True)
        manager.save_checkbox_states()
        
        ini_file = mod_dir / CHECKBOX_STATES_FILE
        assert ini_file.exists()
        
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(ini_file)
        assert CHECKBOX_STATES_SECTION in config

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_save_checkbox_states_with_ui_states(self, mock_mymodfiles):
        """Test saving checkbox states with UI states merged."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        
        # Create mod directory
        mod_dir = Path(self.temp_dir) / "TestMod"
        mod_dir.mkdir(parents=True)
        
        manager = DefinitionManager(mod_name="TestMod")
        
        ui_states = {
            Path("C:\\Test\\file1.def"): True,
            Path("C:\\Test\\file2.def"): False
        }
        manager.save_checkbox_states(ui_states)
        
        assert manager.get_saved_state(Path("C:\\Test\\file1.def")) is True
        assert manager.get_saved_state(Path("C:\\Test\\file2.def")) is False

    def test_load_checkbox_states_no_mod_name(self):
        """Test loading states without mod name does nothing."""
        manager = DefinitionManager()
        manager.load_checkbox_states()
        assert manager._checkbox_states == {}

    def test_save_checkbox_states_no_mod_name(self):
        """Test saving states without mod name does nothing."""
        manager = DefinitionManager()
        manager._checkbox_states["test"] = True
        manager.save_checkbox_states()  # Should not raise


class TestModNameProperty:
    """Tests for mod_name property setter."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.definition_manager.get_default_mymodfiles_dir')
    def test_set_mod_name_loads_states(self, mock_mymodfiles):
        """Test setting mod_name loads checkbox states."""
        mock_mymodfiles.return_value = Path(self.temp_dir)
        
        # Create mod directory with states file
        mod_dir = Path(self.temp_dir) / "NewMod"
        mod_dir.mkdir(parents=True)
        ini_file = mod_dir / CHECKBOX_STATES_FILE
        ini_file.write_text(f'''[{CHECKBOX_STATES_SECTION}]
C~|Path|file.def = true
''')
        
        manager = DefinitionManager()
        assert manager.mod_name is None
        
        manager.mod_name = "NewMod"
        assert manager.mod_name == "NewMod"
        # States should be loaded
        assert manager.get_saved_state(Path("C:\\Path\\file.def")) is True

    def test_set_mod_name_none_clears_states(self):
        """Test setting mod_name to None clears states."""
        manager = DefinitionManager()
        manager._checkbox_states["test"] = True
        
        manager.mod_name = None
        assert manager._checkbox_states == {}


class TestParseDefinitionExtended:
    """Extended tests for parse_definition."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_definition_with_multiple_changes(self):
        """Test parsing definition with multiple changes."""
        def_file = Path(self.temp_dir) / "multi.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>Multi-change mod</description>
    <author>Tester</author>
    <mod file="\\Moria\\Content\\Test.json">
        <change item="Item1" property="Prop1" value="100" />
        <change item="Item2" property="Prop2" value="200" />
        <change item="Item3" property="Prop3" value="300" />
    </mod>
</definition>''')
        
        result = DefinitionManager.parse_definition(def_file)
        
        assert result is not None
        assert len(result['changes']) == 3
        assert result['changes'][0]['item'] == 'Item1'
        assert result['changes'][1]['item'] == 'Item2'
        assert result['changes'][2]['item'] == 'Item3'

    def test_parse_definition_missing_change_attributes(self):
        """Test parsing definition with missing change attributes."""
        def_file = Path(self.temp_dir) / "partial.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <mod file="\\Test.json">
        <change item="OnlyItem" />
    </mod>
</definition>''')
        
        result = DefinitionManager.parse_definition(def_file)
        
        assert result is not None
        assert len(result['changes']) == 1
        assert result['changes'][0]['item'] == 'OnlyItem'
        assert result['changes'][0]['property'] == ''
        assert result['changes'][0]['value'] == ''

    def test_parse_definition_no_mod_element(self):
        """Test parsing definition without mod element."""
        def_file = Path(self.temp_dir) / "nomod.def"
        def_file.write_text('''<?xml version="1.0" encoding="utf-8"?>
<definition>
    <description>No mod element</description>
</definition>''')
        
        result = DefinitionManager.parse_definition(def_file)
        
        assert result is not None
        assert result['mod_file'] == ''
        assert result['changes'] == []
