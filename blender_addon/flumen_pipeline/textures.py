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


_FORMAT_BY_EXT = {
    ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".exr": "OPEN_EXR",
    ".tif": "TIFF", ".tiff": "TIFF", ".tga": "TARGA", ".bmp": "BMP",
}


def format_for_ext(ext: str) -> str | None:
    """Blender image file_format enum for a file extension, or None to leave the
    image's current format alone."""
    return _FORMAT_BY_EXT.get((ext or "").lower())


def udim_stem(name: str) -> str:
    """The stem of a UDIM image name, dropping the '.<UDIM>.<ext>' tail, e.g.
    'Frank_BaseColor.<UDIM>.png' -> 'Frank_BaseColor'."""
    return name.split(".<UDIM>")[0]


def build_manifest(entries: list[dict], base: str, version: int) -> dict:
    """The <base>_vNNN.manifest.json payload: the publish identity plus every
    texture it carries, sorted by name for stable diffs."""
    return {
        "base": base,
        "version": int(version),
        "textures": sorted(entries, key=lambda e: e["name"]),
    }
