"""Tests for the addon's texture-publish helpers (no bpy — pure file/string logic)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blender_addon"))

from flumen_pipeline import textures


def test_sha1_file_matches_known(tmp_path):
    f = tmp_path / "t.png"
    f.write_bytes(b"hello")
    # sha1("hello") is a fixed, well-known digest.
    assert textures.sha1_file(str(f)) == "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"


def test_hashed_name_is_content_addressed():
    sha = "aaf4c61ddcc5e8a2dabede0f3b482cd9aea9434d"
    assert textures.hashed_name("diffuse", ".png", sha) == "diffuse.aaf4c61d.png"
    # tolerates an extension without the dot, and an empty extension
    assert textures.hashed_name("d", "png", sha) == "d.aaf4c61d.png"
    assert textures.hashed_name("d", "", sha) == "d.aaf4c61d"


def test_hashed_name_distinguishes_content():
    # same basename, different content -> different published names (no clobber)
    a = textures.hashed_name("tex", ".png", "1111111122223333")
    b = textures.hashed_name("tex", ".png", "4444444455556666")
    assert a != b


def test_texture_entry_and_manifest(tmp_path):
    f = tmp_path / "diffuse.png"
    f.write_bytes(b"hello")
    sha = textures.sha1_file(str(f))
    name = textures.hashed_name("diffuse", ".png", sha)
    e = textures.texture_entry(str(f), name, 2048, 2048, "sRGB", sha)
    assert e == {"name": name, "colorspace": "sRGB", "width": 2048,
                 "height": 2048, "bytes": 5, "sha1": sha}

    # a second texture, given out of order, to check the manifest sorts by name
    g = tmp_path / "normal.exr"
    g.write_bytes(b"world")
    e2 = textures.texture_entry(str(g), "normal.aaaaaaaa.exr", 1024, 1024, "Non-Color")
    m = textures.build_manifest([e, e2], "hero_surface", 3)
    assert m["base"] == "hero_surface" and m["version"] == 3
    assert [t["name"] for t in m["textures"]] == sorted([e["name"], e2["name"]])
