# -*- coding:utf-8 -*-

# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110- 1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# <pep8 compliant>

# ----------------------------------------------------------
# Author: Stephen Leger (s-leger)
#
# ----------------------------------------------------------
# noinspection PyUnresolvedReferences
import bpy
# noinspection PyUnresolvedReferences
from bpy.props import BoolProperty, StringProperty
from mathutils import Vector, Matrix
from mathutils.geometry import (
    intersect_line_plane
    )
from bpy_extras import view3d_utils
import logging
logger = logging.getLogger("archipack")


class ArchipackObject():
    """
        Shared property of archipack's objects PropertyGroup
        provide basic support for copy to selected
        and datablock access / filtering by object
    """

    def iskindof(self, o, typ):
        """
            return true if object contains databloc of typ name
        """
        return o.data is not None and typ in o.data

    @classmethod
    def filter(cls, o):
        """
            Filter object with this class in data
            return
            True when object contains this datablock
            False otherwhise
            usage:
            class_name.filter(object) from outside world
            self.__class__.filter(object) from instance
        """
        try:
            return cls.__name__ in o.data
        except:
            pass
        return False

    @classmethod
    def datablock(cls, o):
        """
            Retrieve datablock from base object
            return
                datablock when found
                None when not found
            usage:
                class_name.datablock(object) from outside world
                self.__class__.datablock(object) from instance
        """
        try:
            return getattr(o.data, cls.__name__)[0]
        except:
            pass
        return None

    def find_in_selection(self, context, auto_update=True):
        """
            find witch selected object this datablock instance belongs to
            store context to be able to restore after oops
            provide support for "copy to selected"
            return
            object or None when instance not found in selected objects
        """
        if auto_update is False:
            return None

        active = context.active_object
        selected = context.selected_objects[:]

        for o in selected:
            if self.__class__.datablock(o) == self:
                self.previously_selected = selected
                self.previously_active = active
                return o

        return None

    def restore_context(self, context):
        # restore context
        bpy.ops.object.select_all(action="DESELECT")

        try:
            for o in self.previously_selected:
                o.select = True
        except:
            pass
        if self.previously_active is not None:
            self.previously_active.select = True
            context.scene.objects.active = self.previously_active
        self.previously_selected = None
        self.previously_active = None


class ArchipackCreateTool():
    """
        Shared property of archipack's create tool Operator
    """
    auto_manipulate = BoolProperty(
            name="Auto manipulate",
            description="Enable object's manipulators after create",
            options={'SKIP_SAVE'},
            default=True
            )
    filepath = StringProperty(
            options={'SKIP_SAVE'},
            name="Preset",
            description="Full filename of python preset to load at create time",
            default=""
            )

    @property
    def archipack_category(self):
        """
            return target object name from ARCHIPACK_OT_object_name
        """
        return self.bl_idname[13:]

    def load_preset(self, d):
        """
            Load python preset
            d: archipack object datablock
            preset: full filename.py with path
        """
        d.auto_update = False
        fallback = True
        if self.filepath != "":
            try:
                bpy.ops.script.python_file_run(filepath=self.filepath)
                fallback = False
            except:
                pass
            if fallback:
                # fallback to load preset on background process
                try:
                    exec(compile(open(self.filepath).read(), self.filepath, 'exec'))
                except:
                    print("Archipack unable to load preset file : %s" % (self.filepath))
                    pass
        d.auto_update = True

    def add_material(self, o, material='DEFAULT', category=None):
        # skip if preset allready add material
        if "archipack_material" in o:
            return
        try:
            if category is None:
                category = self.archipack_category
            if bpy.ops.archipack.material.poll():
                bpy.ops.archipack.material(category=category, material=material)
        except:
            print("Archipack %s materials not found" % (self.archipack_category))
            pass

    def manipulate(self):
        if self.auto_manipulate:
            try:
                op = getattr(bpy.ops.archipack, self.archipack_category + "_manipulate")
                if op.poll():
                    op('INVOKE_DEFAULT')
            except:
                print("Archipack bpy.ops.archipack.%s_manipulate not found" % (self.archipack_category))
                pass


class ArchpackDrawTool():
    """
        Draw tools
    """
    def region_2d_to_orig_and_vect(self, context, event):

        region = context.region
        rv3d = context.region_data
        coord = (event.mouse_region_x, event.mouse_region_y)

        vec = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        orig = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

        return rv3d.is_perspective, orig, vec

    def mouse_to_plane(self, context, event, origin=Vector((0, 0, 0)), normal=Vector((0, 0, 1))):
        """
            convert mouse pos to 3d point over plane defined by origin and normal
            return None if the point is behind camera view
        """
        is_perspective, orig, vec = self.region_2d_to_orig_and_vect(context, event)
        pt = intersect_line_plane(orig, orig + vec, origin, normal, False)

        # fix issue with parallel plane
        if pt is None:
            pt = intersect_line_plane(orig, orig + vec, origin, vec, False)

        if pt is None:
            return None

        if is_perspective:
            # Check if point is behind point of view (mouse over horizon)
            y = Vector((0, 0, 1))
            x = vec.cross(y)
            x = y.cross(vec)
            itM = Matrix([
                [x.x, y.x, vec.x, orig.x],
                [x.y, y.y, vec.y, orig.y],
                [x.z, y.z, vec.z, orig.z],
                [0, 0, 0, 1]
                ]).inverted()
            res = itM * pt

            if res.z < 0:
                return None

        return pt

    def mouse_to_scene_raycast(self, context, event):
        """
            convert mouse pos to 3d point over plane defined by origin and normal
        """
        is_perspective, orig, vec = self.region_2d_to_orig_and_vect(context, event)
        res, pos, normal, face_index, object, matrix_world = context.scene.ray_cast(
            orig,
            vec)
        return res, pos, normal, face_index, object, matrix_world

    def mouse_hover_wall(self, context, event):
        """
            convert mouse pos to matrix at bottom of surrounded wall, y oriented outside wall
        """
        res, pt, y, i, o, tM = self.mouse_to_scene_raycast(context, event)
        if res and o.data is not None:

            z = Vector((0, 0, 1))
            y = -y
            x = y.cross(z)

            if 'archipack_wall2' in o.data:
                d = o.data.archipack_wall2[0]
                pt += (0.5 * d.width) * y.normalized()
                return True, Matrix([
                    [x.x, y.x, z.x, pt.x],
                    [x.y, y.y, z.y, pt.y],
                    [x.z, y.z, z.z, o.matrix_world.translation.z],
                    [0, 0, 0, 1]
                    ]), o, d.width, y

            elif 'archipack_wall' in o.data:
                # one point on the oposite to raycast side (1 unit inside)
                # @TODO: estimate the needed width - increase and re-cast when nothing is found
                #        within a limit of n iterations so single sided walls wont make it fail
                #        - ensure the ray hit same object ?

                p0 = pt + y.normalized()
                # direction
                dp = -y.normalized()
                # cast another ray to find wall depth
                res, pos, normal, face_index, object, matrix_world = context.scene.ray_cast(
                    p0,
                    dp)
                if res:
                    width = (pt - pos).to_2d().length
                    print("hit:%s  w:%s  pt:%s pos:%s" % (object.name, width, pt, pos))
                    p1 = pt + (0.5 * width) * y.normalized()
                    return True, Matrix([
                        [x.x, y.x, z.x, p1.x],
                        [x.y, y.y, z.y, p1.y],
                        [x.z, y.z, z.z, o.matrix_world.translation.z],
                        [0, 0, 0, 1]
                        ]), o, width, y
        return False, Matrix(), None, 0, Vector()
