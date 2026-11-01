// The burn at the apoapsis which turns the orbit after the atmospheric pass into a circular one: the C++ version of
// calc/circular_burn.py (``CircularBurn``).
//
// The trajectory is integrated through the first atmospheric pass and on until the spacecraft stops climbing, the
// apoapsis is pinned down by bisecting the last step, and the burn is the change of velocity to the circular orbit's
// there. The burn is impulsive (instantaneous). Double precision, no allocations.

#include "trajectory.hpp"

using namespace calc;

namespace {

// The status codes returned by calc_circular_burn, mirrored by calc/native.py.
enum Status : int32_t {
    OK = 0,
    NO_APOAPSIS = 1,  // It misses the atmosphere, crashes, escapes, or doesn't reach the apoapsis by ``max_time``.
};

} // namespace

// Finds the first apoapsis after the atmospheric pass of the trajectory from the initial state (integrated every
// ``time_step`` s, like calc_trajectory, for at most ``max_time`` s) and the burn which circularises the orbit there.
//
// ``apoapsis`` (7 doubles) is set to the state at the apoapsis just before the burn: the position (m), the velocity
// (m/s) and the time (s). ``delta_v`` (3 doubles) is set to the change of velocity (m/s), so the velocity after the
// burn is their sum. Returns one of the ``Status`` codes.
CALC_API int32_t calc_circular_burn(const CalcPhysics* physics, const double* initial_position,
                                    const double* initial_velocity, double time_step, double max_time,
                                    double* apoapsis, double* delta_v)
{
    Integrator integrator(*physics);
    const double gm = physics->gravitational_constant * physics->titan_mass;
    const double radius_squared = integrator.titan_radius() * integrator.titan_radius();
    const double atmosphere_radius_squared = integrator.atmosphere_radius() * integrator.atmosphere_radius();

    State state{
        {initial_position[0], initial_position[1], initial_position[2]},
        {initial_velocity[0], initial_velocity[1], initial_velocity[2]},
        0.0,
    };
    bool has_entered = false, has_exited = false;

    // Like ``exit_state`` in calc/optimal_angle.cpp, then on until the distance from Titan stops growing.
    while (true) {
        const double distance_squared = dot(state.position, state.position);
        if (distance_squared <= radius_squared || state.time > max_time)
            return NO_APOAPSIS;  // Crashed, or took too long.

        const double radial = dot(state.position, state.velocity);  // > 0 while climbing

        if (distance_squared < atmosphere_radius_squared) {
            has_entered = true;
        } else if (has_entered && !has_exited) {
            // Just out of the atmosphere: from here only gravity acts, so a positive energy means it escapes.
            has_exited = true;
            if (0.5 * dot(state.velocity, state.velocity) - gm / std::sqrt(distance_squared) >= 0)
                return NO_APOAPSIS;
        } else if (!has_entered && radial > 0) {
            return NO_APOAPSIS;  // Moving away from Titan without having entered: it missed the atmosphere.
        }

        const State next = integrator.step(state, time_step);

        if (has_exited && radial > 0 && dot(next.position, next.velocity) <= 0) {
            // The apoapsis is during this step: bisect its length for where the radial velocity is 0.
            State at_apoapsis = next;  // Always the latest state found past the apoapsis.
            double low = 0.0, high = time_step;
            for (int i = 0; i < 64 && high - low > 0.0; ++i) {
                const double middle = 0.5 * (low + high);
                const State trial = integrator.step(state, middle);
                if (dot(trial.position, trial.velocity) > 0) {
                    low = middle;
                } else {
                    high = middle;
                    at_apoapsis = trial;
                }
            }
            state = at_apoapsis;
            break;
        }

        state = next;
    }

    // The circular orbit's velocity is perpendicular to the position, in the plane of the orbit and in the direction
    // of travel: the velocity without its (tiny) radial part, scaled to sqrt(GM / r).
    const Vec3 position = state.position, velocity = state.velocity;
    const double r = length(position);
    const Vec3 radial_direction = (1.0 / r) * position;
    const Vec3 tangential = velocity + (-dot(radial_direction, velocity)) * radial_direction;
    const Vec3 circular_velocity = (std::sqrt(gm / r) / length(tangential)) * tangential;
    const Vec3 change = circular_velocity + (-1.0) * velocity;

    apoapsis[0] = position.x; apoapsis[1] = position.y; apoapsis[2] = position.z;
    apoapsis[3] = velocity.x; apoapsis[4] = velocity.y; apoapsis[5] = velocity.z;
    apoapsis[6] = state.time;
    delta_v[0] = change.x; delta_v[1] = change.y; delta_v[2] = change.z;
    return OK;
}
