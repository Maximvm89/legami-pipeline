"""Blender operators for the Legami pipeline addon."""

import os
import subprocess

import bpy

from . import settings_io


def _prefs():
    """Addon preferences if the addon was installed the normal way, else None
    (when auto-loaded for a session, settings come from env vars instead)."""
    try:
        return bpy.context.preferences.addons[__package__].preferences
    except (KeyError, AttributeError):
        return None


def _pref_local_root():
    p = _prefs()
    return getattr(p, "local_root", None) if p else None


def _shell_toolkit(args, report):
    """Run an animpipe CLI command via the toolkit the launcher exposed."""
    py = os.environ.get("LEGAMI_TOOLKIT_PY")
    td = os.environ.get("LEGAMI_TOOLKIT_DIR")
    if not py or not td:
        report({"ERROR"}, "Toolkit not available — launch from the Workspace app.")
        return False
    try:
        subprocess.check_call([py, "-m", "animpipe"] + args, cwd=td)
        return True
    except Exception as exc:  # noqa: BLE001
        report({"ERROR"}, f"Command failed: {exc}")
        return False


def _apply_one(report, label, fn):
    """Run a single setting application, collecting warnings instead of crashing."""
    try:
        fn()
        return True
    except Exception as exc:  # noqa: BLE001 — we want to keep going
        report.append(f"  - skipped {label}: {exc}")
        return False


def apply_settings(scene, data: dict, root: str, report: list):
    """Apply the project_settings dict to a scene. Returns nothing; fills report."""
    cm = data.get("color_management", {})
    rn = data.get("render", {})
    un = data.get("units", {})
    fr = data.get("frame_range", {})
    out = data.get("output", {})

    # --- Color management (names must exist in the active OCIO config) ---
    ds = scene.display_settings
    vs = scene.view_settings
    if cm.get("display_device"):
        _apply_one(report, "display_device",
                   lambda: setattr(ds, "display_device", cm["display_device"]))
    if cm.get("view_transform"):
        _apply_one(report, "view_transform",
                   lambda: setattr(vs, "view_transform", cm["view_transform"]))
    if cm.get("look") is not None:
        _apply_one(report, "look", lambda: setattr(vs, "look", cm["look"]))
    if cm.get("exposure") is not None:
        _apply_one(report, "exposure",
                   lambda: setattr(vs, "exposure", float(cm["exposure"])))
    if cm.get("gamma") is not None:
        _apply_one(report, "gamma", lambda: setattr(vs, "gamma", float(cm["gamma"])))
    if cm.get("sequencer_space"):
        _apply_one(report, "sequencer colorspace",
                   lambda: setattr(scene.sequencer_colorspace_settings, "name",
                                   cm["sequencer_space"]))

    # --- Render ---
    if rn.get("engine"):
        _apply_one(report, "render engine",
                   lambda: setattr(scene.render, "engine", rn["engine"]))
    if rn.get("film_transparent") is not None:
        _apply_one(report, "film transparent",
                   lambda: setattr(scene.render, "film_transparent",
                                   bool(rn["film_transparent"])))
    if rn.get("resolution_x"):
        _apply_one(report, "resolution_x",
                   lambda: setattr(scene.render, "resolution_x", int(rn["resolution_x"])))
    if rn.get("resolution_y"):
        _apply_one(report, "resolution_y",
                   lambda: setattr(scene.render, "resolution_y", int(rn["resolution_y"])))
    if rn.get("resolution_percentage"):
        _apply_one(report, "resolution %",
                   lambda: setattr(scene.render, "resolution_percentage",
                                   int(rn["resolution_percentage"])))
    if rn.get("fps"):
        _apply_one(report, "fps", lambda: setattr(scene.render, "fps", int(rn["fps"])))
    if rn.get("fps_base"):
        _apply_one(report, "fps_base",
                   lambda: setattr(scene.render, "fps_base", float(rn["fps_base"])))

    # --- Cycles (only if that engine is active) ---
    cyc = rn.get("cycles", {})
    if cyc and getattr(scene.render, "engine", "") == "CYCLES" and hasattr(scene, "cycles"):
        if cyc.get("device"):
            _apply_one(report, "cycles device",
                       lambda: setattr(scene.cycles, "device", cyc["device"]))
        if cyc.get("samples"):
            _apply_one(report, "cycles samples",
                       lambda: setattr(scene.cycles, "samples", int(cyc["samples"])))
        if cyc.get("use_denoising") is not None:
            _apply_one(report, "cycles denoising",
                       lambda: setattr(scene.cycles, "use_denoising",
                                       bool(cyc["use_denoising"])))

    # --- Frame range ---
    if fr.get("start") is not None:
        _apply_one(report, "frame start",
                   lambda: setattr(scene, "frame_start", int(fr["start"])))
    if fr.get("end") is not None:
        _apply_one(report, "frame end",
                   lambda: setattr(scene, "frame_end", int(fr["end"])))

    # --- Units ---
    if un.get("system"):
        _apply_one(report, "unit system",
                   lambda: setattr(scene.unit_settings, "system", un["system"]))
    if un.get("scale_length"):
        _apply_one(report, "unit scale",
                   lambda: setattr(scene.unit_settings, "scale_length",
                                   float(un["scale_length"])))
    if un.get("length_unit"):
        _apply_one(report, "length unit",
                   lambda: setattr(scene.unit_settings, "length_unit", un["length_unit"]))

    # --- Output ---
    if out.get("base_path_rel"):
        base = os.path.join(root, out["base_path_rel"])
        _apply_one(report, "output path",
                   lambda: setattr(scene.render, "filepath", base + os.sep))
    if out.get("file_format"):
        _apply_one(report, "file format",
                   lambda: setattr(scene.render.image_settings, "file_format",
                                   out["file_format"]))
    if out.get("color_depth"):
        _apply_one(report, "color depth",
                   lambda: setattr(scene.render.image_settings, "color_depth",
                                   str(out["color_depth"])))
    if out.get("exr_codec"):
        _apply_one(report, "exr codec",
                   lambda: setattr(scene.render.image_settings, "exr_codec",
                                   out["exr_codec"]))


class LEGAMI_OT_apply_project_settings(bpy.types.Operator):
    bl_idname = "legami.apply_project_settings"
    bl_label = "Apply Project Settings"
    bl_description = "Apply the project's standard color, render, units and output settings to this scene"
    bl_options = {"REGISTER", "UNDO"}

    apply_all_scenes: bpy.props.BoolProperty(
        name="All Scenes", default=False,
        description="Apply to every scene in this file, not just the active one")

    def execute(self, context):
        root = settings_io.find_project_root(_pref_local_root())
        if not root:
            self.report({"ERROR"}, "No project root. Launch via the Legami launcher, "
                                   "or set Local Project Root in addon preferences.")
            return {"CANCELLED"}
        try:
            data = settings_io.load_settings(root)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        scenes = list(bpy.data.scenes) if self.apply_all_scenes else [context.scene]
        warnings: list[str] = []
        for sc in scenes:
            apply_settings(sc, data, root, warnings)

        ocio = os.environ.get("BLENDER_OCIO", "(not set)")
        if warnings:
            self.report({"WARNING"},
                        f"Applied with {len(warnings)} skipped setting(s). See console.")
            print("[Legami] Project settings applied with warnings:")
            print("\n".join(warnings))
            print(f"[Legami] BLENDER_OCIO = {ocio}")
        else:
            self.report({"INFO"}, "Project settings applied.")
        return {"FINISHED"}


class LEGAMI_OT_verify_ocio(bpy.types.Operator):
    bl_idname = "legami.verify_ocio"
    bl_label = "Verify Color Config"
    bl_description = "Check that Blender loaded the project OCIO config and the project's color names exist"

    def execute(self, context):
        root = settings_io.find_project_root(_pref_local_root())
        env_ocio = os.environ.get("BLENDER_OCIO")
        expected = settings_io.ocio_path(root) if root else None

        msgs = []
        if not env_ocio:
            msgs.append("BLENDER_OCIO is NOT set — Blender is using its bundled config. "
                        "Launch via the Legami launcher.")
        elif expected and os.path.normpath(env_ocio) != os.path.normpath(expected):
            msgs.append(f"BLENDER_OCIO points to {env_ocio}, expected {expected}.")
        else:
            msgs.append(f"OCIO OK: {env_ocio}")

        # Check the project's color names exist in the active config.
        if root:
            try:
                data = settings_io.load_settings(root)
                cm = data.get("color_management", {})
                vt = cm.get("view_transform")
                views = [i.identifier for i in
                         context.scene.view_settings.bl_rna.properties["view_transform"].enum_items]
                if vt and vt not in views:
                    msgs.append(f"View transform '{vt}' NOT found in active config. "
                                f"Available: {', '.join(views[:8])}...")
                else:
                    msgs.append(f"View transform '{vt}' present.")
            except Exception as exc:  # noqa: BLE001
                msgs.append(f"Could not verify color names: {exc}")

        level = "INFO" if all("OK" in m or "present" in m for m in msgs) else "WARNING"
        self.report({level}, " | ".join(msgs))
        print("[Legami] Verify color config:\n  " + "\n  ".join(msgs))
        return {"FINISHED"}


class LEGAMI_OT_pull_settings(bpy.types.Operator):
    bl_idname = "legami.pull_settings"
    bl_label = "Pull Latest From FTP"
    bl_description = "Re-sync the project config (OCIO + project_settings.json) from the FTP"

    def execute(self, context):
        if _shell_toolkit(["sync", "--remote", "02_pipeline"], self.report):
            self.report({"INFO"}, "Synced latest config. Now Apply Project Settings.")
            return {"FINISHED"}
        return {"CANCELLED"}


def active_task():
    """The task this Blender session was opened for (set by the Workspace app via
    env vars), or None if Blender was launched without a task context."""
    tid = os.environ.get("LEGAMI_TASK_ID")
    if not tid:
        return None
    return {
        "id": tid,
        "type": os.environ.get("LEGAMI_TASK_TYPE", ""),
        "entity": os.environ.get("LEGAMI_TASK_ENTITY", ""),
        "step": os.environ.get("LEGAMI_TASK_STEP", ""),
        "title": os.environ.get("LEGAMI_TASK_TITLE", ""),
        "work_dir": os.environ.get("LEGAMI_TASK_WORK_DIR", ""),
    }


class LEGAMI_OT_save_to_task(bpy.types.Operator):
    bl_idname = "legami.save_to_task"
    bl_label = "Save into task work folder"
    bl_description = ("Save the current .blend into this task's work/ folder with "
                      "an auto-incremented version")

    def execute(self, context):
        task = active_task()
        if not task or not task["work_dir"]:
            self.report({"ERROR"}, "No active task. Open this scene from the "
                                   "Workspace app's 'Open in Blender'.")
            return {"CANCELLED"}
        work_dir = task["work_dir"]
        os.makedirs(work_dir, exist_ok=True)
        base = f"{task['entity'].replace('/', '_')}_{task['step']}"
        existing = [f for f in os.listdir(work_dir)
                    if f.startswith(base) and f.endswith(".blend")]
        version = len(existing) + 1
        path = os.path.join(work_dir, f"{base}_v{version:03d}.blend")
        bpy.ops.wm.save_as_mainfile(filepath=path)
        self.report({"INFO"}, f"Saved {os.path.basename(path)}")
        return {"FINISHED"}


def _next_version(folder: str, base: str) -> int:
    if not os.path.isdir(folder):
        return 1
    existing = [f for f in os.listdir(folder)
                if f.startswith(base + "_v") and f.endswith(".blend")]
    return len(existing) + 1


class LEGAMI_OT_publish(bpy.types.Operator):
    bl_idname = "legami.publish"
    bl_label = "Publish"
    bl_description = ("Write a versioned .blend into this task's publish/ folder, "
                      "upload it, and set the task to Review")

    def execute(self, context):
        task = active_task()
        if not task or not task["work_dir"]:
            self.report({"ERROR"}, "No active task. Open this scene from the "
                                   "Workspace app's 'Open in Blender'.")
            return {"CANCELLED"}

        # publish/ is a sibling of the task's work/ folder
        publish_dir = os.path.join(os.path.dirname(task["work_dir"]), "publish")
        os.makedirs(publish_dir, exist_ok=True)
        name = task["entity"].split("/")[-1]
        base = f"{name}_{task['step']}"
        version = _next_version(publish_dir, base)
        pub_path = os.path.join(publish_dir, f"{base}_v{version:03d}.blend")

        # Write a copy to publish/ without changing the working file.
        bpy.ops.wm.save_as_mainfile(filepath=pub_path, copy=True)

        py = os.environ.get("LEGAMI_TOOLKIT_PY")
        td = os.environ.get("LEGAMI_TOOLKIT_DIR")
        if not py or not td:
            self.report({"WARNING"},
                        f"Saved {os.path.basename(pub_path)} to publish/, but the "
                        f"toolkit wasn't found to upload — push it via the Workspace app.")
            return {"FINISHED"}

        try:
            subprocess.check_call(
                [py, "-m", "animpipe", "publish", "--local", pub_path,
                 "--task", task["id"], "--status", "review"], cwd=td)
        except Exception as exc:  # noqa: BLE001
            self.report({"ERROR"}, f"Saved locally but upload failed: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"},
                    f"Published {os.path.basename(pub_path)}; task set to Review.")
        return {"FINISHED"}


CLASSES = (
    LEGAMI_OT_apply_project_settings,
    LEGAMI_OT_verify_ocio,
    LEGAMI_OT_pull_settings,
    LEGAMI_OT_save_to_task,
    LEGAMI_OT_publish,
)
