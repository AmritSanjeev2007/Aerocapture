# pyright: standard

""" Renders the 3D scene to more efficiently simulate the approach of the spacecraft. """

import glfw
import math
import moderngl

from functools import partial
from pathlib import Path

from imgui_bundle import imgui
from pyglm import glm
from typing import Any, Callable, cast

from .axes import AxesGizmo
from .burn import BurnArrow
from .camera import Camera
from .constants import (
    CITATIONS_PATH, CLEAR_COLOR, FAR_PLANE_KM, FIELD_OF_VIEW_DEG, GUI_SCALE, INITIAL_WINDOW_SIZE, NEAR_PLANE_KM,
    SATURN_TEXTURE_PATH, STARMAP_MAX_WIDTH, STARMAP_TEXTURE_PATH, TITAN_ORBIT_RADIUS_KM, TITAN_RADIUS_KM, TITAN_TEXTURE_PATH,
)
from .control import attach_orbit_controls
from .gui import Gui
from .loading import TextureJob, load_textures
from .scene import Scene
from .textures import decode_hdr_map_image, decode_map_image
from .trajectory import TrajectoryLine

from calc.native import ApoapsisBurn, TrajectoryArrays


CITATIONS_MARGIN = 20
""" The distance in pixels (before ``GUI_SCALE``) of the citations from the bottom left corner of the window. """
WHITE = imgui.IM_COL32(255, 255, 255, 255)
SHADOW = imgui.IM_COL32(0, 0, 0, 160)
""" Drawn under the citations to keep the white text readable when it overlaps a bright Titan or Saturn. """

def read_citations(path: Path) -> list[str]:
    """ Returns the credit lines of the citations file at ``path``, leaving out the source links. """

    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("Retrieved from")]


class Renderer:
    """ Initializes the renderer. It takes in few (optional) arguments such as whether to render
        saturn or the star skybox.

    The object creates and manages the GLFW window, the OpenGL context, the camera, the scene and the GUI. The
    camera uses Blender's viewport controls, see ``control.attach_orbit_controls``, and the GUI is drawn with
    Dear ImGui, see ``gui.Gui``. """

    def __init__(self, saturn: bool = True, skybox: bool = True, window_title: str = "Titan Aerocapture") -> None:

        glfw.init()

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)  # The trajectory is calculated in C++, so no compute shaders.
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)

        self.window = glfw.create_window(*INITIAL_WINDOW_SIZE, window_title, None, None)
        """ A handle to the object that manages the window. """
        assert self.window, "Could not create a window with an OpenGL 3.3 context."

        glfw.make_context_current(self.window)
        glfw.swap_interval(1)

        self.ctx = moderngl.create_context()
        """ A handle to the context used by OpenGL to render objects while minimizing boilerplate. """
        self.ctx.enable(moderngl.DEPTH_TEST)
        self.ctx.depth_func = "<="  # The starfield is drawn at exactly the far plane.

        self.framebuffer_size: tuple[int, int] = glfw.get_framebuffer_size(self.window)
        """ The size of the framebuffer in pixels (width, height). It changes as the window is resized. """

        def viewport_resizer(_: Any, w: int, h: int) -> None:
            self.framebuffer_size = (w, h)
            self.ctx.viewport = (0, 0, w, h)

        glfw.set_framebuffer_size_callback(self.window, viewport_resizer)

        max_size = self.ctx.info["GL_MAX_TEXTURE_SIZE"]
        jobs = [TextureJob("titan", partial(decode_map_image, TITAN_TEXTURE_PATH, max_size))]
        if saturn:
            jobs.append(TextureJob("saturn", partial(decode_map_image, SATURN_TEXTURE_PATH, max_size)))
        if skybox:
            max_width = min(STARMAP_MAX_WIDTH, max_size)
            jobs.append(TextureJob("sky", partial(decode_hdr_map_image, STARMAP_TEXTURE_PATH, max_width)))

        self.gui = Gui(self.window)
        """ The ImGui context, whose widgets are drawn on top of the scene. """

        textures = load_textures(self.window, self.ctx, self.gui, jobs, window_title)
        self.scene = Scene(self.ctx, textures["titan"], textures.get("saturn"), textures.get("sky"))

        # Starts slightly above the ring plane and looks at Titan with Saturn off to the side.
        self.camera = Camera(
            target=glm.vec3(self.scene.titan_position),
            distance=4.0 * TITAN_RADIUS_KM,
            yaw=math.radians(70.0),
            pitch=math.radians(10.0),
            minimum_distance=TITAN_RADIUS_KM + 20.0,
            maximum_distance=2.0 * TITAN_ORBIT_RADIUS_KM,
        )
        attach_orbit_controls(self.window, self.camera, self.gui)

        self.trajectory: TrajectoryLine | None = None
        """ The spacecraft's trajectory, see ``set_trajectory``. """
        self.show_trajectory = True
        self.trajectory_shown_until = math.inf
        """ Only the trajectory up to this time (s) is drawn, e.g. to animate the spacecraft's progress. """

        self.burn: BurnArrow | None = None
        """ The arrow of the circularising burn at the apoapsis, see ``set_burn``. """

        self.axes = AxesGizmo(self.ctx)
        self.show_axes = True
        self.show_citations = True
        self.show_display_panel = True
        self._citations = read_citations(CITATIONS_PATH)

        self._should_run = False

    @property
    def projection_matrix(self) -> glm.mat4x4:
        """ Returns the (readonly) perspective projection matrix for the current window size. """

        width, height = self.framebuffer_size
        aspect = width / max(height, 1)
        return glm.perspective(glm.radians(FIELD_OF_VIEW_DEG), aspect, NEAR_PLANE_KM, FAR_PLANE_KM)

    @property
    def view_projection_matrix(self) -> glm.mat4x4:
        """ Returns the (readonly) matrix which transforms world positions (km) into clip space. Use this to draw
        anything else into the scene, such as the spacecraft's trajectory. """
        return cast(glm.mat4x4, self.projection_matrix * self.camera.view_matrix)

    def draw_scene(self) -> None:
        """ Draws the scene from the camera's point of view into the current framebuffer. """
        self.scene.draw(self.camera, self.projection_matrix, self.framebuffer_size)

    def set_trajectory(self, trajectory: TrajectoryArrays) -> None:
        """ Draws the spacecraft's ``trajectory``, replacing any previous one. It's calculated in C++ by
        ``calc.trajectory.Trajectory.calculate_trajectory``, in the calculations' frame and SI units. """

        if self.trajectory is None:
            self.trajectory = TrajectoryLine(self.ctx)

        self.trajectory.set_points(trajectory)
        self.trajectory_shown_until = math.inf

    def set_burn(self, burn: ApoapsisBurn | None) -> None:
        """ Draws an arrow along the thrust of the circularising ``burn`` at the apoapsis (from
        ``calc.circular_burn``), replacing any previous one, or removes it if ``burn`` is ``None``. """

        if burn is None:
            self.burn = None
            return

        if self.burn is None:
            self.burn = BurnArrow(self.ctx)
        self.burn.set_burn(burn)

    def draw_gui(self) -> None:
        """ Creates the renderer's own widgets: the citations and the display settings panel. Must be called
        between ``gui.begin_frame`` and ``gui.end_frame``, which ``render`` does. """

        if self.burn is not None and self.show_trajectory:
            self.burn.draw_label(self.view_projection_matrix)
        if self.show_axes:
            self.axes.draw_labels(glm.mat3(self.camera.view_matrix))
        if self.show_citations:
            self._draw_citations()
        if self.show_display_panel:
            self._draw_display_panel()

    def _draw_citations(self) -> None:
        """ Draws the citations straight onto the background, in the bottom left corner. """

        draw_list = imgui.get_background_draw_list()
        line_height = imgui.get_text_line_height_with_spacing()
        margin = CITATIONS_MARGIN * GUI_SCALE
        x = margin
        y = imgui.get_io().display_size.y - margin - line_height * len(self._citations)

        for line in self._citations:
            draw_list.add_text((x + 1, y + 1), SHADOW, line)
            draw_list.add_text((x, y), WHITE, line)
            y += line_height

    def _draw_display_panel(self) -> None:
        """ A small window with settings for what's displayed. """

        # The top right corner, as Saturn is on the left in the initial view. It can be dragged or collapsed.
        display_width = imgui.get_io().display_size.x
        margin = 12 * GUI_SCALE
        imgui.set_next_window_pos((display_width - margin, margin), imgui.Cond_.first_use_ever, (1.0, 0.0))

        if imgui.begin("Display", None, imgui.WindowFlags_.always_auto_resize)[0]:
            scene = self.scene

            imgui.begin_disabled(not scene.has_saturn)
            _, scene.show_saturn = imgui.checkbox("Saturn", scene.show_saturn)
            imgui.end_disabled()

            imgui.begin_disabled(not scene.has_skybox)
            _, scene.show_skybox = imgui.checkbox("Starfield", scene.show_skybox)
            _, scene.sky_exposure = imgui.slider_float("Star brightness", scene.sky_exposure, 0.0, 4.0)
            imgui.end_disabled()

            if self.trajectory is not None:
                _, self.show_trajectory = imgui.checkbox("Trajectory", self.show_trajectory)
            _, self.show_axes = imgui.checkbox("Axes", self.show_axes)
            _, self.show_citations = imgui.checkbox("Citations", self.show_citations)

            imgui.separator()
            altitude = self.camera.distance - TITAN_RADIUS_KM
            imgui.text(f"Camera altitude: {altitude:,.0f} km")
            if imgui.button("Recentre on Titan"):
                self.camera.target = glm.vec3(self.scene.titan_position)

            imgui.text_disabled(f"{imgui.get_io().framerate:.0f} FPS")

        imgui.end()

    def stop_rendering(self) -> None:
        """ Stops the renderer from rendering all subsequent frames. """
        self._should_run = False

    def render(self, exec: Callable[["Renderer"], None] = lambda _: None,
               gui: Callable[["Renderer"], None] = lambda _: None) -> None:
        """Begins the render loop which blocks the main thread until either the window recieves a closed
        event or the renderer is explicitly set to stop rendering via the ``.stop_rendering()`` method.

        This method also takes in an optional `exec` callback which takes in a reference to this renderer
        which is called every frame right after the scene has been drawn but right before the frame is
        swapped with the window's framebuffer. Anything drawn there is depth-tested against the scene.

        The optional `gui` callback is called every frame too, and is where ImGui widgets are created (e.g.
        ``imgui.begin("Window")``, ``imgui.slider_float(...)``, ``imgui.end()``). They're drawn on top of
        everything else."""

        self._should_run = True

        while not glfw.window_should_close(self.window) and self._should_run:
            glfw.poll_events()
            self.gui.begin_frame()
            self.ctx.clear(*CLEAR_COLOR, depth=1.0)

            self.draw_scene()
            if self.trajectory is not None and self.show_trajectory:
                self.trajectory.draw(self.view_projection_matrix, self.framebuffer_size, self.trajectory_shown_until)
                if self.burn is not None:
                    self.burn.draw(self.view_projection_matrix, self.framebuffer_size)
            exec(self)

            # Over everything else in the scene, but under the GUI.
            if self.show_axes:
                self.axes.draw(glm.mat3(self.camera.view_matrix), self.framebuffer_size)

            self.draw_gui()
            gui(self)
            self.gui.end_frame()

            glfw.swap_buffers(self.window)

    def destroy(self) -> None:
        """ Destroys this renderer and frees all its resources. """
        self.gui.destroy()
        glfw.terminate()
