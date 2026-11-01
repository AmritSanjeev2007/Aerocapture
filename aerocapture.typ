// ME22011 Engineering Computation, Assignment 1: Aerocapture at Titan.
// Compile with: typst compile aerocapture.typ

#set document(title: "Computational Modelling of Aerocapture at Titan")
#set page(paper: "a4", margin: (x: 2cm, y: 2cm), numbering: "1")
#set text(size: 11pt, lang: "en", region: "gb")
#set par(justify: true)
#set heading(numbering: "1.1")
#set math.equation(numbering: "(1)")
#set figure(gap: 0.6em)
#show figure.caption: set text(size: 9.5pt)
#show heading.where(level: 1): it => block(above: 1.2em, below: 0.7em, it)

#align(center)[
  #text(size: 16pt, weight: "bold")[Computational Modelling of Aerocapture for a Scientific Mission to Titan]
  #v(0.2em)
  ME22011 Engineering Computation, Assignment 1 \
  _[Group members' names and candidate numbers]_ \
  University of Bath, December 2026
]

#block(inset: (x: 1.2em))[
  *Abstract.* A spacecraft approaching Titan at 6.5 km/s is modelled with a point-mass equation of motion including
  Titan's gravity and quadratic drag through a tabulated atmosphere. The equations are integrated with a classical
  fourth-order Runge–Kutta (RK4) scheme, and the apoapsis after the first atmospheric pass is found exactly from the
  energy and angular momentum at atmospheric exit. A secant solver finds the entry angle $beta = 4.884167 degree$
  that gives the required 9,000 km apoapsis. Without a circularisation burn the orbit's periapsis (236.5 km) lies
  inside the atmosphere, and the spacecraft impacts the surface at $(-835.0, 2434.8)$ km after 47,018 s. Only
  entry angles between 4.866° and 4.903° are captured, and the apoapsis changes by about 730 km per 0.001°, so
  the guidance must hold $beta$ very precisely. As extensions, the model is extended to three dimensions, the
  circularising burn (330.2 m/s prograde) is computed, the solver is accelerated in C++, and an interactive 3-D
  visualisation is built.
]

= Introduction

Aerocapture uses a single pass through a planetary atmosphere to remove enough energy to turn a hyperbolic approach
into a bound, elliptical orbit, saving most of the propellant a propulsive orbit insertion would need. Hall et al.
@hall2005 estimate that for Titan this allows a substantially larger scientific payload. The cost is precision: the
spacecraft must enter a narrow corridor, since too shallow an entry leaves it on an escape trajectory and too steep
an entry brings it down.

The task is to find the initial velocity angle $beta$ that, from $(x_0, y_0) = (-12000, 2000)$ km at
$t_0 = 0$ with speed $U_0 = 6.5$ km/s, gives an orbit whose apoapsis is $H = 9000$ km above the surface,
evaluated from the orbital elements immediately after the first atmospheric pass. The trajectory is then continued,
without a burn, to find where the spacecraft hits the surface. The spacecraft has mass $m = 2000$ kg, cross-sectional
area $A = 14 "m"^2$ and drag coefficient $C_d = 1.2$; Titan has radius $R = 2574$ km and mass
$M = 1.3452 times 10^(23)$ kg. We place the start at $x_0 = -12000$ km so that the spacecraft travels in the $+x$
direction; this is a mirror image of the brief's geometry and changes only the sign of $x$. The angle $beta$ is
measured from the $+x$ axis towards $+y$.

= Model

== Assumptions

+ The spacecraft is a point mass of constant mass $m$ (no ablation or fuel use) and constant $C_d$ and $A$, i.e. a
  fixed attitude with no lift.
+ Titan is a rigid, non-rotating sphere with a spherically symmetric gravity field, fixed in an inertial frame. Its
  atmosphere is at rest relative to it, so the airspeed is the spacecraft's inertial velocity (no winds).
+ The density depends only on altitude, by linear interpolation of the supplied table (0–2,200 km), and is zero
  above 2,200 km. The top of the table is taken as the edge of the atmosphere.
+ Saturn, the Sun and other moons are neglected (no third-body forces).
+ Drag follows the quadratic law with a constant $C_d$ for all Mach and Knudsen numbers.

== Free-body diagram and equations of motion

#figure(
  image("report_figures/fbd.png", width: 52%),
  caption: [Free-body diagram of the spacecraft. Only Titan's weight $bold(W)$, towards Titan's centre, and the drag
    $bold(D)$, opposite to the velocity $bold(v)$, act on it.],
) <fig-fbd>

With $bold(r)$ the position from Titan's centre and $bold(v) = dot(bold(r))$, @fig-fbd gives

$ m dot.double(bold(r)) = bold(W) + bold(D) = -(G M m)/(|bold(r)|^2) hat(bold(r))
  - 1/2 rho(|bold(r)| - R) C_d A |dot(bold(r))| dot(bold(r)), $ <eq-newton>

where the drag is written as $|bold(v)| bold(v)$, which equals $|bold(v)|^2 hat(bold(v))$ but stays defined when
$bold(v) = bold(0)$. @eq-newton is second order; introducing the velocity components as extra unknowns
turns it into the four coupled first-order ODEs in $x$ and $y$, with $r = sqrt(x^2 + y^2)$,
$V = sqrt(v_x^2 + v_y^2)$ and $B = C_d A \/ (2 m)$:

$ dot(x) = v_x, quad dot(y) = v_y, quad
  dot(v)_x = -(G M x)/r^3 - B rho(r - R) V v_x, quad
  dot(v)_y = -(G M y)/r^3 - B rho(r - R) V v_y. $ <eq-odes>

The initial conditions are $x(0) = x_0$, $y(0) = y_0$, $v_x (0) = U_0 cos beta$ and $v_y (0) = U_0 sin beta$.
The code solves the same equations in three dimensions (@sec-3d), with $z = v_z = 0$ for the planar problem.

== Atmosphere

The function `Atmosphere.density` interpolates the supplied table linearly with `numpy.interp`. Above the highest
altitude in the table it returns zero rather than repeating the last value, so that the atmosphere has a definite
edge at $R + 2200$ km. The density there is $8.6 times 10^(-15) "kg/m"^3$, which is negligible, so this edge is
where only gravity remains.

= Numerical methods

== Runge–Kutta integration

Writing the state as $bold(r)$ and $bold(s) = dot(bold(r))$, @eq-newton becomes $dot(bold(r)) = g = bold(s)$ and
$dot(bold(s)) = h(bold(s), bold(r))$, the right-hand side of @eq-odes. Each step of size $Delta t$ uses the
classical RK4 scheme @burden2011 on both functions together, with stages

$ k_"1r" = Delta t thin bold(s)_n, quad & k_"1s" = Delta t thin h(bold(s)_n, bold(r)_n), \
  k_"2r" = Delta t (bold(s)_n + k_"1s"/2), quad & k_"2s" = Delta t thin h(bold(s)_n + k_"1s"/2, bold(r)_n + k_"1r"/2), \
  k_"3r" = Delta t (bold(s)_n + k_"2s"/2), quad & k_"3s" = Delta t thin h(bold(s)_n + k_"2s"/2, bold(r)_n + k_"2r"/2), \
  k_"4r" = Delta t (bold(s)_n + k_"3s"), quad & k_"4s" = Delta t thin h(bold(s)_n + k_"3s", bold(r)_n + k_"3r"), $

and the update

$ bold(r)_(n+1) = bold(r)_n + 1/6 (k_"1r" + 2 k_"2r" + 2 k_"3r" + k_"4r"), quad
  bold(s)_(n+1) = bold(s)_n + 1/6 (k_"1s" + 2 k_"2s" + 2 k_"3s" + k_"4s"), quad t_(n+1) = t_n + Delta t. $

The integration stops when $|bold(r)| <= R$; the impact point is then found between the last two steps. A step of
$Delta t = 1$ s is used throughout (see @sec-convergence). All vectors are double precision, since single
precision only resolves positions of order $10^7$ m to about 1 m.

== Apoapsis after the first pass

After atmospheric exit only gravity acts, so the orbit is fixed by the exit position $bold(r)_e$ and velocity
$dot(bold(r))_e$, and the apoapsis $r_a$ follows without integrating further @curtis2014. The exit is the first step after entry
where $|bold(r)| >= R + 2200$ km. The specific energy $epsilon = 1/2 |dot(bold(r))_e|^2 - G M \/ |bold(r)_e|$ and
the specific angular momentum $h = |bold(r)_e times dot(bold(r))_e|$ are conserved, and at the apoapsis the
velocity is perpendicular to the position, so $|dot(bold(r))_a| = h \/ r_a$. Substituting this into the energy
equation and multiplying by $r_a^2$ gives a quadratic in $r_a$:

$ epsilon r_a^2 + G M r_a - 1/2 h^2 = 0
  quad => quad r_a = (-G M - sqrt(G^2 M^2 + 2 epsilon h^2))/(2 epsilon). $ <eq-apoapsis>

The orbit is only closed if $epsilon < 0$; otherwise the spacecraft escapes and there is no apoapsis. For
$epsilon < 0$ the two roots are the periapsis and apoapsis distances, and the larger is the apoapsis.

== Secant method for the entry angle

Let $f(beta) = (R + H) - r_a (beta)$, the difference between the desired and achieved apoapsis distances from
Titan's centre. $f$ is evaluated by integrating from the initial state until the first step after exit and applying
@eq-apoapsis. It is undefined when the spacecraft misses the atmosphere (it starts moving away from Titan before
entering), crashes during the pass, or escapes ($epsilon >= 0$). Starting from two guesses $beta_0$ and $beta_1$,
the secant method @burden2011 iterates

$ beta_(n+1) = beta_n - f(beta_n) (beta_n - beta_(n-1))/(f(beta_n) - f(beta_(n-1))) $

until $|f(beta_n)| < 1$ m. Because the captured range of $beta$ is very narrow (@sec-sensitivity), a step can land
where $f$ is undefined; it is then halved back towards the previous guess until $f$ is defined again. With the
guesses 4.875° and 4.8875° it converges in about 7 ms.

= Results

== Entry angle and trajectory

The solver gives $beta = 4.884167 degree$, for which the apoapsis after the first pass is 8,999.9998 km above the
surface. @fig-trajectory shows the trajectory and @fig-history its altitude, speed and drag deceleration, and
@tab-events summarises the main events.

#figure(
  image("report_figures/trajectory.png", width: 100%),
  caption: [Trajectory for $beta = 4.884167 degree$ with no burn, marking the apoapsis and the surface-impact point.
    The shaded ring is the atmosphere up to 2,200 km altitude.],
) <fig-trajectory>

#figure(
  image("report_figures/history.png", width: 100%),
  caption: [Altitude and speed against time, and the drag deceleration during the first atmospheric pass.],
) <fig-history>

#figure(
  table(
    columns: (auto, auto, auto),
    align: (left, right, left),
    stroke: none,
    table.hline(),
    table.header([*Event*], [*Time (s)*], [*State*]),
    table.hline(stroke: 0.5pt),
    [Atmospheric entry], [1,229], [6.67 km/s],
    [Peak drag deceleration], [1,782], [2.33 $g_0$ (22.9 m/s²)],
    [First periapsis], [1,842], [279.9 km altitude],
    [Atmospheric exit], [4,602], [1.59 km/s, $epsilon = -0.624$ MJ/kg],
    [Apoapsis], [21,746], [9,000.0 km altitude at $(2210, -11361)$ km],
    [Re-entry], [38,893], [],
    [Surface impact], [47,018], [$(-835.0, 2434.8)$ km, 7.7 m/s],
    table.hline(),
  ),
  caption: [Events along the trajectory for $beta = 4.884167 degree$ ($Delta t = 1$ s). Altitudes are above the
    surface and positions are in Titan-centred coordinates.],
) <tab-events>

The first pass removes 21.0 MJ/kg of specific energy (42 GJ in total), taking the spacecraft from a hyperbolic
approach ($epsilon = +20.4$ MJ/kg) to a bound orbit with semi-major axis 7,192 km, eccentricity 0.609 and period
11.2 h. The deceleration is concentrated in a pulse lasting a few minutes around the periapsis, peaking at 2.33
$g_0$.

== Surface impact

Since no burn is performed, the orbit after the first pass keeps its periapsis at 236.5 km altitude, which is deep
inside the atmosphere. On the second pass the spacecraft does not leave the atmosphere again: it slows to its
terminal velocity and reaches the surface at

$ (x, y) = (-835.0, thin 2434.8) "km", quad t = 47018 "s" approx 13.1 "h", $

which is $108.9 degree$ anticlockwise from the $+x$ axis. The impact speed of 7.7 m/s agrees with the terminal
velocity at the surface, $sqrt(2 m g \/ (rho_0 C_d A)) = 7.70$ m/s with $g = G M \/ R^2 = 1.355 "m/s"^2$ and
$rho_0 = 5.435 "kg/m"^3$, which is a useful check on the drag model.

== Verification and convergence <sec-convergence>

The apoapsis found by integrating the full trajectory to the point where the radial velocity changes sign
(8,999.9998 km) agrees with @eq-apoapsis to better than 1 mm, confirming that the analytical apoapsis is
consistent with the integrator. After the circularising burn (@sec-burn), the integrated orbit stays at the same
radius to within 1 mm over three orbits, which shows that RK4 with $Delta t = 1$ s conserves energy very well in the
gravity-only phase. @tab-convergence shows that the solution is independent of the step size below about 5 s; at
10 s the drag pulse is under-resolved and the impact time moves by 46 s.

#figure(
  table(
    columns: 4,
    align: right,
    stroke: none,
    table.hline(),
    table.header([$Delta t$ (s)], [$beta$ (deg)], [Impact time (s)], [Impact $(x, y)$ (km)]),
    table.hline(stroke: 0.5pt),
    [0.1], [4.8841674], [47,018.21], [$(-835.037, 2434.787)$],
    [0.5], [4.8841674], [47,018.21], [$(-835.037, 2434.787)$],
    [1], [4.8841674], [47,018.21], [$(-835.037, 2434.787)$],
    [2], [4.8841680], [47,018.21], [$(-835.036, 2434.788)$],
    [5], [4.8841684], [47,018.21], [$(-835.034, 2434.788)$],
    [10], [4.8841541], [47,064.50], [$(-835.079, 2434.773)$],
    table.hline(),
  ),
  caption: [Entry angle and impact point against the RK4 step size, each with $beta$ re-solved at that step size.],
) <tab-convergence>

= Discussion

== Sensitivity and the capture corridor <sec-sensitivity>

@fig-sensitivity shows the apoapsis after the first pass against $beta$. Only
$4.866 degree lt.tilde beta lt.tilde 4.903 degree$ gives a captured orbit, a corridor of 0.037°. Below it the
spacecraft never leaves the atmosphere on the first pass and crashes; above it, it leaves with $epsilon >= 0$ and
escapes. Across the corridor the first periapsis only changes from the surface to about 284 km altitude. At the
solution the apoapsis changes by about 730 km per 0.001° of $beta$, so to place the apoapsis within 1 km the
guidance system must deliver $beta$ to about $10^(-6)$ degrees. This is far beyond any realistic navigation
accuracy for a single open-loop entry, and in practice it would be relaxed by closed-loop control of lift during
the pass, which this model omits.

#figure(
  image("report_figures/sensitivity.png", width: 55%),
  caption: [Apoapsis altitude after the first pass against the entry angle (log scale). The shaded band is the
    captured range, the dashed line the 9,000 km target and the red line the solution.],
) <fig-sensitivity>

== Impact of the assumptions

The extreme sensitivity also means that small modelling errors change $beta$ by more than the numerical error.
The drag deceleration depends on $rho C_d A \/ m$ and acts mostly within 300 km of the periapsis, so an error
in the density table or in $C_d$ shifts the corridor; since $C_d$ varies with Mach number and rarefaction at high
altitude, a constant value is the largest single simplification. Titan rotates once every 16 days, so the
atmosphere moves at only about 12 m/s at the equator, which is small compared with the 6.7 km/s entry speed but
would shift the impact point. Neglecting Saturn's gravity is reasonable over a 13-hour trajectory but not over many
orbits, and winds in Titan's atmosphere would alter the airspeed. Lift is neglected entirely: a capsule flying at an
angle of attack generates lift, which would both change the trajectory and provide the control needed to widen the
corridor. Finally, the impact location assumes the spacecraft survives the heating of two passes, which is outside
the scope of this work.

= Extensions

== Three-dimensional geometry <sec-3d>

The code works in three dimensions: the initial velocity is given by a speed, a pitch $theta$ (the angle above the
$x z$ plane) and a yaw $mu$ (measured in the $x z$ plane from $+x$),

$ dot(bold(r))_0 = |dot(bold(r))_0| (cos theta cos mu, thin sin theta, thin -cos theta sin mu), $

and the secant solver holds either angle fixed and solves for the other. With $mu = 0$ the problem reduces to the
planar one and $theta = beta = 4.884167 degree$. With $theta = 0$ the solver gives $mu = 10.833173 degree$, and
the resulting trajectory has the same impact time to within 1 ms. This is expected: both forces are central or
opposite to the velocity, so the motion depends only on the angle between $bold(r)_0$ and $dot(bold(r))_0$, which
is the same (about 165.7°) for both solutions. The solutions therefore form a cone of initial directions about
$bold(r)_0$, and the trajectory for any of them is a rotation of the planar one. This symmetry would be broken by
Titan's rotation or by lift.

== Circularising burn <sec-burn>

If an impulsive burn is made at the apoapsis, the speed there can be raised to the circular orbital speed
$sqrt(G M \/ r_a)$, which lifts the periapsis out of the atmosphere. The apoapsis is found by bisecting the length
of the time step during which the radial velocity $bold(r) dot dot(bold(r))$ changes sign, and the burn is the
change from the tangential velocity there to the circular velocity, along the direction of travel. For
$beta = 4.884167 degree$ the burn is 330.2 m/s prograde (from 550.6 to 880.8 m/s), at 9,000.0 km altitude, 21,747 s
after the start. Treated as instantaneous, this is an impulse of $m Delta v = 660,358$ N s. @fig-burn shows the
resulting orbit, which the integrator keeps at a constant radius.

#figure(
  image("report_figures/burn.png", width: 50%),
  caption: [The trajectory with the circularising burn at the apoapsis: the spacecraft stays in a circular orbit at
    9,000 km altitude instead of re-entering.],
) <fig-burn>

== Performance

Each evaluation of $f$ integrates several thousand RK4 steps, and the Python implementation makes several function
calls per step. The integrator, apoapsis calculation, secant solver and burn were therefore also written in C++ and
called from Python with `ctypes`. Compiled without fast-math, the C++ produces bit-for-bit the same states as the
Python reference, which is kept for readability, and it is hundreds of times faster: the full solve for $beta$ takes
about 7 ms and the 47,018-step trajectory to impact about 10 ms. This makes the sensitivity study in
@fig-sensitivity, which needs thousands of solves, practical.

== Interactive visualisation

To make the results easier to explore, a 3-D viewer was built (@fig-gui). Titan, Saturn and its rings, the Sun and
the starfield are ray-traced on the GPU with OpenGL fragment shaders, and the trajectory is drawn on top. A Dear
ImGui panel lets the user change the initial position, speed, pitch and yaw, lock either angle and run the solver
for any apoapsis altitude, and it reports the resulting apoapsis and impact time. The circularising burn is shown as
an arrow at the apoapsis, so the effect of each parameter on the trajectory can be seen immediately.

#figure(
  grid(
    columns: 2,
    gutter: 0.6em,
    image("report_figures/mission.png", width: 100%),
    image("report_figures/trajectory_gui.png", width: 100%),
  ),
  caption: [The interactive viewer: the control panel after solving for the pitch (left), and the trajectory around
    Titan with Saturn behind (right).],
) <fig-gui>

= Conclusions

A point-mass model with gravity and quadratic drag, integrated with RK4 and combined with an exact apoapsis from the
exit state, finds the entry angle $beta = 4.884167 degree$ that gives a 9,000 km apoapsis after one pass. Without a
burn the periapsis of the resulting orbit is inside the atmosphere, and the spacecraft impacts the surface at
$(-835.0, 2434.8)$ km after 47,018 s. The results are converged in the step size and pass several consistency
checks. The capture corridor is only 0.037° wide, which shows that aerocapture needs either extremely precise
navigation or active control during the pass. A 330.2 m/s burn at the apoapsis circularises the orbit and prevents
the impact. Further work should add lift and closed-loop guidance, Mach-dependent drag, Titan's rotation and an
uncertainty analysis to define a practical entry corridor.

#bibliography(bytes("
hall2005:
  type: article
  title: Cost-Benefit Analysis of the Aerocapture Mission Set
  author: ['Hall, J. L.', 'Noca, M. A.', 'Bailey, R. W.']
  date: 2005
  parent:
    type: periodical
    title: Journal of Spacecraft and Rockets
    volume: 42
    issue: 2
burden2011:
  type: book
  title: Numerical Analysis
  author: ['Burden, R. L.', 'Faires, J. D.']
  edition: 9
  publisher: Brooks/Cole
  date: 2011
curtis2014:
  type: book
  title: Orbital Mechanics for Engineering Students
  author: Curtis, H. D.
  edition: 3
  publisher: Butterworth-Heinemann
  date: 2014
"), title: "References", style: "ieee")
