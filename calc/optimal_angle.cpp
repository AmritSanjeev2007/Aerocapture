// The initial pitch or yaw for a desired apoapsis: the C++ version of calc/optimal_angle.py (``Apoapsis``), see the
// "Optimal Angle" section of report.typ.
//
// The apoapsis after the first atmospheric pass is found from the orbital elements at atmospheric exit (conservation
// of energy and angular momentum), and the free angle with the secant method. Only the atmospheric pass is
// integrated, and no states are stored, so each evaluation is a short loop with no allocations. Double precision.

#include "trajectory.hpp"

#include <limits>

using namespace calc;

namespace {

constexpr int MAX_STEP_HALVINGS = 20;  // Like ``Apoapsis._MAX_STEP_HALVINGS``.

// The status codes returned by calc_optimal_angle, mirrored by calc/native.py.
enum Status : int32_t {
    OK = 0,
    GUESSES_NOT_CAPTURED = 1,  // The first guess misses, crashes or escapes (or every second guess tried does).
    FLAT_SECANT = 2,
    LEFT_CAPTURED_RANGE = 3,
    NOT_CONVERGED = 4,
};

struct Problem {
    const CalcPhysics* physics;
    Vec3 initial_position;
    double speed;
    double fixed_angle;
    bool solve_for_pitch;
    double time_step;
    double max_time;
};

// ``Apoapsis.radius_from_state``: the apoapsis distance of the gravity-only orbit through the state, or NaN if the
// orbit isn't closed.
double radius_from_state(double gm, Vec3 position, Vec3 velocity)
{
    const double energy = 0.5 * dot(velocity, velocity) - gm / length(position);
    const double angular_momentum = length(cross(position, velocity));

    if (energy >= 0)
        return std::numeric_limits<double>::quiet_NaN();

    // energy * r_a^2 + GM * r_a - h^2 / 2 = 0. As the energy is negative, the larger root takes the minus sign.
    double discriminant = gm * gm + 2 * energy * angular_momentum * angular_momentum;
    if (discriminant < 0.0)
        discriminant = 0.0;
    return (-gm - std::sqrt(discriminant)) / (2 * energy);
}

// ``Apoapsis.exit_state`` followed by ``radius_from_state``: the apoapsis distance after the first atmospheric pass
// for an initial pitch and yaw, or NaN if it misses the atmosphere, crashes, escapes or is still inside after
// ``max_time``.
double apoapsis_radius(const CalcPhysics& physics, Vec3 initial_position, double speed, double pitch, double yaw,
                       double time_step, double max_time)
{
    Integrator integrator(physics);
    const double radius_squared = integrator.titan_radius() * integrator.titan_radius();
    const double atmosphere_radius_squared = integrator.atmosphere_radius() * integrator.atmosphere_radius();

    State state{initial_position, initial_velocity(speed, pitch, yaw), 0.0};
    bool has_entered = false;

    // The same loop as ``exit_state``, with the distances compared squared to save square roots.
    while (true) {
        const double distance_squared = dot(state.position, state.position);
        if (distance_squared <= radius_squared || state.time > max_time)
            return std::numeric_limits<double>::quiet_NaN();  // Crashed, or never came out.

        if (distance_squared < atmosphere_radius_squared) {
            has_entered = true;
        } else if (has_entered) {
            const double gm = physics.gravitational_constant * physics.titan_mass;
            return radius_from_state(gm, state.position, state.velocity);
        } else if (dot(state.position, state.velocity) > 0) {
            // Moving away from Titan without having entered: the closest approach missed the atmosphere.
            return std::numeric_limits<double>::quiet_NaN();
        }

        state = integrator.step(state, time_step);
    }
}

// ``Apoapsis.f``: the desired minus the achieved apoapsis distance for a value of the free angle (NaN if none).
double f(const Problem& problem, double desired_radius, double angle)
{
    const double pitch = problem.solve_for_pitch ? angle : problem.fixed_angle;
    const double yaw = problem.solve_for_pitch ? problem.fixed_angle : angle;
    return desired_radius - apoapsis_radius(*problem.physics, problem.initial_position, problem.speed, pitch, yaw,
                                            problem.time_step, problem.max_time);
}

} // namespace

// The apoapsis distance (from Titan's centre, in m) after the first atmospheric pass, or NaN if there is none. See
// ``Apoapsis.apoapsis_radius``.
CALC_API double calc_apoapsis_radius(const CalcPhysics* physics, const double* initial_position, double speed,
                                     double pitch, double yaw, double time_step, double max_time)
{
    const Vec3 position{initial_position[0], initial_position[1], initial_position[2]};
    return apoapsis_radius(*physics, position, speed, pitch, yaw, time_step, max_time);
}

// ``Apoapsis.solve``: finds the free angle (the pitch if ``solve_for_pitch``, otherwise the yaw) giving an apoapsis
// ``desired_altitude`` (m) above Titan's surface, with the other angle held at ``fixed_angle`` (rad). The secant
// method starts from the guesses ``angle_0`` and ``angle_1`` (rad) and stops once the apoapsis is within
// ``tolerance`` (m). The angle is written to ``result``. Returns one of the ``Status`` codes.
CALC_API int32_t calc_optimal_angle(const CalcPhysics* physics, double desired_altitude,
                                    const double* initial_position, double speed, double fixed_angle,
                                    int32_t solve_for_pitch, double angle_0, double angle_1, double tolerance,
                                    int32_t max_iterations, double time_step, double max_time, double* result)
{
    const Problem problem{
        physics,
        {initial_position[0], initial_position[1], initial_position[2]},
        speed,
        fixed_angle,
        solve_for_pitch != 0,
        time_step,
        max_time,
    };
    const double desired_radius = physics->titan_radius + desired_altitude;

    double f_0 = f(problem, desired_radius, angle_0);
    if (std::isnan(f_0))
        return GUESSES_NOT_CAPTURED;

    // The range of captured orbits can be narrower than the gap between the guesses, so the second guess is
    // pulled back towards the first until it's captured too, like a step that leaves the range below.
    double f_1 = f(problem, desired_radius, angle_1);
    for (int halvings = 1; std::isnan(f_1); ++halvings) {
        if (halvings > MAX_STEP_HALVINGS)
            return GUESSES_NOT_CAPTURED;
        angle_1 = 0.5 * (angle_0 + angle_1);
        f_1 = f(problem, desired_radius, angle_1);
    }

    for (int32_t i = 0; i < max_iterations; ++i) {
        if (std::fabs(f_1) < tolerance) {
            *result = angle_1;
            return OK;
        }
        if (f_1 == f_0)
            return FLAT_SECANT;

        double angle_2 = angle_1 - f_1 * (angle_1 - angle_0) / (f_1 - f_0);
        double f_2 = f(problem, desired_radius, angle_2);

        // f has no value where the spacecraft misses, crashes or escapes, so step back towards the last guess.
        for (int halvings = 1; std::isnan(f_2); ++halvings) {
            if (halvings > MAX_STEP_HALVINGS)
                return LEFT_CAPTURED_RANGE;
            angle_2 = 0.5 * (angle_1 + angle_2);
            f_2 = f(problem, desired_radius, angle_2);
        }

        angle_0 = angle_1; f_0 = f_1;
        angle_1 = angle_2; f_1 = f_2;
    }

    return NOT_CONVERGED;
}
