# pyright: standard

""" Loads the C++ calculations (``calc/trajectory.cpp``, ``calc/optimal_angle.cpp`` and ``calc/circular_burn.cpp``)
with ctypes and wraps them for Python. They do the same calculations as ``calc/trajectory.py``,
``calc/optimal_angle.py`` and ``calc/circular_burn.py``, in double
precision, but hundreds of times faster, as Python makes several calls per time step.

The library is compiled automatically the first time it's needed, or when a ``.cpp`` / ``.hpp`` file is newer
than it. To compile it by hand, run ``py -m calc.native``. On Windows it uses Visual Studio's C++ compiler (MSVC)
if it's installed, otherwise g++ (e.g. MSYS2's). The library is unloaded only when Python exits, so close the
program before rebuilding. """

import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import threading

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from calc.atmosphere import Atmosphere
from calc.constants import (
    GRAVITATIONAL_CONSTANT, SPACECRAFT_CROSSSECTIONAL_AREA, SPACECRAFT_DRAG_COEFFICIENT, SPACECRAFT_MASS_KG,
    TITAN_MASS_KG, TITAN_RADIUS_M,
)

_SOURCE_DIR = Path(__file__).resolve().parent
_SOURCES = ("trajectory.cpp", "optimal_angle.cpp", "circular_burn.cpp")
_HEADERS = ("trajectory.hpp",)
_LIBRARY_PATH = _SOURCE_DIR / ("native.dll" if sys.platform == "win32" else "native.so")
""" The compiled library, next to this module (and bundled next to it by ``Aerocapture.spec``). """


# ----------------------------------------------------------------------------------------------------------------
# Building
# ----------------------------------------------------------------------------------------------------------------

def _find_vcvars() -> Path | None:
    """ The path to Visual Studio's ``vcvars64.bat``, which sets up MSVC's environment, if it's installed. """

    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
    if not vswhere.exists():
        return None

    result = subprocess.run(
        [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
         "-property", "installationPath"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        vcvars = Path(line.strip()) / "VC" / "Auxiliary" / "Build" / "vcvars64.bat"
        if vcvars.exists():
            return vcvars
    return None


def build() -> Path:
    """ Compiles the C++ sources into ``_LIBRARY_PATH``, optimized for speed but keeping IEEE double precision
    (no fast-math), so the results match the Python's. """

    sources = [str(_SOURCE_DIR / source) for source in _SOURCES]

    with tempfile.TemporaryDirectory() as build_dir:
        vcvars = _find_vcvars() if sys.platform == "win32" else None

        if vcvars is not None:
            # /O2 /Ob3: speed and aggressive inlining. /GL + /LTCG: optimize across both files. /fp:precise: no
            # reordering or contraction of floating point operations.
            compile_command = subprocess.list2cmdline([
                "cl", "/nologo", "/std:c++17", "/O2", "/Ob3", "/GL", "/fp:precise", "/EHsc", "/LD", *sources,
                f"/Fo{build_dir}\\", f"/Fe{_LIBRARY_PATH}",
                "/link", "/LTCG", f"/IMPLIB:{Path(build_dir) / 'native.lib'}",
            ])
            # Run from a batch file, as cmd's quoting rules for paths with spaces are hard to get right inline.
            script = Path(build_dir) / "build.bat"
            script.write_text(f'@call "{vcvars}" >nul\r\n@{compile_command}\r\n', encoding="utf-8")
            result = subprocess.run(["cmd", "/d", "/c", str(script)], capture_output=True, text=True)
        else:
            compiler = shutil.which("g++") or shutil.which("clang++") or shutil.which("c++")
            if compiler is None:
                raise RuntimeError("No C++ compiler found: install Visual Studio's C++ tools, or g++.")
            # -static so the library doesn't need the compiler's own runtime DLLs next to it on Windows.
            flags = ["-O3", "-std=c++17", "-shared", "-ffp-contract=off", "-fno-math-errno"]
            flags += ["-static"] if sys.platform == "win32" else ["-fPIC"]
            result = subprocess.run([compiler, *flags, *sources, "-o", str(_LIBRARY_PATH)],
                                    capture_output=True, text=True)

    if result.returncode != 0 or not _LIBRARY_PATH.exists():
        raise RuntimeError(f"Compiling the C++ calculations failed:\n{result.stdout}\n{result.stderr}")

    return _LIBRARY_PATH


def _is_stale() -> bool:
    """ Whether the library is missing, or older than its sources. When frozen (e.g. by PyInstaller) the sources
    aren't there, so the bundled library is used as it is. """

    if not _LIBRARY_PATH.exists():
        return True

    built = _LIBRARY_PATH.stat().st_mtime
    sources = [_SOURCE_DIR / name for name in (*_SOURCES, *_HEADERS)]
    return any(source.exists() and source.stat().st_mtime > built for source in sources)


# ----------------------------------------------------------------------------------------------------------------
# Loading
# ----------------------------------------------------------------------------------------------------------------

class _Physics(ctypes.Structure):
    """ Mirrors ``CalcPhysics`` in ``calc/trajectory.hpp``: keep the two in the same order. """

    _fields_ = [
        ("gravitational_constant", ctypes.c_double),
        ("titan_mass", ctypes.c_double),
        ("titan_radius", ctypes.c_double),
        ("spacecraft_area", ctypes.c_double),
        ("drag_coefficient", ctypes.c_double),
        ("spacecraft_mass", ctypes.c_double),
        ("densities", ctypes.POINTER(ctypes.c_double)),
        ("density_count", ctypes.c_int64),
    ]


_DOUBLE_P = ctypes.POINTER(ctypes.c_double)
_PHYSICS_P = ctypes.POINTER(_Physics)


def _load() -> ctypes.CDLL:
    if _is_stale():
        build()

    library = ctypes.CDLL(str(_LIBRARY_PATH))

    library.calc_trajectory.restype = ctypes.c_int64
    library.calc_trajectory.argtypes = [
        _PHYSICS_P, _DOUBLE_P, _DOUBLE_P, ctypes.c_double, ctypes.c_double, ctypes.c_int64,
        _DOUBLE_P, _DOUBLE_P, _DOUBLE_P, ctypes.POINTER(ctypes.c_int32), _DOUBLE_P,
    ]

    library.calc_apoapsis_radius.restype = ctypes.c_double
    library.calc_apoapsis_radius.argtypes = [
        _PHYSICS_P, _DOUBLE_P, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_double,
    ]

    library.calc_optimal_angle.restype = ctypes.c_int32
    library.calc_optimal_angle.argtypes = [
        _PHYSICS_P, ctypes.c_double, _DOUBLE_P, ctypes.c_double, ctypes.c_double, ctypes.c_int32,
        ctypes.c_double, ctypes.c_double, ctypes.c_double, ctypes.c_int32, ctypes.c_double, ctypes.c_double,
        _DOUBLE_P,
    ]

    library.calc_circular_burn.restype = ctypes.c_int32
    library.calc_circular_burn.argtypes = [
        _PHYSICS_P, _DOUBLE_P, _DOUBLE_P, ctypes.c_double, ctypes.c_double, _DOUBLE_P, _DOUBLE_P,
    ]

    return library


_library: ctypes.CDLL | None = None
_library_lock = threading.Lock()


def _get_library() -> ctypes.CDLL:
    """ The library, loaded (and if needed compiled) on first use rather than on import, so ``py -m calc.native``
    can rebuild it without it being in use. """

    global _library
    with _library_lock:
        if _library is None:
            _library = _load()
        return _library


_densities = np.ascontiguousarray(Atmosphere().densities, dtype=np.float64)
""" Kept alive here, as ``_physics`` only points to it. """
_physics = _Physics(
    GRAVITATIONAL_CONSTANT, TITAN_MASS_KG, TITAN_RADIUS_M, SPACECRAFT_CROSSSECTIONAL_AREA,
    SPACECRAFT_DRAG_COEFFICIENT, SPACECRAFT_MASS_KG, _densities.ctypes.data_as(_DOUBLE_P), len(_densities),
)


def _vector(vector) -> NDArray[np.float64]:
    """ Any 3 component vector (e.g. a ``glm.dvec3``) as a contiguous array of doubles. """
    array = np.ascontiguousarray(np.asarray(tuple(vector), dtype=np.float64))
    assert array.shape == (3,), "Expected a vector with 3 components."
    return array


def _pointer(array: NDArray[np.float64]):
    return array.ctypes.data_as(_DOUBLE_P)


# ----------------------------------------------------------------------------------------------------------------
# The calculations
# ----------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class TrajectoryArrays:
    """ The spacecraft's states every time step, starting at t = 0. All in SI units, in the calculations' frame
    (see ``calc/trajectory.py``). """

    positions: NDArray[np.float64]
    """ (N, 3) positions in m. """
    velocities: NDArray[np.float64]
    """ (N, 3) velocities in m/s. """
    times: NDArray[np.float64]
    """ (N,) times in s. """
    impacted: bool
    """ Whether it stopped by hitting Titan's surface (otherwise at ``max_time`` or ``max_points``). """
    impact_position: NDArray[np.float64] | None = None
    """ Where it hit Titan's surface, in m (``None`` if it didn't). It's between the last two time steps, so it
    isn't one of the ``positions``. """
    impact_time: float | None = None
    """ When it hit Titan's surface, in s (``None`` if it didn't). """

    def __len__(self) -> int:
        return len(self.times)


def trajectory(initial_position, initial_velocity, time_step: float, max_time: float,
               max_points: int) -> TrajectoryArrays:
    """ Calculates the trajectory from the initial state like ``Trajectory.calculate_discrete_trajectory``,
    recording every ``time_step`` (s) while the spacecraft is above Titan's surface and the time is at most
    ``max_time`` (s), up to ``max_points`` states. See ``calc_trajectory`` in ``calc/trajectory.cpp``. """

    # There can't be more points than time steps, so don't reserve more memory than that.
    max_points = max(min(int(max_points), int(max_time / time_step) + 2), 0)

    positions = np.empty((max_points, 3), dtype=np.float64)
    velocities = np.empty((max_points, 3), dtype=np.float64)
    times = np.empty(max_points, dtype=np.float64)
    impacted = ctypes.c_int32(0)
    impact = np.zeros(4, dtype=np.float64)

    # ctypes releases the GIL during the call, so the window stays responsive if this runs on another thread.
    count = _get_library().calc_trajectory(
        ctypes.byref(_physics), _pointer(_vector(initial_position)), _pointer(_vector(initial_velocity)),
        time_step, max_time, max_points, _pointer(positions), _pointer(velocities), _pointer(times),
        ctypes.byref(impacted), _pointer(impact),
    )

    # Copied, so the unused part of the arrays is freed.
    hit = bool(impacted.value)
    return TrajectoryArrays(positions[:count].copy(), velocities[:count].copy(), times[:count].copy(), hit,
                            impact[:3].copy() if hit else None, float(impact[3]) if hit else None)


def apoapsis_radius(initial_position, speed: float, pitch: float, yaw: float, time_step: float = 1.0,
                    max_time: float = 86_400.0) -> float | None:
    """ The apoapsis distance (from Titan's centre, in m) after the first atmospheric pass, or ``None`` if it misses
    the atmosphere, crashes or escapes. Like ``Apoapsis.apoapsis_radius``. """

    radius = _get_library().calc_apoapsis_radius(ctypes.byref(_physics), _pointer(_vector(initial_position)), speed,
                                           pitch, yaw, time_step, max_time)
    return None if np.isnan(radius) else float(radius)


GUESSES_NOT_CAPTURED = (
    "The first guess, and a second guess near it, must give a captured orbit (no miss, crash or escape)."
)

_ERRORS = {
    1: (ValueError, GUESSES_NOT_CAPTURED),
    2: (ArithmeticError, "The secant is flat, so the method can't continue. Try other guesses."),
    3: (ArithmeticError, "The secant method left the range of captured orbits."),
    4: (ArithmeticError, "The secant method didn't converge within {max_iterations} iterations."),
}
""" The status codes of ``calc_optimal_angle`` and the errors they raise (the same as ``Apoapsis.solve``'s). """


def optimal_angle(desired_altitude_m: float, initial_position, speed: float, fixed_angle: float,
                  solve_for_pitch: bool, angle_0: float, angle_1: float, tolerance_m: float = 1.0,
                  max_iterations: int = 50, time_step: float = 1.0, max_time: float = 86_400.0) -> float:
    """ Finds the free angle (the pitch if ``solve_for_pitch``, otherwise the yaw) giving an apoapsis
    ``desired_altitude_m`` above Titan's surface, with the other angle held at ``fixed_angle``, by the secant
    method from the guesses ``angle_0`` and ``angle_1`` (all in rad). Like ``Apoapsis.solve``, and raises the same
    errors. """

    result = ctypes.c_double(0.0)
    status = _get_library().calc_optimal_angle(
        ctypes.byref(_physics), desired_altitude_m, _pointer(_vector(initial_position)), speed, fixed_angle,
        int(solve_for_pitch), angle_0, angle_1, tolerance_m, max_iterations, time_step, max_time,
        ctypes.byref(result),
    )

    if status != 0:
        error, message = _ERRORS[status]
        raise error(message.format(max_iterations=max_iterations))
    return result.value


@dataclass(frozen=True)
class ApoapsisBurn:
    """ The impulsive burn at the apoapsis which circularises the orbit. All in SI units, in the calculations' frame
    (see ``calc/trajectory.py``). """

    position: NDArray[np.float64]
    """ Where the burn happens (the apoapsis), in m. """
    velocity: NDArray[np.float64]
    """ The velocity just before the burn, in m/s. """
    time: float
    """ When the burn happens, in s. """
    delta_v: NDArray[np.float64]
    """ The change of velocity, in m/s. The thrust is along it. """

    @property
    def velocity_after(self) -> NDArray[np.float64]:
        """ The velocity just after the burn (the circular orbit's), in m/s. """
        return self.velocity + self.delta_v


def circular_burn(initial_position, initial_velocity, time_step: float, max_time: float) -> ApoapsisBurn | None:
    """ The burn which circularises the orbit at the first apoapsis after the atmospheric pass, integrating every
    ``time_step`` (s) for at most ``max_time`` (s). ``None`` if there's no such apoapsis (it misses the atmosphere,
    crashes, escapes or takes too long). Like ``CircularBurn``, see ``calc_circular_burn`` in
    ``calc/circular_burn.cpp``. """

    apoapsis = np.zeros(7, dtype=np.float64)
    delta_v = np.zeros(3, dtype=np.float64)
    status = _get_library().calc_circular_burn(
        ctypes.byref(_physics), _pointer(_vector(initial_position)), _pointer(_vector(initial_velocity)),
        time_step, max_time, _pointer(apoapsis), _pointer(delta_v),
    )

    if status != 0:
        return None
    return ApoapsisBurn(apoapsis[:3].copy(), apoapsis[3:6].copy(), float(apoapsis[6]), delta_v)


# Builds the library (run using "py -m calc.native")
if __name__ == "__main__":
    print(f"Built {build()}")
