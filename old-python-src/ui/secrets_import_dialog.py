"""Secrets import dialog for importing building mods."""

import logging
import shutil
import threading
import queue
import zipfile
import urllib.request
import urllib.error
from pathlib import Path
from src.ui.shared_utils import get_assets_dir

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

    Each ZIP is extracted into a subdirectory named after the ZIP file
    (minus the .zip extension).  Files are flattened so that all files
    from nested subdirectories end up directly in the subdirectory root.
    The subdirectory is cleared before each extraction.

    Args:
        secrets_dir: The Secrets Source directory

    Returns:
        List of (zip_name, files_extracted) tuples
    """
    results = []
    zip_files = list(secrets_dir.glob("*.zip"))

    for zip_path in zip_files:
        # Create a subdirectory named after the ZIP (minus .zip)
        extract_dir = secrets_dir / zip_path.stem

        # Clear it completely before extracting
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)

            # Flatten: move all files from nested subdirs into extract_dir root
            files_flattened = 0
            for file_path in list(extract_dir.rglob('*')):
                if file_path.is_file() and file_path.parent != extract_dir:
                    dest = extract_dir / file_path.name
                    shutil.move(str(file_path), str(dest))
                    files_flattened += 1

            # Remove now-empty subdirectories
            for dir_path in sorted(extract_dir.rglob('*'), reverse=True):
                if dir_path.is_dir():
                    try:
                        dir_path.rmdir()
                    except OSError:
                        pass  # Not empty, skip

            # Count final files
            file_count = sum(1 for f in extract_dir.iterdir() if f.is_file())
            results.append((zip_path.name, file_count))
            logger.info("Extracted and flattened %s files from %s into %s/",
                         file_count, zip_path.name, extract_dir.name)
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
    """Clear directories and stale root files in Secrets Source.

    Removes all subdirectories (preserving .ini files within them)
    and deletes loose root-level files that are not .zip, .def, or .ini.

    Returns:
        Number of items cleaned
    """
    secrets_dir = get_secrets_source_dir()
    if not secrets_dir.exists():
        return 0

    keep_extensions = {'.zip', '.def', '.ini'}
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
        elif item.suffix.lower() not in keep_extensions:
            try:
                item.unlink()
                cleaned_count += 1
                logger.info("Removed file: %s", item.name)
            except OSError as e:
                logger.error("Failed to remove %s: %s", item.name, e)

    return cleaned_count





class SecretsImportDialog(ctk.CTkToplevel):
    """Dialog for importing and converting Secrets Source mods.

    Auto-starts the import on open and auto-closes on success.
    """

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Importing Secrets")
        self.geometry("550x240")
        self.resizable(False, False)

        # Center on parent
        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 550) // 2
        y = (self.winfo_screenheight() - 240) // 2
        self.geometry(f"550x240+{x}+{y}")

        # Status tracking
        self.is_running = False
        self.should_cancel = False
        self.import_success = False
        self.update_queue = queue.Queue()

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # Start update loop and auto-start import
        self._process_updates()
        self.after(200, self._start_import)

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        self.title_label = ctk.CTkLabel(
            main_frame,
            text="Importing Secrets",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.pack(pady=(0, 10))

        # Status
        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Starting...",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(pady=(0, 5))

        # Detail
        self.detail_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray"
        )
        self.detail_label.pack(pady=(0, 10))

        # Progress bar
        self.progress_bar = ctk.CTkProgressBar(main_frame, mode="determinate", width=450)
        self.progress_bar.pack(pady=(0, 15))
        self.progress_bar.set(0)

        # Cancel button
        self.cancel_btn = ctk.CTkButton(
            main_frame,
            text="Cancel",
            command=self._cancel,
            fg_color="#dc3545",
            hover_color="#c82333",
            width=100,
        )
        self.cancel_btn.pack()

    def _start_import(self):
        """Start the import process."""
        if self.is_running:
            return

        self.is_running = True
        self.should_cancel = False

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
            self.update_queue.put(("detail", f"Removed {dirs_removed} items"))
            self.update_queue.put(("progress", 0.2))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", False))
                return

            # Step 2: Download GitHub repository
            self.update_queue.put(("status", "Downloading from GitHub..."))
            success, message = download_github_repo(
                secrets_dir,
                progress_callback=lambda msg: self.update_queue.put(("detail", msg))
            )

            if not success:
                self.update_queue.put(("status", f"Download failed: {message}"))
                self.update_queue.put(("done", False))
                return

            self.update_queue.put(("detail", message))
            self.update_queue.put(("progress", 0.5))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", False))
                return

            # Step 3: Extract Moria directory from GitHub ZIP to jsondata
            self.update_queue.put(("status", "Extracting Moria data to jsondata..."))
            success, message, file_count = extract_moria_from_github_zip(secrets_dir)

            if not success:
                self.update_queue.put(("status", f"Extract failed: {message}"))
                self.update_queue.put(("done", False))
                return

            self.update_queue.put(("detail", message))
            self.update_queue.put(("progress", 0.7))

            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", False))
                return

            # Step 4: Extract any other ZIP files in Secrets Source
            other_zips = list(secrets_dir.glob("*.zip"))
            if other_zips:
                self.update_queue.put(("status", f"Extracting {len(other_zips)} additional ZIP file(s)..."))
                zip_results = extract_other_zip_files(secrets_dir)
                for zip_name, count in zip_results:
                    if count >= 0:
                        self.update_queue.put(("detail", f"Extracted {count} files from {zip_name}"))
                    else:
                        self.update_queue.put(("detail", f"Failed to extract {zip_name}"))

            self.update_queue.put(("progress", 0.9))

            # Step 5: Generate secrets manifest
            if self.should_cancel:
                self.update_queue.put(("status", "Cancelled"))
                self.update_queue.put(("done", False))
                return

            self.update_queue.put(("status", "Generating secrets manifest..."))
            manifest_count, _manifest_path = generate_secrets_manifest(secrets_dir)
            self.update_queue.put(("detail", f"Manifest: {manifest_count} entries written"))

            self.update_queue.put(("progress", 1.0))
            self.update_queue.put(("status",
                f"Complete! {file_count} files, {manifest_count} manifest entries"))
            self.update_queue.put(("done", True))

        except (urllib.error.URLError, zipfile.BadZipFile, OSError) as e:
            logger.exception("Import process error")
            self.update_queue.put(("status", f"Error: {str(e)}"))
            self.update_queue.put(("done", False))

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
                    self.import_success = bool(value)
                    if self.import_success:
                        # Auto-close after brief delay on success
                        self.after(1500, self.destroy)
                    else:
                        # Show close button on error
                        self.cancel_btn.configure(
                            text="Close",
                            fg_color=("gray60", "gray40"),
                            hover_color=("gray50", "gray30"),
                            command=self.destroy,
                        )
                        self.protocol("WM_DELETE_WINDOW", self.destroy)
                    return

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


def show_secrets_import_dialog(parent) -> None:
    """Show the secrets import dialog.

    Args:
        parent: Parent window
    """
    dialog = SecretsImportDialog(parent)
    dialog.wait_window()


# Nexus download URL for the Secrets of Khazad-dum mod
NEXUS_SECRETS_URL = (
    "https://www.nexusmods.com/thelordoftheringsreturntomoria/mods/75"
)


class SecretsDownloadDialog(ctk.CTkToplevel):
    """Dialog prompting the user to download/browse/drop the Secrets ZIP file."""

    def __init__(self, parent, on_file_added=None):
        super().__init__(parent)

        self.on_file_added = on_file_added
        self.title("Secrets ZIP Required")
        self.geometry("520x340")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Set application icon
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 520) // 2
        y = (self.winfo_screenheight() - 340) // 2
        self.geometry(f"520x340+{x}+{y}")

        self._create_widgets()
        self._setup_drag_and_drop()

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title_label = ctk.CTkLabel(
            main_frame,
            text="Secrets ZIP File Required",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(0, 10))

        # Description
        desc_label = ctk.CTkLabel(
            main_frame,
            text='No "Secrets of Khazad-dum" ZIP file was found.\n'
                 "Download the latest version from Nexus Mods,\n"
                 "then drop the ZIP file here or use Browse.",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        desc_label.pack(pady=(0, 12))

        # Link button (opens browser)
        link_btn = ctk.CTkButton(
            main_frame,
            text="Open Nexus Mods Download Page",
            width=280,
            height=36,
            fg_color=("#F57C00", "#E65100"),
            hover_color=("#E65100", "#BF360C"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._open_nexus_link
        )
        link_btn.pack(pady=(0, 15))

        # Drop zone
        self.drop_frame = ctk.CTkFrame(
            main_frame,
            height=70,
            border_width=2,
            border_color=("gray60", "gray40"),
            fg_color=("gray90", "gray20"),
            corner_radius=8,
        )
        self.drop_frame.pack(fill="x", pady=(0, 10))
        self.drop_frame.pack_propagate(False)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text="Drop ZIP file here",
            font=ctk.CTkFont(size=14),
            text_color=("gray50", "gray60")
        )
        self.drop_label.pack(expand=True)

        # Browse button
        browse_btn = ctk.CTkButton(
            main_frame,
            text="Browse for ZIP File...",
            width=280,
            height=36,
            fg_color=("#2196F3", "#1565C0"),
            hover_color=("#1565C0", "#0D47A1"),
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=8,
            command=self._browse_for_zip
        )
        browse_btn.pack(pady=(0, 10))

        # Close button
        close_btn = ctk.CTkButton(
            main_frame,
            text="Close",
            width=100,
            command=self.destroy
        )
        close_btn.pack()

    def _setup_drag_and_drop(self):
        """Set up drag-and-drop using tkinterdnd2 (if available)."""
        try:
            from tkinterdnd2 import DND_FILES  # pylint: disable=import-outside-toplevel
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop)
            logger.info("Drag-and-drop enabled via tkinterdnd2")
        except Exception:  # pylint: disable=broad-except
            logger.info("Drag-and-drop not available, browse-only mode")
            self.drop_label.configure(text="Use Browse button below")

    def _open_nexus_link(self):
        """Open the Nexus Mods download page in the default browser."""
        import webbrowser  # pylint: disable=import-outside-toplevel
        webbrowser.open(NEXUS_SECRETS_URL)

    def _on_drop(self, event):
        """Handle file drop via tkinterdnd2.

        Args:
            event: Drop event with data attribute containing file paths.
        """
        # tkinterdnd2 returns paths as a string; braces wrap paths with spaces
        raw = event.data
        # Parse paths: {C:\path with spaces\file.zip} or C:\path\file.zip
        paths = []
        i = 0
        while i < len(raw):
            if raw[i] == '{':
                end = raw.index('}', i)
                paths.append(raw[i + 1:end])
                i = end + 2  # skip } and space
            elif raw[i] == ' ':
                i += 1
            else:
                end = raw.find(' ', i)
                if end == -1:
                    end = len(raw)
                paths.append(raw[i:end])
                i = end + 1

        self._copy_zip_files(paths)

    def _browse_for_zip(self):
        """Open a file dialog to select a ZIP file."""
        from tkinter import filedialog  # pylint: disable=import-outside-toplevel

        file_path = filedialog.askopenfilename(
            parent=self,
            title="Select Secrets ZIP File",
            filetypes=[("ZIP files", "*.zip"), ("All files", "*.*")],
        )
        if file_path:
            self._copy_zip_files([file_path])

    def _copy_zip_files(self, paths):
        """Copy ZIP files from the given paths to the Secrets Source directory.

        Args:
            paths: List of file path strings.
        """
        secrets_dir = get_secrets_source_dir()
        secrets_dir.mkdir(parents=True, exist_ok=True)

        copied = False
        for raw_path in paths:
            file_path = Path(raw_path)
            if file_path.suffix.lower() != '.zip':
                continue

            dest = secrets_dir / file_path.name
            try:
                shutil.copy2(str(file_path), str(dest))
                logger.info("Copied ZIP to Secrets Source: %s", dest.name)
                copied = True
            except OSError as e:
                logger.error("Failed to copy %s: %s", file_path.name, e)

        if copied:
            self.drop_label.configure(
                text="ZIP file added successfully!",
                text_color=("#2E7D32", "#4CAF50")
            )
            self.drop_frame.configure(
                border_color=("#2E7D32", "#4CAF50"),
                fg_color=("gray85", "gray25"),
            )
            if self.on_file_added:
                self.on_file_added()
            self.after(1200, self.destroy)
        else:
            self.drop_label.configure(
                text="No ZIP file found — please drop a .zip file",
                text_color=("#F44336", "#EF5350")
            )


def show_secrets_download_dialog(parent, on_file_added=None) -> None:
    """Show the secrets download/drop dialog.

    Args:
        parent: Parent window
        on_file_added: Optional callback when a ZIP is successfully added
    """
    dialog = SecretsDownloadDialog(parent, on_file_added=on_file_added)
    dialog.wait_window()
