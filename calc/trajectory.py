# pyright: standard

""" The module responsible for calculating the function coefficients for describing the spacecraft's trajectory. """

from dataclasses import dataclass
from pyglm import glm
from typing import Callable, Generator

from calc import native
from calc.atmosphere import Atmosphere
from calc.constants import *
from calc.native import TrajectoryArrays

import numpy as np

from display.constants import CALC_TO_DISPLAY

@dataclass(frozen=True)
class RungeKuttaRecord:
    """ A record containing the data/state of a system at specific iteration N. """

    position: glm.dvec3
    """ The position of a body at a specific iteration N, in m. """
    velocity: glm.dvec3
    """ The velocity of a body at a specific iteration N, in m/s. """
    time: float
    """ The time at a specific iteration N, in s. """


def transform_to_display_coords(vector: glm.dvec3 | glm.vec3) -> glm.vec3:
    """ Transforms a ``vector`` from the frame used in the calculations (+x roughly away from the Sun, +y Titan's
    axis of rotation) into the world frame used in ``display/*`` (see ``CALC_TO_DISPLAY``). The vector's length and
    units are unchanged: ``display/*`` works in km, so divide positions (in m) by 1000 first. """
    return glm.vec3(glm.dmat3(CALC_TO_DISPLAY) * glm.dvec3(vector))


class Trajectory:
    """ Represents the trajectory of the spacecraft in cartesian coordinates centered around Titan. It takes in an
        initial cartesian position (x, y, z); where +x is a vector (roughly) pointing away from the sun and +y
        is Titan's axis of rotation. It additionally takes in 3 arguments describing the spacecraft's initial
        velocity in the following format: (speed, pitch, yaw). The pitch is the angle between the velocity
        vector and the XZ plane. The yaw is the clockwise angle between the +ve X-axis and the projection of the
        velocity vector onto the XZ plane. This class uses left-handed coordinate axes. All quantities are in SI
        units (m, m/s, s, rad).

        Vectors are double precision (``glm.dvec3``): single precision only resolves positions of ~1e7 m to ~1 m,
        which adds up over a long simulation.

        The same integration is also written in C++, in ``calc/trajectory.hpp`` and ``calc/trajectory.cpp``
        (see ``calculate_trajectory``). It gives the same states, bit for bit, but hundreds of times faster than
        ``calculate_discrete_trajectory``, which makes several Python calls per time step. Both must implement the
        same physics: change ``_acceleration`` / ``_runge_kutta`` and the C++ together. """

    def __init__(self, initial_pos: glm.dvec3, speed: float, pitch: float, yaw: float) -> None:
        self.titan_atmosphere = Atmosphere()

        self.position: glm.dvec3 = glm.dvec3(initial_pos)

        vel_x: float = speed * np.cos(pitch) * np.cos(yaw)
        vel_y: float = speed * np.sin(pitch)
        vel_z: float = speed * np.cos(pitch) * -np.sin(yaw)

        self.velocity: glm.dvec3 = glm.dvec3(vel_x, vel_y, vel_z)

    @staticmethod
    def _gravity_acceleration(position: glm.dvec3) -> glm.dvec3:
        """ Calculates the acceleration of the spacecraft due to Titan's gravity, -GM/r^2 towards Titan's centre. """

        distance_from_titan = glm.length(position)
        acceleration_magnitude = (-GRAVITATIONAL_CONSTANT * TITAN_MASS_KG) / (distance_from_titan**2)

        return acceleration_magnitude * glm.normalize(position)

    @staticmethod
    def _drag_acceleration(position: glm.dvec3, velocity: glm.dvec3, atm: Atmosphere) -> glm.dvec3:
        """ Calculates the acceleration of the spacecraft due to the drag from Titan's atmosphere,
            -(rho * Cd * A / 2m) * |v| * v. """

        speed = glm.length(velocity)
        altitude = glm.length(position) - TITAN_RADIUS_M  # The density data is indexed by the altitude in m.
        air_density = float(atm.density(altitude))

        drag_factor = 0.5 * air_density * SPACECRAFT_CROSSSECTIONAL_AREA * SPACECRAFT_DRAG_COEFFICIENT / SPACECRAFT_MASS_KG

        # Written as |v| * v rather than |v|^2 * normalize(v), which would be NaN when the speed is 0.
        return -drag_factor * speed * velocity

    @staticmethod
    def _acceleration(position: glm.dvec3, velocity: glm.dvec3, atm: Atmosphere) -> glm.dvec3:
        """ The total acceleration of the spacecraft, i.e. the sum of the forces divided by its mass. """
        return Trajectory._gravity_acceleration(position) + Trajectory._drag_acceleration(position, velocity, atm)

    @staticmethod
    def _runge_kutta(position: glm.dvec3, velocity: glm.dvec3, time: float, atm: Atmosphere, dt: float) -> RungeKuttaRecord:
        """ Calculates a single iteration output of the (classical) 4th-order Runge-Kutta. """

        acceleration = Trajectory._acceleration

        k_1pos = dt * velocity
        k_1vel = dt * acceleration(position, velocity, atm)

        k_2pos = dt * (velocity + 0.5*k_1vel)
        k_2vel = dt * acceleration(position + 0.5*k_1pos, velocity + 0.5*k_1vel, atm)

        k_3pos = dt * (velocity + 0.5*k_2vel)
        k_3vel = dt * acceleration(position + 0.5*k_2pos, velocity + 0.5*k_2vel, atm)

        # The last stage is evaluated at the end of the step, i.e. a full step rather than a half one.
        k_4pos = dt * (velocity + k_3vel)
        k_4vel = dt * acceleration(position + k_3pos, velocity + k_3vel, atm)

        position_next = position + (1.0/6)*(k_1pos + 2*k_2pos + 2*k_3pos + k_4pos)
        velocity_next = velocity + (1.0/6)*(k_1vel + 2*k_2vel + 2*k_3vel + k_4vel)
        time_next = time + dt

        return RungeKuttaRecord(position=position_next, velocity=velocity_next, time=time_next)


    def calculate_discrete_trajectory(self, time_step: float, stop_predicate: Callable[[RungeKuttaRecord], bool]) -> Generator[RungeKuttaRecord, None, None]:
        """ Calculates the trajectory of this spaceship by returning an iterator of records of the state of the
            spaceship after each ``time_step`` (in s), starting with the initial state at t = 0. The iterator
            continues to (maybe infinitely) yield the state-records while ``stop_predicate(record) == True``.
            For example, ``lambda record: glm.length(record.position) > TITAN_RADIUS_M`` stops at impact. """

        record = RungeKuttaRecord(position=glm.dvec3(self.position), velocity=glm.dvec3(self.velocity), time=0.0)

        while stop_predicate(record):
            yield record
            record = Trajectory._runge_kutta(record.position, record.velocity, record.time, self.titan_atmosphere, time_step)

    def calculate_trajectory(self, time_step: float, max_time: float, max_points: int = 2_000_000) -> TrajectoryArrays:
        """ Calculates the whole trajectory at once in C++ (``calc/trajectory.cpp``), and returns the states every
            ``time_step`` (s) from t = 0 as arrays. Like ``calculate_discrete_trajectory`` with the stop predicate
            ``|position| > R and time <= max_time``, and at most ``max_points`` states. """
        return native.trajectory(self.position, self.velocity, time_step, max_time, max_points)




if __name__ == "__main__":
    print("Testing Trajectory Calculations")
