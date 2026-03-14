"""Combined import dialog.

Chains the game-file import (retoc extract + JSON conversion) with
the secrets import (IoStore extraction, JSON conversion, manifest generation)
into a single seamless flow with continuous progress.
"""

import logging
import shutil
import subprocess
import tempfile
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
    get_game_install_path,
    get_max_workers,
)
from src.constants import RETOC_EXE, RETOC_UE_VERSION, UASSETGUI_EXE
from src.ui.shared_utils import (
    UASSET_EXTENSIONS,
    get_retoc_dir,
    get_jsondata_dir,
    get_files_to_convert,
    update_buildings_ini_from_json,
)
from src.ui.import_dialog import (
    get_game_file_paths_to_import,
    convert_file_to_json,
    strip_duplicate_rows,
)
from src.ui.secrets_import_dialog import (
    get_secrets_source_dir,
    # download_github_repo,        # Commented out — GitHub flow replaced by IoStore extraction
    # extract_moria_from_github_zip,
    extract_other_zip_files,
    generate_secrets_manifest,
    clear_all_directories_in_secrets_source,
    # GITHUB_ZIP_FILENAME,
    show_secrets_download_dialog,
)


logger = logging.getLogger(__name__)


class CombinedImportDialog(ctk.CTkToplevel):
    """Dialog that runs game-file import then secrets import in one flow."""

    def __init__(self, parent: ctk.CTk):
        super().__init__(parent)

        self.title("Moria MOD Creator - Import")
        self.geometry("550x240")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Set application icon
        from src.ui.shared_utils import get_assets_dir  # pylint: disable=import-outside-toplevel
        icon_path = get_assets_dir() / "icons" / "application icons" / "app_icon.ico"
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
                    logger.info("Combined import cancelled — cleaning up directories")
                    self.update_queue.put(("status", "Cleaning up..."))
                    self._cleanup_all_directories()
                    self.update_queue.put(("status", "Cancelled — directories reset"))
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
            # Remove ALL ZIPs
            for z in secrets_dir.glob("*.zip"):
                try:
                    z.unlink()
                    logger.info("Removed ZIP: %s", z.name)
                except OSError:
                    pass
            # Clear retoc output from secrets extraction
            secrets_retoc = secrets_dir / "retoc"
            if secrets_retoc.exists():
                shutil.rmtree(secrets_retoc, ignore_errors=True)
                logger.info("Cleared Secrets Source/retoc")
            # Clear jsondata output from secrets conversion
            secrets_jsondata = secrets_dir / "jsondata"
            if secrets_jsondata.exists():
                shutil.rmtree(secrets_jsondata, ignore_errors=True)
                logger.info("Cleared Secrets Source/jsondata")
            # Clear subdirectories (extracted mod files)
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

        # --- Phase 3: extract base game files only (exclude DLC subdirectories) ---
        logger.info("Part 1 Phase 3: Extracting %d game files with retoc", len(files_to_import))
        q.put(("title", "Extracting Game Files"))
        q.put(("status", f"Extracting {len(files_to_import)} game files..."))
        total = len(files_to_import)
        ok_count = 0

        # Copy only base game paks to a temp dir so retoc doesn't pick up DLC paks
        game_paks_temp = tempfile.mkdtemp(prefix="game_paks_")
        try:
            for ext in (".pak", ".ucas", ".utoc"):
                src = paks_path / f"Moria-WindowsNoEditor{ext}"
                if src.exists():
                    shutil.copy2(str(src), game_paks_temp)
            for name_g in ("global.ucas", "global.utoc"):
                src = paks_path / name_g
                if src.exists():
                    shutil.copy2(str(src), game_paks_temp)
            logger.info("Copied base game paks to temp dir (excluding DLC)")
        except OSError as e:
            logger.error("Failed to copy base game paks: %s", e)
            q.put(("error", f"Failed to copy base game paks: {e}"))
            shutil.rmtree(game_paks_temp, ignore_errors=True)
            return False

        for i, fp in enumerate(files_to_import):
            if self.cancelled:
                shutil.rmtree(game_paks_temp, ignore_errors=True)
                return False
            name = Path(fp).stem
            display = name if len(name) <= 50 else name[:47] + "..."
            q.put(("file", display))
            q.put(("progress", i / total))
            q.put(("count", f"Extracting {i + 1} / {total}"))

            cmd = (
                f'"{retoc_exe}" to-legacy --version UE4_27 '
                f'--filter "{name}" "{game_paks_temp}" "{retoc_output}"'
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

        shutil.rmtree(game_paks_temp, ignore_errors=True)
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
                    executor.shutdown(wait=True, cancel_futures=True)
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
        """Extract IoStore mod, convert to JSON, and generate manifest."""
        q = self.update_queue
        secrets_dir = get_secrets_source_dir()

        # Remove old ZIPs so user provides a fresh copy each time
        if secrets_dir.exists():
            for z in secrets_dir.glob("*.zip"):
                try:
                    z.unlink()
                    logger.info("Removed old secrets ZIP: %s", z.name)
                except OSError as e:
                    logger.warning("Could not remove %s: %s", z.name, e)

        # Always prompt user to download/provide the latest Secrets ZIP
        logger.info("Prompting user for Secrets ZIP")
        q.put(("need_secrets_zip", None))

    def _run_secrets_pipeline(self, secrets_dir: Path):
        """Execute the secrets pipeline (runs in background thread).

        Steps:
        1. Extract user-provided ZIPs into subdirectories
        2. IoStore extraction — retoc to-legacy on each mod's .pak/.ucas/.utoc
        3. JSON conversion — parallel UAssetGUI tojson on extracted .uasset files
        4. Generate secrets manifest from all converted JSON files
        """
        q = self.update_queue

        def _cancel_cleanup():
            """Clean up directories on cancel and signal done."""
            logger.info("Secrets pipeline cancelled — cleaning up directories")
            q.put(("status", "Cleaning up..."))
            self._cleanup_all_directories()
            q.put(("status", "Cancelled — directories reset"))
            q.put(("done", False))

        q.put(("title", "Importing Secrets"))
        q.put(("progress", 0))
        q.put(("file", ""))
        q.put(("count", ""))
        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 1: Extract user ZIP files ---
        logger.info("Secrets pipeline step 1: Extracting ZIP files")
        all_zips = list(secrets_dir.glob("*.zip"))
        if all_zips:
            logger.info("Found %d ZIP file(s) to extract", len(all_zips))
            q.put(("status", f"Extracting {len(all_zips)} ZIP file(s)..."))
            zip_results = extract_other_zip_files(secrets_dir)
            for zip_name, count in zip_results:
                if count >= 0:
                    logger.info("Extracted %d files from %s", count, zip_name)
                    q.put(("file", f"Extracted {count} files from {zip_name}"))
                else:
                    logger.error("Failed to extract %s", zip_name)
                    q.put(("file", f"Failed to extract {zip_name}"))
        else:
            logger.debug("No ZIP files found")
        q.put(("progress", 0.05))
        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 2: IoStore extraction (retoc to-legacy) ---
        logger.info("Secrets pipeline step 2: IoStore extraction")
        q.put(("status", "Extracting IoStore mod files..."))

        secrets_retoc_dir = secrets_dir / "retoc"
        secrets_retoc_dir.mkdir(parents=True, exist_ok=True)

        utils_dir = get_utilities_dir()
        retoc_exe = utils_dir / RETOC_EXE
        if not retoc_exe.exists():
            logger.error("retoc.exe not found at %s", retoc_exe)
            q.put(("error", f"retoc.exe not found at {retoc_exe}"))
            q.put(("done", False))
            return

        # Get game Paks path for global.ucas/global.utoc
        game_path = get_game_install_path()
        paks_path = Path(game_path) / "Moria" / "Content" / "Paks" if game_path else None
        if not paks_path or not paks_path.exists():
            logger.error("Game Paks directory not found: %s", paks_path)
            q.put(("error", "Game Paks directory not found — configure game path in Settings"))
            q.put(("done", False))
            return

        global_ucas = paks_path / "global.ucas"
        global_utoc = paks_path / "global.utoc"
        if not global_ucas.exists() or not global_utoc.exists():
            logger.error("global.ucas/global.utoc not found in %s", paks_path)
            q.put(("error", "global.ucas/global.utoc not found in game Paks directory"))
            q.put(("done", False))
            return

        # Find all IoStore mods in extracted subdirectories
        utoc_files = []
        for subdir in secrets_dir.iterdir():
            if subdir.is_dir() and subdir.name not in ("retoc", "jsondata"):
                utoc_files.extend(subdir.glob("*.utoc"))

        if not utoc_files:
            logger.warning("No IoStore mod files (.utoc) found in extracted directories")
            q.put(("status", "No IoStore mod files found"))
            q.put(("progress", 0.45))
        else:
            total_mods = len(utoc_files)
            logger.info("Found %d IoStore mod(s) to extract", total_mods)
            extracted_count = 0

            for i, utoc_file in enumerate(utoc_files):
                if self.cancelled:
                    _cancel_cleanup()
                    return

                stem = utoc_file.stem
                mod_dir = utoc_file.parent
                q.put(("file", f"Extracting {stem} ({i + 1}/{total_mods})..."))

                # Create temp dir with mod files + global files
                temp_paks = tempfile.mkdtemp(prefix="secrets_paks_")
                try:
                    # Copy matching mod files (.pak, .ucas, .utoc with same stem)
                    for ext in (".pak", ".ucas", ".utoc"):
                        src = mod_dir / (stem + ext)
                        if src.exists():
                            shutil.copy2(str(src), temp_paks)
                            logger.debug("Copied %s to temp dir", src.name)

                    # Copy global files for name resolution
                    shutil.copy2(str(global_ucas), temp_paks)
                    shutil.copy2(str(global_utoc), temp_paks)

                    # Run retoc to-legacy (no filter — extract ALL)
                    cmd = (
                        f'"{retoc_exe}" to-legacy --version {RETOC_UE_VERSION} '
                        f'"{temp_paks}" "{secrets_retoc_dir}"'
                    )
                    logger.info("Running retoc: %s", cmd)
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        encoding='utf-8', errors='replace', timeout=300,
                        creationflags=subprocess.CREATE_NO_WINDOW
                        if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
                    )
                    if result.returncode == 0:
                        extracted_count += 1
                        logger.info("Successfully extracted IoStore mod: %s", stem)
                    else:
                        logger.error("retoc failed for %s: %s", stem,
                                     result.stderr.strip() if result.stderr else "Unknown error")
                        q.put(("file", f"Failed to extract {stem}"))

                except subprocess.TimeoutExpired:
                    logger.error("retoc timed out for %s", stem)
                    q.put(("file", f"Timeout extracting {stem}"))
                except OSError as e:
                    logger.error("Error extracting %s: %s", stem, e)
                    q.put(("file", f"Error extracting {stem}: {e}"))
                finally:
                    shutil.rmtree(temp_paks, ignore_errors=True)

                q.put(("progress", 0.05 + 0.40 * (i + 1) / total_mods))

            logger.info("IoStore extraction complete: %d/%d mods extracted",
                         extracted_count, total_mods)

        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 3: Convert extracted .uasset files to JSON ---
        logger.info("Secrets pipeline step 3: Converting to JSON")
        q.put(("title", "Converting Secrets to JSON"))
        q.put(("status", "Scanning for extracted files..."))

        secrets_jsondata_dir = secrets_dir / "jsondata"
        secrets_jsondata_dir.mkdir(parents=True, exist_ok=True)

        uassetgui_exe = utils_dir / UASSETGUI_EXE
        if not uassetgui_exe.exists():
            logger.error("UAssetGUI.exe not found at %s", uassetgui_exe)
            q.put(("error", f"UAssetGUI.exe not found at {uassetgui_exe}"))
            q.put(("done", False))
            return

        # Find all .uasset files in secrets retoc output
        uasset_files = []
        if secrets_retoc_dir.exists():
            for ext in UASSET_EXTENSIONS:
                uasset_files.extend(secrets_retoc_dir.rglob(f"*{ext}"))

        total_c = len(uasset_files)
        if total_c == 0:
            logger.warning("No .uasset files found in Secrets Source/retoc/")
            q.put(("status", "No files to convert"))
            q.put(("progress", 0.70))
        else:
            max_workers = get_max_workers()
            logger.info("Converting %d secrets files using %d workers", total_c, max_workers)
            q.put(("status", f"Converting {total_c} files using {max_workers} workers..."))
            converted = 0
            errors = 0

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        convert_file_to_json,
                        uassetgui_exe,
                        f,
                        secrets_retoc_dir,
                        secrets_jsondata_dir,
                    ): f
                    for f in uasset_files
                }
                for future in as_completed(futures):
                    if self.cancelled:
                        executor.shutdown(wait=True, cancel_futures=True)
                        _cancel_cleanup()
                        return
                    success, _ = future.result()
                    if success:
                        converted += 1
                    else:
                        errors += 1
                    q.put(("progress", 0.45 + 0.25 * (converted + errors) / total_c))
                    q.put(("count", f"Converted {converted} / {total_c} ({errors} errors)"))

            logger.info("Secrets JSON conversion complete: %d converted, %d errors",
                         converted, errors)

        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 3a: Cross-reference secrets retoc against game files ---
        logger.info("Secrets pipeline step 3a: Cross-referencing with game files")
        q.put(("title", "Cross-Referencing Game Files"))
        q.put(("status", "Checking for missing game JSON files..."))

        game_retoc_dir = get_retoc_dir()
        game_jsondata_dir = get_jsondata_dir()
        crossref_converted = 0

        if secrets_retoc_dir.exists() and game_retoc_dir.exists():
            for secrets_uasset in secrets_retoc_dir.rglob("*.uasset"):
                rel_path = secrets_uasset.relative_to(secrets_retoc_dir)
                game_retoc_file = game_retoc_dir / rel_path
                game_json_file = game_jsondata_dir / rel_path.with_suffix(".json")

                if game_retoc_file.exists() and not game_json_file.exists():
                    success, msg = convert_file_to_json(
                        uassetgui_exe, game_retoc_file,
                        game_retoc_dir, game_jsondata_dir,
                    )
                    if success:
                        crossref_converted += 1
                        logger.info("Cross-ref converted: %s", rel_path)
                    else:
                        logger.warning("Cross-ref failed: %s", msg)

        if crossref_converted > 0:
            q.put(("file", f"Converted {crossref_converted} missing game file(s)"))
        q.put(("progress", 0.75))

        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 3b: Strip duplicate rows from secrets JSON ---
        logger.info("Secrets pipeline step 3b: Stripping duplicate rows")
        q.put(("title", "Stripping Duplicate Rows"))
        q.put(("status", "Comparing secrets to game data..."))

        secrets_json_files = list(secrets_jsondata_dir.rglob("*.json")) if secrets_jsondata_dir.exists() else []
        total_stripped = 0
        total_new_rows = 0
        files_stripped = 0

        for i, secrets_json in enumerate(secrets_json_files):
            if self.cancelled:
                _cancel_cleanup()
                return

            rel_path = secrets_json.relative_to(secrets_jsondata_dir)
            game_json = game_jsondata_dir / rel_path

            if not game_json.exists():
                logger.debug("No game file for %s — keeping as-is (new file)", rel_path)
                continue

            removed, remaining = strip_duplicate_rows(secrets_json, game_json)
            if removed > 0:
                files_stripped += 1
                total_stripped += removed
                total_new_rows += remaining
                logger.info("Stripped %d duplicate rows from %s, %d new rows remain",
                            removed, rel_path, remaining)
                q.put(("file", f"Stripped {removed} rows from {rel_path.name} ({remaining} new)"))

            if secrets_json_files:
                q.put(("progress", 0.75 + 0.15 * (i + 1) / len(secrets_json_files)))

        if files_stripped > 0:
            logger.info("Duplicate stripping complete: %d rows removed from %d files, %d new rows total",
                         total_stripped, files_stripped, total_new_rows)
            q.put(("status", f"Stripped {total_stripped} duplicate rows from {files_stripped} files"))
        else:
            logger.info("No duplicate rows found in secrets JSON files")
        q.put(("progress", 0.90))

        if self.cancelled:
            _cancel_cleanup()
            return

        # --- Step 4: Generate manifest ---
        logger.info("Secrets pipeline step 4: Generating secrets manifest")
        q.put(("status", "Generating secrets manifest..."))
        manifest_count, _ = generate_secrets_manifest(secrets_dir)
        logger.info("Secrets manifest generated with %d entries", manifest_count)
        q.put(("file", f"Manifest: {manifest_count} entries"))
        q.put(("progress", 1.0))

        json_count = len(uasset_files) if uasset_files else 0
        logger.info("Combined import completed: %d files converted, %d manifest entries",
                     json_count, manifest_count)
        q.put(("status", f"Import complete! {json_count} files converted, {manifest_count} manifest entries"))
        q.put(("done", True))

    # ------------------------------------------------------------------
    # Secrets ZIP prompt (runs on main thread)
    # ------------------------------------------------------------------

    def _prompt_for_secrets_zip(self):
        """Show the secrets-download dialog, then resume the pipeline."""
        # Temporarily release grab so the child dialog can work
        self.grab_release()

        show_secrets_download_dialog(self)

        # Re-grab and check whether a ZIP appeared
        self.grab_set()
        secrets_dir = get_secrets_source_dir()
        has_zip = any(
            secrets_dir.glob("*.zip")
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
        """Handle cancel — let running work finish, then clean up."""
        logger.info("Combined import cancelled by user")
        self.cancelled = True
        self.status_label.configure(text="Cancelling (waiting for current work to finish)...")


def show_combined_import_dialog(parent) -> bool:
    """Show the combined import dialog and wait for it to close.

    Args:
        parent: Parent window.

    Returns:
        True if import succeeded.
    """
    dialog = CombinedImportDialog(parent)
    parent.wait_window(dialog)
    return dialog.result
