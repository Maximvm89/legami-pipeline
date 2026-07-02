"""Run by Blender at startup (via `blender --python`) to auto-load the Flumen
add-on for this session — no manual install required.

The launcher sets FLUMEN_ADDON_DIR to the folder that CONTAINS the
`flumen_pipeline` package. If the user has already installed/enabled the add-on
the normal way, this does nothing and defers to their install.
"""

import os
import sys

import bpy


def _load():
    addon_dir = os.environ.get("FLUMEN_ADDON_DIR")
    if not addon_dir or not os.path.isdir(addon_dir):
        return
    # Already installed & enabled by the user? Leave it alone.
    if "flumen_pipeline" in bpy.context.preferences.addons.keys():
        return
    if addon_dir not in sys.path:
        sys.path.insert(0, addon_dir)
    try:
        import flumen_pipeline
        flumen_pipeline.register()
        print("[Flumen] add-on loaded for this session from", addon_dir)
    except Exception as exc:  # noqa: BLE001
        print("[Flumen] failed to load add-on:", exc)


_load()
