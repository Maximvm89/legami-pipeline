"""Single source of the toolkit version.

Order of truth:
  1. A VERSION file shipped in the bundle (written by build.py from the git tag)
     — this is what a frozen .exe reports, since git isn't available there.
  2. `git describe --tags` in a source checkout (so dev runs show the live tag).
  3. The hardcoded fallback in flumen.__init__.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _bundle_version() -> str | None:
    """VERSION file beside the executable (or inside the bundle) when frozen."""
    if not getattr(sys, "frozen", False):
        return None
    for base in (os.path.dirname(sys.executable), getattr(sys, "_MEIPASS", "")):
        if not base:
            continue
        try:
            with open(os.path.join(base, "VERSION"), encoding="utf-8") as fh:
                v = fh.read().strip()
                if v:
                    return v
        except OSError:
            continue
    return None


def _git_describe() -> str | None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        out = subprocess.run(
            ["git", "describe", "--tags", "--always", "--dirty"],
            cwd=root, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 and out.stdout.strip() else None


def get_version() -> str:
    from . import __version__ as fallback
    return _bundle_version() or _git_describe() or fallback
