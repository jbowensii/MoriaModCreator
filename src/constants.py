"""Constants used throughout Moria MOD Creator."""

# Application info
APP_NAME = "Moria MOD Creator"
APP_VERSION = "0.3"

# Unreal Engine versions
UE_VERSION = "VER_UE4_27"  # For UAssetGUI
RETOC_UE_VERSION = "UE4_27"  # For retoc

# File extensions
DEF_FILE_EXTENSION = ".def"
JSON_FILE_EXTENSION = ".json"
UASSET_FILE_EXTENSION = ".uasset"

# Directory names
JSONFILES_DIR = "jsonfiles"
UASSET_DIR = "uasset"
FINALMOD_DIR = "finalmod"
JSONDATA_DIR = "jsondata"

# Utility executables
UASSETGUI_EXE = "UAssetGUI.exe"
RETOC_EXE = "retoc.exe"
FMODEL_EXE = "FModel.exe"

# Icon sizes
TOOLBAR_ICON_SIZE = (32, 32)
TITLE_ICON_SIZE = (40, 40)

# Checkbox states
CHECKBOX_STATE_NONE = "none"
CHECKBOX_STATE_MIXED = "mixed"
CHECKBOX_STATE_ALL = "all"

# UI Colors
COLOR_CHECKBOX_DEFAULT = "#1f6aa5"  # Blue - default checkbox color
COLOR_CHECKBOX_MIXED = "#FFA500"    # Orange - mixed/partial state
COLOR_STATUS_TEXT = "#FFA500"       # Orange - status bar text
COLOR_SAVE_BUTTON = "#28a745"       # Green - save button
COLOR_SAVE_BUTTON_HOVER = "#218838" # Dark green - save button hover

# INI file settings
CHECKBOX_STATES_FILE = "checkbox_states.ini"
CHECKBOX_STATES_SECTION = "Paths"

# Build timeout (seconds)
BUILD_TIMEOUT = 60
