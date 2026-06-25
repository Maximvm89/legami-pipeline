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

# Files/dirs copied alongside the executables so the app is self-contained.
# (Per-user config.yaml/.env are created from these examples on first run.)
SIDE_FILES = [
    "folder_schema.yaml",
    "README.md",
]
SIDE_DIRS = [
    "blender_addon",     # addon the launcher auto-loads / installs into Blender
    "color_pipeline",    # pinned OCIO config + color policy
    "pipeline_config",   # default project_settings.json
]


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def _read_env_value(key: str) -> str:
    """Read a single KEY from the build box's .env (no dotenv dependency)."""
    if os.environ.get(key):
        return os.environ[key]
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(f"{key}=") and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def bake_show_config(dist_dir: str) -> bool:
    """If the build box has a project config, bake a sanitized, preconfigured
    config.yaml into the bundle (show settings + SFTP host, NO local paths or
    credentials) so artists download a ready-to-run bundle. Returns True if baked.
    """
    import yaml
    cfg_path = os.path.join(ROOT, "config.yaml")
    if not os.path.isfile(cfg_path):
        return False
    with open(cfg_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    project = raw.get("project") or {}
    if not all(project.get(k) for k in ("name", "code", "remote_root")):
        return False
    sftp = raw.get("sftp") or {}
    host = sftp.get("host") or _read_env_value("SFTP_HOST")
    port = sftp.get("port") or _read_env_value("SFTP_PORT") or 22
    lines = [
        "# Preconfigured for this show by the pipeline TD — do not edit.",
        "# Your login is entered in the Workspace app (Sign in…), not here.",
        "project:",
        f'  name: "{project["name"]}"',
        f'  code: "{project["code"]}"',
        f'  remote_root: "{project["remote_root"]}"',
        "schema: \"folder_schema.yaml\"",
    ]
    if host:
        lines += ["sftp:", f'  host: "{host}"', f"  port: {int(port)}"]
    lines += ["tools:", "  blender_path: null", ""]
    with open(os.path.join(dist_dir, "config.yaml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    return True


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

    if bake_show_config(DIST):
        print("  baked preconfigured config.yaml (show settings + SFTP host)")
    else:
        # No show config on this box — ship the examples for a manual setup.
        for name in ("config.example.yaml", ".env.example"):
            src = os.path.join(ROOT, name)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(DIST, name))
        print("  no show config.yaml found — shipped config.example.yaml instead")

    print(f"\nBundle ready: {DIST}")
    for exe in sorted(os.listdir(DIST)):
        path = os.path.join(DIST, exe)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            print(f"  executable: {exe}")

    if args.zip:
        tag = "windows" if os.name == "nt" else platform.system().lower()
        archive = os.path.join(ROOT, "dist", f"Legami-{tag}")
        shutil.make_archive(archive, "zip", os.path.join(ROOT, "dist"), "Legami")
        print(f"  zipped: {archive}.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
