"""Local project folder resolution + persistence.

Regression for issues #3 (turntable used the auto-rig instead of the show
template) and #4 (the local folder had to be re-set every launch). Both came from
resolved_local_root() ignoring the launcher's LEGAMI_PROJECT_ROOT env and from the
folder being stored only in the cache config.yaml, which is re-downloaded (and so
wiped) on each sign-in.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from animpipe import config as cfgmod
from animpipe.config import ProjectConfig


def _cfg(local_root=None):
    return ProjectConfig(name="Legami", code="LEGAMI", remote_root="/shared/Legami",
                         schema={}, assets={}, shots={}, local_root=local_root)


def _isolate(tmp_path, monkeypatch):
    """Point the per-user store at a temp dir and clear the env var."""
    monkeypatch.setattr(cfgmod, "LOCAL_ROOT_FILE", str(tmp_path / "local_root"))
    monkeypatch.delenv("LEGAMI_PROJECT_ROOT", raising=False)


def test_default_when_nothing_set(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    c = _cfg()
    assert c.resolved_local_root().endswith("Legami/LEGAMI".replace("/", __import__("os").sep))


def test_config_local_root_wins_over_default(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    c = _cfg(local_root="/explicit/from/config")
    assert c.resolved_local_root() == "/explicit/from/config"


def test_per_user_file_survives_blank_config(tmp_path, monkeypatch):
    # The cached config has no local_root, but the per-user file does -> use it.
    _isolate(tmp_path, monkeypatch)
    cfgmod.save_local_root("E:/Legami_4")
    assert cfgmod.load_local_root() == "E:/Legami_4"
    assert _cfg().resolved_local_root() == "E:/Legami_4"


def test_env_overrides_everything(tmp_path, monkeypatch):
    # The launcher exports LEGAMI_PROJECT_ROOT; subprocesses must honor it so the
    # turntable reads project_settings.json (and its template) from the right folder.
    _isolate(tmp_path, monkeypatch)
    cfgmod.save_local_root("E:/Legami_4")
    monkeypatch.setenv("LEGAMI_PROJECT_ROOT", "E:/from_launcher")
    c = _cfg(local_root="/explicit/from/config")
    assert c.resolved_local_root() == "E:/from_launcher"


def test_save_is_round_trippable_and_trimmed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cfgmod.save_local_root("  E:/Legami_4  ")
    assert cfgmod.load_local_root() == "E:/Legami_4"
