# pyright: standard

""" Draws the circularising burn at the apoapsis (see ``calc/circular_burn.cpp``) as an arrow along its thrust. """

import moderngl
import numpy

from imgui_bundle import imgui
from pyglm import glm

from calc.native import ApoapsisBurn

from .constants import (
    BURN_ARROW_COLOR, BURN_ARROW_LENGTH_KM, BURN_ARROW_WIDTH, BURN_FRAGMENT_SHADER_PATH, BURN_VERTEX_SHADER_PATH,
    SUN_DIRECTION,
)
from .shaders import create_shader_program, set_uniform
from .trajectory import _CALC_TO_DISPLAY, TrajectoryLine

_HEAD_LENGTH = 0.25
_HEAD_RADIUS = 0.08
""" The size of the arrow's conical head, as fractions of its length. """
_HEAD_SEGMENTS = 32
""" How many flat sides approximate the cone's round surface. """
_AMBIENT = 0.35
""" The brightness of the cone's side facing away from the Sun. """
LABEL_COLOR = imgui.IM_COL32(255, 255, 255, 255)
SHADOW = imgui.IM_COL32(0, 0, 0, 160)


def _cone(base: numpy.ndarray, axis: numpy.ndarray, length: float, radius: float) -> numpy.ndarray:
    """ The triangles of a closed cone from the centre of its ``base`` along the unit ``axis``, as rows of
    (position, normal), 6 floats per vertex. """

    # Two unit vectors perpendicular to the axis and to each other.
    helper = numpy.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else numpy.array([0.0, 1.0, 0.0])
    u = numpy.cross(axis, helper)
    u /= numpy.linalg.norm(u)
    v = numpy.cross(axis, u)

    tip = base + length * axis
    angles = numpy.linspace(0.0, 2.0 * numpy.pi, _HEAD_SEGMENTS + 1)
    radial = numpy.cos(angles)[:, None] * u + numpy.sin(angles)[:, None] * v
    rim = base + radius * radial
    # The side's normal leans towards the tip by the cone's half angle.
    normals = length * radial + radius * axis
    normals /= numpy.linalg.norm(normals, axis=1, keepdims=True)

    vertices = []
    for i in range(_HEAD_SEGMENTS):
        tip_normal = normals[i] + normals[i + 1]
        tip_normal /= numpy.linalg.norm(tip_normal)
        vertices += [(tip, tip_normal), (rim[i], normals[i]), (rim[i + 1], normals[i + 1])]
        vertices += [(base, -axis), (rim[i + 1], -axis), (rim[i], -axis)]

    return numpy.array([numpy.concatenate(vertex) for vertex in vertices])


class BurnArrow:
    """ An arrow from the apoapsis along the burn's change of velocity (the direction of the thrust): a line for its
    shaft, like the trajectory's, and a cone lit by the Sun for its head. Its length is fixed
    (``BURN_ARROW_LENGTH_KM``) so it's visible from afar; the magnitude is written next to its tip. Both parts are
    drawn into the 3D scene, so Titan hides them when it's in front. """

    def __init__(self, context: moderngl.Context) -> None:

        self._context = context
        self._shaft = TrajectoryLine(context, BURN_ARROW_COLOR, BURN_ARROW_COLOR, BURN_ARROW_WIDTH)

        self._program = create_shader_program(
            context=context,
            vert_shader_path=BURN_VERTEX_SHADER_PATH,
            frag_shader_path=BURN_FRAGMENT_SHADER_PATH,
        )
        set_uniform(self._program, "uColor", BURN_ARROW_COLOR)
        set_uniform(self._program, "uSunDirection", SUN_DIRECTION)
        set_uniform(self._program, "uAmbient", _AMBIENT)

        self._scope = context.scope(enable_only=moderngl.DEPTH_TEST)
        self._buffer: moderngl.Buffer | None = None
        self._vao: moderngl.VertexArray | None = None

        self._tip = glm.vec3(0.0)
        """ The arrow's tip in km, in the display's frame (for the label). """
        self._label = ""

    def set_burn(self, burn: ApoapsisBurn) -> None:
        """ Points the arrow along a ``burn``'s change of velocity, starting at its position. """

        # In km, in the display's frame (a reflection of the calculations', so lengths and normals are unchanged).
        length = BURN_ARROW_LENGTH_KM
        base = (_CALC_TO_DISPLAY @ burn.position) / 1000.0
        direction = _CALC_TO_DISPLAY @ (burn.delta_v / numpy.linalg.norm(burn.delta_v))
        head_base = base + (1.0 - _HEAD_LENGTH) * length * direction

        # The shaft stops where the cone starts. ``set_polyline`` takes positions in m in the calculations' frame.
        shaft = numpy.array([base, head_base]) * 1000.0 @ _CALC_TO_DISPLAY
        self._shaft.set_polyline(shaft, numpy.zeros(2))

        if self._buffer is not None:
            self._buffer.release()
        cone = _cone(head_base, direction, _HEAD_LENGTH * length, _HEAD_RADIUS * length)
        self._buffer = self._context.buffer(cone.astype(numpy.float32).tobytes())
        self._vao = self._context.vertex_array(self._program, [(self._buffer, "3f 3f", "in_position", "in_normal")])
        self._vertex_count = len(cone)

        self._tip = glm.vec3(*(base + length * direction))
        self._label = f"Burn: {numpy.linalg.norm(burn.delta_v):,.1f} m/s"

    def draw(self, view_projection: glm.mat4, framebuffer_size: tuple[int, int]) -> None:
        """ Draws the arrow, depth-tested against the scene. """

        self._shaft.draw(view_projection, framebuffer_size)

        if self._vao is None:
            return
        set_uniform(self._program, "uViewProj", view_projection)
        with self._scope:
            self._vao.render(mode=moderngl.TRIANGLES, vertices=self._vertex_count)

    def draw_label(self, view_projection: glm.mat4) -> None:
        """ Writes the burn's magnitude next to the arrow's tip. Must be called while building the GUI. """

        clip = view_projection * glm.vec4(self._tip, 1.0)
        if clip.w <= 0.0:
            return  # Behind the camera.

        size = imgui.get_io().display_size
        x = (clip.x / clip.w * 0.5 + 0.5) * size.x + 8.0
        y = (0.5 - clip.y / clip.w * 0.5) * size.y  # ImGui's y axis points down.

        draw_list = imgui.get_background_draw_list()
        draw_list.add_text((x + 1, y + 1), SHADOW, self._label)
        draw_list.add_text((x, y), LABEL_COLOR, self._label)
