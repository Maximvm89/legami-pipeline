"""Tests for animpipe.cli commands that need server interaction (faked)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from animpipe import cli, tasks
from test_tasks import FakeSrv


class _DownloadSrv(FakeSrv):
    """FakeSrv + a download that just records the (remote, local) pair."""
    def __init__(self):
        super().__init__()
        self.downloads = []

    def download(self, remote, local):
        self.downloads.append((remote, local))

    def download_dir(self, remote, local):
        self.downloads.append((remote + "/*", local))
        return 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(monkeypatch, srv, remote_root="/r", local_root="/local"):
    import types as _t
    monkeypatch.setattr(cli, "ProjectConfig",
                        _t.SimpleNamespace(load=lambda _c: _t.SimpleNamespace(
                            remote_root=remote_root,
                            resolved_local_root=lambda: local_root)))
    monkeypatch.setattr(cli, "SFTPCredentials",
                        _t.SimpleNamespace(from_env=lambda _e: _t.SimpleNamespace(
                            user="marco")))
    monkeypatch.setattr(cli, "SFTPClient", lambda creds: srv)


def _args(**kw):
    import types as _t
    base = dict(config="config.yaml", env=".env")
    base.update(kw)
    return _t.SimpleNamespace(**base)


def test_fetch_publish_resolves_newest_via_step(monkeypatch, capsys, tmp_path):
    srv = _DownloadSrv()
    # a model task with two published versions
    mt = tasks.save_task(srv, "/r", tasks.new_task("asset", "characters/hero", "model"))
    tasks.publish_task(srv, "/r", "marco", ["/tmp/hero_model_v001.blend"], mt["id"])
    tasks.publish_task(srv, "/r", "marco", ["/tmp/hero_model_v002.blend"], mt["id"])
    # the SURFACE task asks for its model sibling via --step model
    st = tasks.save_task(srv, "/r",
                         tasks.new_task("asset", "characters/hero", "surface"))

    _patch(monkeypatch, srv, local_root=str(tmp_path))
    rc = cli.cmd_fetch_publish(_args(task=st["id"], step="model", ext=".blend",
                                     into=None))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    # downloaded the NEWEST model publish to the local mirror, and printed its path
    remote, local = srv.downloads[-1]
    assert remote.endswith("hero_model_v002.blend")
    assert local == out and local.endswith("hero_model_v002.blend")


def _surface_with_looks(srv):
    st = tasks.save_task(srv, "/r",
                         tasks.new_task("asset", "characters/frankenstein", "surface"))
    pub = "03_assets/characters/frankenstein/surface/publish/"
    st["publishes"] = [
        {"files": [pub + "frankenstein_surface_default_v001.blend",
                   pub + "frankenstein_surface_default_v001.manifest.json"],
         "time": 1, "by": "marco"},
        {"files": [pub + "frankenstein_surface_default_v002.blend",
                   pub + "frankenstein_surface_default_v002.manifest.json"],
         "time": 2, "by": "marco"},
    ]
    tasks.save_task(srv, "/r", st)
    return st


def test_list_looks_json(monkeypatch, capsys):
    import json
    srv = _DownloadSrv()
    st = _surface_with_looks(srv)
    _patch(monkeypatch, srv)
    rc = cli.cmd_list_looks(_args(task=st["id"]))
    assert rc == 0
    looks = json.loads(capsys.readouterr().out.strip())
    assert [(l["look"], l["version"]) for l in looks] == [("default", 2)]


def test_fetch_look_downloads_blend_manifest_and_textures(monkeypatch, capsys, tmp_path):
    srv = _DownloadSrv()
    st = _surface_with_looks(srv)
    _patch(monkeypatch, srv, local_root=str(tmp_path))
    rc = cli.cmd_fetch_look(_args(task=st["id"], look="default"))
    assert rc == 0
    out = capsys.readouterr().out.strip().splitlines()[-1]
    assert out.endswith("frankenstein_surface_default_v002.blend")  # newest
    fetched = [r for r, _ in srv.downloads]
    assert any(r.endswith("frankenstein_surface_default_v002.blend") for r in fetched)
    assert any(r.endswith(".manifest.json") for r in fetched)
    assert any(r.endswith("/textures/*") for r in fetched)          # textures dir


def test_fetch_look_unknown_name_errors(monkeypatch, capsys, tmp_path):
    srv = _DownloadSrv()
    st = _surface_with_looks(srv)
    _patch(monkeypatch, srv, local_root=str(tmp_path))
    rc = cli.cmd_fetch_look(_args(task=st["id"], look="nope"))
    assert rc == 1
    assert "no look" in capsys.readouterr().err


def test_fetch_publish_errors_when_no_publish(monkeypatch, capsys):
    srv = _DownloadSrv()
    mt = tasks.save_task(srv, "/r", tasks.new_task("asset", "characters/hero", "model"))
    st = tasks.save_task(srv, "/r",
                         tasks.new_task("asset", "characters/hero", "surface"))
    _patch(monkeypatch, srv)
    rc = cli.cmd_fetch_publish(_args(task=st["id"], step="model", ext=".blend",
                                     into=None))
    assert rc == 1
    assert "no published" in capsys.readouterr().err
