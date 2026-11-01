# pyright: standard

""" The main entry point into the program. """

import threading

from calc.constants import TITAN_RADIUS_KM
from calc import native
from calc.circular_burn import calculate_trajectory_with_burn, impulse
from calc.optimal_angle import calculate_optimal_angle
from calc.trajectory import Trajectory
from display.constants import GUI_SCALE, TRAJECTORY_MAX_POINTS
from display.renderer import Renderer

from imgui_bundle import imgui
from pyglm import glm

import numpy as np


INITIAL_POSITION = glm.dvec3(-12_000_000, 2_000_000, 0.0)
""" The initial position of the spacecraft. Refer to trajectory.py for more info on the coordinate system used. """
INITIAL_SPEED = 6_500
""" The initial speed of the spacecraft in m/s. """
INITIAL_PITCH_DEG = 4.88
INITIAL_YAW_DEG = 0.0
""" The initial angles of the spacecraft's velocity in degrees. Refer to trajectory.py for their definitions. """
DESIRED_APOAPSIS_ALTITUDE_KM = 9_000.0
""" The default apoapsis altitude (above Titan's surface) that the optimization aims for, in km. """
MAX_TIME = 100 * 86_400
""" The simulation stops at impact, or after this long (in s) in case the spacecraft never comes down. """
TIME_STEP = 10.0
""" The interval between each iteration. One can imagine this as the "resolution" of the simulation. """
SECOND_GUESS_OFFSET_DEG = 0.0125
""" The secant method needs two initial guesses: the free angle's current value, and this much more. """

ERROR_COLOR = imgui.ImVec4(1.0, 0.45, 0.45, 1.0)


class MissionPanel:
    """ The "Trajectory" window: the spacecraft's initial position, speed, pitch and yaw, and the optimization of
    the pitch or the yaw (whichever isn't locked) for a desired apoapsis. """

    def __init__(self, renderer: Renderer) -> None:

        self.renderer = renderer

        self.position_km = [INITIAL_POSITION.x / 1000, INITIAL_POSITION.y / 1000, INITIAL_POSITION.z / 1000]
        self.speed = float(INITIAL_SPEED)
        self.pitch_deg = INITIAL_PITCH_DEG
        self.yaw_deg = INITIAL_YAW_DEG
        self.pitch_locked = False
        self.yaw_locked = True
        """ At most one angle is locked. The locked one is held constant while the other is optimized. """
        self.desired_altitude_km = DESIRED_APOAPSIS_ALTITUDE_KM
        self.circularize = False
        """ Whether to burn at the apoapsis after the atmospheric pass to make the orbit circular. """
        self.burn_description = ""

        self.outcome = ""
        self.first_pass = ""
        self.optimization_status = ""
        self.optimization_failed = False

        # The optimization runs on a background thread so the window stays responsive (it's fast in C++, but can
        # take longer for other initial states). Its result is applied on this (the OpenGL) thread, as drawing
        # the new trajectory uploads it to the GPU.
        self._optimizer: threading.Thread | None = None
        self._optimized_angle_deg: float | None = None

        self.simulate()

    @property
    def initial_position(self) -> glm.dvec3:
        """ The initial position in m. """
        return glm.dvec3(*self.position_km) * 1000.0

    @property
    def is_optimizing(self) -> bool:
        return self._optimizer is not None and self._optimizer.is_alive()

    def simulate(self) -> None:
        """ Calculates and shows the trajectory for the current initial state, and describes its outcome. """

        pitch, yaw = np.radians(self.pitch_deg), np.radians(self.yaw_deg)

        # The trajectory is calculated in C++ (calc/trajectory.cpp), and its arrays are passed on to be drawn.
        trajectory = Trajectory(self.initial_position, self.speed, pitch, yaw)
        if self.circularize:
            # The burn changes the trajectory after the apoapsis (C++, see calc/circular_burn.cpp).
            states, burn = calculate_trajectory_with_burn(trajectory, TIME_STEP, MAX_TIME, TRAJECTORY_MAX_POINTS)
        else:
            states, burn = trajectory.calculate_trajectory(TIME_STEP, MAX_TIME, TRAJECTORY_MAX_POINTS), None
        self.renderer.set_trajectory(states)
        self.renderer.set_burn(burn)
        self.burn_description = "" if not self.circularize else self.describe_burn(burn)

        end_time = float(states.times[-1]) if len(states) else 0.0
        if states.impact_position is not None and states.impact_time is not None:
            # In km, in the same frame as the initial position above.
            x, y, z = states.impact_position / 1000
            self.outcome = f"Impact after {states.impact_time:,.0f} s at ({x:,.1f}, {y:,.1f}, {z:,.1f}) km"
        elif end_time + TIME_STEP > MAX_TIME:
            self.outcome = f"No impact within {MAX_TIME / 86_400:g} days"
        else:
            self.outcome = f"Cut off after {len(states):,} points ({end_time:,.0f} s)"

        # The apoapsis right after the first atmospheric pass, which is what the optimization targets (C++, see
        # calc/optimal_angle.cpp).
        radius = native.apoapsis_radius(self.initial_position, self.speed, pitch, yaw)
        self.first_pass = (
            "No capture: it misses the atmosphere, crashes or escapes" if radius is None
            else f"Apoapsis after the first pass: {(radius / 1000) - TITAN_RADIUS_KM:,.1f} km"
        )

    @staticmethod
    def describe_burn(burn: native.ApoapsisBurn | None) -> str:
        """ The circularising burn's time, place and thrust direction, for the window. """

        if burn is None:
            return "No apoapsis to burn at: it misses the atmosphere, crashes or escapes"

        altitude_km = np.linalg.norm(burn.position) / 1000 - TITAN_RADIUS_KM
        dv = burn.delta_v
        x, y, z = dv / np.linalg.norm(dv)
        return (
            f"Burn after {burn.time:,.0f} s at {altitude_km:,.1f} km altitude\n"
            f"Delta v: {np.linalg.norm(dv):,.2f} m/s = ({dv[0]:,.2f}, {dv[1]:,.2f}, {dv[2]:,.2f}) m/s\n"
            f"Thrust direction: ({x:.4f}, {y:.4f}, {z:.4f})\n"
            f"Impulse: {np.linalg.norm(impulse(burn)):,.0f} N s (impulsive burn)"
        )

    def _optimize(self, desired_altitude_m: float, initial_position: glm.dvec3, speed: float, pitch: float,
                  yaw: float, solve_for_pitch: bool) -> None:
        """ Runs on the background thread. """

        free = pitch if solve_for_pitch else yaw
        guesses = (free, free + np.radians(SECOND_GUESS_OFFSET_DEG))
        fixed = {"yaw": yaw} if solve_for_pitch else {"pitch": pitch}

        try:
            angles = calculate_optimal_angle(desired_altitude_m, initial_position, speed, guesses, **fixed)
        except (ValueError, ArithmeticError) as error:
            # The secant method needs the current angle to give a captured orbit, which only happens in a narrow
            # range (the second guess is moved towards it until it does too).
            self.optimization_status = f"{error}\nMove the free angle until the outcome shows an apoapsis, then retry."
            self.optimization_failed = True
            return

        self._optimized_angle_deg = float(np.degrees(angles.x if solve_for_pitch else angles.y))

    def start_optimization(self) -> None:
        """ Finds the free angle giving the desired apoapsis, on a background thread. """

        solve_for_pitch = self.yaw_locked
        self.optimization_status = f"Optimizing the {'pitch' if solve_for_pitch else 'yaw'}..."
        self.optimization_failed = False
        self._optimized_angle_deg = None

        self._optimizer = threading.Thread(
            target=self._optimize,
            args=(self.desired_altitude_km * 1000, self.initial_position, self.speed,
                  np.radians(self.pitch_deg), np.radians(self.yaw_deg), solve_for_pitch),
            daemon=True,
        )
        self._optimizer.start()

    def _apply_optimization(self) -> None:
        """ Applies a finished optimization's result, if there is one. """

        if self._optimizer is None or self._optimizer.is_alive():
            return

        self._optimizer = None
        if self._optimized_angle_deg is None:
            return

        name = "pitch" if self.yaw_locked else "yaw"
        if self.yaw_locked:
            self.pitch_deg = self._optimized_angle_deg
        else:
            self.yaw_deg = self._optimized_angle_deg

        self.optimization_status = f"Optimal {name}: {self._optimized_angle_deg:.6f} deg"
        self.simulate()

    def draw(self) -> None:
        """ Creates the window's widgets. Called every frame, through the renderer's ``gui`` callback. """

        self._apply_optimization()

        # The top left corner, out of the way of the Display panel in the top right.
        margin = 12 * GUI_SCALE
        imgui.set_next_window_pos((margin, margin), imgui.Cond_.first_use_ever)
        imgui.begin("Trajectory", None, imgui.WindowFlags_.always_auto_resize)

        # Recalculating takes a moment, so it only happens once a value is let go (or typed in with ctrl + click).
        changed = False
        imgui.begin_disabled(self.is_optimizing)

        imgui.separator_text("Initial state")

        _, self.position_km = imgui.drag_float3("Position (km)", self.position_km, 10.0, format="%.1f")
        changed |= imgui.is_item_deactivated_after_edit()

        _, self.speed = imgui.drag_float("Speed (m/s)", self.speed, 1.0, 0.0, 100_000.0, "%.1f")
        changed |= imgui.is_item_deactivated_after_edit()

        _, self.pitch_deg = imgui.drag_float("Pitch (deg)", self.pitch_deg, 0.001, -90.0, 90.0, "%.4f")
        changed |= imgui.is_item_deactivated_after_edit()
        imgui.same_line()
        clicked, self.pitch_locked = imgui.checkbox("Lock##pitch", self.pitch_locked)
        if clicked and self.pitch_locked:
            self.yaw_locked = False  # Only one angle can be locked.

        _, self.yaw_deg = imgui.drag_float("Yaw (deg)", self.yaw_deg, 0.001, -180.0, 180.0, "%.4f")
        changed |= imgui.is_item_deactivated_after_edit()
        imgui.same_line()
        clicked, self.yaw_locked = imgui.checkbox("Lock##yaw", self.yaw_locked)
        if clicked and self.yaw_locked:
            self.pitch_locked = False

        imgui.separator_text("Optimization")

        _, self.desired_altitude_km = imgui.drag_float(
            "Apoapsis altitude (km)", self.desired_altitude_km, 10.0, 0.0, 1_000_000.0, "%.1f"
        )
        changed |= imgui.is_item_deactivated_after_edit()

        imgui.begin_disabled(not (self.pitch_locked or self.yaw_locked))
        if imgui.button("Optimize"):
            self.start_optimization()
        imgui.end_disabled()

        if not (self.pitch_locked or self.yaw_locked):
            imgui.same_line()
            imgui.text_disabled("Lock the pitch or the yaw first")

        imgui.end_disabled()

        if self.optimization_status:
            if self.optimization_failed:
                imgui.text_colored(ERROR_COLOR, self.optimization_status)
            else:
                imgui.text(self.optimization_status)

        # The burn changes the trajectory after the apoapsis, so it's only done when ticked.
        imgui.separator_text("Burn")
        imgui.begin_disabled(self.is_optimizing)
        clicked, self.circularize = imgui.checkbox("Circularise at the apoapsis", self.circularize)
        changed |= clicked
        imgui.end_disabled()

        imgui.separator_text("Outcome")
        imgui.text(self.first_pass)
        imgui.text(self.outcome)
        if self.burn_description:
            imgui.text(self.burn_description)

        imgui.end()

        if changed:
            self.simulate()


if __name__ == "__main__":

    renderer = Renderer()
    panel = MissionPanel(renderer)

    renderer.render(gui=lambda _: panel.draw())
    renderer.destroy()
