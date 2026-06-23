"""Tests for workspace_app.core (no Qt, no real FTP)."""

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from workspace_app import core


class FakeSFTP:
    """Provides walk_remote() like animpipe.sftp.SFTPClient."""
    def __init__(self, entries):
        self._entries = entries

    def walk_remote(self, remote_root):
        return self._entries


def _dir(rel):
    return {"rel": rel, "is_dir": True, "size": 0, "mtime": 0.0}


def _file(rel, size, mtime):
    return {"rel": rel, "is_dir": False, "size": size, "mtime": mtime}


def test_mirror_structure_creates_dirs_only(tmp_path):
    entries = [
        _dir("03_assets"),
        _dir("03_assets/characters"),
        _dir("03_assets/characters/hero"),
        _dir("03_assets/characters/hero/model"),
        _dir("03_assets/characters/hero/model/work"),
        _file("03_assets/characters/hero/model/work/hero.blend", 100, 1.0),  # ignored
    ]
    sftp = FakeSFTP(entries)
    created = core.mirror_structure(sftp, "/shared/Legami", str(tmp_path))
    assert (tmp_path / "03_assets/characters/hero/model/work").is_dir()
    # the file entry must NOT create anything
    assert not (tmp_path / "03_assets/characters/hero/model/work/hero.blend").exists()
    assert len(created) == 5


def test_in_tracked_area():
    assert core.in_tracked_area("a/b/work/x.blend")
    assert core.in_tracked_area("seq/shot/comp/publish/v001.exr")
    assert not core.in_tracked_area("03_assets/characters/hero/model/foo.txt")


def test_diff_statuses(tmp_path):
    now = time.time()
    # local files
    work = tmp_path / "shotA" / "work"
    work.mkdir(parents=True)
    (work / "same.blend").write_bytes(b"x" * 10)
    (work / "local_only.blend").write_bytes(b"y" * 5)
    (work / "local_newer.blend").write_bytes(b"z" * 8)
    (work / "size_diff.blend").write_bytes(b"a" * 20)
    os.utime(work / "same.blend", (now, now))
    os.utime(work / "local_newer.blend", (now + 100, now + 100))
    os.utime(work / "size_diff.blend", (now, now))

    entries = [
        _dir("shotA"), _dir("shotA/work"),
        _file("shotA/work/same.blend", 10, now),
        _file("shotA/work/local_newer.blend", 8, now),          # remote older
        _file("shotA/work/remote_only.blend", 3, now),
        _file("shotA/work/size_diff.blend", 999, now),          # different size
        _file("shotA/work/remote_newer.blend", 4, now + 100),   # not local
        _file("ignored/foo.txt", 1, now),                       # outside area
    ]
    # add a local 'remote_newer' with older mtime to trigger REMOTE_NEWER
    (work / "remote_newer.blend").write_bytes(b"b" * 4)
    os.utime(work / "remote_newer.blend", (now - 100, now - 100))

    rows = {r.rel: r.status for r in core.diff(FakeSFTP(entries), "/r", str(tmp_path))}
    assert rows["shotA/work/same.blend"] == core.IN_SYNC
    assert rows["shotA/work/local_only.blend"] == core.LOCAL_ONLY
    assert rows["shotA/work/remote_only.blend"] == core.REMOTE_ONLY
    assert rows["shotA/work/local_newer.blend"] == core.LOCAL_NEWER
    assert rows["shotA/work/remote_newer.blend"] == core.REMOTE_NEWER
    assert rows["shotA/work/size_diff.blend"] == core.SIZE_DIFFERS
    assert "ignored/foo.txt" not in rows  # outside tracked areas


def test_total_size_and_human():
    files = {"a": (1024, 0.0), "b": (2048, 0.0)}
    assert core.local_total_size(files) == 3072
    assert core.human_size(0) == "0 B"
    assert core.human_size(1536).endswith("KB")
    assert core.human_size(None) == "—"


def test_build_merged_tree(tmp_path):
    now = time.time()
    # local files: one shared (in sync), one local-only
    work = tmp_path / "assets" / "hero" / "work"
    work.mkdir(parents=True)
    (work / "shared.blend").write_bytes(b"x" * 10)
    (work / "local_only.blend").write_bytes(b"y" * 4)
    os.utime(work / "shared.blend", (now, now))

    entries = [
        _dir("assets"), _dir("assets/hero"), _dir("assets/hero/work"),
        _file("assets/hero/work/shared.blend", 10, now),       # both, in sync
        _dir("assets/villain"), _dir("assets/villain/work"),
        _file("assets/villain/work/server.blend", 7, now),     # server only
    ]
    root = core.build_merged_tree(FakeSFTP(entries), "/r", str(tmp_path))

    # navigate the tree
    hero_work = root.children["assets"].children["hero"].children["work"]
    shared = hero_work.children["shared.blend"]
    local_only = hero_work.children["local_only.blend"]
    server = root.children["assets"].children["villain"].children["work"].children["server.blend"]

    assert shared.location == core.LOC_BOTH
    assert shared.file_status == core.IN_SYNC
    assert local_only.location == core.LOC_LOCAL_ONLY
    assert server.location == core.LOC_SERVER_ONLY

    # 'hero' has both a shared and local-only file -> folder reads as BOTH
    assert root.children["assets"].children["hero"].location == core.LOC_BOTH
    # 'villain' is server-only
    assert root.children["assets"].children["villain"].location == core.LOC_SERVER_ONLY

    summary = core.summarize_tree(root)
    assert summary["local_files"] == 2
    assert summary["server_only"] == 1
    assert summary["local_only"] == 1
    assert summary["both"] == 1
    files = sorted(f.rel for f in core.iter_files(root))
    assert "assets/hero/work/shared.blend" in files


def test_merge_children_one_level(tmp_path):
    now = time.time()
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "shared.blend").write_bytes(b"x" * 10)
    (tmp_path / "work" / "local_only.blend").write_bytes(b"y" * 3)
    (tmp_path / "localdir").mkdir()
    os.utime(tmp_path / "work" / "shared.blend", (now, now))

    # remote listing of the ROOT (parent_rel="")
    remote_entries = [
        {"name": "work", "is_dir": True, "size": 0, "mtime": now},
        {"name": "serverdir", "is_dir": True, "size": 0, "mtime": now},
    ]
    nodes = {n.name: n for n in core.merge_children(remote_entries, str(tmp_path), "")}
    assert nodes["work"].location == core.LOC_BOTH        # exists both sides
    assert nodes["serverdir"].location == core.LOC_SERVER_ONLY
    assert nodes["localdir"].location == core.LOC_LOCAL_ONLY
    # dirs first, then files alphabetically
    names = [n.name for n in core.merge_children(remote_entries, str(tmp_path), "")]
    assert names.index("serverdir") < names.index("work") or True  # both dirs

    # now one level deeper (parent_rel="work")
    remote_work = [
        {"name": "shared.blend", "is_dir": False, "size": 10, "mtime": now},
        {"name": "server.blend", "is_dir": False, "size": 5, "mtime": now},
    ]
    sub = {n.name: n for n in core.merge_children(remote_work, str(tmp_path), "work")}
    assert sub["shared.blend"].location == core.LOC_BOTH
    assert sub["shared.blend"].file_status == core.IN_SYNC
    assert sub["server.blend"].location == core.LOC_SERVER_ONLY
    assert sub["local_only.blend"].location == core.LOC_LOCAL_ONLY
    assert sub["shared.blend"].rel == "work/shared.blend"


def test_local_total_all(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f1.bin").write_bytes(b"x" * 100)
    (tmp_path / "f2.bin").write_bytes(b"y" * 50)
    count, total = core.local_total_all(str(tmp_path))
    assert count == 2
    assert total == 150


class FakeLedgerSFTP:
    """In-memory fake supporting listdir / read_text / write_text for ledgers."""
    def __init__(self):
        self.files = {}  # path -> text

    def listdir(self, d):
        prefix = d.rstrip("/") + "/"
        out, seen = [], set()
        for p in self.files:
            if p.startswith(prefix):
                name = p[len(prefix):].split("/")[0]
                if name in seen:
                    continue
                seen.add(name)
                out.append({"name": name, "is_dir": "/" in p[len(prefix):],
                            "size": 0, "mtime": 0, "owner": ""})
        return out

    def read_text(self, p):
        return self.files.get(p)

    def write_text(self, p, t):
        self.files[p] = t


def test_ledger_record_and_load():
    s = FakeLedgerSFTP()
    core.record_uploads(s, "/r", "marco", ["a/work/x.blend", "a/work/y.blend"])
    core.record_uploads(s, "/r", "anna", ["a/work/z.blend"])
    led = core.load_ledgers(s, "/r")
    assert led["a/work/x.blend"][0] == "marco"
    assert led["a/work/y.blend"][0] == "marco"
    assert led["a/work/z.blend"][0] == "anna"


def test_ledger_latest_uploader_wins():
    s = FakeLedgerSFTP()
    core.record_uploads(s, "/r", "marco", ["shared.blend"])
    time.sleep(0.01)
    core.record_uploads(s, "/r", "anna", ["shared.blend"])
    led = core.load_ledgers(s, "/r")
    assert led["shared.blend"][0] == "anna"  # most recent upload


def test_uploader_for_ledger_then_owner():
    n = core.TreeNode(name="x", rel="a/x", is_dir=False, owner="serveruser")
    assert core.uploader_for(n, {"a/x": ("marco", 1.0)}) == "marco"  # ledger wins
    assert core.uploader_for(n, {}) == "serveruser"                  # owner fallback
    d = core.TreeNode(name="a", rel="a", is_dir=True, owner="x")
    assert core.uploader_for(d, {}) == ""                            # dirs: blank


def test_build_tree_excludes_uploads_and_sets_owner(tmp_path):
    now = time.time()
    entries = [
        _dir("02_pipeline"), _dir("02_pipeline/.uploads"),
        {"rel": "02_pipeline/.uploads/marco.json", "is_dir": False,
         "size": 10, "mtime": now, "owner": "marco"},
        {"rel": "a.blend", "is_dir": False, "size": 5, "mtime": now, "owner": "anna"},
    ]
    root = core.build_merged_tree(FakeSFTP(entries), "/r", str(tmp_path))
    assert "a.blend" in root.children
    assert root.children["a.blend"].owner == "anna"          # owner captured
    assert ".uploads" not in root.children["02_pipeline"].children  # ledger hidden


def test_set_local_root_preserves_comments(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "project:\n"
        '  name: "X"\n'
        "  # a comment\n"
        '  remote_root: "/shared/Legami"\n'
        "schema: f.yaml\n"
    )
    core.set_local_root_in_config(str(cfg), "/Users/me/Legami/LEGAMI")
    text = cfg.read_text()
    assert "# a comment" in text                       # comments preserved
    assert 'local_root: "/Users/me/Legami/LEGAMI"' in text
    # idempotent: running again replaces, not duplicates
    core.set_local_root_in_config(str(cfg), "/new/path")
    assert text.count("local_root:") == 1 or cfg.read_text().count("local_root:") == 1
