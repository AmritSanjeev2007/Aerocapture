# pyright: standard

""" The ray-traced scene of Titan, Saturn and the starfield.

The scene is drawn the same way as a ray-traced globe: a single quad covers the whole screen and the fragment
shader casts a ray through every pixel, intersecting it analytically with Titan, Saturn (an oblate spheroid with
procedural rings) and finally the starfield and the Sun. Every texture is an equirectangular map which is looked up from the
point that was hit.

World frame (units are km):
    + Titan sits at the origin.
    + ``+y`` is the north pole of both Titan and Saturn (Titan orbits almost exactly in Saturn's equatorial plane).
    + Saturn lies in the ``x-z`` plane, ``TITAN_ORBIT_RADIUS_KM`` away from Titan.
    + Titan is tidally locked, so the centre of its map (longitude 0) always faces Saturn.

The shader also writes the depth of whatever it hits into the depth buffer, so anything drawn afterwards with the
regular rasterizer (e.g. the spacecraft's trajectory) is correctly hidden behind Titan or Saturn. """

import math
import moderngl

from pyglm import glm

from .camera import Camera
from .constants import (
    FIELD_OF_VIEW_DEG, SATURN_HAZE_SCALE_HEIGHT_KM, SATURN_RING_HAZE_THICKNESS_KM,
    SATURN_DIRECTION, SATURN_EQUATORIAL_RADIUS_KM, SATURN_POLAR_RADIUS_KM, SATURN_POLE_DEC_DEG,
    SATURN_POLE_RA_DEG, SUN_DISTANCE_KM, SUN_RADIUS_KM, SCREEN_FRAGMENT_SHADER_PATH, SCREEN_VERTEX_SHADER_PATH,
    SUN_DIRECTION, TITAN_HAZE_SCALE_HEIGHT_KM, TITAN_ORBIT_RADIUS_KM, TITAN_RADIUS_KM,
)
from .shaders import create_fullscreen_quad, create_shader_program, set_uniform


def _sky_rotation() -> glm.mat3:
    """ Returns the rotation from the world frame to the J2000 equatorial frame of the starmap, which maps the
    world's ``+y`` axis onto Saturn's north pole. """

    ra = math.radians(SATURN_POLE_RA_DEG)
    dec = math.radians(SATURN_POLE_DEC_DEG)
    pole = glm.vec3(math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))
    node = glm.normalize(glm.cross(glm.vec3(0, 0, 1), pole))

    return glm.mat3(node, pole, glm.cross(node, pole))


class Scene:
    """ Owns the textures and the shader program of the scene and draws it. Saturn and the starfield are only
    drawn when their textures are given (see ``loading.load_textures``). """

    def __init__(self, context: moderngl.Context, titan_texture: moderngl.Texture,
                 saturn_texture: moderngl.Texture | None = None, sky_texture: moderngl.Texture | None = None) -> None:

        self.has_saturn = saturn_texture is not None
        """ Whether Saturn's texture was loaded, so that it can be shown. """
        self.has_skybox = sky_texture is not None
        """ Whether the starfield's texture was loaded, so that it can be shown. """
        self.show_saturn = self.has_saturn
        self.show_skybox = self.has_skybox
        self.sun_direction = SUN_DIRECTION
        """ The direction from the scene towards the Sun. """
        self.titan_position = glm.vec3(0.0)
        self.saturn_position = SATURN_DIRECTION * TITAN_ORBIT_RADIUS_KM
        self.sky_exposure = 1.0

        self._program = create_shader_program(
            context=context,
            vert_shader_path=SCREEN_VERTEX_SHADER_PATH,
            frag_shader_path=SCREEN_FRAGMENT_SHADER_PATH,
        )

        self._vao = create_fullscreen_quad(context, self._program)

        program = self._program
        set_uniform(program, "uTitanRadii", glm.vec3(TITAN_RADIUS_KM))
        set_uniform(program, "uHazeScaleHeight", TITAN_HAZE_SCALE_HEIGHT_KM)
        set_uniform(program, "uSaturnRadii", glm.vec3(
            SATURN_EQUATORIAL_RADIUS_KM, SATURN_POLAR_RADIUS_KM, SATURN_EQUATORIAL_RADIUS_KM
        ))
        set_uniform(program, "uSaturnRotation", glm.mat3(1.0))
        set_uniform(program, "uSaturnHazeScaleHeight", SATURN_HAZE_SCALE_HEIGHT_KM)
        set_uniform(program, "uRingHazeThickness", SATURN_RING_HAZE_THICKNESS_KM)
        set_uniform(program, "uSkyRotation", _sky_rotation())
        set_uniform(program, "uSunAngularRadius", SUN_RADIUS_KM / SUN_DISTANCE_KM)

        # Something valid must stay bound to every sampler, even when Saturn or the starfield wasn't loaded.
        set_uniform(program, "uTitanTexture", 0)
        set_uniform(program, "uSaturnTexture", 1)
        set_uniform(program, "uSkyTexture", 2)
        self._textures = (titan_texture, saturn_texture or titan_texture, sky_texture or titan_texture)

    def _titan_rotation(self) -> glm.mat3:
        """ Titan is tidally locked, so its body frame's ``+z`` axis (longitude 0) points towards Saturn. """

        north = glm.vec3(0, 1, 0)
        towards_saturn = glm.normalize(self.saturn_position - self.titan_position)
        return glm.mat3(glm.normalize(glm.cross(north, towards_saturn)), north, towards_saturn)

    def draw(self, camera: Camera, projection: glm.mat4, framebuffer_size: tuple[int, int]) -> None:
        """ Draws Titan, Saturn and the starfield into the current framebuffer, including its depth. """

        program = self._program
        view = camera.view_matrix

        set_uniform(program, "uResolution", framebuffer_size)
        set_uniform(program, "uInvViewRotProj", glm.inverse(projection * glm.mat4(glm.mat3(view))))
        set_uniform(program, "uViewProj", projection * view)
        set_uniform(program, "uCameraPos", camera.position)
        set_uniform(program, "uSunDir", glm.normalize(self.sun_direction))

        set_uniform(program, "uPixelAngle", math.radians(FIELD_OF_VIEW_DEG) / max(framebuffer_size[1], 1))

        set_uniform(program, "uTitanCenter", self.titan_position)
        set_uniform(program, "uTitanRotation", self._titan_rotation())
        set_uniform(program, "uShowSaturn", self.show_saturn and self.has_saturn)
        set_uniform(program, "uSaturnCenter", self.saturn_position)
        set_uniform(program, "uShowSky", self.show_skybox and self.has_skybox)
        set_uniform(program, "uSkyExposure", self.sky_exposure)

        for location, texture in enumerate(self._textures):
            texture.use(location=location)

        self._vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)
