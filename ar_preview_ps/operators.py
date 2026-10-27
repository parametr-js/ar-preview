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

import os
import tempfile
import time

import bmesh
import bpy

from . import server

GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'META', 'FONT'}
TEMP_NAME = "AR_Preview_Export"   # temporary collection / merged mesh
GREY_NAME = "AR_Grey"

# Result of the last export, shown in the panel.
last_export = {"triangles": 0, "size_mb": 0.0}


# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

def temp_path():
    folder = bpy.app.tempdir or tempfile.gettempdir()
    return os.path.join(folder, "ar_preview.usdz")


def gather_objects(context, selected_only):
    """Geometry objects plus empties that instance a collection."""
    source = context.selected_objects if selected_only else context.visible_objects
    return [obj for obj in source
            if obj.type in GEOMETRY_TYPES or obj.instance_type == 'COLLECTION']


def iter_meshes(depsgraph, objects):
    """Yield (evaluated mesh, world matrix, materials) for objects incl. their instances.

    Meshes are temporary - valid only inside one loop step.
    """
    wanted = set(objects)
    for inst in depsgraph.object_instances:
        owner = inst.parent if inst.is_instance else inst.object
        if owner.original not in wanted:
            continue
        obj = inst.object
        if obj.type not in GEOMETRY_TYPES:
            continue  # e.g. the empty of a collection instance, its content comes separately
        mesh = obj.to_mesh()
        if mesh is not None:
            materials = [slot.material for slot in obj.material_slots]
            yield mesh, inst.matrix_world.copy(), materials
        obj.to_mesh_clear()


def count_triangles(depsgraph, objects):
    total = 0
    for mesh, _matrix, _materials in iter_meshes(depsgraph, objects):
        total += sum(poly.loop_total - 2 for poly in mesh.polygons)
    return total


def build_merged_object(depsgraph, objects):
    """One mesh object in world space with one material slot per unique material."""
    bm = bmesh.new()
    materials = []

    for mesh, matrix, mesh_materials in iter_meshes(depsgraph, objects):
        # Remap local material indices to the merged material list.
        index_map = []
        for mat in mesh_materials or [None]:
            if mat not in materials:
                materials.append(mat)
            index_map.append(materials.index(mat))
        for poly in mesh.polygons:
            poly.material_index = index_map[min(poly.material_index, len(index_map) - 1)]

        mesh.transform(matrix)
        bm.from_mesh(mesh)  # repeated calls append geometry

    merged_mesh = bpy.data.meshes.new(TEMP_NAME)
    bm.to_mesh(merged_mesh)
    bm.free()
    for mat in materials:
        merged_mesh.materials.append(mat)
    return bpy.data.objects.new(TEMP_NAME, merged_mesh)


def remove_temp_data():
    obj = bpy.data.objects.get(TEMP_NAME)
    if obj is not None:
        bpy.data.objects.remove(obj)
    mesh = bpy.data.meshes.get(TEMP_NAME)
    if mesh is not None:
        bpy.data.meshes.remove(mesh)
    col = bpy.data.collections.get(TEMP_NAME)
    if col is not None:
        bpy.data.collections.remove(col)  # linked originals stay in their own collections


def export_usdz(context, filepath):
    """Export scene geometry to filepath. Returns triangle count, None if nothing to export."""
    settings = context.scene.ar_preview
    objects = gather_objects(context, settings.selected_only)
    if not objects:
        return None

    depsgraph = context.evaluated_depsgraph_get()
    triangles = count_triangles(depsgraph, objects)

    # Export goes through a temporary collection, so the scene stays untouched.
    remove_temp_data()
    temp_col = bpy.data.collections.new(TEMP_NAME)
    context.scene.collection.children.link(temp_col)
    try:
        if settings.merge_meshes:
            temp_col.objects.link(build_merged_object(depsgraph, objects))
        else:
            for obj in objects:
                temp_col.objects.link(obj)

        bpy.ops.wm.usd_export(
            filepath=filepath,
            check_existing=False,
            collection=temp_col.name,
            evaluation_mode='VIEWPORT',
            export_animation=False,
            export_cameras=False,
            export_lights=False,
            convert_world_material=False,
            export_materials=True,
            generate_preview_surface=True,
            use_instancing=settings.use_instancing and not settings.merge_meshes,
            convert_scene_units='METERS',
            usdz_downscale_size='2048',
        )
    finally:
        remove_temp_data()

    last_export["triangles"] = triangles
    last_export["size_mb"] = os.path.getsize(filepath) / (1024 * 1024)
    return triangles


def report_triangles(operator, settings, triangles):
    if triangles > settings.triangle_limit:
        operator.report({'WARNING'}, "Exported %d triangles - above limit %d"
                        % (triangles, settings.triangle_limit))
    else:
        operator.report({'INFO'}, "Exported %d triangles" % triangles)


class ARP_OT_view_in_ar(bpy.types.Operator):
    """Export the scene and show it on the phone (scan the QR code with the camera)"""
    bl_idname = "ar_preview.view_in_ar"
    bl_label = "View in AR"

    @classmethod
    def poll(cls, context):
        if not bpy.app.online_access:
            cls.poll_message_set("Allow Online Access in Preferences > System > Network")
            return False
        return True

    def execute(self, context):
        settings = context.scene.ar_preview
        path = temp_path()
        triangles = export_usdz(context, path)
        if triangles is None:
            self.report({'WARNING'}, "Nothing to export")
            return {'CANCELLED'}

        if not server.is_running():
            try:
                server.start(settings.port, settings.ip_override.strip())
            except OSError as err:
                self.report({'ERROR'}, "Server could not start on port %d: %s" % (settings.port, err))
                return {'CANCELLED'}

        info = "%d triangles, %.1f MB, %s" % (triangles, last_export["size_mb"], time.strftime("%H:%M:%S"))
        server.publish(path, info, settings.lock_scale)
        report_triangles(self, settings, triangles)
        return {'FINISHED'}


class ARP_OT_stop_server(bpy.types.Operator):
    """Stop the local server"""
    bl_idname = "ar_preview.stop_server"
    bl_label = "Stop Server"

    def execute(self, context):
        server.stop()
        return {'FINISHED'}


class ARP_OT_save_usdz(bpy.types.Operator):
    """Save the scene as a USDZ file (open it on the phone e.g. via AirDrop or Files)"""
    bl_idname = "ar_preview.save_usdz"
    bl_label = "Save USDZ"

    def execute(self, context):
        settings = context.scene.ar_preview
        if settings.file_path.startswith("//") and not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file first or use an absolute path")
            return {'CANCELLED'}

        path = bpy.path.abspath(settings.file_path)
        if not path.lower().endswith(".usdz"):
            path += ".usdz"
        os.makedirs(os.path.dirname(path), exist_ok=True)

        triangles = export_usdz(context, path)
        if triangles is None:
            self.report({'WARNING'}, "Nothing to export")
            return {'CANCELLED'}

        report_triangles(self, settings, triangles)
        self.report({'INFO'}, "Saved %s" % path)
        return {'FINISHED'}


# -----------------------------------------------------------------------------
# Grey material
# -----------------------------------------------------------------------------

def get_grey_material():
    mat = bpy.data.materials.get(GREY_NAME)
    if mat is None:
        mat = bpy.data.materials.new(GREY_NAME)
        if mat.node_tree is None:  # Blender 4.x, from 5.0 materials always have nodes
            mat.use_nodes = True
        grey = (0.5, 0.5, 0.5, 1.0)
        bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
        bsdf.inputs["Base Color"].default_value = grey
        bsdf.inputs["Roughness"].default_value = 0.8
        mat.diffuse_color = grey  # viewport Solid mode
    return mat


class ARP_OT_grey_material(bpy.types.Operator):
    """Replace all materials of selected objects with a plain grey material (undoable)"""
    bl_idname = "ar_preview.grey_material"
    bl_label = "Assign Grey Material"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        objects = [o for o in context.selected_objects if o.type in GEOMETRY_TYPES]
        if not objects:
            self.report({'WARNING'}, "No geometry selected")
            return {'CANCELLED'}

        mat = get_grey_material()
        for obj in objects:
            if not obj.material_slots:
                obj.data.materials.append(mat)
            for slot in obj.material_slots:
                slot.material = mat

        self.report({'INFO'}, "Grey material assigned to %d objects" % len(objects))
        return {'FINISHED'}


classes = (ARP_OT_view_in_ar, ARP_OT_stop_server, ARP_OT_save_usdz, ARP_OT_grey_material)
