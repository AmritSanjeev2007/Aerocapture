# pyright: standard

""" The immediate mode GUI (Dear ImGui, through imgui-bundle) drawn on top of the scene.

Widgets are written inside the ``gui`` callback of ``Renderer.render`` (or in ``Renderer.draw_gui``), every frame::

    def gui(renderer: Renderer) -> None:
        imgui.begin("Trajectory")
        _, renderer.scene.show_saturn = imgui.checkbox("Saturn", renderer.scene.show_saturn)
        imgui.end()

    renderer.render(gui=gui)

See https://pthom.github.io/imgui_manual_online/manual/imgui_manual.html for every available widget. """

import glfw
import math
import os

from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer
from pathlib import Path
from typing import Any

from .constants import GUI_FONT_FILE, GUI_FONT_SIZE, GUI_SCALE, TITLE_FONT_FILE


def find_system_font(name: str) -> Path | None:
    """ Returns the path to the font file ``name`` in the system's font folders, if it exists. """

    folders = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
    ]
    for folder in folders:
        if (folder / name).is_file():
            return folder / name

    linux_fonts = Path("/usr/share/fonts")  # Fonts are sorted into subfolders on Linux.
    return next(linux_fonts.rglob(name), None) if linux_fonts.is_dir() else None


def _load_font(name: str, size: float) -> imgui.ImFont | None:
    path = find_system_font(name)
    return imgui.get_io().fonts.add_font_from_file_ttf(str(path), size) if path is not None else None


def draw_glowing_text(draw_list: imgui.ImDrawList, font: imgui.ImFont, size: float, center: tuple[float, float],
                      color: tuple[float, float, float], text: str, glow_radius: float) -> None:
    """ Draws ``text`` centred on ``center`` with a soft glow around it, made of faint copies of the text spread
    out in rings up to ``glow_radius`` pixels away. """

    imgui.push_font(font, size)
    width, height = imgui.calc_text_size(text)
    imgui.pop_font()
    x, y = center[0] - width / 2, center[1] - height / 2

    RINGS, COPIES_PER_RING = 6, 16
    for ring in range(RINGS, 0, -1):
        radius = glow_radius * ring / RINGS
        alpha = 0.05 * (1.0 - ring / (RINGS + 1))
        glow_color = imgui.color_convert_float4_to_u32((*color, alpha))

        for i in range(COPIES_PER_RING):
            angle = math.tau * (i + 0.5 * ring) / COPIES_PER_RING
            offset = (x + radius * math.cos(angle), y + radius * math.sin(angle))
            draw_list.add_text(font, size, offset, glow_color, text)

    draw_list.add_text(font, size, (x, y), imgui.color_convert_float4_to_u32((*color, 1.0)), text)


class Gui:
    """ Owns the ImGui context of a ``window``, forwards its inputs to ImGui and draws the widgets with OpenGL.
    Everything is scaled by ``GUI_SCALE``.

    The window's input callbacks belong to ``control.attach_orbit_controls``, which forwards every event here
    first, and only moves the camera when ImGui doesn't want the mouse (e.g. when dragging a slider). """

    def __init__(self, window: Any) -> None:

        imgui.create_context()
        io = imgui.get_io()
        io.set_ini_filename("")  # Don't litter the working directory with an imgui.ini file.

        # ImGui's built-in fonts are used for whichever of these isn't installed.
        self.font = _load_font(GUI_FONT_FILE, GUI_FONT_SIZE * GUI_SCALE) or imgui.get_font()
        self.title_font = _load_font(TITLE_FONT_FILE, GUI_FONT_SIZE * GUI_SCALE) or self.font
        """ For large headings, e.g. the title of the loading screen. Any size can be drawn without blurring. """

        imgui.style_colors_dark()
        style = imgui.get_style()
        style.window_rounding = 6.0
        style.frame_rounding = 4.0
        style.window_border_size = 0.0
        style.scale_all_sizes(GUI_SCALE)

        self._impl = GlfwRenderer(window, attach_callbacks=False)
        glfw.set_char_callback(window, self._impl.char_callback)  # Typing into text fields.

    @property
    def wants_mouse(self) -> bool:
        """ Whether the mouse is over (or dragging) a widget, so the scene shouldn't react to it. """
        return imgui.get_io().want_capture_mouse

    @property
    def wants_keyboard(self) -> bool:
        """ Whether a widget (e.g. a text field) is being typed into, so the scene shouldn't react to keys. """
        return imgui.get_io().want_capture_keyboard

    # Input forwarding, called by the window's callbacks (see ``control.attach_orbit_controls``).

    def on_mouse_button(self, window: Any, button: int, action: int, mods: int) -> None:
        self._impl.mouse_button_callback(window, button, action, mods)

    def on_mouse_move(self, window: Any, x: float, y: float) -> None:
        self._impl.mouse_callback(window, x, y)

    def on_scroll(self, window: Any, xoffset: float, yoffset: float) -> None:
        self._impl.scroll_callback(window, xoffset, yoffset)

    def on_key(self, window: Any, key: int, scancode: int, action: int, mods: int) -> None:
        self._impl.keyboard_callback(window, key, scancode, action, mods)

    def begin_frame(self) -> None:
        """ Starts a new GUI frame, after which widgets can be created. """

        self._impl.process_inputs()
        imgui.new_frame()

    def end_frame(self) -> None:
        """ Draws all the widgets created since ``begin_frame`` into the current framebuffer. """

        imgui.render()
        self._impl.render(imgui.get_draw_data())

    def destroy(self) -> None:
        """ Frees the GUI's OpenGL resources and its ImGui context. """

        self._impl.shutdown()
        imgui.destroy_context()
