""" The module responsible for calculating the air density of Titan's atmosphere at various heights. """

from numpy.typing import NDArray
from calc.constants import TITAN_AIR_DENSITY_PATH

import numpy as np

class Atmosphere:
    """ Responsible for loading and accessing the air density data. """

    def __init__(self) -> None:
        self.densities: NDArray[np.float64] = np.loadtxt(TITAN_AIR_DENSITY_PATH, delimiter=',', dtype=np.float64)
        assert self.densities.shape[1] == 2, "Could not load air density data correctly."

    def density(self, h: float | list[float]) -> np.float64 | NDArray[np.float64]:
        """ Calculates (by interpolation) the air density at any given height (h) or list of 
            heights and accordingly returns either a single ``float64`` or a 1-D list of 
            ``float64``s corresponding to each height query. Density data is returned in kg/m^3. Above the
            highest height in the data, the density is 0 (instead of the last value repeating forever). """
        return np.interp(h, self.densities[:, 0], self.densities[:, 1], right=0.0)


# Test code (run using "py -m calc.atmosphere")
if __name__ == '__main__':
    
    # Generate a table
    print('Altitude (m) | Density (kg/m^3)')

    atmosphere = Atmosphere()
    
    # Function accepts single values
    print(f'{-1:12.1e} | {atmosphere.density(-1).item():.3e}')
    print(f'{0:12.1e} | {atmosphere.density(0).item():.3e}')
  

    # Function also accepts multiple values as a list or NumPy array
    heights: list[float] = [0.1,1,10,100,1e3,1e4,1e5,1e6]

    from typing import cast  # Just to make pyright happy :)
    densities = cast(NDArray[np.float64], atmosphere.density(heights))

    for n, height in enumerate(heights):
        print(f'{height:12.1e} | {densities[n]:.3e}')
