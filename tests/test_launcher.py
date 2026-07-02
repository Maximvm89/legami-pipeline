"""Tests for flumen.launcher path resolution (source vs frozen)."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flumen import launcher


def test_bootstrap_path_source(monkeypatch):
    # From source: next to the module, and it must actually exist (it's the file
    # Blender runs to auto-load the add-on).
    monkeypatch.delattr(launcher.sys, "frozen", raising=False)
    p = launcher._bootstrap_path()
    assert p == str(Path(launcher.__file__).parent / "blender_bootstrap.py")
    assert os.path.isfile(p)


def test_bootstrap_path_frozen(monkeypatch):
    # Frozen: under the PyInstaller bundle's flumen/ data dir (where the spec
    # ships it), NOT inside the unreachable archive.
    monkeypatch.setattr(launcher.sys, "frozen", True, raising=False)
    monkeypatch.setattr(launcher.sys, "_MEIPASS", "/bundle", raising=False)
    assert launcher._bootstrap_path() == os.path.join(
        "/bundle", "flumen", "blender_bootstrap.py")
