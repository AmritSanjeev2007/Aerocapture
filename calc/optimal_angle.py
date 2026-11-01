# pyright: standard

""" The module responsible for calculating the initial pitch and yaw to achieve an elliptical orbit with the specified apoapsis.

``calculate_optimal_angle`` runs in C++ (``calc/optimal_angle.cpp``). The ``Apoapsis`` class below is the same
calculation in Python, kept as the readable reference: change both together. """

from pyglm import glm
from typing import Literal, TypeAlias

from calc import native
from calc.atmosphere import Atmosphere
from calc.constants import GRAVITATIONAL_CONSTANT, TITAN_MASS_KG, TITAN_RADIUS_M
from calc.trajectory import RungeKuttaRecord, Trajectory


double: TypeAlias = glm.double

GUESSES_NOT_CAPTURED = native.GUESSES_NOT_CAPTURED


def _pitch_solver(desired_altitude_m: double, initial_pos: glm.dvec3, speed: double, yaw: double,
                  guesses: tuple[double, double]) -> double:
    """ Solves for the pitch angle that gives the trajectory with the desired apoapsis, with the ``yaw`` fixed. """
    return native.optimal_angle(desired_altitude_m, initial_pos, speed, yaw, True, *guesses)

def _yaw_solver(desired_altitude_m: double, initial_pos: glm.dvec3, speed: double, pitch: double,
                guesses: tuple[double, double]) -> double:
    """ Solves for the yaw angle that gives the trajectory with the desired apoapsis, with the ``pitch`` fixed. """
    return native.optimal_angle(desired_altitude_m, initial_pos, speed, pitch, False, *guesses)


def calculate_optimal_angle(desired_altitude_m: double, initial_pos: glm.dvec3, speed: double,
                            guesses: tuple[double, double], pitch: double | None = None,
                            yaw: double | None = None) -> glm.dvec2:
    """ Finds the initial (pitch, yaw) giving an apoapsis ``desired_altitude_m`` above Titan's surface after the
        first atmospheric pass. Exactly one of ``pitch`` and ``yaw`` is given and held constant, and the other is
        solved for with the secant method, starting from the two ``guesses`` (in rad) for it. Runs in C++, and
        raises the same errors as ``Apoapsis.solve``. """

    if pitch is None:
        assert yaw is not None, "If the pitch is empty, the yaw MUST be given."
        return glm.dvec2(_pitch_solver(desired_altitude_m, initial_pos, speed, yaw, guesses), yaw)

    if yaw is None:
        return glm.dvec2(pitch, _yaw_solver(desired_altitude_m, initial_pos, speed, pitch, guesses))

    raise ValueError("Only one of the pitch and yaw can be given, as the other is solved for.")


class Apoapsis:
    """ Implements the "Optimal Angle" section of report.typ: finds the initial pitch or yaw (with the other held
        constant) for which the orbit after the first atmospheric pass has the desired apoapsis. The apoapsis is
        calculated from the orbital elements at atmospheric exit, using conservation of energy and angular
        momentum, and the free angle is found with the secant method. All quantities are in SI units
        (m, m/s, s, rad). """

    _MAX_STEP_HALVINGS = 20
    """ How many times a secant step is halved back towards the last good guess when it lands on a trajectory
        with no apoapsis (it misses the atmosphere, crashes or escapes). """

    def __init__(self, desired_altitude_m: float, initial_pos: glm.dvec3, speed: float, pitch: float | None = None,
                 yaw: float | None = None, time_step: float = 1.0, max_time: float = 86_400.0) -> None:
        """ Exactly one of ``pitch`` and ``yaw`` is given: that angle is held constant and the other is free. """

        if (pitch is None) == (yaw is None):
            raise ValueError("Give exactly one of the pitch and yaw, as the other is solved for.")

        self.fixed_angle = pitch if pitch is not None else yaw
        """ The value of the angle that is held constant. """
        self.free_angle: Literal["pitch", "yaw"] = "pitch" if pitch is None else "yaw"
        """ Which angle is solved for. Every ``angle`` argument below is a value of this angle. """

        self.desired_altitude_m = desired_altitude_m
        """ The desired apoapsis altitude H, above Titan's surface. """
        self.desired_radius_m = TITAN_RADIUS_M + desired_altitude_m
        """ The desired apoapsis distance from Titan's centre, R + H (this is what the apoapsis is compared to). """

        self.initial_pos = glm.dvec3(initial_pos)
        self.speed = speed
        self.time_step = time_step
        self.max_time = max_time
        """ The longest a single atmospheric pass is simulated for, as a safety net. """

        # The density data stops at its highest altitude (and is 0 above it), so that is where the atmosphere ends.
        self.atmosphere_radius_m = TITAN_RADIUS_M + float(Atmosphere().densities[-1, 0])
        """ The distance from Titan's centre to the top of the atmosphere. """

    def angles(self, angle: float) -> tuple[float, float]:
        """ The initial (pitch, yaw) for a value of the free ``angle``. """
        assert self.fixed_angle is not None
        return (angle, self.fixed_angle) if self.free_angle == "pitch" else (self.fixed_angle, angle)

    @staticmethod
    def radius_from_state(position: glm.dvec3, velocity: glm.dvec3) -> float | None:
        """ Calculates the apoapsis distance (from Titan's centre) of the orbit through ``position`` with
            ``velocity``, when only gravity acts. Returns ``None`` if the orbit isn't closed (it escapes). """

        gm = GRAVITATIONAL_CONSTANT * TITAN_MASS_KG

        # The specific (per unit mass) energy and angular momentum, which are both conserved after exit.
        energy = 0.5 * glm.dot(velocity, velocity) - gm / glm.length(position)
        angular_momentum = glm.length(glm.cross(position, velocity))

        if energy >= 0:
            return None

        # energy * r_a^2 + GM * r_a - h^2 / 2 = 0. As the energy is negative, the larger root takes the minus sign.
        discriminant = max(gm**2 + 2 * energy * angular_momentum**2, 0.0)
        return (-gm - discriminant**0.5) / (2 * energy)

    def exit_state(self, angle: float) -> RungeKuttaRecord | None:
        """ Simulates the first atmospheric pass for an initial free ``angle`` and returns the state just after the
            spacecraft leaves the atmosphere. Returns ``None`` if it misses the atmosphere, crashes into the surface
            or is still inside after ``max_time``. """

        trajectory = Trajectory(self.initial_pos, self.speed, *self.angles(angle))
        records = trajectory.calculate_discrete_trajectory(
            self.time_step,
            lambda record: glm.length(record.position) > TITAN_RADIUS_M and record.time <= self.max_time)

        has_entered = False

        for record in records:
            distance = glm.length(record.position)

            if distance < self.atmosphere_radius_m:
                has_entered = True
            elif has_entered:
                return record
            elif glm.dot(record.position, record.velocity) > 0:
                # Moving away from Titan without having entered: the closest approach missed the atmosphere.
                return None

        return None

    def apoapsis_radius(self, angle: float) -> float | None:
        """ The apoapsis distance (from Titan's centre) after the first atmospheric pass, for an initial free
            ``angle``. Returns ``None`` if there is no apoapsis (see ``exit_state`` and ``radius_from_state``). """

        record = self.exit_state(angle)
        return None if record is None else Apoapsis.radius_from_state(record.position, record.velocity)

    def f(self, angle: float) -> float | None:
        """ The difference between the desired and achieved apoapses for an initial free ``angle``, whose root the
            secant method finds. Returns ``None`` if there is no apoapsis. """

        radius = self.apoapsis_radius(angle)
        return None if radius is None else self.desired_radius_m - radius

    def solve(self, angle_0: float, angle_1: float, tolerance_m: float = 1.0, max_iterations: int = 50) -> float:
        """ Finds the free angle giving the desired apoapsis with the secant method, starting from the two guesses
            ``angle_0`` and ``angle_1``. The first guess must give a captured orbit, and the second is moved
            towards the first until it does too. Stops once the apoapsis is within
            ``tolerance_m`` of the desired one. """

        f_0 = self.f(angle_0)
        if f_0 is None:
            raise ValueError(GUESSES_NOT_CAPTURED)

        # The range of captured orbits can be narrower than the gap between the guesses, so the second guess is
        # pulled back towards the first until it's captured too, like a step that leaves the range below.
        f_1 = self.f(angle_1)
        halvings = 0
        while f_1 is None:
            halvings += 1
            if halvings > Apoapsis._MAX_STEP_HALVINGS:
                raise ValueError(GUESSES_NOT_CAPTURED)
            angle_1 = 0.5 * (angle_0 + angle_1)
            f_1 = self.f(angle_1)

        for _ in range(max_iterations):
            if abs(f_1) < tolerance_m:
                return angle_1
            if f_1 == f_0:
                raise ArithmeticError("The secant is flat, so the method can't continue. Try other guesses.")

            angle_2 = angle_1 - f_1 * (angle_1 - angle_0) / (f_1 - f_0)
            f_2 = self.f(angle_2)

            # f has no value where the spacecraft misses, crashes or escapes, so step back towards the last guess.
            halvings = 0
            while f_2 is None:
                halvings += 1
                if halvings > Apoapsis._MAX_STEP_HALVINGS:
                    raise ArithmeticError("The secant method left the range of captured orbits.")
                angle_2 = 0.5 * (angle_1 + angle_2)
                f_2 = self.f(angle_2)

            angle_0, f_0, angle_1, f_1 = angle_1, f_1, angle_2, f_2

        raise ArithmeticError(f"The secant method didn't converge within {max_iterations} iterations.")


# Test code (run using "py -m calc.optimal_angle"): the C++ and the Python reference must agree.
if __name__ == "__main__":

    import numpy as np
    import time

    initial_pos = glm.dvec3(-12_000_000, 2_000_000, 0.0)

    for name, kwargs, guesses in (("pitch", {"yaw": 0.0}, (4.875, 4.8875)), ("yaw", {"pitch": 0.0}, (10.825, 10.83))):
        guesses = (np.radians(guesses[0]), np.radians(guesses[1]))

        start = time.perf_counter()
        angles = calculate_optimal_angle(9_000_000, initial_pos, 6_500, guesses, **kwargs)
        cpp_time = time.perf_counter() - start
        pitch, yaw = angles.x, angles.y

        apoapsis = Apoapsis(9_000_000, initial_pos, 6_500, **kwargs)
        start = time.perf_counter()
        python_angle = apoapsis.solve(*guesses)
        python_time = time.perf_counter() - start

        cpp_angle = pitch if name == "pitch" else yaw
        radius = native.apoapsis_radius(initial_pos, 6_500, pitch, yaw)

        print(f"Solving for the {name}: pitch = {np.degrees(pitch):.6f} deg, yaw = {np.degrees(yaw):.6f} deg, "
              f"apoapsis altitude = {(radius or 0.0) - TITAN_RADIUS_M:,.1f} m")
        print(f"    C++ {cpp_time * 1000:.1f} ms, Python {python_time * 1000:.1f} ms, "
              f"same angle: {cpp_angle == python_angle} (difference {np.degrees(cpp_angle - python_angle):.2e} deg)")
