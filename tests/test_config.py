"""Unit tests for the configuration module."""

from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil

from src.config import (
    validate_config,
    is_config_valid,
    get_appdata_dir,
    get_default_utilities_dir,
    get_default_output_dir,
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
