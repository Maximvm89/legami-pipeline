"""Set-dressing model: named, versioned prop layouts published over an environment.

A dressing publish is an INSTANCE MANIFEST — a JSON list of {asset, source_step,
blend_rel, transform} entries referencing published assets — plus the working
.blend for reference. Light, diffable, rebuildable: a shot rebuilds the layout by
linking each referenced publish and applying the stored transforms, so props stay
linked/overridable per shot instead of being baked into one heavy file.

Naming mirrors looks: '<asset>_dressing_<name>_vNNN.blend' + sibling
'.manifest.json', published through the ordinary task publish path. Pure helpers —
no bpy, no network.
"""

from __future__ import annotations

import re

DRESSING_STEP = "dressing"
MANIFEST_SUFFIX = ".manifest.json"


def normalize_dressing_name(name: str) -> str:
    """A safe dressing slug: lowercase, spaces/punctuation -> underscore. Empty ->
    'default'. (Same rules as look names, so artists learn one convention.)"""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "default"


def dressing_base(asset_name: str, name: str) -> str:
    """Versionless publish base: '<asset>_dressing_<name>'."""
    return f"{asset_name}_dressing_{normalize_dressing_name(name)}"


def dressing_filename(asset_name: str, name: str, version: int) -> str:
    return f"{dressing_base(asset_name, name)}_v{version:03d}.blend"


def parse_dressing_filename(filename: str, asset_name: str):
    """(dressing_name, version) from a publish file name, or None. Anchored on the
    asset's own name so underscores in either stay unambiguous."""
    m = re.match(re.escape(asset_name) + r"_dressing_(.+)_v(\d+)\.blend$", filename)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def manifest_name_for(blend_filename: str) -> str:
    return blend_filename[:-len(".blend")] + MANIFEST_SUFFIX


def matrix_to_rows(mat) -> list[list[float]]:
    """A 4x4 matrix (duck-typed: iterable of 4 rows of 4 floats — mathutils.Matrix
    or nested lists) -> nested lists, rounded for stable/diffable manifests."""
    return [[round(float(v), 6) for v in row] for row in mat]


def build_dressing_manifest(name: str, version: int, environment: dict | None,
                            props: list[dict], workfile_rel: str = "") -> dict:
    """The published manifest. `environment` = {asset, source_step, blend_rel} of
    the environment the props were placed over; `props` entries carry
    {id, asset, source_step, blend_rel, collection, object, matrix_world}."""
    return {
        "dressing": normalize_dressing_name(name),
        "version": int(version),
        "environment": dict(environment) if environment else {},
        "workfile_rel": workfile_rel or "",
        "props": [dict(p) for p in props or []],
    }
