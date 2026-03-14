"""Separate Secrets Source files into 'In Game' and 'Not In Game' directories,
then repack the 'Not In Game' uasset files into an IoStore pak.

Compares JSON files in Secrets Source/jsondata/ against the base game files
in output/jsondata/ by relative path.  Files whose paths exist in the game
go to 'In Game'; all others go to 'Not In Game'.  Both jsondata/ and retoc/
subdirectories are separated.

After separation, the 'Not In Game' retoc/ uasset files are repacked via
retoc to-zen into a pak/ucas/utoc set in the Downloads folder.

Usage:
  python scripts/separate_secrets.py           # Dry-run (preview only)
  python scripts/separate_secrets.py --run     # Actually copy and repack
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------

RETOC_UE_VERSION = "UE4_27"
RETOC_EXE = "retoc.exe"
PAK_NAME = "TobiSecretsOfKhazaddum_NoGameFiles_P"


# ---------------------------------------------------------------------------
#  Path helpers
# ---------------------------------------------------------------------------

def get_appdata_root() -> Path:
    """Get the MoriaMODCreator AppData directory."""
    return Path(os.environ['APPDATA']) / 'MoriaMODCreator'


def get_secrets_source() -> Path:
    return get_appdata_root() / 'Secrets Source'


def get_game_jsondata() -> Path:
    return get_appdata_root() / 'output' / 'jsondata'


def get_utilities_dir() -> Path:
    return get_appdata_root() / 'utilities'


def get_downloads_dir() -> Path:
    return Path.home() / 'Downloads'


# ---------------------------------------------------------------------------
#  Step 1 & 2: Separate files
# ---------------------------------------------------------------------------

def collect_relative_paths(root: Path, extension: str) -> set[str]:
    """Collect all relative paths (as posix strings) under root with given extension."""
    paths = set()
    for p in root.rglob(f'*{extension}'):
        paths.add(p.relative_to(root).as_posix())
    return paths


def separate_files(secrets_src: Path, game_jsondata: Path, dry_run: bool) -> tuple[int, int]:
    """Separate jsondata and retoc files into In Game / Not In Game dirs.

    Returns (in_game_count, not_in_game_count) based on jsondata comparison.
    """
    src_jsondata = secrets_src / 'jsondata'
    src_retoc = secrets_src / 'retoc'

    if not src_jsondata.exists():
        print(f"ERROR: Source jsondata not found: {src_jsondata}")
        sys.exit(1)

    # Collect game file relative paths
    game_paths = collect_relative_paths(game_jsondata, '.json')
    print(f"  Game jsondata files: {len(game_paths)}")

    # Collect secrets source relative paths
    secrets_json_paths = collect_relative_paths(src_jsondata, '.json')
    print(f"  Secrets Source jsondata files: {len(secrets_json_paths)}")

    # Classify
    in_game_paths = secrets_json_paths & game_paths
    not_in_game_paths = secrets_json_paths - game_paths

    print(f"  In Game: {len(in_game_paths)} files")
    print(f"  Not In Game: {len(not_in_game_paths)} files")

    if in_game_paths:
        print("\n  In Game files:")
        for p in sorted(in_game_paths):
            print(f"    {p}")

    if dry_run:
        print("\n  [DRY RUN] No files copied.")
        return len(in_game_paths), len(not_in_game_paths)

    # Clean up existing output dirs
    for subdir in ('In Game', 'Not In Game'):
        target = secrets_src / subdir
        if target.exists():
            print(f"  Removing existing {subdir}/ directory...")
            shutil.rmtree(target)

    # Copy files
    for category, paths in [('In Game', in_game_paths), ('Not In Game', not_in_game_paths)]:
        # Copy jsondata
        for rel_path in sorted(paths):
            src = src_jsondata / rel_path
            dst = secrets_src / category / 'jsondata' / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

            # Copy corresponding uasset from retoc
            uasset_rel = rel_path.replace('.json', '.uasset')
            uasset_src = src_retoc / uasset_rel
            if uasset_src.exists():
                uasset_dst = secrets_src / category / 'retoc' / uasset_rel
                uasset_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(uasset_src, uasset_dst)

        json_count = len(paths)
        uasset_count = sum(
            1 for p in paths
            if (src_retoc / p.replace('.json', '.uasset')).exists()
        )
        print(f"  Copied {json_count} JSON + {uasset_count} uasset files to {category}/")

    return len(in_game_paths), len(not_in_game_paths)


# ---------------------------------------------------------------------------
#  Step 3: Repack Not In Game files via retoc
# ---------------------------------------------------------------------------

def repack_not_in_game(secrets_src: Path, dry_run: bool) -> bool:
    """Repack Not In Game uasset files into IoStore format."""
    uasset_dir = secrets_src / 'Not In Game' / 'retoc'
    downloads = get_downloads_dir()
    output_dir = downloads / PAK_NAME
    output_utoc = output_dir / f'{PAK_NAME}.utoc'

    retoc_path = get_utilities_dir() / RETOC_EXE
    if not retoc_path.exists():
        print(f"  ERROR: {RETOC_EXE} not found at {retoc_path}")
        return False

    if not uasset_dir.exists():
        print(f"  ERROR: Not In Game retoc dir not found: {uasset_dir}")
        return False

    # Count uasset files
    uasset_count = sum(1 for _ in uasset_dir.rglob('*.uasset'))
    print(f"  Uasset files to repack: {uasset_count}")
    print(f"  Output: {output_dir}")

    if dry_run:
        print("  [DRY RUN] Retoc not executed.")
        return True

    # Clean and create output dir
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(retoc_path),
        'to-zen',
        '--version', RETOC_UE_VERSION,
        str(uasset_dir),
        str(output_utoc)
    ]

    print(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=str(get_utilities_dir()),
            check=False
        )

        if result.returncode != 0:
            print(f"  ERROR: retoc failed with code {result.returncode}")
            if result.stdout.strip():
                print(f"  stdout: {result.stdout.strip()}")
            if result.stderr.strip():
                print(f"  stderr: {result.stderr.strip()}")
            return False

        # Verify output files
        expected = [f'{PAK_NAME}.pak', f'{PAK_NAME}.ucas', f'{PAK_NAME}.utoc']
        created = [f for f in expected if (output_dir / f).exists()]
        print(f"  Created: {', '.join(created)}")

        if len(created) < 3:
            missing = [f for f in expected if f not in created]
            print(f"  WARNING: Missing expected files: {', '.join(missing)}")
            return False

        return True

    except OSError as e:
        print(f"  ERROR running retoc: {e}")
        return False


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------

def main():
    dry_run = '--run' not in sys.argv
    mode = "DRY RUN" if dry_run else "LIVE"

    print(f"=== Secrets Source File Separator & Repacker [{mode}] ===\n")

    secrets_src = get_secrets_source()
    game_jsondata = get_game_jsondata()

    if not secrets_src.exists():
        print(f"ERROR: Secrets Source not found: {secrets_src}")
        sys.exit(1)
    if not game_jsondata.exists():
        print(f"ERROR: Game jsondata not found: {game_jsondata}")
        sys.exit(1)

    # Step 1 & 2: Separate files
    print("Step 1-2: Separating files into In Game / Not In Game...")
    in_game, not_in_game = separate_files(secrets_src, game_jsondata, dry_run)

    # Step 3: Repack
    print(f"\nStep 3: Repacking {not_in_game} Not In Game files via retoc...")
    success = repack_not_in_game(secrets_src, dry_run)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary:")
    print(f"  In Game:     {in_game} files")
    print(f"  Not In Game: {not_in_game} files")
    print(f"  Repack:      {'SUCCESS' if success else 'FAILED'}")
    if not dry_run and success:
        print(f"  Output:      {get_downloads_dir() / PAK_NAME}")
    if dry_run:
        print(f"\n  Run with --run to execute.")


if __name__ == '__main__':
    main()
