"""Texture-publish helpers for the surface department.

No `bpy` import — pure file/string logic, so it is unit-testable outside Blender.
The Blender operator collects images (which needs bpy) and calls into here to
hash, name, and manifest them. Keeping a published look "safe" means: every
texture it references is copied beside the .blend (under publish/textures/) with
a content-addressed name, and a manifest records each one's identity (resolution,
colorspace, size, sha1) so missing or altered textures are detectable later.
"""

from __future__ import annotations

import hashlib
import os


def sha1_file(path: str, _chunk: int = 1 << 20) -> str:
    """SHA-1 of a file's contents (streamed, so big EXRs don't blow memory)."""
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(_chunk), b""):
            h.update(block)
    return h.hexdigest()


def hashed_name(stem: str, ext: str, sha1: str) -> str:
    """Content-addressed file name: '<stem>.<sha1[:8]><ext>'. Two textures with the
    same basename but different content get distinct names; identical content maps
    to the same name (natural dedupe)."""
    ext = ext if ext.startswith(".") or ext == "" else "." + ext
    return f"{stem}.{sha1[:8]}{ext}"


def texture_entry(src_path: str, name: str, width: int, height: int,
                  colorspace: str, sha1: str | None = None) -> dict:
    """One manifest row for a copied texture. `name` is the published file name
    (under publish/textures/); fields capture its identity for verification."""
    sha1 = sha1 or sha1_file(src_path)
    return {
        "name": name,
        "colorspace": colorspace or "",
        "width": int(width),
        "height": int(height),
        "bytes": os.path.getsize(src_path),
        "sha1": sha1,
    }


def build_manifest(entries: list[dict], base: str, version: int) -> dict:
    """The <base>_vNNN.manifest.json payload: the publish identity plus every
    texture it carries, sorted by name for stable diffs."""
    return {
        "base": base,
        "version": int(version),
        "textures": sorted(entries, key=lambda e: e["name"]),
    }
