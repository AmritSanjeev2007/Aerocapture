# Aerocapture
Python simulation of aerocapture at Titan. Solves the 2-D equations of motion with a Runge-Kutta integrator and an atmospheric density model, uses the secant method to find the entry angle β that gives a 9,000 km apoapsis after one atmospheric pass, then follows the decaying orbit to find where the spacecraft impacts the surface.

The scene (Titan, Saturn and its rings, the Sun and the stars) is shown in a 3D window that is ray-traced on the GPU with OpenGL fragment shaders.

## Requirements

+ Python 3.15 (other recent versions should work too).
+ A graphics card and driver that support OpenGL 3.3.
+ [Git LFS](https://git-lfs.com), since the textures in `assets/` are stored with it.
+ About 1 GB of free video memory for the textures.

## Setup

1. Clone the repository and download the textures:

   ```bash
   git lfs install
   git clone https://github.com/AmritSanjeev2007/Aerocapture.git
   cd Aerocapture
   git lfs pull
   ```

   If `assets/starmap.exr` is only a few hundred bytes, the LFS files haven't been downloaded yet. Run `git lfs pull` again.

2. Create a virtual environment and install the dependencies.

   Windows (PowerShell):

   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

   macOS / Linux:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

   Keep `opencv-python-headless` below version 5 (as pinned in `requirements.txt`). OpenCV 5's wheels can't read the OpenEXR starmap.

## Running

From the root of the repository, with the virtual environment activated:

```bash
python main.py
```

A loading screen is shown for a few seconds while the textures are decoded, then the scene appears.

### Controls

The camera uses the same controls as Blender's viewport:

| Input                         | Action                          |
| ----------------------------- | ------------------------------- |
| Middle mouse drag             | Orbit around Titan              |
| Shift + middle mouse drag     | Pan                             |
| Ctrl + middle mouse drag      | Zoom                            |
| Scroll wheel                  | Zoom                            |
| Ctrl + scroll / Shift + scroll | Pan horizontally / vertically  |
| Home or Numpad `.`            | Recentre the view on Titan      |
| Escape                        | Quit                            |

## Project layout

+ `main.py`: the entry point.
+ `display/`: the 3D renderer.
  + `renderer.py`: the window, OpenGL context and render loop.
  + `scene.py`: draws Titan, Saturn, the Sun and the starfield.
  + `camera.py` and `control.py`: the orbiting camera and its mouse and keyboard controls.
  + `loading.py`, `textures.py` and `text.py`: the loading screen, texture loading and text rendering.
  + `constants.py`: file paths, window and camera settings, and the sizes of the bodies.
+ `shaders/`: the GLSL shaders.
+ `assets/`: the textures and their citations.
+ `titan_height_density.csv`: the atmospheric density model of Titan.

References:

Check ``assets/CITATIONS`` for more information.

+ *"Titan Enhanced Color Map (11K)"* by Askaniy Anpilogov
+ *"Saturn 2011 Texture Map"* by Askaniy Anpilogov
+ *"Deep Star Maps 2020"* by Ernie Wright/NASA
