# pyright: standard

""" Draws the spacecraft's trajectory, calculated in C++ (see ``calc/trajectory.cpp``), as a line. """

import math
import moderngl
import numpy

from imgui_bundle import imgui
from pyglm import glm

from calc.native import TrajectoryArrays

from .constants import (
    CALC_TO_DISPLAY, TRAJECTORY_END_COLOR, TRAJECTORY_FRAGMENT_SHADER_PATH, TRAJECTORY_START_COLOR,
    TRAJECTORY_VERTEX_SHADER_PATH, TRAJECTORY_WIDTH,
)
from .shaders import create_shader_program, set_uniform

_POINT_SIZE = 16
""" The size in bytes of one point (``vec4``): position in km (display frame) and time in s. """

_CALC_TO_DISPLAY = numpy.array([[CALC_TO_DISPLAY[column][row] for column in range(3)] for row in range(3)])
""" ``CALC_TO_DISPLAY`` as a (row-major) NumPy matrix. """


class TrajectoryLine:
    """ The spacecraft's trajectory, drawn as a line coloured by time (from ``TRAJECTORY_START_COLOR`` to
    ``TRAJECTORY_END_COLOR``) through the states calculated by ``calc/trajectory.cpp``. It's drawn into the 3D
    scene, so Titan and Saturn hide the parts behind them. """

    def __init__(self, context: moderngl.Context, start_color: tuple[float, float, float] = TRAJECTORY_START_COLOR,
                 end_color: tuple[float, float, float] = TRAJECTORY_END_COLOR,
                 width: float = TRAJECTORY_WIDTH) -> None:

        self._context = context
        self.width = width
        """ The width of the line in window points. """

        self._program = create_shader_program(
            context=context,
            vert_shader_path=TRAJECTORY_VERTEX_SHADER_PATH,
            frag_shader_path=TRAJECTORY_FRAGMENT_SHADER_PATH,
        )
        set_uniform(self._program, "uStartColor", start_color)
        set_uniform(self._program, "uEndColor", end_color)

        self._scope = context.scope(enable_only=moderngl.DEPTH_TEST | moderngl.BLEND)
        self._buffers: list[moderngl.Buffer] = []
        self._vao: moderngl.VertexArray | None = None

        self.point_count = 0
        """ The number of points (one per time step) the line goes through. """
        self.time_range = (0.0, 0.0)
        """ The time (s) of the first and the last point. """
        self.impacted = False
        """ Whether the trajectory ended by hitting Titan's surface. """

    def set_points(self, trajectory: TrajectoryArrays) -> None:
        """ Draws the line through the states of a ``trajectory`` (e.g. from
        ``calc.trajectory.Trajectory.calculate_trajectory``), replacing any previous one. """

        self.impacted = trajectory.impacted
        self.set_polyline(trajectory.positions, trajectory.times)

    def set_polyline(self, positions: numpy.ndarray, times: numpy.ndarray) -> None:
        """ Draws the line through any (N, 3) ``positions`` (m, in the calculations' frame), coloured by their
        (N,) ``times`` (s), replacing any previous one. """

        for buffer in self._buffers:
            buffer.release()

        count = len(times)
        self.point_count = count
        self.time_range = (float(times[0]), float(times[-1])) if count else (0.0, 0.0)

        # The points, ready for the vertex shader: xyz in the display's frame and in km, w the time in s.
        points = numpy.empty((count, 4), dtype=numpy.float32)
        points[:, :3] = (positions @ _CALC_TO_DISPLAY.T) / 1000.0
        points[:, 3] = times

        # Each segment is an instance, made of its start and end points: the same points, shifted by one.
        self._vao = None
        self._buffers = []
        if count > 1:
            starts = self._context.buffer(points[:-1].tobytes())
            ends = self._context.buffer(points[1:].tobytes())
            self._buffers = [starts, ends]
            self._vao = self._context.vertex_array(
                self._program, [(starts, "4f/i", "in_start"), (ends, "4f/i", "in_end")]
            )

    def draw(self, view_projection: glm.mat4, framebuffer_size: tuple[int, int], shown_until: float = math.inf) -> None:
        """ Draws the line, depth-tested against the scene. Only the part up to the time ``shown_until`` (s) is
        drawn, e.g. to animate the spacecraft's progress. """

        if self._vao is None:
            return

        set_uniform(self._program, "uViewProj", view_projection)
        set_uniform(self._program, "uResolution", framebuffer_size)
        # The width is in window points, which differ from framebuffer pixels on high DPI screens.
        pixels_per_point = framebuffer_size[0] / max(imgui.get_io().display_size.x, 1.0)
        set_uniform(self._program, "uWidth", self.width * pixels_per_point)
        set_uniform(self._program, "uTimeRange", self.time_range)
        set_uniform(self._program, "uShownUntil", min(shown_until, 3.0e38))  # Infinity isn't a valid uniform.

        with self._scope:
            self._context.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA  # Premultiplied alpha.
            self._vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4, instances=self.point_count - 1)
