#!/usr/bin/env python

# This file is part of the Printrun suite.
#
# Printrun is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Printrun is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Printrun.  If not, see <http://www.gnu.org/licenses/>.

from threading import Lock
import logging
import traceback
import numpy
import numpy.linalg

import wx
from wx import glcanvas

import pyglet
pyglet.options['debug_gl'] = True

from pyglet.gl import glEnable, glDisable, GL_LIGHTING, glLightfv, \
    GL_LIGHT0, GL_LIGHT1, GL_LIGHT2, GL_POSITION, GL_DIFFUSE, \
    GL_AMBIENT, GL_SPECULAR, GL_COLOR_MATERIAL, \
    glShadeModel, GL_SMOOTH, GL_NORMALIZE, \
    GL_BLEND, glBlendFunc, glClear, glClearColor, \
    glClearDepth, GL_COLOR_BUFFER_BIT, GL_CULL_FACE, \
    GL_DEPTH_BUFFER_BIT, glDepthFunc, GL_DEPTH_TEST, \
    GLdouble, glGetDoublev, glGetIntegerv, GLint, \
    GL_LEQUAL, glLoadIdentity, glMatrixMode, GL_MODELVIEW, \
    GL_MODELVIEW_MATRIX, GL_ONE_MINUS_SRC_ALPHA, glOrtho, \
    GL_PROJECTION, GL_PROJECTION_MATRIX, glScalef, \
    GL_SRC_ALPHA, glTranslatef, gluPerspective, gluUnProject, \
    glViewport, GL_VIEWPORT
from pyglet import gl
from .trackball import trackball, mulquat,axis_to_quat
from .libtatlin.actors import vec

class wxGLPanel(wx.Panel):
    '''A simple class for using OpenGL with wxPython.'''

    orbit_control = True
    orthographic = True
    color_background = (0.98, 0.98, 0.78, 1)
    do_lights = True

    def __init__(self, parent, id, pos = wx.DefaultPosition,
                 size = wx.DefaultSize, style = 0,
                 antialias_samples = 0):
        # Forcing a no full repaint to stop flickering
        style = style | wx.NO_FULL_REPAINT_ON_RESIZE
        super(wxGLPanel, self).__init__(parent, id, pos, size, style)

        self.GLinitialized = False
        self.mview_initialized = False
        attribList = (glcanvas.WX_GL_RGBA,  # RGBA
                      glcanvas.WX_GL_DOUBLEBUFFER,  # Double Buffered
                      glcanvas.WX_GL_DEPTH_SIZE, 24)  # 24 bit

        if antialias_samples > 0 and hasattr(glcanvas, "WX_GL_SAMPLE_BUFFERS"):
            attribList += (glcanvas.WX_GL_SAMPLE_BUFFERS, 1,
                           glcanvas.WX_GL_SAMPLES, antialias_samples)

        self.width = None
        self.height = None

        self.sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.canvas = glcanvas.GLCanvas(self, attribList = attribList)
        self.context = glcanvas.GLContext(self.canvas)
        self.sizer.Add(self.canvas, 1, wx.EXPAND)
        self.SetSizerAndFit(self.sizer)

        self.rot_lock = Lock()
        self.basequat = [0, 0, 0, 1]
        self.zoom_factor = 1.0
        # top view
        self.angle_z = 0
        self.angle_x = 0 #math.radians(90);

        self.gl_broken = False

        # bind events
        self.canvas.Bind(wx.EVT_ERASE_BACKGROUND, self.processEraseBackgroundEvent)
        self.canvas.Bind(wx.EVT_SIZE, self.processSizeEvent)
        self.canvas.Bind(wx.EVT_PAINT, self.processPaintEvent)

    def processEraseBackgroundEvent(self, event):
        '''Process the erase background event.'''
        pass  # Do nothing, to avoid flashing on MSWin

    def processSizeEvent(self, event):
        '''Process the resize event.'''
        if self.IsFrozen():
            event.Skip()
            return
        if (wx.VERSION > (2, 9) and self.canvas.IsShownOnScreen()) or self.canvas.GetContext():
            # Make sure the frame is shown before calling SetCurrent.
            self.canvas.SetCurrent(self.context)
            self.OnReshape()
            self.Refresh(False)
            timer = wx.CallLater(100, self.Refresh)
            timer.Start()
        event.Skip()

    def processPaintEvent(self, event):
        '''Process the drawing event.'''
        self.canvas.SetCurrent(self.context)

        if not self.gl_broken:
            try:
                self.OnInitGL()
                self.OnDraw()
            except pyglet.gl.lib.GLException:
                self.gl_broken = True
                logging.error(_("OpenGL failed, disabling it:")
                              + "\n" + traceback.format_exc())
        event.Skip()

    def Destroy(self):
        # clean up the pyglet OpenGL context
        self.pygletcontext.destroy()
        # call the super method
        super(wxGLPanel, self).Destroy()

    # ==========================================================================
    # GLFrame OpenGL Event Handlers
    # ==========================================================================
    def OnInitGL(self, call_reshape = True):
        '''Initialize OpenGL for use in the window.'''
        if self.GLinitialized:
            return
        self.GLinitialized = True
        # create a pyglet context for this panel
        self.pygletcontext = gl.Context(gl.current_context)
        self.pygletcontext.canvas = self
        self.pygletcontext.set_current()
        # normal gl init
        glClearColor(*self.color_background)
        glClearDepth(1.0)                # set depth value to 1
        glDepthFunc(GL_LEQUAL)
        glEnable(GL_COLOR_MATERIAL)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_CULL_FACE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        if call_reshape:
            self.OnReshape()

    def OnReshape(self):
        """Reshape the OpenGL viewport based on the size of the window"""
        size = self.GetClientSize()
        oldwidth, oldheight = self.width, self.height
        width, height = size.width, size.height
        if width < 1 or height < 1:
            return
        self.width = max(float(width), 1.0)
        self.height = max(float(height), 1.0)
        self.OnInitGL(call_reshape = False)
        glViewport(0, 0, width, height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        if self.orthographic:
            glOrtho(-width / 2, width / 2, -height / 2, height / 2,
                    -5 * self.dist, 5 * self.dist)
        else:
            gluPerspective(60., float(width) / height, 10.0, 3 * self.dist)
            glTranslatef(0, 0, -self.dist)  # Move back
        glMatrixMode(GL_MODELVIEW)

        if not self.mview_initialized:
            self.reset_mview(0.9)
            self.mview_initialized = True
        elif oldwidth is not None and oldheight is not None:
            wratio = self.width / oldwidth
            hratio = self.height / oldheight

            factor = min(wratio * self.zoomed_width, hratio * self.zoomed_height)
            x, y, _ = self.mouse_to_3d(self.width / 2, self.height / 2)
            self.zoom(factor, (x, y))
            self.zoomed_width *= wratio / factor
            self.zoomed_height *= hratio / factor

        # Wrap text to the width of the window
        if self.GLinitialized:
            self.pygletcontext.set_current()
            self.update_object_resize()

    def setup_lights(self):
        if not self.do_lights:
            return
        glEnable(GL_LIGHTING)
        glDisable(GL_LIGHT0)
        glLightfv(GL_LIGHT0, GL_AMBIENT, vec(0.4, 0.4, 0.4, 1.0))
        glLightfv(GL_LIGHT0, GL_SPECULAR, vec(0, 0, 0, 0))
        glLightfv(GL_LIGHT0, GL_DIFFUSE, vec(0, 0, 0, 0))
        glEnable(GL_LIGHT1)
        glLightfv(GL_LIGHT1, GL_AMBIENT, vec(0, 0, 0, 1.0))
        glLightfv(GL_LIGHT1, GL_SPECULAR, vec(0.6, 0.6, 0.6, 1.0))
        glLightfv(GL_LIGHT2, GL_DIFFUSE, vec(0.8, 0.8, 0.8, 1))
        glLightfv(GL_LIGHT1, GL_POSITION, vec(1, 2, 3, 0))
        glEnable(GL_LIGHT2)
        glLightfv(GL_LIGHT2, GL_AMBIENT, vec(0, 0, 0, 1.0))
        glLightfv(GL_LIGHT2, GL_SPECULAR, vec(0.6, 0.6, 0.6, 1.0))
        glLightfv(GL_LIGHT2, GL_DIFFUSE, vec(0.8, 0.8, 0.8, 1))
        glLightfv(GL_LIGHT2, GL_POSITION, vec(-1, -1, 3, 0))
        glEnable(GL_NORMALIZE)
        glShadeModel(GL_SMOOTH)

    def reset_mview(self, factor):
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        self.setup_lights()
        if self.orthographic:
            wratio = self.width / self.dist
            hratio = self.height / self.dist
            minratio = float(min(wratio, hratio))
            self.zoom_factor = 1.0
            self.zoomed_width = wratio / minratio
            self.zoomed_height = hratio / minratio
            glScalef(factor * minratio, factor * minratio, 1)

    def OnDraw(self, *args, **kwargs):
        """Draw the window."""
        self.pygletcontext.set_current()
        glClearColor(*self.color_background)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        self.draw_objects()
        self.canvas.SwapBuffers()

    # ==========================================================================
    # To be implemented by a sub class
    # ==========================================================================
    def create_objects(self):
        '''create opengl objects when opengl is initialized'''
        pass

    def update_object_resize(self):
        '''called when the window recieves only if opengl is initialized'''
        pass

    def draw_objects(self):
        '''called in the middle of ondraw after the buffer has been cleared'''
        pass

    # ==========================================================================
    # Utils
    # ==========================================================================
    def get_modelview_mat(self, local_transform):
        mvmat = (GLdouble * 16)()
        glGetDoublev(GL_MODELVIEW_MATRIX, mvmat)
        return mvmat

    def mouse_to_3d(self, x, y, z = 1.0, local_transform = False):
        x = float(x)
        y = self.height - float(y)
        # The following could work if we were not initially scaling to zoom on
        # the bed
        # if self.orthographic:
        #    return (x - self.width / 2, y - self.height / 2, 0)
        pmat = (GLdouble * 16)()
        mvmat = self.get_modelview_mat(local_transform)
        viewport = (GLint * 4)()
        px = (GLdouble)()
        py = (GLdouble)()
        pz = (GLdouble)()
        glGetIntegerv(GL_VIEWPORT, viewport)
        glGetDoublev(GL_PROJECTION_MATRIX, pmat)
        glGetDoublev(GL_MODELVIEW_MATRIX, mvmat)
        gluUnProject(x, y, z, mvmat, pmat, viewport, px, py, pz)
        return (px.value, py.value, pz.value)

    def mouse_to_ray(self, x, y, local_transform = False):
        x = float(x)
        y = self.height - float(y)
        pmat = (GLdouble * 16)()
        mvmat = (GLdouble * 16)()
        viewport = (GLint * 4)()
        px = (GLdouble)()
        py = (GLdouble)()
        pz = (GLdouble)()
        glGetIntegerv(GL_VIEWPORT, viewport)
        glGetDoublev(GL_PROJECTION_MATRIX, pmat)
        mvmat = self.get_modelview_mat(local_transform)
        gluUnProject(x, y, 1, mvmat, pmat, viewport, px, py, pz)
        ray_far = (px.value, py.value, pz.value)
        gluUnProject(x, y, 0., mvmat, pmat, viewport, px, py, pz)
        ray_near = (px.value, py.value, pz.value)
        return ray_near, ray_far

    def mouse_to_plane(self, x, y, plane_normal, plane_offset, local_transform = False):
        # Ray/plane intersection
        ray_near, ray_far = self.mouse_to_ray(x, y, local_transform)
        ray_near = numpy.array(ray_near)
        ray_far = numpy.array(ray_far)
        ray_dir = ray_far - ray_near
        ray_dir = ray_dir / numpy.linalg.norm(ray_dir)
        plane_normal = numpy.array(plane_normal)
        q = ray_dir.dot(plane_normal)
        if q == 0:
            return None
        t = - (ray_near.dot(plane_normal) + plane_offset) / q
        if t < 0:
            return None
        return ray_near + t * ray_dir

    def zoom(self, factor, to = None):
        glMatrixMode(GL_MODELVIEW)
        if to:
            delta_x = to[0]
            delta_y = to[1]
            glTranslatef(delta_x, delta_y, 0)
        glScalef(factor, factor, 1)
        self.zoom_factor *= factor
        if to:
            glTranslatef(-delta_x, -delta_y, 0)
        wx.CallAfter(self.Refresh)

    def zoom_to_center(self, factor):
        self.canvas.SetCurrent(self.context)
        x, y, _ = self.mouse_to_3d(self.width / 2, self.height / 2)
        self.zoom(factor, (x, y))

    def orbit(self, p1x, p1y, p2x, p2y):

        rz = p2x-p1x;
        self.angle_z-=rz
        rotz = axis_to_quat([0.0,0.0,1.0],self.angle_z)

        rx = p2y-p1y;
        self.angle_x+=rx
        rota = axis_to_quat([1.0,0.0,0.0],self.angle_x)
    
        return mulquat(rotz,rota)

    def handle_rotation(self, event):
        if self.initpos is None:
            self.initpos = event.GetPositionTuple()
        else:
            p1 = self.initpos
            p2 = event.GetPositionTuple()
            sz = self.GetClientSize()
            p1x = float(p1[0]) / (sz[0] / 2) - 1
            p1y = 1 - float(p1[1]) / (sz[1] / 2)
            p2x = float(p2[0]) / (sz[0] / 2) - 1
            p2y = 1 - float(p2[1]) / (sz[1] / 2)
            if self.orbit_control:
                with self.rot_lock:
                    self.basequat = self.orbit(p1x, p1y, p2x, p2y)
            else:
                quat = trackball(p1x, p1y, p2x, p2y, self.dist / 250.0)
                with self.rot_lock:
                    self.basequat = mulquat(self.basequat, quat)
            self.initpos = p2

    def handle_translation(self, event):
        if self.initpos is None:
            self.initpos = event.GetPositionTuple()
        else:
            p1 = self.initpos
            p2 = event.GetPositionTuple()
            if self.orthographic:
                x1, y1, _ = self.mouse_to_3d(p1[0], p1[1])
                x2, y2, _ = self.mouse_to_3d(p2[0], p2[1])
                glTranslatef(x2 - x1, y2 - y1, 0)
            else:
                glTranslatef(p2[0] - p1[0], -(p2[1] - p1[1]), 0)
            self.initpos = p2
