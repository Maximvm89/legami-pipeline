"""Addon preferences — per-user SFTP login + local paths."""

import bpy


class FlumenPipelinePrefs(bpy.types.AddonPreferences):
    bl_idname = __package__

    sftp_host: bpy.props.StringProperty(
        name="SFTP Host", default="ftp.fantastificio.com")
    sftp_port: bpy.props.IntProperty(name="Port", default=22, min=1, max=65535)
    sftp_user: bpy.props.StringProperty(name="Username", default="")
    sftp_password: bpy.props.StringProperty(
        name="Password", default="", subtype="PASSWORD",
        description="Stored in Blender preferences (not encrypted). For shared "
                    "machines, leave blank and enter per session.")
    remote_root: bpy.props.StringProperty(
        name="Remote Root", default="/shared/Flumen")
    local_root: bpy.props.StringProperty(
        name="Local Project Root", subtype="DIR_PATH", default="",
        description="Where the project is synced on this machine. Usually set "
                    "automatically by the launcher; override here if needed.")

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Your FTP Login (per-user)", icon="USER")
        box.prop(self, "sftp_host")
        row = box.row()
        row.prop(self, "sftp_user")
        row.prop(self, "sftp_port")
        box.prop(self, "sftp_password")
        box.label(text="Tip: leave password blank on shared machines.", icon="INFO")

        box = layout.box()
        box.label(text="Project Paths", icon="FILE_FOLDER")
        box.prop(self, "remote_root")
        box.prop(self, "local_root")
        box.label(text="Note: when opened via the Workspace app, these are set "
                       "automatically — you don't need to fill them in.", icon="INFO")
