""" The module for handling the inputs which move the camera around. """

import glfw
import math

from enum import Enum, auto
from pyglm import glm
from typing import Any

from .camera import Camera
from .constants import (
    DRAG_ZOOM_RATE, FIELD_OF_VIEW_DEG, MOUSE_SENSITIVITY, SCROLL_PAN_PIXELS, SCROLL_ZOOM_RATE,
)


class _DragMode(Enum):
    NONE = auto()
    ORBIT = auto()
    PAN = auto()
    ZOOM = auto()


def attach_orbit_controls(window: Any, camera: Camera) -> None:
    """ Lets the user control the ``camera`` from the ``window`` the same way as Blender's viewport:

    + Middle mouse drag: orbit around the target.
    + Shift + middle mouse drag: pan.
    + Ctrl + middle mouse drag: zoom (drag up to zoom in).
    + Scroll: zoom. Ctrl + scroll pans horizontally and shift + scroll pans vertically.
    + Home or numpad period: recentre the view on the initial target (Titan).
    + Escape: close the window. """

    home_target = glm.vec3(camera.target)
    mode = _DragMode.NONE
    last_mouse_pos = glfw.get_cursor_pos(window)

    def pan_per_pixel() -> float:
        """ The pan distance, as a fraction of the camera's distance, that keeps the target under the cursor. """

        _, height = glfw.get_window_size(window)
        return 2.0 * math.tan(math.radians(FIELD_OF_VIEW_DEG) / 2.0) / max(height, 1)

    def on_button(_: Any, button: int, action: int, mods: int) -> None:
        nonlocal mode

        if action == glfw.RELEASE:
            mode = _DragMode.NONE
            return

        if button == glfw.MOUSE_BUTTON_MIDDLE:
            if mods & glfw.MOD_SHIFT:
                mode = _DragMode.PAN
            elif mods & glfw.MOD_CONTROL:
                mode = _DragMode.ZOOM
            else:
                mode = _DragMode.ORBIT

    def on_move(_: Any, x: float, y: float) -> None:
        nonlocal last_mouse_pos
        dx, dy = x - last_mouse_pos[0], y - last_mouse_pos[1]
        last_mouse_pos = (x, y)

        if mode == _DragMode.ORBIT:
            camera.revolve_by(-dx * MOUSE_SENSITIVITY, dy * MOUSE_SENSITIVITY)
        elif mode == _DragMode.PAN:
            scale = pan_per_pixel()
            camera.pan(-dx * scale, dy * scale)  # The scene follows the cursor.
        elif mode == _DragMode.ZOOM:
            camera.zoom(math.exp(-dy * DRAG_ZOOM_RATE))

    def on_scroll(win: Any, xoffset: float, yoffset: float) -> None:
        step = pan_per_pixel() * SCROLL_PAN_PIXELS

        if glfw.get_key(win, glfw.KEY_LEFT_CONTROL) or glfw.get_key(win, glfw.KEY_RIGHT_CONTROL):
            camera.pan(-yoffset * step, 0.0)
        elif glfw.get_key(win, glfw.KEY_LEFT_SHIFT) or glfw.get_key(win, glfw.KEY_RIGHT_SHIFT):
            camera.pan(0.0, yoffset * step)
        else:
            camera.zoom(math.exp(yoffset * SCROLL_ZOOM_RATE))

    def on_key(win: Any, key: int, _scancode: int, action: int, _mods: int) -> None:
        if action != glfw.PRESS:
            return

        if key == glfw.KEY_ESCAPE:
            glfw.set_window_should_close(win, True)
        elif key in (glfw.KEY_HOME, glfw.KEY_KP_DECIMAL):
            camera.target = glm.vec3(home_target)

    glfw.set_mouse_button_callback(window, on_button)
    glfw.set_cursor_pos_callback(window, on_move)
    glfw.set_scroll_callback(window, on_scroll)
    glfw.set_key_callback(window, on_key)
