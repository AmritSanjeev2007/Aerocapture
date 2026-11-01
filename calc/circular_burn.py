# pyright: standard

""" The module responsible for the burn at the apoapsis which turns the orbit after the atmospheric pass into a
circular one, and for the trajectory with that burn.

``calculate_circular_burn`` runs in C++ (``calc/circular_burn.cpp``). The ``CircularBurn`` class below is the same
calculation in Python, kept as the readable reference: change both together. """

from pyglm import glm

import numpy as np

from calc import native
from calc.atmosphere import Atmosphere
from calc.constants import GRAVITATIONAL_CONSTANT, SPACECRAFT_MASS_KG, TITAN_MASS_KG, TITAN_RADIUS_M
from calc.native import ApoapsisBurn, TrajectoryArrays
from calc.trajectory import RungeKuttaRecord, Trajectory


def calculate_circular_burn(trajectory: Trajectory, time_step: float, max_time: float) -> ApoapsisBurn | None:
    """ The impulsive burn which circularises the orbit at the first apoapsis after the atmospheric pass of a
        ``trajectory``, integrated every ``time_step`` (s) for at most ``max_time`` (s). ``None`` if there's no such
        apoapsis (it misses the atmosphere, crashes, escapes or takes too long). Runs in C++. """
    return native.circular_burn(trajectory.position, trajectory.velocity, time_step, max_time)


def impulse(burn: ApoapsisBurn) -> np.ndarray:
    """ The impulse (the thrust integrated over the burn) the engine must give, m * delta v, in N s. The thrust
        points along it, and for a burn lasting ``t`` seconds its average magnitude is ``|impulse| / t``. """
    return SPACECRAFT_MASS_KG * burn.delta_v


def calculate_trajectory_with_burn(trajectory: Trajectory, time_step: float, max_time: float,
                                   max_points: int = 2_000_000) -> tuple[TrajectoryArrays, ApoapsisBurn | None]:
    """ Like ``Trajectory.calculate_trajectory``, but with the circularising burn at the first apoapsis after the
        atmospheric pass: the states up to the apoapsis, the apoapsis itself, and the circular orbit from there
        (all in C++). If there's no apoapsis, it's the trajectory without a burn, and the burn is ``None``. """

    burn = calculate_circular_burn(trajectory, time_step, max_time)
    if burn is None:
        return trajectory.calculate_trajectory(time_step, max_time, max_points), None

    # The burn is found with the same steps, so the states before it are exactly the ones without the burn.
    before = native.trajectory(trajectory.position, trajectory.velocity, time_step, burn.time, max_points)
    after = native.trajectory(burn.position, burn.velocity_after, time_step, max_time - burn.time,
                              max(max_points - len(before), 0))

    # ``after`` starts at the apoapsis, with the velocity after the burn.
    states = TrajectoryArrays(
        np.concatenate((before.positions, after.positions)),
        np.concatenate((before.velocities, after.velocities)),
        np.concatenate((before.times, after.times + burn.time)),
        after.impacted,
        after.impact_position,
        None if after.impact_time is None else after.impact_time + burn.time,
    )
    return states, burn


class CircularBurn:
    """ Finds the burn at the first apoapsis after the atmospheric pass which makes the orbit circular, assuming
        it's impulsive (instantaneous). At the apoapsis the velocity is perpendicular to the position, and the
        circular orbit's speed there is sqrt(GM / r), so the burn is the change from one to the other, in the
        direction of travel. All quantities are in SI units (m, m/s, s, rad). """

    def __init__(self, initial_pos: glm.dvec3, speed: float, pitch: float, yaw: float, time_step: float,
                 max_time: float) -> None:

        self.trajectory = Trajectory(initial_pos, speed, pitch, yaw)
        self.time_step = time_step
        self.max_time = max_time
        """ The longest the trajectory is simulated for, as a safety net. """

        # The density data stops at its highest altitude (and is 0 above it), so that is where the atmosphere ends.
        self.atmosphere_radius_m = TITAN_RADIUS_M + float(Atmosphere().densities[-1, 0])

    def apoapsis_state(self) -> RungeKuttaRecord | None:
        """ The state at the first apoapsis after the atmospheric pass, found by bisecting the length of the time
            step during which the spacecraft stops climbing. Returns ``None`` if it misses the atmosphere, crashes,
            escapes or doesn't get there within ``max_time``. """

        gm = GRAVITATIONAL_CONSTANT * TITAN_MASS_KG
        atmosphere = self.trajectory.titan_atmosphere
        step = Trajectory._runge_kutta

        record = RungeKuttaRecord(self.trajectory.position, self.trajectory.velocity, 0.0)
        has_entered = has_exited = False

        while True:
            distance = glm.length(record.position)
            if distance <= TITAN_RADIUS_M or record.time > self.max_time:
                return None

            radial = glm.dot(record.position, record.velocity)  # > 0 while climbing

            if distance < self.atmosphere_radius_m:
                has_entered = True
            elif has_entered and not has_exited:
                # Just out of the atmosphere: from here only gravity acts, so a positive energy means it escapes.
                has_exited = True
                if 0.5 * glm.dot(record.velocity, record.velocity) - gm / distance >= 0:
                    return None
            elif not has_entered and radial > 0:
                return None  # Moving away from Titan without having entered: it missed the atmosphere.

            next_record = step(record.position, record.velocity, record.time, atmosphere, self.time_step)

            if has_exited and radial > 0 and glm.dot(next_record.position, next_record.velocity) <= 0:
                # The apoapsis is during this step: bisect its length for where the radial velocity is 0.
                at_apoapsis, low, high = next_record, 0.0, self.time_step
                for _ in range(64):
                    if high - low <= 0.0:
                        break
                    middle = 0.5 * (low + high)
                    trial = step(record.position, record.velocity, record.time, atmosphere, middle)
                    if glm.dot(trial.position, trial.velocity) > 0:
                        low = middle
                    else:
                        high, at_apoapsis = middle, trial
                return at_apoapsis

            record = next_record

    @staticmethod
    def delta_v(position: glm.dvec3, velocity: glm.dvec3) -> glm.dvec3:
        """ The change of ``velocity`` at ``position`` which makes the orbit circular: to sqrt(GM / r), along the
            velocity without its radial part (which is ~0 at the apoapsis). """

        gm = GRAVITATIONAL_CONSTANT * TITAN_MASS_KG
        r = glm.length(position)
        radial_direction = (1.0 / r) * position
        tangential = velocity + (-glm.dot(radial_direction, velocity)) * radial_direction
        circular_velocity = ((gm / r) ** 0.5 / glm.length(tangential)) * tangential
        return circular_velocity + (-1.0) * velocity

    def solve(self) -> tuple[RungeKuttaRecord, glm.dvec3] | None:
        """ The state at the apoapsis just before the burn, and the burn's change of velocity. ``None`` if there's
            no apoapsis (see ``apoapsis_state``). """

        record = self.apoapsis_state()
        return None if record is None else (record, CircularBurn.delta_v(record.position, record.velocity))


# Test code (run using "py -m calc.circular_burn"): the C++ and the Python reference must agree.
if __name__ == "__main__":

    import time

    initial_pos = glm.dvec3(-12_000_000, 2_000_000, 0.0)
    pitch, yaw = np.radians(4.884167401897255), 0.0
    time_step, max_time = 10.0, 100 * 86_400.0

    start = time.perf_counter()
    burn = calculate_circular_burn(Trajectory(initial_pos, 6_500, pitch, yaw), time_step, max_time)
    cpp_time = time.perf_counter() - start

    start = time.perf_counter()
    python = CircularBurn(initial_pos, 6_500, pitch, yaw, time_step, max_time).solve()
    python_time = time.perf_counter() - start

    assert burn is not None and python is not None, "Expected an apoapsis."
    record, delta_v = python

    altitude = (np.linalg.norm(burn.position) - TITAN_RADIUS_M) / 1000
    print(f"Apoapsis after {burn.time:,.1f} s at {altitude:,.1f} km altitude, "
          f"delta v = {np.linalg.norm(burn.delta_v):.3f} m/s {burn.delta_v}, "
          f"impulse = {np.linalg.norm(impulse(burn)):,.0f} N s")
    print(f"    C++ {cpp_time * 1000:.1f} ms, Python {python_time * 1000:.1f} ms, "
          f"same time: {burn.time == record.time}, same delta v: {tuple(burn.delta_v) == tuple(delta_v)} "
          f"(difference {np.linalg.norm(burn.delta_v - np.array(tuple(delta_v))):.2e} m/s)")

    # After the burn the orbit should stay at the apoapsis' distance.
    states, _ = calculate_trajectory_with_burn(Trajectory(initial_pos, 6_500, pitch, yaw), time_step,
                                               burn.time + 5 * 86_400.0)
    after = np.linalg.norm(states.positions[states.times >= burn.time], axis=1)
    print(f"    After the burn the distance from Titan stays within {after.min() / 1000:,.3f} to "
          f"{after.max() / 1000:,.3f} km for 5 days")
