""" The camera module. """

import math

from pyglm import glm

class Camera:
    """ A camera that orbits around a ``target`` point, always looking at it. Its position is described by the
    ``yaw`` (around ``+y``) and ``pitch`` angles, and its ``distance`` from the target. The ``minimum_distance``
    keeps it from going inside the body it's looking at. """

    MAX_PITCH = math.radians(89)

    def __init__(self, target: glm.vec3, distance: float, yaw: float = 0.0, pitch: float = 0.0,
                 minimum_distance: float = 0.0, maximum_distance: float = math.inf) -> None:

        assert distance > minimum_distance

        self.target = target
        self.distance = distance
        self.yaw = yaw
        self.pitch = pitch
        self.minimum_distance = minimum_distance
        self.maximum_distance = maximum_distance

    def revolve_by(self, yaw: float, pitch: float) -> None:
        """ Revolves this camera around its target by the specified angles (radians). """

        self.yaw += yaw
        self.pitch = max(-self.MAX_PITCH, min(self.MAX_PITCH, self.pitch + pitch))  # Disable roll

    def zoom(self, factor: float) -> None:
        """ Moves the camera closer to its target if the ``factor`` is greater than 1 or further away if the
        ``factor`` is less than 1. It's the height above ``minimum_distance`` that is scaled, so zooming slows
        down near the surface. """

        assert factor > 0.0

        altitude = (self.distance - self.minimum_distance) / factor
        self.distance = min(self.maximum_distance, self.minimum_distance + altitude)

    def pan(self, right: float, up: float) -> None:
        """ Slides the camera and its target sideways, parallel to the screen. The distances are given as
        fractions of the camera's distance to its target, so panning feels the same at every zoom level. """

        forward = glm.normalize(self.target - self.position)
        right_vec = glm.normalize(glm.cross(forward, glm.vec3(0, 1, 0)))
        up_vec = glm.cross(right_vec, forward)

        # A new vector rather than ``+=`` so that whatever the target was shared with isn't moved too.
        self.target = self.target + (right_vec * right + up_vec * up) * self.distance

    @property
    def position(self) -> glm.vec3:
        """ Returns the (readonly) position of this camera in the world frame. """

        direction = glm.vec3(
            math.cos(self.pitch) * math.sin(self.yaw),
            math.sin(self.pitch),
            math.cos(self.pitch) * math.cos(self.yaw),
        )
        return self.target + direction * self.distance

    @property
    def view_matrix(self) -> glm.mat4:
        """ Returns the (readonly) matrix which transforms the world frame into this camera's view frame. """
        return glm.lookAt(self.position, self.target, glm.vec3(0, 1, 0))
