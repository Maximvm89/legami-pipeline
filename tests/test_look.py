"""Tests for the addon's look helpers (no bpy — pure logic + duck-typed objects)."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "blender_addon"))

from flumen_pipeline import look


def _mesh(name, *mats):
    slots = [types.SimpleNamespace(material=(types.SimpleNamespace(name=m)
                                             if m else None)) for m in mats]
    return types.SimpleNamespace(name=name, material_slots=slots)


def test_look_naming_roundtrip():
    assert look.look_base("frankenstein", "default") == "frankenstein_surface_default"
    assert look.look_filename("frankenstein", "default", 3) == \
        "frankenstein_surface_default_v003.blend"
    assert look.parse_look_filename(
        "frankenstein_surface_default_v003.blend", "frankenstein") == ("default", 3)


def test_parse_look_filename_handles_underscores_in_names():
    # both the asset and look names contain underscores — anchoring on the asset
    # keeps it unambiguous
    assert look.parse_look_filename(
        "hero_armor_surface_battle_damaged_v012.blend", "hero_armor") == \
        ("battle_damaged", 12)
    assert look.parse_look_filename("not_a_look.blend", "hero") is None


def test_normalize_look_name():
    assert look.normalize_look_name("Battle Damaged!") == "battle_damaged"
    assert look.normalize_look_name("  ") == "default"
    assert look.normalize_look_name("") == "default"


def test_surface_task_id_matches_make_id():
    from flumen import tasks
    entity = "characters/frankenstein"
    assert look.surface_task_id(entity) == tasks.make_id("asset", entity, "surface")


def test_assignment_map():
    meshes = [_mesh("Body", "hero_mat"), _mesh("Eye", "lambert1"),
              _mesh("Empty")]  # no material slot
    amap = look.assignment_map(meshes)
    assert amap == {"Body": ["hero_mat"], "Eye": ["lambert1"], "Empty": []}


def test_build_look_manifest():
    amap = {"Body": ["hero_mat"], "Belt": ["hero_mat"], "Eye": ["lambert1", None]}
    tex = [{"name": "b.1002.png"}, {"name": "b.1001.png"}]
    m = look.build_look_manifest("default", 2, amap, tex)
    assert m["look"] == "default" and m["version"] == 2
    assert m["assignments"] == amap
    assert m["materials"] == ["hero_mat", "lambert1"]          # sorted, deduped, no None
    assert [t["name"] for t in m["textures"]] == ["b.1001.png", "b.1002.png"]  # sorted
