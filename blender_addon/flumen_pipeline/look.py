"""Look (shader) publishing helpers — pure logic, no `bpy`.

A "look" is a character's materials + textures + a map of which material sits on
which mesh, published so a downstream step (rig, layout, …) can re-apply it onto
the clean character. This module holds the bpy-free pieces (naming, the
assignment map, manifest assembly) so they're unit-testable outside Blender; the
operator supplies the live mesh/material objects.

A look file is named ``<asset>_surface_<look>_vNNN.blend`` — e.g.
``frankenstein_surface_default_v003.blend`` — so one character can carry several
named looks, each versioned independently.
"""

from __future__ import annotations

import re


def look_base(asset_name: str, look: str) -> str:
    """Publish base for a look, e.g. 'frankenstein_surface_default'. Feeds
    next_version() so each named look versions on its own track."""
    return f"{asset_name}_surface_{look}"


def look_filename(asset_name: str, look: str, version: int) -> str:
    return f"{look_base(asset_name, look)}_v{version:03d}.blend"


def parse_look_filename(filename: str, asset_name: str):
    """(look, version) from a look .blend name given the known asset, else None.
    Anchoring on the asset name keeps parsing unambiguous when the asset or look
    name itself contains underscores."""
    m = re.match(re.escape(asset_name) + r"_surface_(.+)_v(\d+)\.blend$", filename)
    return (m.group(1), int(m.group(2))) if m else None


def surface_task_id(entity: str) -> str:
    """Id of the surface task that owns an asset's looks — mirrors
    flumen.tasks.make_id('asset', entity, 'surface'). Lets a downstream task
    (rig, etc.) find the looks published for the same character."""
    return re.sub(r"[^a-z0-9._-]+", "_", f"asset-{entity}-surface".lower())


def normalize_look_name(name: str) -> str:
    """A safe look slug: lowercase, spaces/punctuation -> underscore. Empty ->
    'default'."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "default"


def assignment_map(meshes) -> dict:
    """{mesh_name: [slot material names]} for the meshes being published. Duck-typed:
    each mesh exposes .name and .material_slots (each slot a .material with .name or
    None). This is what downstream uses to re-attach materials by mesh name."""
    amap = {}
    for o in meshes:
        slots = []
        for s in getattr(o, "material_slots", []) or []:
            mat = getattr(s, "material", None)
            slots.append(getattr(mat, "name", None) if mat is not None else None)
        amap[getattr(o, "name", "")] = slots
    return amap


def build_look_manifest(look: str, version: int, amap: dict, textures: list) -> dict:
    """The <base>_vNNN.manifest.json payload for a look: which materials go on which
    meshes, plus the textures it carries (each already content-hashed)."""
    return {
        "look": look,
        "version": int(version),
        "assignments": amap,
        "materials": sorted({m for slots in amap.values() for m in slots if m}),
        "textures": sorted(textures, key=lambda t: t.get("name", "")),
    }
