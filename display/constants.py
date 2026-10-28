# pyright: standard

""" This module contains all the constants that are shared among all source modules. Distances are in km. """

from pathlib import Path
from pyglm import glm

_PROJECT_PATH = Path(__file__).resolve().parent.parent

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

# ====== WINDOW & CAMERA =======

INITIAL_WINDOW_SIZE = (1280, 800)
""" The initial size (width, height) of the window at its creation in pixels. """
CLEAR_COLOR = (0.0, 0.0, 0.0, 1.0)
ACCENT_COLOR = (0.95, 0.60, 0.25)
""" The colour of Titan's haze, used for the loading bar and the title. """
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
