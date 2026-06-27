#!/usr/bin/env python3
"""Build the standalone Legami bundle (CLI + Workspace app) with PyInstaller.

Runs the shared spec, then stages the files an artist needs next to the two
executables in dist/Legami/. PyInstaller cannot cross-compile: run this ON the
target OS (macOS build for Mac artists, Windows build for Windows artists).

    python build.py            # clean build into dist/Legami
    python build.py --zip      # also zip dist/Legami -> dist/Legami-<os>.zip
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "Legami")

# Files/dirs copied alongside the executables. The bundle is show-agnostic — the
# artist signs in (host + project root + login) and the app downloads the show
# config from the server, so nothing project-specific is shipped here.
SIDE_FILES = [
    "README.md",
]
SIDE_DIRS = [
    "blender_addon",     # addon the launcher auto-loads / installs into Blender
]


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def _version() -> str:
    """The build version from the git tag (what `git describe` reports), so a
    release built from tag v0.1.0 stamps 'v0.1.0'. Falls back for untagged trees."""
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"],
                             cwd=ROOT, capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "0.0.0+dev"




def _find_iscc() -> str | None:
    """Locate the Inno Setup command-line compiler (Windows only)."""
    import glob

    # 1. Explicit override.
    override = os.environ.get("LEGAMI_ISCC")
    if override and os.path.isfile(override):
        return override
    # 2. On PATH.
    for name in ("ISCC", "iscc"):
        found = shutil.which(name)
        if found:
            return found
    # 3. Registry — Inno Setup records its install dir under its uninstall key
    #    (HKLM for all-users, HKCU for a per-user install).
    try:
        import winreg
        keys = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 5_is1")
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key in keys:
                try:
                    with winreg.OpenKey(root, key) as k:
                        loc = winreg.QueryValueEx(k, "InstallLocation")[0]
                    cand = os.path.join(loc, "ISCC.exe")
                    if os.path.isfile(cand):
                        return cand
                except OSError:
                    continue
    except ImportError:
        pass
    # 4. Default install folders (glob copes with the version in the folder name).
    bases = [os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    for base in filter(None, bases):
        for cand in glob.glob(os.path.join(base, "Inno Setup*", "ISCC.exe")):
            if os.path.isfile(cand):
                return cand
    return None


def _make_installer(version: str) -> int:
    """Compile packaging/legami.iss into dist/Legami-Setup-<version>.exe."""
    if os.name != "nt":
        print("error: --installer builds a Windows installer and must run on "
              "Windows (Inno Setup is Windows-only).", file=sys.stderr)
        return 1
    iscc = _find_iscc()
    if not iscc:
        print("error: Inno Setup (ISCC.exe) not found.\n"
              "  Install it:  winget install JRSoftware.InnoSetup\n"
              "  (or download from https://jrsoftware.org/isdl.php)\n"
              "  If it's installed somewhere custom, set LEGAMI_ISCC to the full "
              "path of ISCC.exe and re-run.\n"
              "  The bundle in dist\\Legami\\ is already built — you can also compile "
              "the installer directly:\n"
              "    \"C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe\" "
              "/DAppVersion=0.1.0 packaging\\legami.iss",
              file=sys.stderr)
        return 1
    print(f"Using Inno Setup: {iscc}")
    iss = os.path.join(ROOT, "packaging", "legami.iss")
    _run([iscc, f"/DAppVersion={version.lstrip('v')}", iss])
    out = os.path.join(ROOT, "dist", f"Legami-Setup-{version.lstrip('v')}.exe")
    print(f"\nInstaller ready: {out}" if os.path.isfile(out)
          else "warning: ISCC ran but the installer wasn't found where expected.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", action="store_true", help="zip the bundle when done")
    ap.add_argument("--installer", action="store_true",
                    help="compile a Windows installer with Inno Setup (Windows only)")
    args = ap.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("error: PyInstaller not installed. Run:\n"
              "  pip install -r requirements-build.txt", file=sys.stderr)
        return 1

    # Clean previous build/dist so stale files never linger.
    for d in ("build", "dist"):
        shutil.rmtree(os.path.join(ROOT, d), ignore_errors=True)

    _run([sys.executable, "-m", "PyInstaller",
          os.path.join("packaging", "legami.spec"), "--noconfirm"])

    if not os.path.isdir(DIST):
        print(f"error: expected bundle at {DIST}", file=sys.stderr)
        return 1

    for name in SIDE_FILES:
        src = os.path.join(ROOT, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(DIST, name))
    for name in SIDE_DIRS:
        src = os.path.join(ROOT, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(DIST, name), dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))

    # Stamp the version so the frozen app can report it (git isn't available
    # to a built .exe).
    version = _version()
    with open(os.path.join(DIST, "VERSION"), "w", encoding="utf-8") as fh:
        fh.write(version + "\n")

    print(f"\nBundle ready: {DIST}  (version {version})")
    for exe in sorted(os.listdir(DIST)):
        path = os.path.join(DIST, exe)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"  executable: {exe}")

    if args.zip:
        tag = "windows" if os.name == "nt" else platform.system().lower()
        archive = os.path.join(ROOT, "dist", f"Legami-{tag}-{version}")
        shutil.make_archive(archive, "zip", os.path.join(ROOT, "dist"), "Legami")
        print(f"  zipped: {archive}.zip")

    if args.installer:
        return _make_installer(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
