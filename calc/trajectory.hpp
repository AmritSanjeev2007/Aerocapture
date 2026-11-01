// The shared core of calc/trajectory.cpp and calc/optimal_angle.cpp: the physics of calc/trajectory.py
// (``Trajectory._acceleration`` and ``Trajectory._runge_kutta``) in double precision.
//
// Everything is header-only and inline so the compiler can inline the whole Runge-Kutta step into the loops that
// call it. Units: SI (m, m/s, s, rad) in the calculations' frame, like calc/*.

#pragma once

#include <cmath>
#include <cstdint>

#if defined(_WIN32)
    #define CALC_API extern "C" __declspec(dllexport)
#else
    #define CALC_API extern "C" __attribute__((visibility("default")))
#endif

namespace calc {

struct Vec3 {
    double x, y, z;
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator*(double s, Vec3 v) { return {s * v.x, s * v.y, s * v.z}; }
inline double dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline double length(Vec3 v) { return std::sqrt(dot(v, v)); }
inline Vec3 cross(Vec3 a, Vec3 b) { return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x}; }

} // namespace calc

// The constants of the physics, filled in by calc/native.py from calc/constants.py (so they're only defined once).
// Mirrored by ``calc.native._Physics``: keep the two in the same order.
struct CalcPhysics {
    double gravitational_constant;  // G, in m^3 kg^-1 s^-2
    double titan_mass;              // kg
    double titan_radius;            // m
    double spacecraft_area;         // m^2
    double drag_coefficient;
    double spacecraft_mass;         // kg
    const double* densities;        // The atmosphere's profile: (altitude in m, density in kg/m^3) pairs, sorted
    int64_t density_count;          // The number of pairs
};

namespace calc {

// The atmosphere's density, by linear interpolation of the table like numpy.interp (with ``right=0``).
//
// The altitude barely changes from one evaluation to the next, so instead of a binary search every time, the
// bracket of the last lookup is kept and walked from: almost always it's still right, or one row away.
class Atmosphere {
public:
    explicit Atmosphere(const CalcPhysics& physics)
        : table_(physics.densities), count_(physics.density_count), low_(0) {}

    double top() const { return table_[2 * (count_ - 1)]; }

    double density(double altitude) {
        const double* t = table_;
        const int64_t last = count_ - 1;

        if (altitude > t[2 * last])
            return 0.0;
        if (altitude == t[2 * last])
            return t[2 * last + 1];
        if (altitude <= t[0])
            return t[1];  // numpy.interp's ``left`` default is the first value.

        // Here t[0] < altitude < t[last], so a bracket t[low] <= altitude < t[low + 1] exists.
        int64_t low = low_;
        while (t[2 * low] > altitude) --low;
        while (t[2 * (low + 1)] <= altitude) ++low;
        low_ = low;

        // The same formula (and order of operations) as numpy.interp.
        const double x0 = t[2 * low], y0 = t[2 * low + 1];
        const double x1 = t[2 * low + 2], y1 = t[2 * low + 3];
        const double slope = (y1 - y0) / (x1 - x0);
        return slope * (altitude - x0) + y0;
    }

private:
    const double* table_;
    int64_t count_;
    int64_t low_;
};

// The state of the spacecraft at one time step, like ``RungeKuttaRecord``.
struct State {
    Vec3 position;
    Vec3 velocity;
    double time;
};

// Integrates the equations of motion, like ``Trajectory`` (gravity + drag, classical 4th-order Runge-Kutta).
class Integrator {
public:
    explicit Integrator(const CalcPhysics& physics)
        : atmosphere_(physics),
          gm_(-physics.gravitational_constant * physics.titan_mass),
          radius_(physics.titan_radius),
          area_(physics.spacecraft_area),
          drag_coefficient_(physics.drag_coefficient),
          mass_(physics.spacecraft_mass) {}

    double titan_radius() const { return radius_; }
    double atmosphere_radius() const { return radius_ + atmosphere_.top(); }

    // ``Trajectory._acceleration``, with the operations in the same order as the Python.
    Vec3 acceleration(Vec3 position, Vec3 velocity) {
        const double r = length(position);

        // -GM/r^2 * normalize(position), where glm.normalize multiplies by 1 / |position|.
        const Vec3 gravity = (gm_ / (r * r)) * ((1.0 / r) * position);

        const double speed = length(velocity);
        const double air_density = atmosphere_.density(r - radius_);
        const double drag_factor = 0.5 * air_density * area_ * drag_coefficient_ / mass_;

        return gravity + ((-drag_factor * speed) * velocity);
    }

    // ``Trajectory._runge_kutta``: one step of ``dt``.
    State step(const State& s, double dt) {
        const Vec3 p = s.position, v = s.velocity;

        const Vec3 k1p = dt * v;
        const Vec3 k1v = dt * acceleration(p, v);

        const Vec3 k2p = dt * (v + 0.5 * k1v);
        const Vec3 k2v = dt * acceleration(p + 0.5 * k1p, v + 0.5 * k1v);

        const Vec3 k3p = dt * (v + 0.5 * k2v);
        const Vec3 k3v = dt * acceleration(p + 0.5 * k2p, v + 0.5 * k2v);

        const Vec3 k4p = dt * (v + k3v);
        const Vec3 k4v = dt * acceleration(p + k3p, v + k3v);

        constexpr double sixth = 1.0 / 6;
        return {
            p + sixth * (((k1p + 2.0 * k2p) + 2.0 * k3p) + k4p),
            v + sixth * (((k1v + 2.0 * k2v) + 2.0 * k3v) + k4v),
            s.time + dt,
        };
    }

private:
    Atmosphere atmosphere_;
    double gm_;
    double radius_;
    double area_;
    double drag_coefficient_;
    double mass_;
};

// The initial velocity for a speed, pitch and yaw, like ``Trajectory.__init__``.
inline Vec3 initial_velocity(double speed, double pitch, double yaw) {
    return {
        speed * std::cos(pitch) * std::cos(yaw),
        speed * std::sin(pitch),
        speed * std::cos(pitch) * -std::sin(yaw),
    };
}

} // namespace calc
