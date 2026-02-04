"""Unit tests for the configuration module."""

from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil
import configparser

from src.config import (
    validate_config,
    is_config_valid,
    get_appdata_dir,
    get_default_utilities_dir,
    get_default_output_dir,
    get_default_mymodfiles_dir,
    get_default_definitions_dir,
    get_buildings_dir,
    get_constructions_dir,
    get_config_path,
    config_exists,
    load_config,
    save_config,
    get_game_install_path,
    get_utilities_dir,
    get_output_dir,
    get_mymodfiles_dir,
    get_definitions_dir,
    get_color_scheme,
    get_max_workers,
    get_constructions_json_dir,
    set_constructions_json_dir,
    check_steam_path,
    check_epic_path,
    get_available_install_options,
    COLOR_SCHEMES,
    DEFAULT_COLOR_SCHEME,
    _cache,
)


class TestConfigValidation:
    """Tests for configuration validation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.config.get_utilities_dir')
    @patch('src.config.get_output_dir')
    @patch('src.config.get_default_mymodfiles_dir')
    @patch('src.config.get_definitions_dir')
    @patch('src.config.get_game_install_path')
    def test_validate_all_missing(
        self,
        mock_game,
        mock_definitions,
        mock_mymodfiles,
        mock_output,
        mock_utilities
    ):
        """Test validation when utilities directory is missing."""
        missing_dir = Path(self.temp_dir) / 'nonexistent'
        mock_utilities.return_value = missing_dir
        mock_output.return_value = Path(self.temp_dir) / 'output'
        mock_mymodfiles.return_value = Path(self.temp_dir) / 'mymodfiles'
        mock_definitions.return_value = Path(self.temp_dir) / 'definitions'
        mock_game.return_value = None
        
        issues = validate_config()
        assert any('Utilities directory not found' in issue for issue in issues)

    @patch('src.config.get_utilities_dir')
    @patch('src.config.get_output_dir')
    @patch('src.config.get_default_mymodfiles_dir')
    @patch('src.config.get_definitions_dir')
    @patch('src.config.get_game_install_path')
    def test_validate_missing_utilities(
        self,
        mock_game,
        mock_definitions,
        mock_mymodfiles,
        mock_output,
        mock_utilities
    ):
        """Test validation when required utilities are missing."""
        utilities_dir = Path(self.temp_dir) / 'utilities'
        utilities_dir.mkdir(parents=True)
        
        mock_utilities.return_value = utilities_dir
        mock_output.return_value = Path(self.temp_dir) / 'output'
        mock_mymodfiles.return_value = Path(self.temp_dir) / 'mymodfiles'
        mock_definitions.return_value = Path(self.temp_dir) / 'definitions'
        mock_game.return_value = None
        
        issues = validate_config()
        assert any('UAssetGUI.exe' in issue for issue in issues)
        assert any('retoc.exe' in issue for issue in issues)

    @patch('src.config.get_utilities_dir')
    @patch('src.config.get_output_dir')
    @patch('src.config.get_default_mymodfiles_dir')
    @patch('src.config.get_definitions_dir')
    @patch('src.config.get_game_install_path')
    def test_validate_all_valid(
        self,
        mock_game,
        mock_definitions,
        mock_mymodfiles,
        mock_output,
        mock_utilities
    ):
        """Test validation when everything is valid."""
        utilities_dir = Path(self.temp_dir) / 'utilities'
        utilities_dir.mkdir(parents=True)
        (utilities_dir / 'UAssetGUI.exe').touch()
        (utilities_dir / 'retoc.exe').touch()
        
        mock_utilities.return_value = utilities_dir
        mock_output.return_value = Path(self.temp_dir) / 'output'
        mock_mymodfiles.return_value = Path(self.temp_dir) / 'mymodfiles'
        mock_definitions.return_value = Path(self.temp_dir) / 'definitions'
        mock_game.return_value = None
        
        issues = validate_config()
        assert len(issues) == 0

    @patch('src.config.get_utilities_dir')
    @patch('src.config.get_output_dir')
    @patch('src.config.get_default_mymodfiles_dir')
    @patch('src.config.get_definitions_dir')
    @patch('src.config.get_game_install_path')
    def test_validate_invalid_game_path(
        self,
        mock_game,
        mock_definitions,
        mock_mymodfiles,
        mock_output,
        mock_utilities
    ):
        """Test validation when game path doesn't exist."""
        utilities_dir = Path(self.temp_dir) / 'utilities'
        utilities_dir.mkdir(parents=True)
        (utilities_dir / 'UAssetGUI.exe').touch()
        (utilities_dir / 'retoc.exe').touch()
        
        mock_utilities.return_value = utilities_dir
        mock_output.return_value = Path(self.temp_dir) / 'output'
        mock_mymodfiles.return_value = Path(self.temp_dir) / 'mymodfiles'
        mock_definitions.return_value = Path(self.temp_dir) / 'definitions'
        mock_game.return_value = "C:\\NonExistent\\Game\\Path"
        
        issues = validate_config()
        assert any('Game installation path not found' in issue for issue in issues)


class TestIsConfigValid:
    """Tests for is_config_valid function."""

    @patch('src.config.validate_config')
    def test_is_valid_true(self, mock_validate):
        """Test is_config_valid returns True when no issues."""
        mock_validate.return_value = []
        assert is_config_valid() is True

    @patch('src.config.validate_config')
    def test_is_valid_false(self, mock_validate):
        """Test is_config_valid returns False when issues exist."""
        mock_validate.return_value = ["Some issue"]
        assert is_config_valid() is False


class TestDirectoryPaths:
    """Tests for directory path functions."""

    def test_get_appdata_dir(self):
        """Test that appdata directory is created."""
        result = get_appdata_dir()
        assert result.exists()
        assert 'MoriaMODCreator' in str(result)

    def test_get_default_utilities_dir(self):
        """Test default utilities directory path."""
        result = get_default_utilities_dir()
        assert 'utilities' in str(result)

    def test_get_default_output_dir(self):
        """Test default output directory path."""
        result = get_default_output_dir()
        assert 'output' in str(result)

    def test_get_default_mymodfiles_dir(self):
        """Test default mymodfiles directory path."""
        result = get_default_mymodfiles_dir()
        assert 'mymodfiles' in str(result)

    def test_get_default_definitions_dir(self):
        """Test default definitions directory path."""
        result = get_default_definitions_dir()
        assert 'definitions' in str(result)

    def test_get_buildings_dir(self):
        """Test buildings directory is created."""
        result = get_buildings_dir()
        assert result.exists()
        assert 'Build' in str(result)

    def test_get_constructions_dir(self):
        """Test constructions directory is created."""
        result = get_constructions_dir()
        assert result.exists()
        assert 'Constructions' in str(result)

    def test_get_config_path(self):
        """Test config path returns correct filename."""
        result = get_config_path()
        assert result.name == 'config.ini'


class TestConfigConstants:
    """Tests for configuration constants."""

    def test_color_schemes_list(self):
        """Test color schemes list contains expected values."""
        assert "Match Windows Theme" in COLOR_SCHEMES
        assert "Light Mode" in COLOR_SCHEMES
        assert "Dark Mode" in COLOR_SCHEMES

    def test_default_color_scheme(self):
        """Test default color scheme is valid."""
        assert DEFAULT_COLOR_SCHEME in COLOR_SCHEMES


class TestLoadConfig:
    """Tests for load_config function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        # Clear cache before each test
        _cache.config = None
        _cache.mtime = None

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        # Clear cache after each test
        _cache.config = None
        _cache.mtime = None

    @patch('src.config.get_config_path')
    def test_load_config_nonexistent(self, mock_path):
        """Test loading config when file doesn't exist."""
        mock_path.return_value = Path(self.temp_dir) / 'nonexistent.ini'
        config = load_config()
        assert isinstance(config, configparser.ConfigParser)
        assert len(config.sections()) == 0

    @patch('src.config.get_config_path')
    def test_load_config_existing(self, mock_path):
        """Test loading config from existing file."""
        config_file = Path(self.temp_dir) / 'config.ini'
        config_file.write_text('''[Game]
install_path = C:\\Test\\Path
install_type = Steam
''')
        mock_path.return_value = config_file
        
        config = load_config()
        assert config.has_section('Game')
        assert config.get('Game', 'install_path') == 'C:\\Test\\Path'

    @patch('src.config.get_config_path')
    def test_load_config_caching(self, mock_path):
        """Test config caching works."""
        config_file = Path(self.temp_dir) / 'config.ini'
        config_file.write_text('''[Game]
install_path = C:\\Test\\Path
''')
        mock_path.return_value = config_file
        
        # First load
        config1 = load_config()
        # Second load should return cached
        config2 = load_config()
        assert config1 is config2


class TestSaveConfig:
    """Tests for save_config function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        _cache.config = None
        _cache.mtime = None

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        _cache.config = None
        _cache.mtime = None

    @patch('src.config.get_config_path')
    @patch('src.config.get_constructions_dir')
    def test_save_config_creates_file(self, mock_constructions, mock_path):
        """Test save_config creates config file."""
        config_file = Path(self.temp_dir) / 'config.ini'
        mock_path.return_value = config_file
        mock_constructions.return_value = Path(self.temp_dir) / 'constructions'
        
        save_config(
            game_install_path='C:\\Game\\Path',
            install_type='Steam',
            utilities_dir=str(Path(self.temp_dir) / 'utilities'),
            output_dir=str(Path(self.temp_dir) / 'output'),
            mymodfiles_dir=str(Path(self.temp_dir) / 'mymodfiles'),
            definitions_dir=str(Path(self.temp_dir) / 'definitions'),
            color_scheme='Dark Mode',
            max_workers=4
        )
        
        assert config_file.exists()
        config = configparser.ConfigParser()
        config.read(config_file)
        assert config.get('Game', 'install_path') == 'C:\\Game\\Path'
        assert config.get('Performance', 'max_workers') == '4'


class TestGetConfigValues:
    """Tests for config getter functions."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        _cache.config = None
        _cache.mtime = None

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        _cache.config = None
        _cache.mtime = None

    @patch('src.config.load_config')
    def test_get_game_install_path_configured(self, mock_load):
        """Test getting game path when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Game\\Path'
        mock_load.return_value = mock_config
        
        result = get_game_install_path()
        assert result == 'C:\\Game\\Path'

    @patch('src.config.load_config')
    def test_get_game_install_path_not_configured(self, mock_load):
        """Test getting game path when not configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        
        result = get_game_install_path()
        assert result is None

    @patch('src.config.load_config')
    def test_get_color_scheme_configured(self, mock_load):
        """Test getting color scheme when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'Dark Mode'
        mock_load.return_value = mock_config
        
        result = get_color_scheme()
        assert result == 'Dark Mode'

    @patch('src.config.load_config')
    def test_get_color_scheme_default(self, mock_load):
        """Test getting color scheme uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        
        result = get_color_scheme()
        assert result == DEFAULT_COLOR_SCHEME

    @patch('src.config.load_config')
    def test_get_max_workers_configured(self, mock_load):
        """Test getting max_workers when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = '5'
        mock_load.return_value = mock_config
        
        result = get_max_workers()
        assert result == 5

    @patch('src.config.load_config')
    def test_get_max_workers_invalid(self, mock_load):
        """Test getting max_workers with invalid value returns default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'invalid'
        mock_load.return_value = mock_config
        
        result = get_max_workers()
        assert result == 1

    @patch('src.config.load_config')
    def test_get_max_workers_default(self, mock_load):
        """Test getting max_workers uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        
        result = get_max_workers()
        assert result == 1

    @patch('src.config.load_config')
    def test_get_constructions_json_dir_configured(self, mock_load):
        """Test getting constructions JSON dir when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Path\\To\\Json'
        mock_load.return_value = mock_config
        
        result = get_constructions_json_dir()
        assert result == Path('C:\\Path\\To\\Json')

    @patch('src.config.load_config')
    def test_get_constructions_json_dir_not_configured(self, mock_load):
        """Test getting constructions JSON dir when not configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        
        result = get_constructions_json_dir()
        assert result is None


class TestSetConstructionsJsonDir:
    """Tests for set_constructions_json_dir function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        _cache.config = None
        _cache.mtime = None

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        _cache.config = None
        _cache.mtime = None

    @patch('src.config.get_config_path')
    @patch('src.config.load_config')
    def test_set_constructions_json_dir(self, mock_load, mock_path):
        """Test setting constructions JSON directory."""
        config_file = Path(self.temp_dir) / 'config.ini'
        mock_path.return_value = config_file
        
        mock_config = configparser.ConfigParser()
        mock_load.return_value = mock_config
        
        set_constructions_json_dir('C:\\New\\Path')
        
        assert config_file.exists()


class TestInstallPaths:
    """Tests for installation path detection."""

    @patch('src.config.Path')
    def test_check_steam_path_exists(self, mock_path):
        """Test Steam path check when exists."""
        mock_path.return_value.exists.return_value = True
        # Can't directly test since it uses module-level constant
        # Just verify function runs without error
        result = check_steam_path()
        assert isinstance(result, bool)

    @patch('src.config.Path')
    def test_check_epic_path_exists(self, mock_path):
        """Test Epic path check when exists."""
        mock_path.return_value.exists.return_value = True
        result = check_epic_path()
        assert isinstance(result, bool)

    def test_get_available_install_options_always_has_custom(self):
        """Test Custom is always available as install option."""
        options = get_available_install_options()
        assert len(options) >= 1
        assert options[-1][0] == "Custom"
        assert options[-1][1] == ""


class TestConfigExists:
    """Tests for config_exists function."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @patch('src.config.get_config_path')
    def test_config_exists_true(self, mock_path):
        """Test config_exists returns True when file exists."""
        config_file = Path(self.temp_dir) / 'config.ini'
        config_file.touch()
        mock_path.return_value = config_file
        
        assert config_exists() is True

    @patch('src.config.get_config_path')
    def test_config_exists_false(self, mock_path):
        """Test config_exists returns False when file doesn't exist."""
        mock_path.return_value = Path(self.temp_dir) / 'nonexistent.ini'
        
        assert config_exists() is False


class TestDirectoryGetters:
    """Tests for directory getter functions that use config."""

    def setup_method(self):
        """Set up test fixtures."""
        _cache.config = None
        _cache.mtime = None

    def teardown_method(self):
        """Clean up test fixtures."""
        _cache.config = None
        _cache.mtime = None

    @patch('src.config.load_config')
    def test_get_utilities_dir_configured(self, mock_load):
        """Test getting utilities dir when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Custom\\Utilities'
        mock_load.return_value = mock_config
        
        result = get_utilities_dir()
        assert result == Path('C:\\Custom\\Utilities')

    @patch('src.config.load_config')
    @patch('src.config.get_default_utilities_dir')
    def test_get_utilities_dir_default(self, mock_default, mock_load):
        """Test getting utilities dir uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        mock_default.return_value = Path('C:\\Default\\Utilities')
        
        result = get_utilities_dir()
        assert result == Path('C:\\Default\\Utilities')

    @patch('src.config.load_config')
    def test_get_output_dir_configured(self, mock_load):
        """Test getting output dir when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Custom\\Output'
        mock_load.return_value = mock_config
        
        result = get_output_dir()
        assert result == Path('C:\\Custom\\Output')

    @patch('src.config.load_config')
    @patch('src.config.get_default_output_dir')
    def test_get_output_dir_default(self, mock_default, mock_load):
        """Test getting output dir uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        mock_default.return_value = Path('C:\\Default\\Output')
        
        result = get_output_dir()
        assert result == Path('C:\\Default\\Output')

    @patch('src.config.load_config')
    def test_get_mymodfiles_dir_configured(self, mock_load):
        """Test getting mymodfiles dir when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Custom\\MyModFiles'
        mock_load.return_value = mock_config
        
        result = get_mymodfiles_dir()
        assert result == Path('C:\\Custom\\MyModFiles')

    @patch('src.config.load_config')
    @patch('src.config.get_default_mymodfiles_dir')
    def test_get_mymodfiles_dir_default(self, mock_default, mock_load):
        """Test getting mymodfiles dir uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        mock_default.return_value = Path('C:\\Default\\MyModFiles')
        
        result = get_mymodfiles_dir()
        assert result == Path('C:\\Default\\MyModFiles')

    @patch('src.config.load_config')
    def test_get_definitions_dir_configured(self, mock_load):
        """Test getting definitions dir when configured."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = True
        mock_config.get.return_value = 'C:\\Custom\\Definitions'
        mock_load.return_value = mock_config
        
        result = get_definitions_dir()
        assert result == Path('C:\\Custom\\Definitions')

    @patch('src.config.load_config')
    @patch('src.config.get_default_definitions_dir')
    def test_get_definitions_dir_default(self, mock_default, mock_load):
        """Test getting definitions dir uses default."""
        mock_config = MagicMock()
        mock_config.has_option.return_value = False
        mock_load.return_value = mock_config
        mock_default.return_value = Path('C:\\Default\\Definitions')
        
        result = get_definitions_dir()
        assert result == Path('C:\\Default\\Definitions')
