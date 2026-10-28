""" The loading screen which is shown while the (large) textures are loaded. """

import glfw
import moderngl
import time

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable

from .constants import ACCENT_COLOR, CLEAR_COLOR, LOADING_FRAGMENT_SHADER_PATH, SCREEN_VERTEX_SHADER_PATH
from .shaders import create_fullscreen_quad, create_shader_program, set_uniform
from .text import TextRenderer, TextStyle
from .textures import MapImage, upload_map_texture

PROGRESS_SMOOTHING = 0.15
""" The fraction of the remaining distance the bar moves towards the real progress each frame. """
TITLE = "Aerocapture"
TITLE_STYLE = TextStyle(size=64, font="bahnschrift.ttf", color=ACCENT_COLOR, glow_radius=12, glow_strength=0.8)
""" Shares the colour of the loading bar, and glows like its leading edge. """

@dataclass(frozen=True)
class TextureJob:
    """ A texture to be loaded: its ``name`` and a ``decode`` function which is run on a background thread. """

    name: str
    decode: Callable[[], MapImage]


class LoadingScreen:
    """ Draws the title and a progress bar in the middle of the window. """

    def __init__(self, context: moderngl.Context) -> None:

        self._program = create_shader_program(
            context=context,
            vert_shader_path=SCREEN_VERTEX_SHADER_PATH,
            frag_shader_path=LOADING_FRAGMENT_SHADER_PATH,
        )
        self._vao = create_fullscreen_quad(context, self._program)
        self._start_time = time.perf_counter()

        self._text = TextRenderer(context)
        self._title = self._text.create(TITLE, TITLE_STYLE)

    def draw(self, progress: float, framebuffer_size: tuple[int, int]) -> None:
        """ Draws the loading screen with the bar filled up to ``progress`` (between 0 and 1). """

        set_uniform(self._program, "uResolution", framebuffer_size)
        set_uniform(self._program, "uProgress", progress)
        set_uniform(self._program, "uTime", time.perf_counter() - self._start_time)
        set_uniform(self._program, "uFillColor", ACCENT_COLOR)
        self._vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)

        # Just above the bar, which sits in the middle of the window.
        width, height = framebuffer_size
        self._text.draw(self._title, (width / 2, height / 2 - 24), framebuffer_size, anchor=(0.5, 1.0))


def load_textures(window: Any, context: moderngl.Context, jobs: list[TextureJob],
                  title: str) -> dict[str, moderngl.Texture]:
    """ Loads the textures of all the ``jobs`` while showing a loading screen in the ``window``, and returns them
    by name. The window's ``title`` is restored once done, as the progress is also shown there.

    The images are decoded in parallel on background threads, and uploaded one per frame on this thread (which
    owns the OpenGL context), so the window stays responsive and the progress bar keeps moving.

    Each texture counts as two steps of progress: decoding and uploading. """

    screen = LoadingScreen(context)

    textures: dict[str, moderngl.Texture] = {}
    decoded: list[tuple[str, MapImage]] = []
    total_steps = 2 * len(jobs)
    finished_steps = 0
    shown_progress = 0.0

    def draw_frame() -> None:
        width, height = glfw.get_framebuffer_size(window)
        context.viewport = (0, 0, width, height)
        context.clear(*CLEAR_COLOR, depth=1.0)
        screen.draw(shown_progress, (width, height))
        glfw.swap_buffers(window)

    with ThreadPoolExecutor(max_workers=max(len(jobs), 1)) as pool:
        pending: dict[Future[MapImage], str] = {pool.submit(job.decode): job.name for job in jobs}

        while len(textures) < len(jobs):
            glfw.poll_events()

            for future in [f for f in pending if f.done()]:
                decoded.append((pending.pop(future), future.result()))  # Re-raises any decoding error.
                finished_steps += 1

            # Only one upload per frame, so the bar gets redrawn in between.
            if decoded:
                name, image = decoded.pop(0)
                textures[name] = upload_map_texture(context, image)
                finished_steps += 1

            progress = finished_steps / total_steps
            shown_progress += (progress - shown_progress) * PROGRESS_SMOOTHING
            glfw.set_window_title(window, f"{title} | Loading textures {round(progress * 100)}%")
            draw_frame()

    # Let the bar catch up and fill completely before the scene appears.
    while shown_progress < 0.995:
        glfw.poll_events()
        shown_progress += (1.0 - shown_progress) * PROGRESS_SMOOTHING * 2.0
        draw_frame()

    glfw.set_window_title(window, title)
    return textures
