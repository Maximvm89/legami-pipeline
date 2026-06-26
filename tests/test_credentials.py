"""Tests for per-user credential save/load and show-level SFTP config."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import animpipe.config as config
from animpipe.config import SFTPCredentials, ProjectConfig


def _isolate_cred_file(tmp_path, monkeypatch):
    """Point the per-user credentials file at a temp path and clear env."""
    cred = tmp_path / "credentials.env"
    monkeypatch.setattr(config, "USER_CRED_FILE", str(cred))
    for k in ("SFTP_HOST", "SFTP_PORT", "SFTP_USER", "SFTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    return cred


def test_signed_in_false_then_true(tmp_path, monkeypatch):
    cred = _isolate_cred_file(tmp_path, monkeypatch)
    assert SFTPCredentials.signed_in() is False
    SFTPCredentials(host="h", port=22, user="marco", password="pw").save_user()
    assert cred.exists()
    assert SFTPCredentials.signed_in() is True


def test_save_then_from_env_roundtrip(tmp_path, monkeypatch):
    _isolate_cred_file(tmp_path, monkeypatch)
    SFTPCredentials(host="sftp.show.com", port=2222, user="marco",
                    password="s3cret").save_user()
    got = SFTPCredentials.from_env(env_file=None)
    assert (got.host, got.port, got.user, got.password) == \
        ("sftp.show.com", 2222, "marco", "s3cret")


def test_save_user_writes_no_password_line_blank(tmp_path, monkeypatch):
    cred = _isolate_cred_file(tmp_path, monkeypatch)
    SFTPCredentials(host="h", port=22, user="u", password=None).save_user()
    assert "SFTP_PASSWORD=\n" in cred.read_text()


def test_project_config_parses_sftp_host(tmp_path):
    (tmp_path / "folder_schema.yaml").write_text("root: {}\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'project:\n  name: "Show"\n  code: "SHW"\n  remote_root: "/p/SHW"\n'
        'sftp:\n  host: "sftp.show.com"\n  port: 2200\n'
        'schema: "folder_schema.yaml"\n')
    pc = ProjectConfig.load(str(cfg))
    assert pc.sftp_host == "sftp.show.com" and pc.sftp_port == 2200


def test_project_config_sftp_defaults_when_absent(tmp_path):
    (tmp_path / "folder_schema.yaml").write_text("root: {}\n")
    cfg = tmp_path / "config.yaml"
    cfg.write_text('project:\n  name: "S"\n  code: "S"\n  remote_root: "/p"\n'
                   'schema: "folder_schema.yaml"\n')
    pc = ProjectConfig.load(str(cfg))
    assert pc.sftp_host is None and pc.sftp_port == 22


def test_remote_root_roundtrips(tmp_path, monkeypatch):
    _isolate_cred_file(tmp_path, monkeypatch)
    SFTPCredentials(host="h", port=22, user="u", password="p",
                    remote_root="/shared/Legami").save_user()
    monkeypatch.delenv("LEGAMI_REMOTE_ROOT", raising=False)
    assert SFTPCredentials.from_env(env_file=None).remote_root == "/shared/Legami"


def test_load_falls_back_to_cached_config(tmp_path, monkeypatch):
    # No local config.yaml, but a cached one the app "downloaded" — load uses it.
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "folder_schema.yaml").write_text("root: {}\n")
    (cache / "config.yaml").write_text(
        'project:\n  name: "Cached"\n  code: "CCH"\n  remote_root: "/shared/CCH"\n'
        'schema: "folder_schema.yaml"\n')
    monkeypatch.setattr(config, "CACHED_CONFIG", str(cache / "config.yaml"))
    pc = ProjectConfig.load(str(tmp_path / "does_not_exist.yaml"))
    assert pc.name == "Cached" and pc.remote_root == "/shared/CCH"


def test_remote_config_dir():
    from animpipe.project_sync import remote_config_dir
    assert remote_config_dir("/shared/Legami/") == "/shared/Legami/02_pipeline"
    assert remote_config_dir("/shared/Legami") == "/shared/Legami/02_pipeline"


def test_publish_config_strips_machine_fields():
    from animpipe.cli import sanitize_published_config
    raw = {"project": {"name": "L", "code": "L", "remote_root": "/r",
                       "local_root": "/Users/someone/Legami"},
           "tools": {"blender_path": "/Applications/Blender.app"},
           "schema": "folder_schema.yaml"}
    out = sanitize_published_config(raw)
    assert "local_root" not in out["project"]   # per-machine — must not be published
    assert "tools" not in out
    assert out["project"]["remote_root"] == "/r"  # show fields preserved
