# Aerocapture
Python simulation of aerocapture at Titan. Solves the 2-D equations of motion with a Runge-Kutta integrator and an atmospheric density model, uses the secant method to find the entry angle β that gives a 9,000 km apoapsis after one atmospheric pass, then follows the decaying orbit to find where the spacecraft impacts the surface.

The scene (Titan, Saturn and its rings, the Sun and the stars) is shown in a 3D window that is ray-traced on the GPU with OpenGL fragment shaders.

## Requirements

+ Python 3.15 (other recent versions should work too).
+ A graphics card and driver that support OpenGL 3.3, which almost all made since 2010 do.
+ A C++17 compiler, for the trajectory calculations in `calc/*.cpp`: on Windows, Visual Studio's "Desktop development with C++" (or g++ from MSYS2); on macOS, Xcode's command line tools; on Linux, g++ or clang.
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

### GUI

The GUI is drawn with [Dear ImGui](https://github.com/ocornut/imgui), through [imgui-bundle](https://github.com/pthom/imgui_bundle). A **Display** panel in the top right toggles Saturn, the starfield, the axes gizmo and the citations, and changes the brightness of the stars. The gizmo in the bottom right corner shows the directions of the world's x (red), y (green, north) and z (blue) axes, like Blender's. Mouse input over a panel goes to the panel instead of the camera.

New windows and widgets are written in the `gui` callback of `Renderer.render`, which runs every frame:

```python
from imgui_bundle import imgui

def gui(renderer):
    imgui.begin("Trajectory")
    imgui.text(f"Camera distance: {renderer.camera.distance:,.0f} km")
    _, renderer.scene.show_saturn = imgui.checkbox("Show Saturn", renderer.scene.show_saturn)
    imgui.end()

renderer.render(gui=gui)
```

The [ImGui manual](https://pthom.github.io/imgui_manual_online/manual/imgui_manual.html) shows every widget along with its code.

To make the whole GUI bigger or smaller (e.g. on a high-resolution screen), change `GUI_SCALE` in `display/constants.py`.

### Trajectory

`Trajectory.calculate_trajectory` calculates the spacecraft's trajectory from its initial state and returns it as NumPy arrays (positions, velocities and times, plus whether it impacted). `Renderer.set_trajectory` draws them. The line is coloured by time, from blue to red, and Titan and Saturn hide the parts behind them:

```python
trajectory = Trajectory(initial_position, speed, pitch, yaw)
states = trajectory.calculate_trajectory(time_step=1.0, max_time=86_400)
renderer.set_trajectory(states)
renderer.render()
```

The calculation stops when the spacecraft hits Titan or `max_time` is reached. If it hit Titan, `states.impact_position` (m) and `states.impact_time` (s) say where and when it reached the surface, found by bisecting the last time step. Afterwards, `renderer.trajectory.impacted` and `renderer.trajectory.time_range` describe the outcome.

### C++ calculations

The trajectory (`calc/trajectory.cpp`) and the optimal angle's secant method (`calc/optimal_angle.cpp`) run in C++, in double precision, and share the physics in `calc/trajectory.hpp`. `calc/native.py` loads them with `ctypes` and returns NumPy arrays. They give the same results, bit for bit, as the Python in `calc/trajectory.py` and `calc/optimal_angle.py` (kept as the readable reference), but about 80 times faster for the optimization and hundreds of times faster for a whole trajectory.

The library (`calc/native.dll`, or `calc/native.so` elsewhere) is compiled automatically the first time it's needed, and again whenever a `.cpp` or `.hpp` file changes. To compile it by hand:

```bash
python -m calc.native
```

To check that the C++ and the Python agree (both should find a pitch of 4.884167° and a yaw of 10.833173°):

```bash
python -m calc.optimal_angle
```

To animate the spacecraft's progress, set `renderer.trajectory_shown_until` (s) to the current time. Only the part of the line up to that time is drawn.

## Building a standalone .exe

The app can be packaged into a single Windows executable, with the textures and shaders bundled in:

```powershell
pip install pyinstaller
pyinstaller Aerocapture.spec
```

The result is `dist/Aerocapture.exe` (about 230 MB). It runs on any Windows PC with OpenGL 3.3, without Python installed. Build it after running the app once (or `python -m calc.native`), so the compiled `calc/native.dll` exists to be bundled. It takes a few extra seconds to start, as the bundled files are unpacked first. To see printed messages and errors in a terminal, set `console=True` in `Aerocapture.spec`.

## Project layout

+ `main.py`: the entry point.
+ `display/`: the 3D renderer.
  + `renderer.py`: the window, OpenGL context and render loop.
  + `scene.py`: draws Titan, Saturn, the Sun and the starfield.
  + `camera.py` and `control.py`: the orbiting camera and its mouse and keyboard controls.
  + `gui.py`: the ImGui setup, and the forwarding of mouse and keyboard input to it.
  + `loading.py` and `textures.py`: the loading screen and texture loading.
  + `constants.py`: file paths, window and camera settings, and the sizes of the bodies.
+ `calc/`: the calculations.
  + `trajectory.py` / `trajectory.cpp`: the equations of motion and the Runge-Kutta integration (the shared C++ physics is in `trajectory.hpp`).
  + `optimal_angle.py` / `optimal_angle.cpp`: the secant method for the pitch or yaw giving the desired apoapsis.
  + `native.py`: compiles and loads the C++, and wraps it for Python.
  + `atmosphere.py` and `titan_height_density.csv`: the atmospheric density model of Titan.
  + `constants.py`: the physical constants.
+ `shaders/`: the GLSL shaders.
+ `assets/`: the textures and their citations.

References:

Check ``assets/CITATIONS`` for more information.

+ *"Titan Enhanced Color Map (11K)"* by Askaniy Anpilogov
+ *"Saturn 2011 Texture Map"* by Askaniy Anpilogov
+ *"Deep Star Maps 2020"* by Ernie Wright/NASA
