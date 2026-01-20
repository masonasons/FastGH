#!/usr/bin/env python
"""Build script for FastGH using PyInstaller - supports Windows and macOS."""

import os
import subprocess
import sys
import shutil
import tempfile
import platform as platform_mod
from pathlib import Path

from version import APP_NAME, APP_VERSION

APP_DESCRIPTION = "A GitHub desktop client"
APP_COPYRIGHT = "Copyright 2024"
APP_VENDOR = "FastGH"


def get_platform():
    """Get the current platform."""
    if sys.platform == "darwin":
        return "macos"
    elif sys.platform == "win32":
        return "windows"
    else:
        return "linux"


def get_git_commit_sha():
    """Get the current git commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def create_build_info_file(script_dir: Path):
    """Create build_info.txt with commit SHA in script directory for PyInstaller to bundle."""
    commit_sha = get_git_commit_sha()
    if commit_sha:
        build_info_path = script_dir / "build_info.txt"
        with open(build_info_path, 'w') as f:
            f.write(commit_sha)
        print(f"Created build_info.txt: commit {commit_sha[:8]}")
        return build_info_path
    return None


def cleanup_build_info_file(script_dir: Path):
    """Remove build_info.txt after build to keep source directory clean."""
    build_info_path = script_dir / "build_info.txt"
    if build_info_path.exists():
        build_info_path.unlink()
        print("Cleaned up build_info.txt")


def get_hidden_imports():
    """Get list of hidden imports that PyInstaller might miss."""
    return [
        # wx submodules
        "wx.adv",
        "wx.html",
        "wx.xml",
        # Our packages
        "models",
        "models.repository",
        "models.issue",
        "models.commit",
        "models.user",
        "models.workflow",
        "models.release",
        "models.notification",
        "models.event",
        "GUI",
        "GUI.main",
        "GUI.view",
        "GUI.options",
        "GUI.accounts",
        "GUI.issues",
        "GUI.pullrequests",
        "GUI.commits",
        "GUI.actions",
        "GUI.releases",
        "GUI.search",
        "GUI.theme",
        # Other modules
        "config",
        "application",
        "github_api",
        "version",
        # keyboard_handler
        "keyboard_handler",
        "keyboard_handler.wx_handler",
        # requests/urllib
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
        # Other
        "json",
        "threading",
        "datetime",
        "webbrowser",
    ]


def get_data_files(script_dir: Path):
    """Get list of data files to include in the bundle."""
    datas = []
    # Include build_info.txt if it exists (created before build)
    build_info = script_dir / "build_info.txt"
    if build_info.exists():
        datas.append((str(build_info), "."))
    return datas


def get_binaries():
    """Get platform-specific binaries to include."""
    binaries = []

    if sys.platform == "win32":
        # Include keyboard_handler DLLs if present
        try:
            import keyboard_handler
            kh_path = Path(keyboard_handler.__file__).parent
            for dll in kh_path.glob("*.dll"):
                binaries.append((str(dll), "keyboard_handler"))
        except ImportError:
            pass

    return binaries


def build_windows(script_dir: Path, output_dir: Path) -> tuple:
    """Build for Windows using PyInstaller.

    Returns:
        Tuple of (success: bool, artifact_path: Path or None)
    """
    dist_dir = output_dir / "dist"
    build_dir = output_dir / "build"

    # Clean previous build
    for d in [dist_dir, build_dir]:
        if d.exists():
            print(f"Cleaning {d}...")
            shutil.rmtree(d)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create build_info.txt BEFORE building command so get_data_files can include it
    create_build_info_file(script_dir)

    # Build PyInstaller command
    main_script = script_dir / "FastGH.pyw"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",  # No console window
        "--noconfirm",  # Overwrite without asking
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={output_dir}",
    ]

    # Add hidden imports
    for imp in get_hidden_imports():
        cmd.extend(["--hidden-import", imp])

    # Add data files
    for src, dst in get_data_files(script_dir):
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # Add binaries
    for src, dst in get_binaries():
        cmd.extend(["--add-binary", f"{src}{os.pathsep}{dst}"])

    # Collect keyboard_handler
    cmd.extend(["--collect-all", "keyboard_handler"])

    # Add main script
    cmd.append(str(main_script))

    print(f"Building {APP_NAME} v{APP_VERSION} for Windows...")
    print(f"Output: {output_dir}")
    print()

    try:
        result = subprocess.run(cmd, cwd=script_dir)
    finally:
        # Clean up build_info.txt from source directory
        cleanup_build_info_file(script_dir)

    if result.returncode != 0:
        return False, None

    # The output will be in dist_dir / APP_NAME
    app_dir = dist_dir / APP_NAME
    if not app_dir.exists():
        print("Error: Build output not found")
        return False, None

    # Create zip file for distribution
    zip_path = create_windows_zip(output_dir, app_dir)

    return True, zip_path


def create_windows_zip(output_dir: Path, app_dir: Path) -> Path:
    """Create a zip file of the Windows build for distribution."""
    import zipfile

    zip_name = f"{APP_NAME}-{APP_VERSION}-Windows.zip"
    zip_path = output_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()

    print(f"Creating zip: {zip_name}...")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in app_dir.rglob('*'):
            if file_path.is_file():
                arc_name = Path(APP_NAME) / file_path.relative_to(app_dir)
                zipf.write(file_path, arc_name)

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"Zip created: {zip_path}")
    print(f"Zip size: {zip_size_mb:.1f} MB")

    return zip_path


def build_macos(script_dir: Path, output_dir: Path) -> tuple:
    """Build for macOS using PyInstaller.

    Returns:
        Tuple of (success: bool, artifact_path: Path or None)
    """
    import plistlib

    dist_dir = output_dir / "dist"
    build_dir = output_dir / "build"

    # Clean previous build
    for d in [dist_dir, build_dir]:
        if d.exists():
            print(f"Cleaning {d}...")
            shutil.rmtree(d)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create build_info.txt BEFORE building command so get_data_files can include it
    create_build_info_file(script_dir)

    # Bundle identifier
    bundle_id = f"me.masonasons.{APP_NAME.lower()}"

    main_script = script_dir / "FastGH.pyw"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",  # Create .app bundle
        "--noconfirm",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={output_dir}",
        f"--osx-bundle-identifier={bundle_id}",
    ]

    # Add hidden imports
    for imp in get_hidden_imports():
        cmd.extend(["--hidden-import", imp])

    # Add data files
    for src, dst in get_data_files(script_dir):
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    # Collect keyboard_handler
    cmd.extend(["--collect-all", "keyboard_handler"])

    # Add main script
    cmd.append(str(main_script))

    print(f"Building {APP_NAME} v{APP_VERSION} for macOS...")
    print(f"Output: {output_dir}")
    print()

    try:
        result = subprocess.run(cmd, cwd=script_dir)
    finally:
        # Clean up build_info.txt from source directory
        cleanup_build_info_file(script_dir)

    if result.returncode != 0:
        return False, None

    # The app bundle will be in dist_dir
    app_path = dist_dir / f"{APP_NAME}.app"
    if not app_path.exists():
        print("Error: App bundle not found")
        return False, None

    # Update Info.plist
    plist_path = app_path / "Contents" / "Info.plist"
    if plist_path.exists():
        print("Updating Info.plist...")
        with open(plist_path, 'rb') as f:
            plist = plistlib.load(f)

        plist.update({
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleIdentifier': bundle_id,
            'CFBundleVersion': APP_VERSION,
            'CFBundleShortVersionString': APP_VERSION,
            'NSHumanReadableCopyright': APP_COPYRIGHT,
            'LSMinimumSystemVersion': '10.13',
            'NSHighResolutionCapable': True,
        })

        with open(plist_path, 'wb') as f:
            plistlib.dump(plist, f)

    # Code sign the app (ad-hoc)
    sign_macos_app(app_path)

    # Create DMG
    dmg_path = create_macos_dmg(output_dir, app_path)

    return True, dmg_path


def sign_macos_app(app_path: Path):
    """Sign the macOS app bundle with ad-hoc signature."""
    print("Signing app with ad-hoc signature...")

    # Clear extended attributes
    subprocess.run(["xattr", "-cr", str(app_path)], capture_output=True)

    # Sign app bundle
    result = subprocess.run(
        ["codesign", "--force", "--sign", "-", str(app_path)],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        print("Code signing successful!")
    else:
        print(f"Code signing warning: {result.stderr}")


def create_macos_dmg(output_dir: Path, app_path: Path) -> Path:
    """Create a DMG disk image for macOS distribution."""
    dmg_name = f"{APP_NAME}-{APP_VERSION}.dmg"
    dmg_path = output_dir / dmg_name

    if dmg_path.exists():
        dmg_path.unlink()

    print(f"Creating DMG: {dmg_name}...")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Copy app
        temp_app = temp_path / app_path.name
        shutil.copytree(app_path, temp_app, symlinks=True)

        # Create Applications symlink
        try:
            (temp_path / "Applications").symlink_to("/Applications")
        except OSError:
            pass

        # Create DMG
        result = subprocess.run([
            "hdiutil", "create",
            "-volname", APP_NAME,
            "-srcfolder", str(temp_path),
            "-ov",
            "-format", "UDZO",
            "-imagekey", "zlib-level=9",
            str(dmg_path)
        ], capture_output=True, text=True)

        if result.returncode == 0:
            dmg_size_mb = dmg_path.stat().st_size / (1024 * 1024)
            print(f"DMG created: {dmg_path}")
            print(f"DMG size: {dmg_size_mb:.1f} MB")
        else:
            print(f"DMG creation failed: {result.stderr}")
            return None

    return dmg_path


def main():
    """Build FastGH executable using PyInstaller."""
    script_dir = Path(__file__).parent.resolve()

    platform = get_platform()
    print(f"Detected platform: {platform}")

    output_dir = Path.home() / "app_dist" / APP_NAME

    print(f"Building {APP_NAME} v{APP_VERSION} with PyInstaller...")
    print(f"Output: {output_dir}")
    print()

    if platform == "windows":
        success, artifact_path = build_windows(script_dir, output_dir)
    elif platform == "macos":
        success, artifact_path = build_macos(script_dir, output_dir)
    else:
        print(f"Unsupported platform: {platform}")
        sys.exit(1)

    if success:
        print()
        print("=" * 50)
        print("Build completed successfully!")
        print(f"Output: {output_dir}")

        if artifact_path and artifact_path.exists():
            dest_path = script_dir / artifact_path.name
            print(f"Copying to source folder: {dest_path}")
            shutil.copy2(artifact_path, dest_path)
            print(f"Artifact: {dest_path}")

        print("=" * 50)
    else:
        print()
        print("=" * 50)
        print("Build failed!")
        print("=" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()
