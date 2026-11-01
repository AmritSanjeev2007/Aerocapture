// The spacecraft's whole trajectory, for drawing: the C++ version of calc/trajectory.py
// (``Trajectory.calculate_discrete_trajectory``), which replaces the old compute shader shaders/trajectory.comp.
//
// The integration is sequential (each step needs the previous one), so it's one tight loop with no allocations,
// writing straight into arrays owned by the caller (NumPy arrays, see calc/native.py). Double precision throughout.

#include "trajectory.hpp"

using namespace calc;

// Integrates from the initial state every ``time_step`` (s), recording every state from t = 0, while the spacecraft
// is above Titan's surface and the time is at most ``max_time`` (s), like calc/trajectory.py's stop predicate
// ``|position| > R and time <= max_time``. At most ``max_points`` states are recorded.
//
// The states go into ``positions`` and ``velocities`` (``max_points`` x 3 each, row-major, either can be null) and
// ``times`` (``max_points``, can be null). ``impacted`` (can be null) is set to 1 if it stopped by hitting Titan,
// and then ``impact`` (4 doubles, can be null) is set to the position (m) and time (s) at which it reached the
// surface. Returns the number of states recorded.
CALC_API int64_t calc_trajectory(const CalcPhysics* physics, const double* initial_position,
                                 const double* initial_velocity, double time_step, double max_time,
                                 int64_t max_points, double* positions, double* velocities, double* times,
                                 int32_t* impacted, double* impact)
{
    Integrator integrator(*physics);
    const double radius = integrator.titan_radius();
    const double radius_squared = radius * radius;

    State state{
        {initial_position[0], initial_position[1], initial_position[2]},
        {initial_velocity[0], initial_velocity[1], initial_velocity[2]},
        0.0,
    };

    State previous = state;  // The last state recorded (above the surface).
    int64_t count = 0;
    bool hit = false;

    while (count < max_points) {
        // |position| > R, compared squared to save a square root per step.
        if (dot(state.position, state.position) <= radius_squared) {
            hit = true;
            break;
        }
        if (state.time > max_time)
            break;

        if (positions) {
            double* p = positions + 3 * count;
            p[0] = state.position.x; p[1] = state.position.y; p[2] = state.position.z;
        }
        if (velocities) {
            double* v = velocities + 3 * count;
            v[0] = state.velocity.x; v[1] = state.velocity.y; v[2] = state.velocity.z;
        }
        if (times)
            times[count] = state.time;
        ++count;

        previous = state;
        state = integrator.step(state, time_step);
    }

    if (impacted)
        *impacted = hit ? 1 : 0;

    if (hit && impact) {
        // The surface was crossed during the last step, so find where by bisecting the length of a single step from
        // the last state above it. (If it started inside, there was no step: the impact is the initial state.)
        State at_surface = state;
        if (count > 0) {
            double low = 0.0, high = time_step;  // ``at_surface`` is always the latest state found inside.
            for (int i = 0; i < 64 && high - low > 0.0; ++i) {
                const double middle = 0.5 * (low + high);
                const State trial = integrator.step(previous, middle);
                if (dot(trial.position, trial.position) > radius_squared) {
                    low = middle;
                } else {
                    high = middle;
                    at_surface = trial;
                }
            }
        }
        impact[0] = at_surface.position.x;
        impact[1] = at_surface.position.y;
        impact[2] = at_surface.position.z;
        impact[3] = at_surface.time;
    }

    return count;
}
