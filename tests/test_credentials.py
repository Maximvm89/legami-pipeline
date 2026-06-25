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
