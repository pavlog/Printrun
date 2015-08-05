# -*- coding: utf-8 -*-
# Copyright (C) 2013 Guillaume Seguin
# Copyright (C) 2011 Denis Kobozev
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import time
import numpy
import array
import math
import logging
import threading

from ctypes import sizeof

from pyglet.gl import glPushMatrix, glPopMatrix, glTranslatef, \
    glGenLists, glNewList, GL_COMPILE, glEndList, glCallList, \
    GL_ELEMENT_ARRAY_BUFFER, GL_UNSIGNED_INT, GL_TRIANGLES, GL_LINE_LOOP, \
    GL_ARRAY_BUFFER, GL_STATIC_DRAW, glColor4f, glVertex3f, \
    glBegin, glEnd, GL_LINES, glEnable, glDisable, glGetFloatv, \
    GL_LINE_SMOOTH, glLineWidth, GL_LINE_WIDTH, GLfloat, GL_FLOAT, GLuint, \
    glVertexPointer, glColorPointer, glDrawArrays, glDrawRangeElements, \
    glEnableClientState, glDisableClientState, GL_VERTEX_ARRAY, GL_COLOR_ARRAY, \
    GL_FRONT_AND_BACK, GL_FRONT, glMaterialfv, GL_SPECULAR, GL_EMISSION, \
    glColorMaterial, GL_AMBIENT_AND_DIFFUSE, glMaterialf, GL_SHININESS, \
    GL_NORMAL_ARRAY, glNormalPointer, GL_LIGHTING, glColor3f
from pyglet.graphics.vertexbuffer import create_buffer, VertexBufferObject

from printrun.utils import install_locale
install_locale('pronterface')

def vec(*args):
    return (GLfloat * len(args))(*args)

def compile_display_list(func, *options):
    display_list = glGenLists(1)
    glNewList(display_list, GL_COMPILE)
    func(*options)
    glEndList()
    return display_list

def numpy2vbo(nparray, target = GL_ARRAY_BUFFER, usage = GL_STATIC_DRAW, use_vbos = True):
    vbo = create_buffer(nparray.nbytes, target = target, usage = usage, vbo = use_vbos)
    vbo.bind()
    vbo.set_data(nparray.ctypes.data)
    return vbo

def triangulate_rectangle(i1, i2, i3, i4):
    return [i1, i4, i3, i3, i2, i1]

def triangulate_box(i1, i2, i3, i4,
                    j1, j2, j3, j4):
    return [i1, i2, j2, j2, j1, i1, i2, i3, j3, j3, j2, i2,
            i3, i4, j4, j4, j3, i3, i4, i1, j1, j1, j4, i4]

class BoundingBox(object):
    """
    A rectangular box (cuboid) enclosing a 3D model, defined by lower and upper corners.
    """
    def __init__(self, upper_corner, lower_corner):
        self.upper_corner = upper_corner
        self.lower_corner = lower_corner

    @property
    def width(self):
        width = abs(self.upper_corner[0] - self.lower_corner[0])
        return round(width, 2)

    @property
    def depth(self):
        depth = abs(self.upper_corner[1] - self.lower_corner[1])
        return round(depth, 2)

    @property
    def height(self):
        height = abs(self.upper_corner[2] - self.lower_corner[2])
        return round(height, 2)


class Platform(object):
    """
    Platform on which models are placed.
    """
    graduations_major = 10

    def __init__(self, build_dimensions, light = False, circular = False):
        self.light = light
        self.circular = circular
        self.width = build_dimensions[0]
        self.depth = build_dimensions[1]
        self.height = build_dimensions[2]
        self.xoffset = build_dimensions[3]
        self.yoffset = build_dimensions[4]
        self.zoffset = build_dimensions[5]

        self.color_grads_minor = (0xaf / 255, 0xdf / 255, 0x5f / 255, 0.1)
        self.color_grads_interm = (0xaf / 255, 0xdf / 255, 0x5f / 255, 0.2)
        self.color_grads_major = (0xaf / 255, 0xdf / 255, 0x5f / 255, 0.33)

        self.initialized = False
        self.loaded = True

    def init(self):
        self.display_list = compile_display_list(self.draw)
        self.initialized = True

    def draw(self):
        glPushMatrix()

        glTranslatef(self.xoffset, self.yoffset, self.zoffset)

        def color(i):
            if i % self.graduations_major == 0:
                glColor4f(*self.color_grads_major)
            elif i % (self.graduations_major / 2) == 0:
                glColor4f(*self.color_grads_interm)
            else:
                if self.light: return False
                glColor4f(*self.color_grads_minor)
            return True

        # draw the grid
        glBegin(GL_LINES)
        if self.circular:  # Draw a circular grid
            for i in range(0, int(math.ceil(self.width + 1))):
                angle = math.asin(2 * float(i) / self.width - 1)
                x = (math.cos(angle) + 1) * self.depth / 2
                if color(i):
                    glVertex3f(float(i), self.depth - x, 0.0)
                    glVertex3f(float(i), x, 0.0)

            for i in range(0, int(math.ceil(self.depth + 1))):
                angle = math.acos(2 * float(i) / self.depth - 1)
                x = (math.sin(angle) + 1) * self.width / 2
                if color(i):
                    glVertex3f(self.width - x, float(i), 0.0)
                    glVertex3f(x, float(i), 0.0)
        else:  # Draw a rectangular grid
            for i in range(0, int(math.ceil(self.width + 1))):
                if color(i):
                    glVertex3f(float(i), 0.0, 0.0)
                    glVertex3f(float(i), self.depth, 0.0)

            for i in range(0, int(math.ceil(self.depth + 1))):
                if color(i):
                    glVertex3f(0, float(i), 0.0)
                    glVertex3f(self.width, float(i), 0.0)
        glEnd()

        if self.circular:
            glBegin(GL_LINE_LOOP)
            for i in range(0, 360):
                angle = math.radians(i)
                glVertex3f((math.cos(angle) + 1) * self.width / 2,
                           (math.sin(angle) + 1) * self.depth / 2, 0.0)
            glEnd()

        glPopMatrix()

        # draw center of world
        glBegin(GL_LINES)
        glColor4f(1,0,0,1)
        glVertex3f(-1.0, 1.0, 0.0)
        glVertex3f(1.0, -1.0, 0.0)
        glVertex3f(-1.0, -1.0, 0.0)
        glVertex3f(1.0, 1.0, 0.0)
        # draw z axis
        glColor4f(0,1,0,1)
        glVertex3f(0.0, 0.0, 0.0)
        glVertex3f(0.0, 0.0, 1.0)
        glEnd()

    def display(self, mode_2d=False):
        # FIXME: using the list sometimes results in graphical corruptions
        # glCallList(self.display_list)
        self.draw()

class PrintHead(object):
    def __init__(self):
        self.color = (43. / 255, 0., 175. / 255, 1.0)
        self.scale = 5
        self.height = 5

        self.initialized = False
        self.loaded = True

    def init(self):
        self.display_list = compile_display_list(self.draw)
        self.initialized = True

    def draw(self):
        glPushMatrix()

        glBegin(GL_LINES)
        glColor4f(*self.color)
        for di in [-1, 1]:
            for dj in [-1, 1]:
                glVertex3f(0, 0, 0)
                glVertex3f(self.scale * di, self.scale * dj, self.height)
        glEnd()

        glPopMatrix()

    def display(self, mode_2d=False):
        glEnable(GL_LINE_SMOOTH)
        orig_linewidth = (GLfloat)()
        glGetFloatv(GL_LINE_WIDTH, orig_linewidth)
        glLineWidth(3.0)
        glCallList(self.display_list)
        glLineWidth(orig_linewidth)
        glDisable(GL_LINE_SMOOTH)

class Model(object):
    """
    Parent class for models that provides common functionality.
    """
    AXIS_X = (1, 0, 0)
    AXIS_Y = (0, 1, 0)
    AXIS_Z = (0, 0, 1)

    letter_axis_map = {
        'x': AXIS_X,
        'y': AXIS_Y,
        'z': AXIS_Z,
    }

    axis_letter_map = dict([(v, k) for k, v in letter_axis_map.items()])

    lock = None

    def __init__(self, offset_x=0, offset_y=0):
        self.offset_x = offset_x
        self.offset_y = offset_y

        self.lock = threading.Lock()

        self.init_model_attributes()

    def init_model_attributes(self):
        """
        Set/reset saved properties.
        """
        self.invalidate_bounding_box()
        self.modified = False

    def invalidate_bounding_box(self):
        self._bounding_box = None

    @property
    def bounding_box(self):
        """
        Get a bounding box for the model.
        """
        if self._bounding_box is None:
            self._bounding_box = self._calculate_bounding_box()
        return self._bounding_box

    def _calculate_bounding_box(self):
        """
        Calculate an axis-aligned box enclosing the model.
        """
        # swap rows and columns in our vertex arrays so that we can do max and
        # min on axis 1
        xyz_rows = self.vertices.reshape(-1, order='F').reshape(3, -1)
        lower_corner = xyz_rows.min(1)
        upper_corner = xyz_rows.max(1)
        box = BoundingBox(upper_corner, lower_corner)
        return box

    @property
    def width(self):
        return self.bounding_box.width

    @property
    def depth(self):
        return self.bounding_box.depth

    @property
    def height(self):
        return self.bounding_box.height

    def movement_color(self, move):
        """
        Return the color to use for particular type of movement.
        """
        if move.extruding:
            if move.current_tool == 0:
                return self.color_tool0
            elif move.current_tool == 1:
                return self.color_tool1
            elif move.current_tool == 2:
                return self.color_tool2
            elif move.current_tool == 3:
                return self.color_tool3
            else:
                return self.color_tool4

        return self.color_travel

def movement_angle(src, dst, precision=0):
    x = dst[0] - src[0]
    y = dst[1] - src[1]
    angle = math.degrees(math.atan2(y, -x))  # negate x for clockwise rotation angle
    return round(angle, precision)

def get_next_move(gcode, layer_idx, gline_idx):
    gline_idx += 1
    while layer_idx < len(gcode.all_layers):
        layer = gcode.all_layers[layer_idx]
        while gline_idx < len(layer):
            gline = layer[gline_idx]
            if gline.is_move:
                return gline
            gline_idx += 1
        layer_idx += 1
        gline_idx = 0
    return None

class GcodeModel(Model):
    """
    Model for displaying Gcode data.
    """

    color_travel = (0.6, 0.6, 0.6, 0.6)
    color_tool0 = (1.0, 0.0, 0.0, 1.0)
    color_tool1 = (0.67, 0.05, 0.9, 1.0)
    color_tool2 = (1.0, 0.8, 0., 1.0)
    color_tool3 = (1.0, 0., 0.62, 1.0)
    color_tool4 = (0., 1.0, 0.58, 1.0)
    color_printed = (0.2, 0.75, 0, 1.0)
    color_current = (0, 0.9, 1.0, 1.0)
    color_current_printed = (0.1, 0.4, 0, 1.0)

    display_travels = True

    buffers_created = False
    use_vbos = True
    loaded = False
    fully_loaded = False

    gcode = None

    path_halfwidth = 0.2
    path_halfheight = 0.2

    def set_path_size(self, path_halfwidth, path_halfheight):
        with self.lock:
            self.path_halfwidth = path_halfwidth
            self.path_halfheight = path_halfheight

    def load_data(self, model_data, callback=None):
        t_start = time.time()
        self.gcode = model_data

        self.count_travel_indices = count_travel_indices = [0]
        self.count_print_indices = count_print_indices = [0]
        self.count_print_vertices = count_print_vertices = [0]

        # Some trivial computations, but that's mostly for documentation :)
        # Not like 10 multiplications are going to cost much time vs what's
        # about to happen :)

        # Max number of values which can be generated per gline
        # to store coordinates/colors/normals.
        # Nicely enough we have 3 per kind of thing for all kinds.
        coordspervertex = 3
        verticesperline = 8
        coordsperline = coordspervertex * verticesperline
        coords_count = lambda nlines: nlines * coordsperline

        travelverticesperline = 2
        travelcoordsperline = coordspervertex * travelverticesperline
        travel_coords_count = lambda nlines: nlines * travelcoordsperline

        trianglesperface = 2
        facesperbox = 4
        trianglesperbox = trianglesperface * facesperbox
        verticespertriangle = 3
        indicesperbox = verticespertriangle * trianglesperbox
        boxperline = 2
        indicesperline = indicesperbox * boxperline
        indices_count = lambda nlines: nlines * indicesperline

        nlines = len(model_data)
        ntravelcoords = travel_coords_count(nlines)
        ncoords = coords_count(nlines)
        nindices = indices_count(nlines)
        travel_vertices = self.travels = numpy.zeros(ntravelcoords, dtype = GLfloat)
        travel_vertex_k = 0
        vertices = self.vertices = numpy.zeros(ncoords, dtype = GLfloat)
        vertex_k = 0
        colors = self.colors = numpy.zeros(ncoords, dtype = GLfloat)
        color_k = 0
        normals = self.normals = numpy.zeros(ncoords, dtype = GLfloat)
        normal_k = 0
        indices = self.indices = numpy.zeros(nindices, dtype = GLuint)
        index_k = 0
        self.layer_idxs_map = {}
        self.layer_stops = [0]

        prev_is_extruding = False
        prev_move_normal_x = None
        prev_move_normal_y = None
        prev_move_angle = None

        prev_pos = (0, 0, 0)
        layer_idx = 0

        self.printed_until = 0
        self.only_current = False

        twopi = 2 * math.pi

        processed_lines = 0

        while layer_idx < len(model_data.all_layers):
            with self.lock:
                nlines = len(model_data)
                remaining_lines = nlines - processed_lines
                # Only reallocate memory which might be needed, not memory
                # for everything
                ntravelcoords = coords_count(remaining_lines) + travel_vertex_k
                ncoords = coords_count(remaining_lines) + vertex_k
                nindices = indices_count(remaining_lines) + index_k
                if ncoords > vertices.size:
                    self.travels.resize(ntravelcoords, refcheck = False)
                    self.vertices.resize(ncoords, refcheck = False)
                    self.colors.resize(ncoords, refcheck = False)
                    self.normals.resize(ncoords, refcheck = False)
                    self.indices.resize(nindices, refcheck = False)
                layer = model_data.all_layers[layer_idx]
                has_movement = False
                for gline_idx, gline in enumerate(layer):
                    if not gline.is_move:
                        continue
                    if gline.x is None and gline.y is None and gline.z is None:
                        continue
                    has_movement = True
                    current_pos = (gline.current_x, gline.current_y, gline.current_z)
                    if not gline.extruding:
                        travel_vertices[travel_vertex_k] = prev_pos[0]
                        travel_vertices[travel_vertex_k + 1] = prev_pos[1]
                        travel_vertices[travel_vertex_k + 2] = prev_pos[2]
                        travel_vertices[travel_vertex_k + 3] = current_pos[0]
                        travel_vertices[travel_vertex_k + 4] = current_pos[1]
                        travel_vertices[travel_vertex_k + 5] = current_pos[2]
                        travel_vertex_k += 6
                        prev_is_extruding = False
                    else:
                        gline_color = self.movement_color(gline)

                        next_move = get_next_move(model_data, layer_idx, gline_idx)
                        next_is_extruding = (next_move.extruding
                                             if next_move is not None else False)

                        delta_x = current_pos[0] - prev_pos[0]
                        delta_y = current_pos[1] - prev_pos[1]
                        norm = delta_x * delta_x + delta_y * delta_y
                        if norm == 0:  # Don't draw anything if this move is Z+E only
                            continue
                        norm = math.sqrt(norm)
                        move_normal_x = - delta_y / norm
                        move_normal_y = delta_x / norm
                        move_angle = math.atan2(delta_y, delta_x)

                        # FIXME: compute these dynamically
                        path_halfwidth = self.path_halfwidth * 1.2
                        path_halfheight = self.path_halfheight * 1.2

                        new_indices = []
                        new_vertices = []
                        new_normals = []
                        if prev_is_extruding:
                            # Store previous vertices indices
                            prev_id = vertex_k / 3 - 4
                            avg_move_normal_x = (prev_move_normal_x + move_normal_x) / 2
                            avg_move_normal_y = (prev_move_normal_y + move_normal_y) / 2
                            norm = avg_move_normal_x * avg_move_normal_x + avg_move_normal_y * avg_move_normal_y
                            if norm == 0:
                                avg_move_normal_x = move_normal_x
                                avg_move_normal_y = move_normal_y
                            else:
                                norm = math.sqrt(norm)
                                avg_move_normal_x /= norm
                                avg_move_normal_y /= norm
                            delta_angle = move_angle - prev_move_angle
                            delta_angle = (delta_angle + twopi) % twopi
                            fact = abs(math.cos(delta_angle / 2))
                            # If move is turning too much, avoid creating a big peak
                            # by adding an intermediate box
                            if fact < 0.5:
                                # FIXME: It looks like there's some heavy code duplication here...
                                hw = path_halfwidth
                                p1x = prev_pos[0] - hw * prev_move_normal_x
                                p2x = prev_pos[0] + hw * prev_move_normal_x
                                p1y = prev_pos[1] - hw * prev_move_normal_y
                                p2y = prev_pos[1] + hw * prev_move_normal_y
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] + path_halfheight))
                                new_vertices.extend((p1x, p1y, prev_pos[2]))
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] - path_halfheight))
                                new_vertices.extend((p2x, p2y, prev_pos[2]))
                                new_normals.extend((0, 0, 1))
                                new_normals.extend((-prev_move_normal_x, -prev_move_normal_y, 0))
                                new_normals.extend((0, 0, -1))
                                new_normals.extend((prev_move_normal_x, prev_move_normal_y, 0))
                                first = vertex_k / 3
                                # Link to previous
                                new_indices += triangulate_box(prev_id, prev_id + 1,
                                                               prev_id + 2, prev_id + 3,
                                                               first, first + 1,
                                                               first + 2, first + 3)
                                p1x = prev_pos[0] - hw * move_normal_x
                                p2x = prev_pos[0] + hw * move_normal_x
                                p1y = prev_pos[1] - hw * move_normal_y
                                p2y = prev_pos[1] + hw * move_normal_y
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] + path_halfheight))
                                new_vertices.extend((p1x, p1y, prev_pos[2]))
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] - path_halfheight))
                                new_vertices.extend((p2x, p2y, prev_pos[2]))
                                new_normals.extend((0, 0, 1))
                                new_normals.extend((-move_normal_x, -move_normal_y, 0))
                                new_normals.extend((0, 0, -1))
                                new_normals.extend((move_normal_x, move_normal_y, 0))
                                prev_id += 4
                                first += 4
                                # Link to previous
                                new_indices += triangulate_box(prev_id, prev_id + 1,
                                                               prev_id + 2, prev_id + 3,
                                                               first, first + 1,
                                                               first + 2, first + 3)
                            else:
                                hw = path_halfwidth / fact
                                # Compute vertices
                                p1x = prev_pos[0] - hw * avg_move_normal_x
                                p2x = prev_pos[0] + hw * avg_move_normal_x
                                p1y = prev_pos[1] - hw * avg_move_normal_y
                                p2y = prev_pos[1] + hw * avg_move_normal_y
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] + path_halfheight))
                                new_vertices.extend((p1x, p1y, prev_pos[2]))
                                new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] - path_halfheight))
                                new_vertices.extend((p2x, p2y, prev_pos[2]))
                                new_normals.extend((0, 0, 1))
                                new_normals.extend((-avg_move_normal_x, -avg_move_normal_y, 0))
                                new_normals.extend((0, 0, -1))
                                new_normals.extend((avg_move_normal_x, avg_move_normal_y, 0))
                                first = vertex_k / 3
                                # Link to previous
                                new_indices += triangulate_box(prev_id, prev_id + 1,
                                                               prev_id + 2, prev_id + 3,
                                                               first, first + 1,
                                                               first + 2, first + 3)
                        else:
                            # Compute vertices normal to the current move and cap it
                            p1x = prev_pos[0] - path_halfwidth * move_normal_x
                            p2x = prev_pos[0] + path_halfwidth * move_normal_x
                            p1y = prev_pos[1] - path_halfwidth * move_normal_y
                            p2y = prev_pos[1] + path_halfwidth * move_normal_y
                            new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] + path_halfheight))
                            new_vertices.extend((p1x, p1y, prev_pos[2]))
                            new_vertices.extend((prev_pos[0], prev_pos[1], prev_pos[2] - path_halfheight))
                            new_vertices.extend((p2x, p2y, prev_pos[2]))
                            new_normals.extend((0, 0, 1))
                            new_normals.extend((-move_normal_x, -move_normal_y, 0))
                            new_normals.extend((0, 0, -1))
                            new_normals.extend((move_normal_x, move_normal_y, 0))
                            first = vertex_k / 3
                            new_indices = triangulate_rectangle(first, first + 1,
                                                                first + 2, first + 3)

                        if not next_is_extruding:
                            # Compute caps and link everything
                            p1x = current_pos[0] - path_halfwidth * move_normal_x
                            p2x = current_pos[0] + path_halfwidth * move_normal_x
                            p1y = current_pos[1] - path_halfwidth * move_normal_y
                            p2y = current_pos[1] + path_halfwidth * move_normal_y
                            new_vertices.extend((current_pos[0], current_pos[1], current_pos[2] + path_halfheight))
                            new_vertices.extend((p1x, p1y, current_pos[2]))
                            new_vertices.extend((current_pos[0], current_pos[1], current_pos[2] - path_halfheight))
                            new_vertices.extend((p2x, p2y, current_pos[2]))
                            new_normals.extend((0, 0, 1))
                            new_normals.extend((-move_normal_x, -move_normal_y, 0))
                            new_normals.extend((0, 0, -1))
                            new_normals.extend((move_normal_x, move_normal_y, 0))
                            end_first = vertex_k / 3 + len(new_vertices) / 3 - 4
                            new_indices += triangulate_rectangle(end_first + 3, end_first + 2,
                                                                 end_first + 1, end_first)
                            new_indices += triangulate_box(first, first + 1,
                                                           first + 2, first + 3,
                                                           end_first, end_first + 1,
                                                           end_first + 2, end_first + 3)

                        for new_i, item in enumerate(new_indices):
                            indices[index_k + new_i] = item
                        index_k += len(new_indices)
                        for new_i, item in enumerate(new_vertices):
                            vertices[vertex_k + new_i] = item
                        vertex_k += len(new_vertices)
                        for new_i, item in enumerate(new_normals):
                            normals[normal_k + new_i] = item
                        normal_k += len(new_normals)
                        new_colors = list(gline_color)[:-1] * (len(new_vertices) / 3)
                        for new_i, item in enumerate(new_colors):
                            colors[color_k + new_i] = item
                        color_k += len(new_colors)

                        prev_is_extruding = True
                        prev_move_normal_x = move_normal_x
                        prev_move_normal_y = move_normal_y
                        prev_move_angle = move_angle

                    prev_pos = current_pos
                    count_travel_indices.append(travel_vertex_k / 3)
                    count_print_indices.append(index_k)
                    count_print_vertices.append(vertex_k / 3)
                    gline.gcview_end_vertex = len(count_print_indices) - 1

                if has_movement:
                    self.layer_stops.append(len(count_print_indices) - 1)
                    self.layer_idxs_map[layer_idx] = len(self.layer_stops) - 1
                    self.max_layers = len(self.layer_stops) - 1
                    self.num_layers_to_draw = self.max_layers + 1
                    self.initialized = False
                    self.loaded = True

            processed_lines += len(layer)

            if callback:
                callback(layer_idx + 1)

            yield layer_idx
            layer_idx += 1

        with self.lock:
            self.dims = ((model_data.xmin, model_data.xmax, model_data.width),
                         (model_data.ymin, model_data.ymax, model_data.depth),
                         (model_data.zmin, model_data.zmax, model_data.height))

            self.travels.resize(travel_vertex_k, refcheck = False)
            self.vertices.resize(vertex_k, refcheck = False)
            self.colors.resize(color_k, refcheck = False)
            self.normals.resize(normal_k, refcheck = False)
            self.indices.resize(index_k, refcheck = False)

            self.layer_stops = array.array('L', self.layer_stops)
            self.count_travel_indices = array.array('L', count_travel_indices)
            self.count_print_indices = array.array('L', count_print_indices)
            self.count_print_vertices = array.array('L', count_print_vertices)

            self.max_layers = len(self.layer_stops) - 1
            self.num_layers_to_draw = self.max_layers + 1
            self.loaded = True
            self.initialized = False
            self.loaded = True
            self.fully_loaded = True

        t_end = time.time()

        logging.debug(_('Initialized 3D visualization in %.2f seconds') % (t_end - t_start))
        logging.debug(_('Vertex count: %d') % ((len(self.vertices) + len(self.travels)) / 3))
        yield None

    def copy(self):
        copy = GcodeModel()
        for var in ["vertices", "colors", "travels", "indices", "normals",
                    "max_layers", "num_layers_to_draw", "printed_until",
                    "layer_stops", "dims", "only_current",
                    "layer_idxs_map", "count_travel_indices",
                    "count_print_indices", "count_print_vertices",
                    "path_halfwidth", "path_halfheight",
                    "gcode"]:
            setattr(copy, var, getattr(self, var))
        copy.loaded = True
        copy.fully_loaded = True
        copy.initialized = False
        return copy

    # ------------------------------------------------------------------------
    # DRAWING
    # ------------------------------------------------------------------------

    def init(self):
        with self.lock:
            self.layers_loaded = self.max_layers
            self.initialized = True
            if self.buffers_created:
                self.travel_buffer.delete()
                self.index_buffer.delete()
                self.vertex_buffer.delete()
                self.vertex_color_buffer.delete()
                self.vertex_normal_buffer.delete()
            self.travel_buffer = numpy2vbo(self.travels, use_vbos = self.use_vbos)
            self.index_buffer = numpy2vbo(self.indices, use_vbos = self.use_vbos,
                                          target = GL_ELEMENT_ARRAY_BUFFER)
            self.vertex_buffer = numpy2vbo(self.vertices, use_vbos = self.use_vbos)
            self.vertex_color_buffer = numpy2vbo(self.colors, use_vbos = self.use_vbos)
            self.vertex_normal_buffer = numpy2vbo(self.normals, use_vbos = self.use_vbos)
            if self.fully_loaded:
                # Delete numpy arrays after creating VBOs after full load
                self.travels = None
                self.indices = None
                self.vertices = None
                self.colors = None
                self.normals = None
            self.buffers_created = True

    def display(self, mode_2d=False):
        with self.lock:
            glPushMatrix()
            glTranslatef(self.offset_x, self.offset_y, 0)
            glEnableClientState(GL_VERTEX_ARRAY)

            has_vbo = isinstance(self.vertex_buffer, VertexBufferObject)
            if self.display_travels:
                self._display_travels(has_vbo)

            glEnable(GL_LIGHTING)
            glEnableClientState(GL_NORMAL_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)
            glMaterialfv(GL_FRONT, GL_SPECULAR, vec(1, 1, 1, 1))
            glMaterialfv(GL_FRONT_AND_BACK, GL_EMISSION, vec(0, 0, 0, 0))
            glMaterialf(GL_FRONT_AND_BACK, GL_SHININESS, 50)

            glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
            self._display_movements(has_vbo)

            glDisable(GL_LIGHTING)

            glDisableClientState(GL_COLOR_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)

            glPopMatrix()

    def _display_travels(self, has_vbo):
        self.travel_buffer.bind()
        glVertexPointer(3, GL_FLOAT, 0, self.travel_buffer.ptr)

        # Prevent race condition by using the number of currently loaded layers
        max_layers = self.layers_loaded
        # TODO: show current layer travels in a different color
        end = self.layer_stops[min(self.num_layers_to_draw, max_layers)]
        end_index = self.count_travel_indices[end]
        glColor4f(*self.color_travel)
        if self.only_current:
            if self.num_layers_to_draw < max_layers:
                end_prev_layer = self.layer_stops[self.num_layers_to_draw - 1]
                start_index = self.count_travel_indices[end_prev_layer + 1]
                glDrawArrays(GL_LINES, start_index, end_index - start_index + 1)
        else:
            glDrawArrays(GL_LINES, 0, end_index)

        self.travel_buffer.unbind()

    def _draw_elements(self, start, end, draw_type = GL_TRIANGLES):
        # Don't attempt printing empty layer
        if self.count_print_indices[end] == self.count_print_indices[start - 1]:
            return
        glDrawRangeElements(draw_type,
                            self.count_print_vertices[start - 1],
                            self.count_print_vertices[end] - 1,
                            self.count_print_indices[end] - self.count_print_indices[start - 1],
                            GL_UNSIGNED_INT,
                            sizeof(GLuint) * self.count_print_indices[start - 1])

    def _display_movements(self, has_vbo):
        self.vertex_buffer.bind()
        glVertexPointer(3, GL_FLOAT, 0, self.vertex_buffer.ptr)

        self.vertex_color_buffer.bind()
        glColorPointer(3, GL_FLOAT, 0, self.vertex_color_buffer.ptr)

        self.vertex_normal_buffer.bind()
        glNormalPointer(GL_FLOAT, 0, self.vertex_normal_buffer.ptr)

        self.index_buffer.bind()

        # Prevent race condition by using the number of currently loaded layers
        max_layers = self.layers_loaded

        start = 1
        layer_selected = self.num_layers_to_draw <= max_layers
        if layer_selected:
            end_prev_layer = self.layer_stops[self.num_layers_to_draw - 1]
        else:
            end_prev_layer = 0
        end = self.layer_stops[min(self.num_layers_to_draw, max_layers)]

        glDisableClientState(GL_COLOR_ARRAY)

        glColor3f(*self.color_printed[:-1])

        # Draw printed stuff until end or end_prev_layer
        cur_end = min(self.printed_until, end)
        if not self.only_current:
            if 1 <= end_prev_layer <= cur_end:
                self._draw_elements(1, end_prev_layer)
            elif cur_end >= 1:
                self._draw_elements(1, cur_end)

        glEnableClientState(GL_COLOR_ARRAY)

        # Draw nonprinted stuff until end_prev_layer
        start = max(cur_end, 1)
        if end_prev_layer >= start:
            if not self.only_current:
                self._draw_elements(start, end_prev_layer)
            cur_end = end_prev_layer

        # Draw current layer
        if layer_selected:
            glDisableClientState(GL_COLOR_ARRAY)

            glColor3f(*self.color_current_printed[:-1])

            if cur_end > end_prev_layer:
                self._draw_elements(end_prev_layer + 1, cur_end)

            glColor3f(*self.color_current[:-1])

            if end > cur_end:
                self._draw_elements(cur_end + 1, end)

            glEnableClientState(GL_COLOR_ARRAY)

        # Draw non printed stuff until end (if not ending at a given layer)
        start = max(self.printed_until, 1)
        if not layer_selected and end >= start:
            self._draw_elements(start, end)

        self.index_buffer.unbind()
        self.vertex_buffer.unbind()
        self.vertex_color_buffer.unbind()
        self.vertex_normal_buffer.unbind()

class GcodeModelLight(Model):
    """
    Model for displaying Gcode data.
    """

    color_travel = (0.6, 0.6, 0.6, 0.6)
    color_tool0 = (1.0, 0.0, 0.0, 0.6)
    color_tool1 = (0.67, 0.05, 0.9, 0.6)
    color_tool2 = (1.0, 0.8, 0., 0.6)
    color_tool3 = (1.0, 0., 0.62, 0.6)
    color_tool4 = (0., 1.0, 0.58, 0.6)
    color_printed = (0.2, 0.75, 0, 0.6)
    color_current = (0, 0.9, 1.0, 0.8)
    color_current_printed = (0.1, 0.4, 0, 0.8)

    buffers_created = False
    use_vbos = True
    loaded = False
    fully_loaded = False

    gcode = None

    def load_data(self, model_data, callback=None):
        t_start = time.time()
        self.gcode = model_data

        self.layer_idxs_map = {}
        self.layer_stops = [0]

        prev_pos = (0, 0, 0)
        layer_idx = 0
        nlines = len(model_data)
        vertices = self.vertices = numpy.zeros(nlines * 6, dtype = GLfloat)
        vertex_k = 0
        colors = self.colors = numpy.zeros(nlines * 8, dtype = GLfloat)
        color_k = 0
        self.printed_until = -1
        self.only_current = False
        while layer_idx < len(model_data.all_layers):
            with self.lock:
                nlines = len(model_data)
                if nlines * 6 != vertices.size:
                    self.vertices.resize(nlines * 6, refcheck = False)
                    self.colors.resize(nlines * 8, refcheck = False)
                layer = model_data.all_layers[layer_idx]
                has_movement = False
                for gline in layer:
                    if not gline.is_move:
                        continue
                    if gline.x is None and gline.y is None and gline.z is None:
                        continue
                    has_movement = True
                    vertices[vertex_k] = prev_pos[0]
                    vertices[vertex_k + 1] = prev_pos[1]
                    vertices[vertex_k + 2] = prev_pos[2]
                    current_pos = (gline.current_x, gline.current_y, gline.current_z)
                    vertices[vertex_k + 3] = current_pos[0]
                    vertices[vertex_k + 4] = current_pos[1]
                    vertices[vertex_k + 5] = current_pos[2]
                    vertex_k += 6

                    vertex_color = self.movement_color(gline)
                    colors[color_k] = vertex_color[0]
                    colors[color_k + 1] = vertex_color[1]
                    colors[color_k + 2] = vertex_color[2]
                    colors[color_k + 3] = vertex_color[3]
                    colors[color_k + 4] = vertex_color[0]
                    colors[color_k + 5] = vertex_color[1]
                    colors[color_k + 6] = vertex_color[2]
                    colors[color_k + 7] = vertex_color[3]
                    color_k += 8

                    prev_pos = current_pos
                    gline.gcview_end_vertex = vertex_k / 3

                if has_movement:
                    self.layer_stops.append(vertex_k / 3)
                    self.layer_idxs_map[layer_idx] = len(self.layer_stops) - 1
                    self.max_layers = len(self.layer_stops) - 1
                    self.num_layers_to_draw = self.max_layers + 1
                    self.initialized = False
                    self.loaded = True

            if callback:
                callback(layer_idx + 1)

            yield layer_idx
            layer_idx += 1

        with self.lock:
            self.dims = ((model_data.xmin, model_data.xmax, model_data.width),
                         (model_data.ymin, model_data.ymax, model_data.depth),
                         (model_data.zmin, model_data.zmax, model_data.height))

            self.vertices.resize(vertex_k, refcheck = False)
            self.colors.resize(color_k, refcheck = False)
            self.max_layers = len(self.layer_stops) - 1
            self.num_layers_to_draw = self.max_layers + 1
            self.initialized = False
            self.loaded = True
            self.fully_loaded = True

        t_end = time.time()

        logging.debug(_('Initialized 3D visualization in %.2f seconds') % (t_end - t_start))
        logging.debug(_('Vertex count: %d') % (len(self.vertices) / 3))
        yield None

    def copy(self):
        copy = GcodeModelLight()
        for var in ["vertices", "colors", "max_layers",
                    "num_layers_to_draw", "printed_until",
                    "layer_stops", "dims", "only_current",
                    "layer_idxs_map", "gcode"]:
            setattr(copy, var, getattr(self, var))
        copy.loaded = True
        copy.fully_loaded = True
        copy.initialized = False
        return copy

    # ------------------------------------------------------------------------
    # DRAWING
    # ------------------------------------------------------------------------

    def init(self):
        with self.lock:
            self.layers_loaded = self.max_layers
            self.initialized = True
            if self.buffers_created:
                self.vertex_buffer.delete()
                self.vertex_color_buffer.delete()
            self.vertex_buffer = numpy2vbo(self.vertices, use_vbos = self.use_vbos)
            self.vertex_color_buffer = numpy2vbo(self.colors, use_vbos = self.use_vbos)  # each pair of vertices shares the color
            if self.fully_loaded:
                # Delete numpy arrays after creating VBOs after full load
                self.vertices = None
                self.colors = None
            self.buffers_created = True

    def display(self, mode_2d=False):
        with self.lock:
            glPushMatrix()
            glTranslatef(self.offset_x, self.offset_y, 0)
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_COLOR_ARRAY)

            self._display_movements(mode_2d)

            glDisableClientState(GL_COLOR_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)
            glPopMatrix()

    def _display_movements(self, mode_2d=False):
        self.vertex_buffer.bind()
        has_vbo = isinstance(self.vertex_buffer, VertexBufferObject)
        if has_vbo:
            glVertexPointer(3, GL_FLOAT, 0, None)
        else:
            glVertexPointer(3, GL_FLOAT, 0, self.vertex_buffer.ptr)

        self.vertex_color_buffer.bind()
        if has_vbo:
            glColorPointer(4, GL_FLOAT, 0, None)
        else:
            glColorPointer(4, GL_FLOAT, 0, self.vertex_color_buffer.ptr)

        # Prevent race condition by using the number of currently loaded layers
        max_layers = self.layers_loaded

        start = 0
        if self.num_layers_to_draw <= max_layers:
            end_prev_layer = self.layer_stops[self.num_layers_to_draw - 1]
        else:
            end_prev_layer = -1
        end = self.layer_stops[min(self.num_layers_to_draw, max_layers)]

        glDisableClientState(GL_COLOR_ARRAY)

        glColor4f(*self.color_printed)

        # Draw printed stuff until end or end_prev_layer
        cur_end = min(self.printed_until, end)
        if not self.only_current:
            if 0 <= end_prev_layer <= cur_end:
                glDrawArrays(GL_LINES, start, end_prev_layer)
            elif cur_end >= 0:
                glDrawArrays(GL_LINES, start, cur_end)

        glEnableClientState(GL_COLOR_ARRAY)

        # Draw nonprinted stuff until end_prev_layer
        start = max(cur_end, 0)
        if end_prev_layer >= start:
            if not self.only_current:
                glDrawArrays(GL_LINES, start, end_prev_layer - start)
            cur_end = end_prev_layer

        # Draw current layer
        if end_prev_layer >= 0:
            glDisableClientState(GL_COLOR_ARRAY)

            # Backup & increase line width
            orig_linewidth = (GLfloat)()
            glGetFloatv(GL_LINE_WIDTH, orig_linewidth)
            glLineWidth(2.0)

            glColor4f(*self.color_current_printed)

            if cur_end > end_prev_layer:
                glDrawArrays(GL_LINES, end_prev_layer, cur_end - end_prev_layer)

            glColor4f(*self.color_current)

            if end > cur_end:
                glDrawArrays(GL_LINES, cur_end, end - cur_end)

            # Restore line width
            glLineWidth(orig_linewidth)

            glEnableClientState(GL_COLOR_ARRAY)

        # Draw non printed stuff until end (if not ending at a given layer)
        start = max(self.printed_until, 0)
        end = end - start
        if end_prev_layer < 0 and end > 0 and not self.only_current:
            glDrawArrays(GL_LINES, start, end)

        self.vertex_buffer.unbind()
        self.vertex_color_buffer.unbind()
