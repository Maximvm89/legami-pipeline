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




def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", action="store_true", help="zip the bundle when done")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
