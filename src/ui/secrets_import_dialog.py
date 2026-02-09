"""Secrets import dialog for importing building mods."""

import logging
import shutil
import threading
import queue
import zipfile
import urllib.request
import urllib.error
from pathlib import Path

import customtkinter as ctk

from src.config import get_appdata_dir


logger = logging.getLogger(__name__)

# Secrets source directory name
SECRETS_SOURCE_DIR = "Secrets Source"


def get_secrets_source_dir() -> Path:
    """Get the Secrets Source directory."""
    return get_appdata_dir() / SECRETS_SOURCE_DIR


# GitHub repository URL for RtoM-ArmorBuildings-Mod
GITHUB_REPO_URL = "https://github.com/TobiIchiro/RtoM-ArmorBuildings-Mod/tree/NoFatStacks"
GITHUB_ZIP_URL = "https://github.com/TobiIchiro/RtoM-ArmorBuildings-Mod/archive/refs/heads/NoFatStacks.zip"
GITHUB_ZIP_FILENAME = "RtoM-ArmorBuildings-Mod.zip"


def get_jsondata_dir() -> Path:
    """Get the jsondata directory for extracted mod data."""
    return get_secrets_source_dir() / "jsondata"


def download_github_repo(secrets_dir: Path, progress_callback=None) -> tuple[bool, str]:
    """Download the RtoM-ArmorBuildings-Mod repository as a ZIP file.

    Args:
        secrets_dir: The Secrets Source directory to save the ZIP to
        progress_callback: Optional callback for progress updates

    Returns:
        Tuple of (success, message)
    """
    secrets_dir.mkdir(parents=True, exist_ok=True)
    zip_path = secrets_dir / GITHUB_ZIP_FILENAME

    # Remove old ZIP file if it exists
    if zip_path.exists():
        try:
            zip_path.unlink()
            logger.info("Removed old %s", GITHUB_ZIP_FILENAME)
        except OSError as e:
            logger.warning("Could not remove old ZIP file: %s", e)

    try:
        if progress_callback:
            progress_callback(f"Downloading from {GITHUB_REPO_URL}...")

        # Create a request with a user agent (GitHub may block requests without one)
        request = urllib.request.Request(
            GITHUB_ZIP_URL,
            headers={'User-Agent': 'MoriaMODCreator/1.0'}
        )

        with urllib.request.urlopen(request, timeout=60) as response:
            # Read and save the ZIP file
            data = response.read()
            zip_path.write_bytes(data)

        file_size = zip_path.stat().st_size / 1024  # KB
        logger.info("Downloaded %s (%s KB)", GITHUB_ZIP_FILENAME, f"{file_size:.1f}")
        return (True, f"Downloaded {GITHUB_ZIP_FILENAME} ({file_size:.1f} KB)")

    except urllib.error.HTTPError as e:
        # Try main branch as fallback
        if e.code == 404:
            try:
                fallback_url = "https://github.com/TobiIchiro/RtoM-ArmorBuildings-Mod/archive/refs/heads/main.zip"
                request = urllib.request.Request(
                    fallback_url,
                    headers={'User-Agent': 'MoriaMODCreator/1.0'}
                )
                with urllib.request.urlopen(request, timeout=60) as response:
                    data = response.read()
                    zip_path.write_bytes(data)

                file_size = zip_path.stat().st_size / 1024
                logger.info("Downloaded %s from main branch (%s KB)", GITHUB_ZIP_FILENAME, f"{file_size:.1f}")
                return (True, f"Downloaded {GITHUB_ZIP_FILENAME} ({file_size:.1f} KB)")
            except (urllib.error.URLError, OSError) as e2:
                logger.error("Failed to download from main branch: %s", e2)
                return (False, f"Download failed: {str(e2)}")
        else:
            logger.error("HTTP error downloading repo: %s", e)
            return (False, f"HTTP error {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        logger.error("URL error downloading repo: %s", e)
        return (False, f"Connection error: {str(e.reason)}")
    except OSError as e:
        logger.error("Error downloading repo: %s", e)
        return (False, f"Download error: {str(e)}")


def extract_moria_from_github_zip(secrets_dir: Path) -> tuple[bool, str, int]:
    """Extract the Moria directory from the GitHub ZIP to jsondata.

    Looks for modified-json/Moria inside the ZIP and extracts it
    to the jsondata directory, preserving the Moria directory structure.

    Args:
        secrets_dir: The Secrets Source directory containing the ZIP

    Returns:
        Tuple of (success, message, files_extracted)
    """
    zip_path = secrets_dir / GITHUB_ZIP_FILENAME
    jsondata_dir = get_jsondata_dir()

    if not zip_path.exists():
        return (False, f"{GITHUB_ZIP_FILENAME} not found", 0)

    try:
        # Clear existing jsondata directory
        if jsondata_dir.exists():
            shutil.rmtree(jsondata_dir)
        jsondata_dir.mkdir(parents=True, exist_ok=True)

        files_extracted = 0

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Find the modified-json/Moria path inside the ZIP
            # GitHub ZIPs have a root folder like "RtoM-ArmorBuildings-Mod-main/"
            moria_prefix = None

            for name in zf.namelist():
                # Look for modified-json/Moria/ in the path
                if '/modified-json/Moria/' in name or '/modified-json/Moria' in name:
                    # Find the index where Moria starts
                    idx = name.find('/modified-json/Moria')
                    if idx != -1:
                        moria_prefix = name[:idx] + '/modified-json/'
                        break

            if not moria_prefix:
                return (False, "Could not find modified-json/Moria in ZIP", 0)

            # Extract files from modified-json/Moria/ to jsondata/
            for name in zf.namelist():
                if name.startswith(moria_prefix + 'Moria/'):
                    # Get the path starting from Moria/
                    relative_path = name[len(moria_prefix):]

                    # Skip directory entries
                    if name.endswith('/'):
                        # Create directory
                        dir_path = jsondata_dir / relative_path
                        dir_path.mkdir(parents=True, exist_ok=True)
                    else:
                        # Extract file
                        dest_path = jsondata_dir / relative_path
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        with zf.open(name) as src:
                            dest_path.write_bytes(src.read())
                        files_extracted += 1

        logger.info("Extracted %s files to jsondata/Moria", files_extracted)
        return (True, f"Extracted {files_extracted} files to jsondata/Moria", files_extracted)

    except zipfile.BadZipFile:
        logger.error("Bad ZIP file: %s", GITHUB_ZIP_FILENAME)
        return (False, f"Bad ZIP file: {GITHUB_ZIP_FILENAME}", 0)
    except OSError as e:
        logger.error("Error extracting %s: %s", GITHUB_ZIP_FILENAME, e)
        return (False, f"Extract error: {str(e)}", 0)


def generate_secrets_manifest(secrets_dir: Path) -> tuple[int, Path]:
    """Generate secrets manifest.def from all JSON files in jsondata.

    Scans jsondata/ for all .json files, excluding StringTables directory,
    and writes a manifest XML listing them.

    Args:
        secrets_dir: The Secrets Source directory

    Returns:
        Tuple of (file_count, manifest_path)
    """
    jsondata_dir = secrets_dir / "jsondata"
    exclude_dirs = {'StringTables'}

    json_files = sorted(
        f for f in jsondata_dir.rglob('*.json')
        if f.is_file() and not any(ex in f.parts for ex in exclude_dirs)
    ) if jsondata_dir.exists() else []

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<manifest>',
        '  <!-- Secrets manifest: lists all JSON files to overlay during build Phase B -->',
    ]
    for f in json_files:
        rel = str(f.relative_to(jsondata_dir)).replace('\\', '/')
        lines.append(f'  <mod file="{rel}" />')
    lines.append('</manifest>')
    lines.append('')

    manifest_path = secrets_dir / 'secrets manifest.def'
    manifest_path.write_text('\n'.join(lines), encoding='utf-8')
    logger.info("Generated secrets manifest with %d entries at %s", len(json_files), manifest_path)
    return (len(json_files), manifest_path)


def extract_other_zip_files(secrets_dir: Path) -> list[tuple[str, int]]:
    """Extract all ZIP files in Secrets Source directory except the GitHub one.

    Args:
        secrets_dir: The Secrets Source directory

    Returns:
        List of (zip_name, files_extracted) tuples
    """
    results = []
    zip_files = list(secrets_dir.glob("*.zip"))

    for zip_path in zip_files:
        # Skip the GitHub ZIP file
        if zip_path.name == GITHUB_ZIP_FILENAME:
            continue

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                file_count = len(zf.namelist())
                zf.extractall(secrets_dir)
                results.append((zip_path.name, file_count))
                logger.info("Extracted %s files from %s", file_count, zip_path.name)
        except zipfile.BadZipFile:
            logger.error("Bad ZIP file: %s", zip_path.name)
            results.append((zip_path.name, -1))  # -1 indicates error
        except OSError as e:
            logger.error("Error extracting %s: %s", zip_path.name, e)
            results.append((zip_path.name, -1))

    return results








def _remove_dir_contents_keep_ini(directory: Path) -> int:
    """Remove all files and subdirectories in a directory, preserving .ini files.

    Args:
        directory: The directory to clean

    Returns:
        Number of items removed
    """
    removed = 0
    for item in directory.iterdir():
        if item.is_dir():
            removed += _remove_dir_contents_keep_ini(item)
            # Remove the directory only if it's now empty
            if not any(item.iterdir()):
                item.rmdir()
                removed += 1
        elif not item.suffix.lower() == '.ini':
            item.unlink()
            removed += 1
    return removed


def clear_all_directories_in_secrets_source() -> int:
    """Clear all directories in Secrets Source, keeping only ZIP files and .ini files.

    Returns:
        Number of directories cleaned
    """
    secrets_dir = get_secrets_source_dir()
    if not secrets_dir.exists():
        return 0

    cleaned_count = 0
    for item in secrets_dir.iterdir():
        if item.is_dir():
            try:
                _remove_dir_contents_keep_ini(item)
                # Remove top-level dir only if empty
                if not any(item.iterdir()):
                    item.rmdir()
                cleaned_count += 1
                logger.info("Cleaned directory: %s", item.name)
            except OSError as e:
                logger.error("Failed to clean %s: %s", item.name, e)

    return cleaned_count





class SecretsImportDialog(ctk.CTkToplevel):
    """Dialog for importing and converting Secrets Source mods."""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Import Secrets")
        self.geometry("600x450")
        self.resizable(True, True)

        # Center on parent
        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = Path(__file__).parent.parent.parent / "assets" / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Status tracking
        self.is_running = False
        self.should_cancel = False
        self.update_queue = queue.Queue()

        self._create_widgets()
        self._check_requirements()

        # Start update loop
        self._process_updates()

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main container
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Import Secrets Source Mods",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 10))

        # Description
        desc_label = ctk.CTkLabel(
            main_frame,
            text="Extract and convert mod packages from Secrets Source to JSON.\n"
                 "This will clear existing legacy/json folders and re-convert all mods.",
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        desc_label.pack(pady=(0, 15))

        # Mod list frame
        list_frame = ctk.CTkFrame(main_frame)
        list_frame.pack(fill="both", expand=True, pady=(0, 15))

        list_label = ctk.CTkLabel(
            list_frame,
            text="Mods to Process:",
            font=ctk.CTkFont(size=13, weight="bold")
        )
        list_label.pack(anchor="w", padx=10, pady=(10, 5))

        # Scrollable mod list
        self.mod_list = ctk.CTkTextbox(
            list_frame,
            height=100,
            font=ctk.CTkFont(size=12)
        )
        self.mod_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Progress section
        progress_frame = ctk.CTkFrame(main_frame)
        progress_frame.pack(fill="x", pady=(0, 15))

        self.status_label = ctk.CTkLabel(
            progress_frame,
            text="Ready",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(10, 5))

        self.progress_bar = ctk.CTkProgressBar(progress_frame, width=400)
        self.progress_bar.pack(pady=(0, 5))
        self.progress_bar.set(0)

        self.detail_label = ctk.CTkLabel(
            progress_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.detail_label.pack(pady=(0, 10))

        # Buttons
        button_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_frame.pack(fill="x")

        self.start_btn = ctk.CTkButton(
            button_frame,
            text="Start Import",
            width=120,
            command=self._start_import,
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610")
        )
        self.start_btn.pack(side="left", padx=5)

        self.cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            command=self._cancel,
            fg_color=("#757575", "#616161"),
            hover_color=("#616161", "#424242")
        )
        self.cancel_btn.pack(side="left", padx=5)

        self.close_btn = ctk.CTkButton(
            button_frame,
            text="Close",
            width=100,
            command=self.destroy
        )
        self.close_btn.pack(side="right", padx=5)

    def _check_requirements(self):
        """Check for requirements and show current state."""
        secrets_dir = get_secrets_source_dir()

        # Show information about what will happen
        info_lines = [
            f"📥 Will download: {GITHUB_REPO_URL}",
            "",
            f"📁 Target folder: {secrets_dir}",
        ]

        # Check for existing ZIP files
        zip_files = list(secrets_dir.glob("*.zip")) if secrets_dir.exists() else []
        if zip_files:
            info_lines.append("")
            info_lines.append("Existing ZIP files (will be extracted):")
            for zip_file in zip_files:
                info_lines.append(f"  📦 {zip_file.name}")

        self.mod_list.insert("1.0", "\n".join(info_lines))

    def _start_import(self):
        """Start the import process."""
        if self.is_running:
            return

        self.is_running = True
        self.should_cancel = False
        self.start_btn.configure(state="disabled")

        # Start import in background thread
        thread = threading.Thread(target=self._run_import_process, daemon=True)
        thread.start()

    def _run_import_process(self):
        """Run the import process in a background thread."""
        try:
            secrets_dir = get_secrets_source_dir()

            # Step 1: Clear all directories (keep only ZIP files)
            self.update_queue.put(("status", "Clearing existing directories..."))
            dirs_removed = clear_all_directories_in_secrets_source()
            self.update_queue.put(("detail", f"Removed {dirs_removed} directories"))
            self.update_queue.put(("progress", 0.2))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", None))
                return

            # Step 1.1: Download GitHub repository
            self.update_queue.put(("status", "Downloading from GitHub..."))
            success, message = download_github_repo(
                secrets_dir,
                progress_callback=lambda msg: self.update_queue.put(("detail", msg))
            )

            if not success:
                self.update_queue.put(("status", f"Download failed: {message}"))
                self.update_queue.put(("done", None))
                return

            self.update_queue.put(("detail", message))
            self.update_queue.put(("progress", 0.5))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", None))
                return

            # Step 2: Extract Moria directory from GitHub ZIP to jsondata
            self.update_queue.put(("status", "Extracting Moria data to jsondata..."))
            success, message, file_count = extract_moria_from_github_zip(secrets_dir)

            if not success:
                self.update_queue.put(("status", f"Extract failed: {message}"))
                self.update_queue.put(("done", None))
                return

            self.update_queue.put(("detail", message))
            self.update_queue.put(("progress", 0.7))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", None))
                return

            # Step 3: Extract any other ZIP files in Secrets Source
            other_zips = [z for z in secrets_dir.glob("*.zip") if z.name != GITHUB_ZIP_FILENAME]
            if other_zips:
                self.update_queue.put(("status", f"Extracting {len(other_zips)} additional ZIP file(s)..."))
                zip_results = extract_other_zip_files(secrets_dir)
                for zip_name, count in zip_results:
                    if count >= 0:
                        self.update_queue.put(("detail", f"Extracted {count} files from {zip_name}"))
                    else:
                        self.update_queue.put(("detail", f"Failed to extract {zip_name}"))

            self.update_queue.put(("progress", 0.9))

            # Step 4: Generate secrets manifest
            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", None))
                return

            self.update_queue.put(("status", "Generating secrets manifest..."))
            manifest_count, _manifest_path = generate_secrets_manifest(secrets_dir)
            self.update_queue.put(("detail", f"Manifest: {manifest_count} entries written"))

            self.update_queue.put(("progress", 1.0))
            self.update_queue.put(("status",
                f"Complete! Extracted {file_count} files, manifest has {manifest_count} entries"))

        except (urllib.error.URLError, zipfile.BadZipFile, OSError) as e:
            logger.exception("Import process error")
            self.update_queue.put(("status", f"Error: {str(e)}"))
        finally:
            self.update_queue.put(("done", None))

    def _process_updates(self):
        """Process updates from the background thread."""
        try:
            while True:
                update_type, value = self.update_queue.get_nowait()

                if update_type == "status":
                    self.status_label.configure(text=value)
                elif update_type == "detail":
                    self.detail_label.configure(text=value)
                elif update_type == "progress":
                    self.progress_bar.set(value)
                elif update_type == "done":
                    self.is_running = False
                    self.start_btn.configure(state="normal")

        except queue.Empty:
            pass

        # Schedule next update check
        if self.winfo_exists():
            self.after(100, self._process_updates)

    def _cancel(self):
        """Cancel the import process."""
        if self.is_running:
            self.should_cancel = True
            self.status_label.configure(text="Cancelling...")
        else:
            self.destroy()


def show_secrets_import_dialog(parent) -> None:
    """Show the secrets import dialog.

    Args:
        parent: Parent window
    """
    dialog = SecretsImportDialog(parent)
    dialog.wait_window()
