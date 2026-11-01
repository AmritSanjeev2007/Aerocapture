# pyright: standard

""" A gizmo in the corner of the window which shows the orientation of the world's axes, like Blender's. """

import moderngl

from imgui_bundle import imgui
from pyglm import glm

from .constants import (
    AXES_FRAGMENT_SHADER_PATH, AXES_GIZMO_LENGTH, AXES_GIZMO_MARGIN, AXES_VERTEX_SHADER_PATH, AXIS_COLORS,
    CALC_TO_DISPLAY, GUI_SCALE,
)
from .shaders import create_fullscreen_quad, create_shader_program, set_uniform

AXIS_NAMES = ("X", "Y", "Z")
LABEL_SIZE = 12.0
""" The font size of the axis names, in pixels (before ``GUI_SCALE``). They're written on the tips' circles. """
LABEL_COLOR = imgui.IM_COL32(0, 0, 0, 255)
_AXES = (glm.vec3(1, 0, 0), glm.vec3(0, 1, 0), glm.vec3(0, 0, 1))


class AxesGizmo:
    """ Draws the x (red), y (green) and z (blue) axes of the calculations' frame (see ``CALC_TO_DISPLAY``) in the
    bottom right corner of the window, rotated by the camera's rotation. It's drawn over the scene with its own shader, and the axis names are added with
    ImGui (so the gizmo stays below the GUI's windows). """

    def __init__(self, context: moderngl.Context) -> None:

        self._context = context
        self._program = create_shader_program(
            context=context,
            vert_shader_path=AXES_VERTEX_SHADER_PATH,
            frag_shader_path=AXES_FRAGMENT_SHADER_PATH,
        )
        self._program["uAxisColors"].write(b"".join(glm.vec3(*color).to_bytes() for color in AXIS_COLORS))
        self._vao = create_fullscreen_quad(context, self._program)
        self._scope = context.scope(enable_only=moderngl.BLEND)

    @staticmethod
    def _layout(size: tuple[float, float]) -> tuple[glm.vec2, float]:
        """ The centre and the axis length of the gizmo, in the units of a window of the given ``size``
        (measured from the bottom left corner). """

        length = AXES_GIZMO_LENGTH * GUI_SCALE
        offset = (AXES_GIZMO_MARGIN + AXES_GIZMO_LENGTH) * GUI_SCALE
        return glm.vec2(size[0] - offset, offset), length

    def draw(self, rotation: glm.mat3, framebuffer_size: tuple[int, int]) -> None:
        """ Draws the axes, rotated by the camera's ``rotation`` (world frame -> view frame), on top of whatever
        has been drawn so far, ignoring the depth buffer. """

        rotation = rotation * CALC_TO_DISPLAY

        # ImGui (and GUI_SCALE) measure in window points, which differ from framebuffer pixels on high DPI screens.
        window_width = imgui.get_io().display_size.x
        pixels_per_point = framebuffer_size[0] / max(window_width, 1.0)
        center, length = self._layout((framebuffer_size[0] / pixels_per_point, framebuffer_size[1] / pixels_per_point))
        center, length = center * pixels_per_point, length * pixels_per_point

        # The quad only covers the gizmo, with room for the tip circles and the backdrop.
        half_size = length + 20.0 * GUI_SCALE * pixels_per_point
        width, height = framebuffer_size
        rect = (
            2.0 * center.x / width - 1.0, 2.0 * center.y / height - 1.0,
            2.0 * half_size / width, 2.0 * half_size / height,
        )

        set_uniform(self._program, "uRect", rect)
        set_uniform(self._program, "uRotation", rotation)  # Calculation frame -> view frame
        set_uniform(self._program, "uCenter", (center.x, center.y))
        set_uniform(self._program, "uLength", length)
        set_uniform(self._program, "uPixelScale", GUI_SCALE * pixels_per_point)

        with self._scope:
            self._context.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA  # Premultiplied alpha.
            self._vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)

    def draw_labels(self, rotation: glm.mat3) -> None:
        """ Writes the names of the positive axes onto their circles. Must be called while building the GUI. """

        display_size = imgui.get_io().display_size
        center, length = self._layout((display_size.x, display_size.y))
        draw_list = imgui.get_background_draw_list()
        imgui.push_font(None, LABEL_SIZE * GUI_SCALE)

        for name, axis in zip(AXIS_NAMES, _AXES):
            tip = rotation * CALC_TO_DISPLAY * axis
            # ImGui's y axis points down, while the view frame's points up.
            x, y = center.x + tip.x * length, display_size.y - (center.y + tip.y * length)
            text_size = imgui.calc_text_size(name)
            draw_list.add_text((x - text_size.x / 2, y - text_size.y / 2), LABEL_COLOR, name)

        imgui.pop_font()
