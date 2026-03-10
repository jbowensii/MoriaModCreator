"""Complete build and release script for Moria MOD Creator.

This script:
1. Builds the executable with PyInstaller
2. Signs the executable
3. Creates installer zip bundles
4. Builds the Inno Setup installer (if available)
5. Signs the installer

Usage:
    python scripts/build_release.py [--no-sign] [--no-installer]
"""

import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path
import os
import shutil

# Files matching these patterns (case-insensitive) are excluded from installer zips
EXCLUDED_FILENAME_PATTERNS = [re.compile(r'mereak', re.IGNORECASE),
                              re.compile(r'ax', re.IGNORECASE)]


def is_excluded_file(filename):
    """Check if a filename matches any excluded pattern."""
    return any(p.search(filename) for p in EXCLUDED_FILENAME_PATTERNS)


def run_command(cmd, description, timeout=120):
    """Run a command and print status.

    Args:
        cmd: Command to run (list or string).
        description: Description of what the command does.
        timeout: Timeout in seconds.

    Returns:
        True if successful, False otherwise.
    """
    print(f"\n{'='*60}")
    print(f"{description}...")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            shell=isinstance(cmd, str),
            check=False
        )
        if result.returncode == 0:
            print(f"[OK] {description} completed successfully")
            if result.stdout:
                print(result.stdout)
            return True

        print(f"[ERROR] {description} failed!")
        print(result.stderr)
        return False
    except subprocess.TimeoutExpired:
        print(f"[ERROR] {description} timed out!")
        return False
    except (OSError, ValueError) as e:
        print(f"[ERROR] {description} failed: {e}")
        return False


def verify_signature(file_path):
    """Verify that a file has a valid Authenticode signature.

    Uses PowerShell Get-AuthenticodeSignature to check the signature status.

    Args:
        file_path: Path to the signed file.

    Returns:
        True if the signature is valid, False otherwise.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        print(f"[ERROR] Cannot verify signature - file not found: {file_path}")
        return False

    ps_cmd = (
        f'$sig = Get-AuthenticodeSignature -FilePath "{file_path}"; '
        f'Write-Output "Status: $($sig.Status)"; '
        f'Write-Output "Signer: $($sig.SignerCertificate.Subject)"; '
        f'if ($sig.Status -eq "Valid") {{ exit 0 }} else {{ exit 1 }}'
    )

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=30,
            check=False
        )

        if result.returncode == 0:
            print(f"[OK] Signature verified: {file_path.name}")
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    print(f"     {line}")
            return True

        print(f"[ERROR] Signature verification FAILED for {file_path.name}")
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                print(f"     {line}")
        if result.stderr:
            print(result.stderr)
        return False

    except subprocess.TimeoutExpired:
        print(f"[ERROR] Signature verification timed out for {file_path.name}")
        return False
    except (OSError, ValueError) as e:
        print(f"[ERROR] Signature verification error: {e}")
        return False


def build_executable(project_root):
    """Build the executable with PyInstaller."""
    spec_file = project_root / "MoriaMODCreator.spec"
    return run_command(
        ["pyinstaller", str(spec_file), "--noconfirm"],
        "Building executable with PyInstaller",
        timeout=180
    )


def sign_file(file_path):
    """Sign a file using the signing script."""
    # Import signing function from sign_executable module
    sys.path.insert(0, str(Path(__file__).parent.parent))

    try:
        from scripts.sign_executable import sign_file as sign_func  # pylint: disable=import-outside-toplevel
        return sign_func(file_path)
    except ImportError:
        print("Warning: Could not import signing module")
        return False


def copy_to_release(project_root):
    """Copy executable from dist/ to release/."""
    dist_exe = project_root / "dist" / "MoriaMODCreator.exe"
    release_dir = project_root / "release"
    release_exe = release_dir / "MoriaMODCreator.exe"

    release_dir.mkdir(exist_ok=True)

    if not dist_exe.exists():
        print(f"[ERROR] Executable not found: {dist_exe}")
        return False

    shutil.copy2(dist_exe, release_exe)
    print("[OK] Copied executable to release/")
    return True


def create_installer_zips(project_root):
    """Create zip bundles for the installer.

    All installer content is sourced from docs/ in the repo (the source of truth).
    """
    docs_dir = project_root / 'docs'
    installer_dir = project_root / 'installer'

    print("\nCreating installer zip bundles...")

    skipped_files = []

    # Definitions.zip — from docs/definitions/
    print("  - Definitions.zip...")
    with zipfile.ZipFile(installer_dir / 'Definitions.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        defs_dir = docs_dir / 'definitions'
        if defs_dir.exists():
            for root, _, files in os.walk(defs_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(defs_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # changeconstructions.zip — from docs/changeconstructions/
    print("  - changeconstructions.zip...")
    with zipfile.ZipFile(installer_dir / 'changeconstructions.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        cc_dir = docs_dir / 'changeconstructions'
        if cc_dir.exists():
            for root, _, files in os.walk(cc_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(cc_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # changesecrets.zip — from docs/changesecrets/
    print("  - changesecrets.zip...")
    with zipfile.ZipFile(installer_dir / 'changesecrets.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        cs_dir = docs_dir / 'changesecrets'
        if cs_dir.exists():
            for root, _, files in os.walk(cs_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(cs_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # prebuilt_modfiles.zip — from docs/prebuilt modfiles/
    print("  - prebuilt_modfiles.zip...")
    with zipfile.ZipFile(installer_dir / 'prebuilt_modfiles.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        prebuilt_dir = docs_dir / 'prebuilt modfiles'
        if prebuilt_dir.exists():
            for root, _, files in os.walk(prebuilt_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(prebuilt_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # SecretsSource.zip — from docs/Secrets Source/ (.def files only)
    print("  - SecretsSource.zip...")
    with zipfile.ZipFile(installer_dir / 'SecretsSource.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        secrets_dir = docs_dir / 'Secrets Source'
        if secrets_dir.exists():
            for file_path in secrets_dir.rglob('*.def'):
                if is_excluded_file(file_path.name):
                    skipped_files.append(file_path.name)
                    continue
                arcname = file_path.relative_to(secrets_dir)
                zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # NewObjects.zip — from docs/New Objects/
    print("  - NewObjects.zip...")
    with zipfile.ZipFile(installer_dir / 'NewObjects.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        new_obj_dir = docs_dir / 'New Objects'
        if new_obj_dir.exists():
            for root, _, files in os.walk(new_obj_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(new_obj_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # utilities.zip — from docs/utilities/
    print("  - utilities.zip...")
    with zipfile.ZipFile(installer_dir / 'utilities.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
        utils_dir = docs_dir / 'utilities'
        if utils_dir.exists():
            for root, _, files in os.walk(utils_dir):
                for file in files:
                    if is_excluded_file(file):
                        skipped_files.append(file)
                        continue
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(utils_dir)
                    zf.write(file_path, arcname)
            print(f"    Added {len(zf.namelist())} files")

    # Copy all zips to dist/ as well
    dist_dir = project_root / 'dist'
    dist_dir.mkdir(exist_ok=True)
    zip_names = [
        'Definitions.zip', 'changeconstructions.zip', 'changesecrets.zip',
        'prebuilt_modfiles.zip', 'SecretsSource.zip',
        'NewObjects.zip', 'utilities.zip'
    ]
    for name in zip_names:
        src = installer_dir / name
        if src.exists():
            shutil.copy2(src, dist_dir / name)
    print("[OK] Installer zips created and copied to dist/")

    if skipped_files:
        print(f"\n  Excluded {len(skipped_files)} personal file(s):")
        for name in sorted(set(skipped_files)):
            print(f"    - {name}")

    return True


def build_installer(project_root):
    """Build the Inno Setup installer."""
    iss_file = project_root / "installer" / "MoriaMODCreator.iss"

    # Try to find Inno Setup compiler
    iscc_paths = [
        "C:/Program Files (x86)/Inno Setup 6/ISCC.exe",
        "C:/Program Files/Inno Setup 6/ISCC.exe",
        str(Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe"),
    ]

    iscc = None
    for path in iscc_paths:
        if Path(path).exists():
            iscc = path
            break

    if not iscc:
        # Try to find in PATH
        result = subprocess.run(
            ["where", "iscc"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False
        )
        if result.returncode == 0:
            iscc = result.stdout.strip().split('\n')[0]

    if not iscc:
        print("Warning: Inno Setup compiler not found. Skipping installer build.")
        print("Install Inno Setup from https://jrsoftware.org/isdl.php")
        return False

    return run_command(
        [iscc, str(iss_file)],
        "Building Inno Setup installer",
        timeout=120
    )


def main():
    """Main build process: build executable, sign, create installer zips, build & sign installer."""
    parser = argparse.ArgumentParser(description="Build release for Moria MOD Creator")
    parser.add_argument("--no-sign", action="store_true", help="Skip code signing")
    parser.add_argument("--no-installer", action="store_true", help="Skip installer build")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent

    print("="*60)
    print("Moria MOD Creator - Release Build Script")
    print("="*60)

    # Step 1: Build executable
    if not build_executable(project_root):
        print("\n[ERROR] Build failed!")
        return 1

    # Step 2: Copy to release/
    if not copy_to_release(project_root):
        print("\n[ERROR] Copy to release failed!")
        return 1

    # Step 3: Sign and verify executable
    if not args.no_sign:
        release_exe = project_root / "release" / "MoriaMODCreator.exe"
        if not sign_file(release_exe):
            print("\n[ERROR] Executable signing failed!")
            return 1
        if not verify_signature(release_exe):
            print("\n[ERROR] Executable signature verification failed!")
            return 1

    # Step 4: Create installer zips
    if not create_installer_zips(project_root):
        print("\n[ERROR] Zip creation failed!")
        return 1

    # Step 5: Build installer
    if not args.no_installer:
        if build_installer(project_root):
            # Step 6: Sign and verify installer
            if not args.no_sign:
                installer = project_root / "release" / "MoriaMODCreator_Setup_v1.1.exe"
                if not installer.exists():
                    print(f"\n[ERROR] Installer not found: {installer}")
                    return 1
                if not sign_file(installer):
                    print("\n[ERROR] Installer signing failed!")
                    return 1
                if not verify_signature(installer):
                    print("\n[ERROR] Installer signature verification failed!")
                    return 1
        else:
            print("\nWarning: Installer build skipped or failed.")

    print("\n" + "="*60)
    print("[OK] Build process complete!")
    print("="*60)
    print("\nRelease files:")
    print("  - release/MoriaMODCreator.exe")
    if (project_root / "release").glob("*.exe"):
        for f in (project_root / "release").glob("*.exe"):
            if f.name.startswith("MoriaMODCreator_Setup"):
                print(f"  - release/{f.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
