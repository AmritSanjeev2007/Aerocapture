# pyright: standard

""" Renders the 3D scene to more efficiently simulate the approach of the spacecraft. """

import glfw
import math
import moderngl

from functools import partial
from pathlib import Path

from pyglm import glm
from typing import Any, Callable, cast

from .camera import Camera
from .constants import (
    CITATIONS_PATH, CLEAR_COLOR, FAR_PLANE_KM, FIELD_OF_VIEW_DEG, INITIAL_WINDOW_SIZE, NEAR_PLANE_KM, SATURN_TEXTURE_PATH,
    STARMAP_MAX_WIDTH, STARMAP_TEXTURE_PATH, TITAN_ORBIT_RADIUS_KM, TITAN_RADIUS_KM, TITAN_TEXTURE_PATH,
)
from .control import attach_orbit_controls
from .loading import TextureJob, load_textures
from .scene import Scene
from .text import TextRenderer, TextStyle
from .textures import decode_hdr_map_image, decode_map_image


CITATIONS_STYLE = TextStyle(size=15, font="arial.ttf", color=(1.0, 1.0, 1.0), line_spacing=5,
                            glow_radius=3, glow_color=(0.0, 0.0, 0.0), glow_strength=0.6)
""" A faint dark glow keeps the white text readable when it overlaps a bright Titan or Saturn. """
CITATIONS_MARGIN = 20
""" The distance in pixels of the citations from the bottom left corner of the window. """

def read_citations(path: Path) -> str:
    """ Returns the credit lines of the citations file at ``path``, leaving out the source links. """

    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line.strip() for line in lines if line.strip() and not line.startswith("Retrieved from"))


class Renderer:
    """ Initializes the renderer. It takes in few (optional) arguments such as whether to render
        saturn or the star skybox.

    The object creates and manages the GLFW window, the OpenGL context, the camera and the scene. The camera
    uses Blender's viewport controls, see ``control.attach_orbit_controls``. """

    def __init__(self, saturn: bool = True, skybox: bool = True, window_title: str = "Titan Aerocapture") -> None:

        glfw.init()

        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
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

        textures = load_textures(self.window, self.ctx, jobs, window_title)
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
        attach_orbit_controls(self.window, self.camera)

        self.text = TextRenderer(self.ctx)
        """ Creates and draws text on top of the scene, see ``text.TextRenderer``. """
        self.show_citations = True
        self._citations = self.text.create(read_citations(CITATIONS_PATH), CITATIONS_STYLE)

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

    def draw_overlay(self) -> None:
        """ Draws the 2D elements on top of everything else, i.e. the citations. """

        if self.show_citations:
            position = (CITATIONS_MARGIN, self.framebuffer_size[1] - CITATIONS_MARGIN)
            self.text.draw(self._citations, position, self.framebuffer_size, anchor=(0.0, 1.0))

    def stop_rendering(self) -> None:
        """ Stops the renderer from rendering all subsequent frames. """
        self._should_run = False

    def render(self, exec: Callable[["Renderer"], None] = lambda _: None) -> None:
        """Begins the render loop which blocks the main thread until either the window recieves a closed
        event or the renderer is explicitly set to stop rendering via the ``.stop_rendering()`` method.

        This method also takes in an optional `exec` callback which takes in a reference to this renderer
        which is called every frame right after the scene has been drawn but right before the frame is
        swapped with the window's framebuffer. Anything drawn there is depth-tested against the scene, and the
        overlay (e.g. the citations) is drawn on top of it."""

        self._should_run = True

        while not glfw.window_should_close(self.window) and self._should_run:
            glfw.poll_events()
            self.ctx.clear(*CLEAR_COLOR, depth=1.0)

            self.draw_scene()
            exec(self)
            self.draw_overlay()

            glfw.swap_buffers(self.window)

    def destroy(self) -> None:
        """ Destroys this renderer and frees all its resources. """
        glfw.terminate()
