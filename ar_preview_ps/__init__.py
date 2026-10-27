# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

"""AR Preview - view the scene in AR on iOS (AR Quick Look) via a local server and QR code."""

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty

from . import operators, qr_preview, server


class ARP_Settings(bpy.types.PropertyGroup):
    selected_only: BoolProperty(
        name="Selected Only",
        description="Export only selected objects, otherwise all visible objects",
        default=False,
    )
    merge_meshes: BoolProperty(
        name="Merge Meshes",
        description="Export as one mesh (temporary copy, the scene is not changed). "
                    "One draw call per material - faster on the phone",
        default=True,
    )
    use_instancing: BoolProperty(
        name="Instancing",
        description="Write collection instances and Geometry Nodes instances as USD instances "
                    "(smaller file). Used only when Merge Meshes is off",
        default=True,
    )
    lock_scale: BoolProperty(
        name="Lock Scale",
        description="Disable pinch-to-scale in AR, the model stays 1:1",
        default=True,
    )
    triangle_limit: IntProperty(
        name="Triangle Limit",
        description="Warn when the export has more triangles",
        default=100_000,
        min=1000,
    )
    port: IntProperty(name="Port", default=8000, min=1024, max=65535)
    ip_override: StringProperty(
        name="IP",
        description="Leave empty for automatic detection. "
                    "Fill in when the computer has more networks (VPN, Ethernet + Wi-Fi)",
        default="",
    )
    file_path: StringProperty(
        name="Path",
        description="Where Save USDZ writes the file. // means the folder of the .blend file",
        default="//ar_preview.usdz",
        subtype='FILE_PATH',
    )


# -----------------------------------------------------------------------------
# Panels
# -----------------------------------------------------------------------------

class ARP_PT_main(bpy.types.Panel):
    bl_label = "AR Preview"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ARP"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ar_preview
        running = server.is_running()

        row = layout.row()
        row.scale_y = 2.0
        row.operator("ar_preview.view_in_ar", text="Update AR" if running else "View in AR",
                     icon='FILE_REFRESH' if running else 'CAMERA_DATA')

        if running:
            col = layout.column(align=True)
            col.template_icon(icon_value=qr_preview.icon_id(server.url), scale=10.0)
            col.label(text=server.url)

        tris = operators.last_export["triangles"]
        if tris:
            over = tris > settings.triangle_limit
            layout.label(
                text="%s triangles, %.1f MB" % (f"{tris:,}".replace(",", " "),
                                                 operators.last_export["size_mb"]),
                icon='ERROR' if over else 'INFO',
            )

        if running:
            layout.operator("ar_preview.stop_server", icon='CANCEL')

        layout.separator()
        layout.operator("ar_preview.grey_material", icon='MATERIAL')


class ARP_PT_options(bpy.types.Panel):
    bl_label = "Options"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ARP"
    bl_parent_id = "ARP_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ar_preview

        layout.prop(settings, "selected_only")
        layout.prop(settings, "merge_meshes")
        row = layout.row()
        row.active = not settings.merge_meshes
        row.prop(settings, "use_instancing")
        layout.prop(settings, "lock_scale")
        layout.prop(settings, "triangle_limit")

        col = layout.column()
        col.enabled = not server.is_running()  # applied on server start
        col.prop(settings, "port")
        col.prop(settings, "ip_override")


class ARP_PT_file(bpy.types.Panel):
    bl_label = "USDZ File"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ARP"
    bl_parent_id = "ARP_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.ar_preview, "file_path", text="")
        layout.operator("ar_preview.save_usdz", icon='EXPORT')


# -----------------------------------------------------------------------------
# Registration
# -----------------------------------------------------------------------------

classes = (ARP_Settings, ARP_PT_main, ARP_PT_options, ARP_PT_file) + operators.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ar_preview = PointerProperty(type=ARP_Settings)
    qr_preview.register()


def unregister():
    server.stop()
    qr_preview.unregister()
    del bpy.types.Scene.ar_preview
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
