# pyright: standard

""" This module contains all the constants that are shared among all (calculation) source modules. """

from pathlib import Path
from pyglm import glm

GRAVITATIONAL_CONSTANT = 6.6743e-11
""" The universal gravitational constant in m^3 kg^-1 s^-2. """

SPACECRAFT_MASS_KG = 2_000
""" The mass of the spacecraft in kg. """
SPACECRAFT_CROSSSECTIONAL_AREA = 14
""" The cross-sectional area of the spacecraft in m^2. """
SPACECRAFT_DRAG_COEFFICIENT = 1.2
""" The (measured) drag coefficient for the spacecraft. """

TITAN_RADIUS_KM = 2_574
""" The radius of Titan in km. """
TITAN_RADIUS_M = TITAN_RADIUS_KM * 1_000
""" The radius of Titan in m (the calculations are in SI units). """
TITAN_MASS_KG = 1.3452e+23
""" The mass of Titan in kg. """
TITAN_AIR_DENSITY_PATH = Path(__file__).resolve().parent / "titan_height_density.csv"
""" The file which contains the air density data for Titan (heights in m). Found next to this module, so it doesn't
depend on the working directory. """

