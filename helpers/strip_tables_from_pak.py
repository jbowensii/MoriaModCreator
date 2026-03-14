"""Strip non-Mods data tables from an IoStore pak and repack.

Extracts an IoStore pak set using 'retoc unpack-raw', removes chunk files
and manifest entries for everything NOT under Content/Mods/, then repacks
with 'retoc pack-raw'.

Usage:
    python helpers/strip_tables_from_pak.py

Output: {SOURCE_DIR}/stripped/RtoMSecretsOfKhazaddum_NoTables_P.*
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --- Configuration ---
SOURCE_DIR = Path(
    r"C:\Program Files\Epic Games\ReturnToMoria\Moria\Content\Paks"
    r"\Secrets of Khazad-dum No FatStacks_P"
)
SOURCE_STEM = "RtoMSecretsOfKhazaddum_NoFatStacks_P"
OUTPUT_STEM = "RtoMSecretsOfKhazaddum_NoTables_P"
RETOC_EXE = Path(
    r"C:\Users\johnb\AppData\Roaming\MoriaMODCreator\utilities\retoc.exe"
)


def run(cmd, description, timeout=300):
    """Run a shell command, print output, return success bool."""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")

    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW")
            else 0x08000000
        )

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, shell=True, check=False,
        **kwargs,
    )
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"  [ERROR] {result.stderr.strip()}")
        return False
    print("  [OK]")
    return True


def main():
    """Extract IoStore pak as raw chunks, remove non-Mods, repack."""
    source_utoc = SOURCE_DIR / f"{SOURCE_STEM}.utoc"
    if not source_utoc.exists():
        print(f"ERROR: Source .utoc not found: {source_utoc}")
        return 1
    if not RETOC_EXE.exists():
        print(f"ERROR: retoc.exe not found: {RETOC_EXE}")
        return 1

    output_dir = SOURCE_DIR / "stripped"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    # retoc creates the output dir itself, so use a path that doesn't exist
    unpack_dir = Path(tempfile.gettempdir()) / f"strip_raw_{id(object()):x}"
    if unpack_dir.exists():
        shutil.rmtree(unpack_dir)

    try:
        # Step 1: Unpack raw chunks (preserves binary data + manifest)
        if not run(
            f'"{RETOC_EXE}" unpack-raw "{source_utoc}" "{unpack_dir}"',
            "Step 1: Unpacking IoStore to raw chunks",
        ):
            return 1

        # Step 2: Read manifest, filter out non-Mods entries
        manifest_path = unpack_dir / "manifest.json"
        chunks_dir = unpack_dir / "chunks"

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        chunk_paths = manifest["chunk_paths"]
        kept_chunks = {}
        removed_chunks = {}

        for chunk_id, path in chunk_paths.items():
            normalized = path.replace("\\", "/")
            if "/Mods/" in normalized:
                kept_chunks[chunk_id] = path
            else:
                removed_chunks[chunk_id] = path

        print(f"\n{'='*60}")
        print("  Step 2: Removing non-Mods chunks")
        print(f"{'='*60}")

        for chunk_id, path in sorted(removed_chunks.items(),
                                     key=lambda x: x[1]):
            chunk_file = chunks_dir / chunk_id
            if chunk_file.exists():
                chunk_file.unlink()
            print(f"  Removed: {path}")

        # Update manifest to only include kept chunks
        manifest["chunk_paths"] = kept_chunks
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        print(f"\n  Kept: {len(kept_chunks)}, Removed: {len(removed_chunks)}")
        if not kept_chunks:
            print("ERROR: No Mods files found!")
            return 1

        # Step 3: Repack with pack-raw
        output_utoc = output_dir / f"{OUTPUT_STEM}.utoc"
        if not run(
            f'"{RETOC_EXE}" pack-raw "{unpack_dir}" "{output_utoc}"',
            f"Step 3: Repacking as {OUTPUT_STEM}",
        ):
            return 1

        # Step 4: Copy .pak stub (IoStore needs .pak + .ucas + .utoc)
        source_pak = SOURCE_DIR / f"{SOURCE_STEM}.pak"
        output_pak = output_dir / f"{OUTPUT_STEM}.pak"
        if source_pak.exists():
            shutil.copy2(source_pak, output_pak)
            print(f"\n  Copied .pak stub ({source_pak.stat().st_size} bytes)")

        # Results
        print(f"\n{'='*60}")
        print("  DONE!")
        print(f"{'='*60}")
        print(f"\n  Output: {output_dir}")
        for f in sorted(output_dir.iterdir()):
            sz = f.stat().st_size / (1024 * 1024)
            print(f"    {f.name}  ({sz:.1f} MB)")
        return 0

    finally:
        shutil.rmtree(unpack_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
