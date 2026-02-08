"""Main entry point for Moria MOD Creator."""

import logging
import customtkinter as ctk

from src.config import config_exists, get_color_scheme, apply_color_scheme
from src.ui.config_dialog import show_config_dialog
from src.ui.main_window import MainWindow

# Configure logging - only for our application
logging.basicConfig(
    level=logging.WARNING,  # Set root logger to WARNING to suppress library debug messages
    format='[%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Our logger stays at DEBUG

logger.info("Imports completed")


def main():
    """Main application entry point."""
    logger.info("main() called")

    # Set default color theme
    logger.debug("Setting color theme...")
    ctk.set_default_color_theme("blue")

    # Apply color scheme from config or default to system
    config_found = config_exists()
    logger.debug("Config exists: %s", config_found)
    if config_found:
        apply_color_scheme(get_color_scheme())
    else:
        ctk.set_appearance_mode("system")

    # Check if first run (no config exists)
    if not config_found:
        logger.info("First run - showing config dialog")
        # Create a temporary root for the config dialog
        temp_root = ctk.CTk()
        temp_root.withdraw()

        # Show configuration dialog
        if not show_config_dialog(temp_root):
            # User cancelled - exit application
            logger.info("User cancelled config dialog - exiting")
            temp_root.destroy()
            return

        # Apply the newly saved color scheme
        apply_color_scheme(get_color_scheme())
        temp_root.destroy()

    # Create and show the main window
    logger.debug("Creating MainWindow...")
    app = MainWindow()
    logger.debug("MainWindow created")

    # Run the application
    logger.info("Starting mainloop...")
    app.mainloop()
    logger.info("mainloop ended")


if __name__ == "__main__":
    main()
