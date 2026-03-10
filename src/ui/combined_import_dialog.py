"""Combined import dialog for Novice mode.

Chains the game-file import (retoc extract + JSON conversion) with
the secrets import (download GitHub repo, extract ZIPs, generate manifest)
into a single seamless flow with continuous progress.
"""

import logging
import shutil
import subprocess
import threading
import queue
from pathlib import Path

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    ThreadPoolExecutor = None
    as_completed = None

import customtkinter as ctk

from src.config import (
    get_appdata_dir,
    get_utilities_dir,
    get_output_dir,
    get_game_install_path,
    get_max_workers,
)
from src.ui.shared_utils import (
    get_retoc_dir,
    get_jsondata_dir,
    get_files_to_convert,
    update_buildings_ini_from_json,
)
from src.ui.import_dialog import (
    get_game_file_paths_to_import,
    convert_file_to_json,
)
from src.ui.secrets_import_dialog import (
    get_secrets_source_dir,
    download_github_repo,
    extract_moria_from_github_zip,
    extract_other_zip_files,
    generate_secrets_manifest,
    clear_all_directories_in_secrets_source,
    GITHUB_ZIP_FILENAME,
    show_secrets_download_dialog,
)


logger = logging.getLogger(__name__)


class CombinedImportDialog(ctk.CTkToplevel):
    """Dialog that runs game-file import then secrets import in one flow."""

    def __init__(self, parent: ctk.CTk, on_secrets_btn_update=None):
        super().__init__(parent)

        self.title("Moria MOD Creator - Import")
        self.geometry("550x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_secrets_btn_update = on_secrets_btn_update

        # Set application icon
        icon_path = (
            Path(__file__).parent.parent.parent
            / "assets" / "icons" / "application icons" / "app_icon.ico"
        )
        if icon_path.exists():
            self.after(10, lambda: self.iconbitmap(str(icon_path)))

        # Center on screen
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 550) // 2
        y = (self.winfo_screenheight() - 240) // 2
        self.geometry(f"550x240+{x}+{y}")

        # State
        self.result = False
        self.cancelled = False
        self.update_queue = queue.Queue()

        self._create_widgets()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.after(100, self._start)

    def _create_widgets(self):
        """Create dialog widgets."""
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        self.title_label = ctk.CTkLabel(
            main_frame,
            text="Importing Game Files",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.title_label.pack(pady=(0, 10))

        self.status_label = ctk.CTkLabel(
            main_frame,
            text="Preparing...",
            font=ctk.CTkFont(size=12),
        )
        self.status_label.pack(pady=(0, 5))

        self.file_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        )
        self.file_label.pack(pady=(0, 10))

        self.progress = ctk.CTkProgressBar(main_frame, mode="determinate", width=450)
        self.progress.pack(pady=(0, 10))
        self.progress.set(0)

        self.count_label = ctk.CTkLabel(
            main_frame,
            text="",
            font=ctk.CTkFont(size=11),
        )
        self.count_label.pack(pady=(0, 10))

        self.cancel_btn = ctk.CTkButton(
            main_frame,
            text="Cancel",
            command=self._on_cancel,
            fg_color="#dc3545",
            hover_color="#c82333",
            width=100,
        )
        self.cancel_btn.pack()

    # ------------------------------------------------------------------
    # Thread management
    # ------------------------------------------------------------------

    def _start(self):
        """Kick off the background import thread."""
        logger.info("Combined import dialog opened, starting combined import")
        thread = threading.Thread(target=self._run_combined, daemon=True)
        thread.start()
        self._check_queue()

    def _check_queue(self):
        """Drain the message queue and apply UI updates."""
        try:
            while True:
                msg_type, data = self.update_queue.get_nowait()
                if msg_type == "title":
                    self.title_label.configure(text=data)
                elif msg_type == "status":
                    self.status_label.configure(text=data)
                elif msg_type == "file":
                    self.file_label.configure(text=data)
                elif msg_type == "progress":
                    self.progress.set(data)
                elif msg_type == "count":
                    self.count_label.configure(text=data)
                elif msg_type == "error":
                    self.status_label.configure(text=data, text_color="red")
                elif msg_type == "done":
                    self.result = data
                    self._show_close_button()
                    return
                elif msg_type == "need_secrets_zip":
                    # Must run on the main thread
                    self._prompt_for_secrets_zip()
                    return
        except queue.Empty:
            pass

        if not self.cancelled:
            self.after(100, self._check_queue)

    # ------------------------------------------------------------------
    # Combined pipeline (runs in background thread)
    # ------------------------------------------------------------------

    def _run_combined(self):
        """Run game import then secrets import sequentially."""
        try:
            # ---------- Upfront cleanup of ALL directories ----------
            self._cleanup_all_directories()

            # ---------- PART 1: Import game files ----------
            logger.info("Combined import: starting Part 1 - game file import")
            game_ok = self._part1_import_game_files()
            if self.cancelled or not game_ok:
                if self.cancelled:
                    logger.info("Combined import cancelled during game file import")
                else:
                    logger.error("Combined import: game file import failed")
                self.update_queue.put(("done", False))
                return

            # ---------- PART 2: Import secrets ----------
            logger.info("Combined import: starting Part 2 - secrets import")
            self._part2_import_secrets()

        except OSError as e:
            logger.exception("Combined import error")
            self.update_queue.put(("error", f"Error: {e}"))
            self.update_queue.put(("done", False))

    # ------------------------------------------------------------------
    # Upfront cleanup — clear ALL directories before import begins
    # ------------------------------------------------------------------

    def _cleanup_all_directories(self):
        """Clear all output, cache, and secrets directories at the start of import."""
        q = self.update_queue
        q.put(("title", "Preparing Import"))
        q.put(("status", "Clearing all directories..."))
        q.put(("progress", 0))

        appdata = get_appdata_dir()

        # 1. Output directories (retoc + jsondata)
        retoc_output = get_retoc_dir()
        jsondata_output = get_jsondata_dir()
        for d in (retoc_output, jsondata_output):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        logger.info("Cleared output directories: retoc, jsondata")

        # 2. Cache directories (constructions, game, secrets)
        cache_dir = appdata / 'cache'
        for sub in ('constructions', 'game', 'secrets'):
            sub_dir = cache_dir / sub
            if sub_dir.exists():
                # Remove JSON files but preserve .ini files (checked_items)
                for item in sub_dir.rglob('*.json'):
                    try:
                        item.unlink()
                    except OSError:
                        pass
                logger.info("Cleared cache: %s", sub)

        # 3. Secrets Source (dirs + stale files, keep .zip/.def/.ini)
        secrets_dir = get_secrets_source_dir()
        if secrets_dir.exists():
            # Remove ALL ZIPs (GitHub ZIP gets re-downloaded fresh)
            for z in secrets_dir.glob("*.zip"):
                try:
                    z.unlink()
                    logger.info("Removed ZIP: %s", z.name)
                except OSError:
                    pass
            # Clear subdirectories
            cleaned = clear_all_directories_in_secrets_source()
            logger.info("Cleared Secrets Source: %d items", cleaned)

        q.put(("status", "All directories cleared"))
        q.put(("progress", 0.05))
        logger.info("Upfront cleanup complete")

    # ------------------------------------------------------------------
    # Part 1 — game files (mirrors ImportDialog._run_import_and_convert)
    # ------------------------------------------------------------------

    def _part1_import_game_files(self) -> bool:
        """Extract game files with retoc and convert to JSON.

        Returns True on success, False on error/cancel.
        """
        q = self.update_queue
        utilities_dir = get_utilities_dir()
        game_path = get_game_install_path()
        max_workers = get_max_workers()

        # --- prerequisites ---
        if not game_path:
            logger.error("Game install path not configured")
            q.put(("error", "Game install path not configured"))
            return False

        retoc_exe = utilities_dir / "retoc.exe"
        uassetgui_exe = utilities_dir / "UAssetGUI.exe"
        retoc_output = get_retoc_dir()
        jsondata_output = get_jsondata_dir()

        if not retoc_exe.exists():
            logger.error("retoc.exe not found at %s", retoc_exe)
            q.put(("error", "retoc.exe not found in utilities folder"))
            return False
        if not uassetgui_exe.exists():
            logger.error("UAssetGUI.exe not found at %s", uassetgui_exe)
            q.put(("error", "UAssetGUI.exe not found in utilities folder"))
            return False

        paks_path = Path(game_path) / "Moria" / "Content" / "Paks"
        if not paks_path.exists():
            logger.error("Paks directory not found at %s", paks_path)
            q.put(("error", f"Paks directory not found at {paks_path}"))
            return False

        # --- Phase 1: scan ---
        logger.info("Part 1 Phase 1: Scanning .def files for required game files")
        q.put(("title", "Importing Game Files"))
        q.put(("status", "Scanning .def files for required game files..."))
        files_to_import = get_game_file_paths_to_import()
        if not files_to_import:
            logger.warning("No files to import - no .def files found")
            q.put(("status", "No files to import"))
            return True

        logger.info("Found %d game files to import", len(files_to_import))
        q.put(("status", f"Found {len(files_to_import)} game files to import"))
        if self.cancelled:
            return False

        # --- Phase 2: (directories already cleared in upfront cleanup) ---

        # --- Phase 3: extract ---
        logger.info("Part 1 Phase 3: Extracting %d game files with retoc", len(files_to_import))
        q.put(("title", "Extracting Game Files"))
        q.put(("status", f"Extracting {len(files_to_import)} game files..."))
        total = len(files_to_import)
        ok_count = 0

        for i, fp in enumerate(files_to_import):
            if self.cancelled:
                return False
            name = Path(fp).stem
            display = name if len(name) <= 50 else name[:47] + "..."
            q.put(("file", display))
            q.put(("progress", i / total))
            q.put(("count", f"Extracting {i + 1} / {total}"))

            cmd = (
                f'"{retoc_exe}" to-legacy --version UE4_27 '
                f'--filter "{name}" "{paks_path}" "{retoc_output}"'
            )
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    timeout=120,
                    shell=True,
                    check=False,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                        if hasattr(subprocess, "CREATE_NO_WINDOW")
                        else 0
                    ),
                )
                if result.returncode == 0:
                    ok_count += 1
                else:
                    logger.warning("Extract failed %s: %s", fp, result.stderr)
            except (subprocess.TimeoutExpired, OSError) as e:
                logger.warning("Extract error %s: %s", fp, e)

        logger.info("Part 1 Phase 3 complete: %d of %d extracted", ok_count, total)
        q.put(("progress", 1.0))
        q.put(("status", f"Extracted {ok_count} of {total} files"))
        if self.cancelled:
            return False

        # --- Phase 4: convert ---
        logger.info("Part 1 Phase 4: Converting extracted files to JSON")
        q.put(("title", "Converting to JSON"))
        q.put(("status", "Scanning for files to convert..."))
        q.put(("progress", 0))

        uasset_files = get_files_to_convert()
        total_c = len(uasset_files)
        if total_c == 0:
            logger.warning("No uasset files found to convert after extraction")
            q.put(("status", "No files to convert"))
            return True

        logger.info("Converting %d files using %d workers", total_c, max_workers)
        q.put(("status", f"Converting {total_c} files using {max_workers} workers..."))
        converted = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    convert_file_to_json,
                    uassetgui_exe,
                    f,
                    retoc_output,
                    jsondata_output,
                ): f
                for f in uasset_files
            }
            for future in as_completed(futures):
                if self.cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    return False
                success, _ = future.result()
                if success:
                    converted += 1
                else:
                    errors += 1
                q.put(("progress", (converted + errors) / total_c))
                q.put(("count", f"Converted {converted} / {total_c} ({errors} errors)"))

        logger.info("Part 1 Phase 4 complete: %d converted, %d errors", converted, errors)

        # --- Phase 5: buildings cache ---
        logger.info("Part 1 Phase 5: Updating buildings cache")
        q.put(("status", "Updating buildings cache..."))
        _, _ = update_buildings_ini_from_json()
        logger.info("Part 1 complete: game import finished with %d files converted", converted)
        q.put(("status", f"Game import complete — {converted} files converted"))
        q.put(("file", ""))
        q.put(("progress", 1.0))
        return True

    # ------------------------------------------------------------------
    # Part 2 — secrets import (mirrors SecretsImportDialog._run_import_process)
    # ------------------------------------------------------------------

    def _part2_import_secrets(self):
        """Download, extract, and manifest the Secrets Source data."""
        q = self.update_queue
        secrets_dir = get_secrets_source_dir()

        # Always remove old non-GitHub ZIPs so user provides a fresh copy each time
        if secrets_dir.exists():
            for z in secrets_dir.glob("*.zip"):
                if z.name != GITHUB_ZIP_FILENAME:
                    try:
                        z.unlink()
                        logger.info("Removed old secrets ZIP: %s", z.name)
                    except OSError as e:
                        logger.warning("Could not remove %s: %s", z.name, e)

        # Always prompt user to download/provide the latest Secrets ZIP
        logger.info("Prompting user for Secrets ZIP")
        q.put(("need_secrets_zip", None))

    def _run_secrets_pipeline(self, secrets_dir: Path):
        """Execute the secrets pipeline (runs in background thread)."""
        q = self.update_queue

        # Step 1: (directories already cleared in upfront cleanup)
        q.put(("title", "Importing Secrets"))
        q.put(("progress", 0))
        q.put(("file", ""))
        q.put(("count", ""))
        if self.cancelled:
            q.put(("done", False))
            return

        # Step 2: download GitHub repo
        logger.info("Secrets pipeline step 2: Downloading from GitHub")
        q.put(("status", "Downloading from GitHub..."))
        ok, msg = download_github_repo(
            secrets_dir,
            progress_callback=lambda m: q.put(("file", m)),
        )
        if not ok:
            logger.error("GitHub download failed: %s", msg)
            q.put(("error", f"Download failed: {msg}"))
            q.put(("done", False))
            return
        logger.info("GitHub download complete")
        q.put(("progress", 0.5))
        if self.cancelled:
            q.put(("done", False))
            return

        # Step 3: extract GitHub ZIP → jsondata
        logger.info("Secrets pipeline step 3: Extracting Moria data to jsondata")
        q.put(("status", "Extracting Moria data to jsondata..."))
        ok, msg, file_count = extract_moria_from_github_zip(secrets_dir)
        if not ok:
            logger.error("GitHub ZIP extraction failed: %s", msg)
            q.put(("error", f"Extract failed: {msg}"))
            q.put(("done", False))
            return
        logger.info("Extracted %d files from GitHub ZIP", file_count)
        q.put(("file", msg))
        q.put(("progress", 0.7))
        if self.cancelled:
            q.put(("done", False))
            return

        # Step 4: extract other ZIP files
        logger.info("Secrets pipeline step 4: Extracting additional ZIP files")
        other_zips = [
            z for z in secrets_dir.glob("*.zip") if z.name != GITHUB_ZIP_FILENAME
        ]
        if other_zips:
            logger.info("Found %d additional ZIP file(s) to extract", len(other_zips))
            q.put(("status", f"Extracting {len(other_zips)} additional ZIP file(s)..."))
            zip_results = extract_other_zip_files(secrets_dir)
            for zip_name, count in zip_results:
                if count >= 0:
                    logger.info("Extracted %d files from %s", count, zip_name)
                    q.put(("file", f"Extracted {count} files from {zip_name}"))
                else:
                    logger.error("Failed to extract %s", zip_name)
                    q.put(("file", f"Failed to extract {zip_name}"))
        else:
            logger.debug("No additional ZIP files found")
        q.put(("progress", 0.9))
        if self.cancelled:
            q.put(("done", False))
            return

        # Step 5: manifest
        logger.info("Secrets pipeline step 5: Generating secrets manifest")
        q.put(("status", "Generating secrets manifest..."))
        manifest_count, _ = generate_secrets_manifest(secrets_dir)
        logger.info("Secrets manifest generated with %d entries", manifest_count)
        q.put(("file", f"Manifest: {manifest_count} entries"))
        q.put(("progress", 1.0))
        logger.info("Combined import completed: %d secret files, %d manifest entries", file_count, manifest_count)
        q.put(("status", f"Import complete! {file_count} secret files, {manifest_count} manifest entries"))
        q.put(("done", True))

    # ------------------------------------------------------------------
    # Secrets ZIP prompt (runs on main thread)
    # ------------------------------------------------------------------

    def _prompt_for_secrets_zip(self):
        """Show the secrets-download dialog, then resume the pipeline."""
        # Temporarily release grab so the child dialog can work
        self.grab_release()

        def _on_zip_added():
            if self.on_secrets_btn_update:
                self.on_secrets_btn_update()

        show_secrets_download_dialog(self, on_file_added=_on_zip_added)

        # Re-grab and check whether a ZIP appeared
        self.grab_set()
        secrets_dir = get_secrets_source_dir()
        has_zip = any(
            z.name != GITHUB_ZIP_FILENAME
            for z in secrets_dir.glob("*.zip")
        ) if secrets_dir.exists() else False

        if has_zip:
            logger.info("Secrets ZIP provided, resuming secrets pipeline")
            # Resume the secrets pipeline in a new thread
            thread = threading.Thread(
                target=self._run_secrets_pipeline,
                args=(secrets_dir,),
                daemon=True,
            )
            thread.start()
            self._check_queue()
        else:
            # User closed without adding a ZIP — finish without secrets
            logger.info("No secrets ZIP provided, completing without secrets")
            self.update_queue.put(("status", "Import complete (secrets skipped)"))
            self.update_queue.put(("progress", 1.0))
            self.update_queue.put(("done", True))
            self._check_queue()

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _show_close_button(self):
        """Switch the cancel button to a close button."""
        self.cancel_btn.configure(
            text="Close",
            fg_color=("#2E7D32", "#1B5E20"),
            hover_color=("#1B5E20", "#0D3610"),
            command=self.destroy,
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_cancel(self):
        """Handle cancel."""
        logger.info("Combined import cancelled by user")
        self.cancelled = True
        self.status_label.configure(text="Cancelling...")


def show_combined_import_dialog(parent, on_secrets_btn_update=None) -> bool:
    """Show the combined import dialog and wait for it to close.

    Args:
        parent: Parent window.
        on_secrets_btn_update: Callback to update secrets button state.

    Returns:
        True if import succeeded.
    """
    dialog = CombinedImportDialog(parent, on_secrets_btn_update=on_secrets_btn_update)
    parent.wait_window(dialog)
    return dialog.result
