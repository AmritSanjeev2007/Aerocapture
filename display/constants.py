# pyright: standard

""" This module contains all the constants that are shared among all (display) source modules. Distances are in km. """

import sys

from pathlib import Path
from pyglm import glm

# When packaged into an .exe (see Aerocapture.spec), the bundled files are unpacked into a temporary folder.
_PROJECT_PATH = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

# ====== FILES =======

ASSETS_PATH = _PROJECT_PATH / "assets"
""" The folder containing all the textures. """
TITAN_TEXTURE_PATH = ASSETS_PATH / "titan.png"
SATURN_TEXTURE_PATH = ASSETS_PATH / "saturn.png"
STARMAP_TEXTURE_PATH = ASSETS_PATH / "starmap.exr"
CITATIONS_PATH = ASSETS_PATH / "CITATIONS"
""" The credits for the textures, shown in the bottom left corner. """

SHADERS_PATH = _PROJECT_PATH / "shaders"
""" The folder containing all the GLSL shaders. """
SCREEN_VERTEX_SHADER_PATH = SHADERS_PATH / "screen.vert"
""" The path to the vertex shader of the full screen quad on which the scene is ray-traced. """
SCREEN_FRAGMENT_SHADER_PATH = SHADERS_PATH / "screen.frag"
""" The path to the fragment shader which ray-traces Titan, Saturn and the starfield. """
LOADING_FRAGMENT_SHADER_PATH = SHADERS_PATH / "loading.frag"
""" The path to the fragment shader which draws the loading screen's progress bar. """
AXES_VERTEX_SHADER_PATH = SHADERS_PATH / "axes.vert"
AXES_FRAGMENT_SHADER_PATH = SHADERS_PATH / "axes.frag"
""" The paths to the shaders which draw the world's axes in the corner of the window. """
TRAJECTORY_VERTEX_SHADER_PATH = SHADERS_PATH / "trajectory.vert"
TRAJECTORY_FRAGMENT_SHADER_PATH = SHADERS_PATH / "trajectory.frag"
""" The paths to the shaders which draw the spacecraft's trajectory. """
BURN_VERTEX_SHADER_PATH = SHADERS_PATH / "burn.vert"
BURN_FRAGMENT_SHADER_PATH = SHADERS_PATH / "burn.frag"
""" The paths to the shaders which draw the cone of the burn's arrow. """

# ====== GUI =======

GUI_SCALE = 2.0
""" Scales the whole GUI: text, widgets, spacing, the citations and the loading screen's title. Increase it on
high resolution screens, e.g. 1.5 or 2.0. """
GUI_FONT_FILE = "segoeui.ttf"
GUI_FONT_SIZE = 16.0
""" The font of the GUI and its size in pixels (before ``GUI_SCALE``). The font is looked up in the system's
font folder, and ImGui's built-in font is used when it's missing. """
TITLE_FONT_FILE = "bahnschrift.ttf"
""" The font of large headings, e.g. the loading screen's title. """
AXES_GIZMO_LENGTH = 40.0
AXES_GIZMO_MARGIN = 24.0
""" The length of each axis of the axes gizmo, and its distance from the bottom right corner of the window, in
pixels (before ``GUI_SCALE``). """
AXIS_COLORS = ((0.96, 0.21, 0.32), (0.54, 0.86, 0.0), (0.17, 0.56, 1.0))
""" The colours of the x, y and z axes (red, green and blue, like Blender's). """
CALC_TO_DISPLAY = glm.mat3(glm.vec3(0, 0, -1), glm.vec3(0, 1, 0), glm.vec3(-1, 0, 0))
""" Transforms vectors from the frame of the calculations (``calc/*``) to the display's world frame. Its columns
are the calculation frame's x, y and z axes as seen in the display's frame: ``x_calc = -z``, ``y_calc = y`` and
``z_calc = -x``. The frames share the y axis (Titan's axis of rotation). The axes gizmo shows the calculation
frame's axes.

Note that this is a reflection (its determinant is -1): the calculation frame is left-handed, while the display's
is right-handed, so cross products (e.g. angular momentum) point the opposite way once transformed. """

# ====== WINDOW & CAMERA =======

INITIAL_WINDOW_SIZE = (1280, 800)
""" The initial size (width, height) of the window at its creation in pixels. """
CLEAR_COLOR = (0.0, 0.0, 0.0, 1.0)
ACCENT_COLOR = (0.95, 0.60, 0.25)
""" The colour of Titan's haze, used for the loading bar and the title. """
TRAJECTORY_WIDTH = 2.0
""" The width of the trajectory's line in window points (pixels on a regular screen). """
TRAJECTORY_START_COLOR = (0.35, 0.80, 1.00)
TRAJECTORY_END_COLOR = (1.00, 0.35, 0.45)
""" The trajectory is coloured by time, from its start colour (the first record) to its end colour (the last). """
BURN_ARROW_COLOR = (0.55, 1.00, 0.45)
BURN_ARROW_WIDTH = 3.0
""" The colour and width (window points) of the arrow showing the circularising burn's thrust at the apoapsis. """
BURN_ARROW_LENGTH_KM = 3_000.0
""" The length of the burn's arrow. It's fixed (the magnitude is written next to it) so it's visible from afar. """
TRAJECTORY_MAX_POINTS = 2_000_000
""" At most this many points (time steps) of a trajectory are calculated and drawn (64 MB on the GPU). """
MOUSE_SENSITIVITY = 0.004
""" Radians of camera revolution per pixel the mouse is dragged. """
SCROLL_ZOOM_RATE = 0.15
""" How much a single scroll step changes the camera's altitude (exponential). """
DRAG_ZOOM_RATE = 0.01
""" How much dragging the mouse by one pixel (with ctrl + middle mouse) changes the camera's altitude. """
SCROLL_PAN_PIXELS = 40.0
""" How many pixels the view pans by per scroll step (with ctrl or shift held). """
FIELD_OF_VIEW_DEG = 45.0
NEAR_PLANE_KM = 1.0
FAR_PLANE_KM = 5.0e6
STARMAP_MAX_WIDTH = 8192
""" The starmap is downsampled to at most this width before being uploaded (it's a half-float texture). """

# ====== BODIES =======

TITAN_RADIUS_KM = 2574.73
TITAN_HAZE_SCALE_HEIGHT_KM = 150.0
""" How quickly the glow of Titan's haze fades above the limb. Visual only, not the simulation's density model. """
SATURN_EQUATORIAL_RADIUS_KM = 60268.0
SATURN_POLAR_RADIUS_KM = 54364.0
SATURN_HAZE_SCALE_HEIGHT_KM = 1200.0
""" How quickly the glow of Saturn's upper atmosphere fades above the limb. Exaggerated so it's visible from Titan. """
SATURN_RING_HAZE_THICKNESS_KM = 1000.0
""" The scale height of the dust drawn around the ring plane. The real rings are only tens of metres thick, which
would make them invisible edge-on, as they're always seen from Titan. Visual only. """
TITAN_ORBIT_RADIUS_KM = 1221870.0
SATURN_DIRECTION = glm.normalize(glm.vec3(-1.0, 0.0, 0.0))
""" The direction from Titan towards Saturn. """
SUN_DIRECTION = glm.normalize(glm.vec3(0.2, 0.35, 1.0))
""" The direction from the scene towards the Sun (i.e., the opposite of the direction the sunlight travels). """
SUN_RADIUS_KM = 695700.0
SUN_DISTANCE_KM = 1.433e9
""" The mean distance between the Sun and Saturn. """
SATURN_POLE_RA_DEG = 40.589
SATURN_POLE_DEC_DEG = 83.537
""" Right ascension and declination (J2000) of Saturn's north pole, used to orient the starfield. """
