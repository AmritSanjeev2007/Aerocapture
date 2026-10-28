#version 330 core

out vec4 FragColor;

uniform vec2 uResolution;
uniform mat4 uInvViewRotProj;   // inverse(projection * rotation part of view): NDC -> world ray direction
uniform mat4 uViewProj;
uniform vec3 uCameraPos;
uniform vec3 uSunDir;           // unit vector pointing towards the Sun

uniform vec3 uTitanCenter;
uniform vec3 uTitanRadii;
uniform mat3 uTitanRotation;    // body frame -> world frame
uniform float uHazeScaleHeight;
uniform sampler2D uTitanTexture;

uniform bool uShowSaturn;
uniform vec3 uSaturnCenter;
uniform vec3 uSaturnRadii;
uniform mat3 uSaturnRotation;
uniform sampler2D uSaturnTexture;
uniform float uSaturnHazeScaleHeight;
uniform float uRingHazeThickness;   // km, the (artistic) scale height of the dust around the ring plane

uniform bool uShowSky;
uniform mat3 uSkyRotation;      // world frame -> J2000 equatorial frame
uniform float uSkyExposure;
uniform sampler2D uSkyTexture;

uniform float uSunAngularRadius;    // radians, as seen from Saturn's system
uniform float uPixelAngle;          // radians covered by one pixel, so the Sun never gets smaller than a pixel

const float PI = 3.14159265358979323846;
const float NO_HIT = 1e30;
const float GAMMA = 2.2;
const float AMBIENT = 0.006;

const int BODY_TITAN = 0;
const int BODY_SATURN = 1;
const int BODY_RINGS = 2;

// Ring boundaries in km from Saturn's centre.
const float C_RING_INNER = 74658.0;
const float B_RING_INNER = 92000.0;
const float B_RING_OUTER = 117580.0;
const float A_RING_INNER = 122170.0;
const float A_RING_OUTER = 136775.0;
const float ENCKE_GAP = 133589.0;

vec3 toLinear(vec3 c) { return pow(c, vec3(GAMMA)); }
vec3 toSrgb(vec3 c) { return pow(clamp(c, 0.0, 1.0), vec3(1.0 / GAMMA)); }

// Samples an equirectangular map. The longitude wraps around at u = 0 / 1, which makes the screen-space
// derivatives jump there and would pick the smallest mip level along the seam, so the jump is removed first.
vec3 sampleEquirect(sampler2D tex, vec2 uv)
{
    vec2 dx = dFdx(uv);
    vec2 dy = dFdy(uv);
    dx.x -= round(dx.x);
    dy.x -= round(dy.x);
    return textureGrad(tex, uv, dx, dy).rgb;
}

// Converts a direction in a body's frame (y = north, +z = longitude 0) to map coordinates.
vec2 bodyMapUv(vec3 dir)
{
    dir = normalize(dir);
    float longitude = atan(dir.x, dir.z);
    float latitude = asin(clamp(dir.y, -1.0, 1.0));
    return vec2(longitude / (2.0 * PI) + 0.5, latitude / PI + 0.5);
}

// Converts a world direction to starmap coordinates (right ascension 0h in the middle, increasing to the left).
vec2 skyMapUv(vec3 dir)
{
    vec3 eq = normalize(uSkyRotation * dir);
    float rightAscension = atan(eq.y, eq.x);
    float declination = asin(clamp(eq.z, -1.0, 1.0));
    return vec2(0.5 - rightAscension / (2.0 * PI), declination / PI + 0.5);
}

// Returns the distance along the ray to the nearest intersection with the ellipsoid, or NO_HIT. `localHit` is
// set to the hit point scaled onto the unit sphere in the body's frame (which is also the map direction).
float intersectEllipsoid(vec3 ro, vec3 rd, vec3 center, vec3 radii, mat3 rotation, out vec3 localHit)
{
    mat3 toBody = transpose(rotation);
    vec3 o = (toBody * (ro - center)) / radii;
    vec3 d = (toBody * rd) / radii;

    // Always give a usable direction, the map is sampled even when nothing is hit.
    localHit = o;

    float a = dot(d, d);
    float b = dot(o, d);
    float c = dot(o, o) - 1.0;
    float discriminant = b * b - a * c;

    if (discriminant < 0.0)
        return NO_HIT;

    float s = sqrt(discriminant);
    float t = (-b - s) / a;
    if (t < 0.0)
        t = (-b + s) / a;  // The ray starts inside the body.
    if (t < 0.0)
        return NO_HIT;

    localHit = o + t * d;
    return t;
}

// World space normal of an ellipsoid from a `localHit` returned by intersectEllipsoid.
vec3 ellipsoidNormal(vec3 localHit, vec3 radii, mat3 rotation)
{
    return normalize(rotation * (localHit / radii));
}

bool occludedBy(vec3 ro, vec3 rd, vec3 center, vec3 radii, mat3 rotation)
{
    vec3 unused;
    return intersectEllipsoid(ro, rd, center, radii, rotation, unused) < NO_HIT;
}

// A rough opacity profile of the main rings, with a bit of procedural fine structure.
float ringOpacity(float r)
{
    if (r < C_RING_INNER || r > A_RING_OUTER)
        return 0.0;

    float opacity;
    if (r < B_RING_INNER)
        opacity = 0.12;                                                     // C ring
    else if (r < B_RING_OUTER)
        opacity = mix(0.55, 0.95, smoothstep(B_RING_INNER, B_RING_INNER + 8000.0, r));  // B ring
    else if (r < A_RING_INNER)
        opacity = 0.04;                                                     // Cassini division
    else
        opacity = 0.6;                                                      // A ring

    if (abs(r - ENCKE_GAP) < 160.0)
        opacity = 0.02;

    opacity *= 0.8 + 0.2 * sin(r * 0.0021) * sin(r * 0.00073 + 1.3);
    return clamp(opacity, 0.0, 1.0);
}

vec3 ringAlbedo(float r)
{
    vec3 dusty = vec3(0.45, 0.40, 0.34);
    vec3 icy = vec3(0.85, 0.78, 0.66);
    return mix(dusty, icy, smoothstep(C_RING_INNER, B_RING_INNER + 10000.0, r));
}

// Intersects the ray with Saturn's ring plane. Returns NO_HIT outside the rings.
float intersectRings(vec3 ro, vec3 rd, out float radius)
{
    vec3 normal = uSaturnRotation[1];
    float denom = dot(rd, normal);
    radius = 0.0;

    if (abs(denom) < 1e-8)
        return NO_HIT;

    float t = dot(uSaturnCenter - ro, normal) / denom;
    if (t <= 0.0)
        return NO_HIT;

    radius = length(ro + rd * t - uSaturnCenter);
    if (radius < C_RING_INNER || radius > A_RING_OUTER)
        return NO_HIT;

    return t;
}

// How much sunlight reaches the point `p` (0 = fully shadowed). `self` is skipped to avoid self-shadowing.
float sunVisibility(vec3 p, int self)
{
    if (self != BODY_TITAN && occludedBy(p, uSunDir, uTitanCenter, uTitanRadii, uTitanRotation))
        return 0.0;

    if (!uShowSaturn)
        return 1.0;

    if (self != BODY_SATURN && occludedBy(p, uSunDir, uSaturnCenter, uSaturnRadii, uSaturnRotation))
        return 0.0;

    float radius;
    if (self != BODY_RINGS && intersectRings(p, uSunDir, radius) < NO_HIT)
        return 1.0 - ringOpacity(radius);

    return 1.0;
}

vec3 shadeSurface(vec3 albedo, vec3 normal, vec3 p, int self)
{
    float diffuse = max(dot(normal, uSunDir), 0.0);
    float visibility = diffuse > 0.0 ? sunVisibility(p, self) : 0.0;
    return albedo * (AMBIENT + diffuse * visibility);
}

// The glow of a body's hazy upper atmosphere, strongest at the limb and when looking towards the Sun. `tHit` and
// `normal` describe where the ray hit the body (if it did) and nothing behind `tLimit` is visible.
vec3 limbHaze(vec3 ro, vec3 rd, float tHit, vec3 normal, float tLimit,
              vec3 center, vec3 radii, mat3 rotation, float scaleHeight, vec3 hazeColor)
{
    float strength;
    vec3 up;

    if (tHit < NO_HIT) {
        if (tHit > tLimit)
            return vec3(0.0);

        up = normal;
        strength = pow(1.0 - max(dot(normal, -rd), 0.0), 4.0);
    } else {
        // The closest approach is found in the body's frame scaled onto the unit sphere, so it works for Saturn's
        // oblate shape too. The ray parameter is the same in both frames.
        mat3 toBody = transpose(rotation);
        vec3 o = (toBody * (ro - center)) / radii;
        vec3 d = (toBody * rd) / radii;

        float tClosest = -dot(o, d) / dot(d, d);
        if (tClosest < 0.0 || tClosest > tLimit)
            return vec3(0.0);

        vec3 closest = o + d * tClosest;
        float altitude = (length(closest) - 1.0) * radii.x;
        up = normalize(rotation * (closest / radii));
        // Faded out completely, otherwise the long faint tail shows up against a black sky.
        strength = exp(-altitude / scaleHeight) * (1.0 - smoothstep(3.0, 6.0, altitude / scaleHeight));
    }

    float illumination = smoothstep(-0.25, 0.35, dot(up, uSunDir));
    float forwardScattering = 0.6 + 2.0 * pow(max(dot(rd, uSunDir), 0.0), 6.0);

    return hazeColor * strength * illumination * forwardScattering;
}

float hash(vec2 p)
{
    return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453);
}

// The dust around Saturn's ring plane, as (scattered light, opacity). Real rings are only tens of metres thick and
// vanish when seen edge-on (which is always the case from Titan), so they're given a soft, artistic thickness:
// a gaussian slab around the ring plane that is ray-marched up to `tLimit`.
vec4 ringHaze(vec3 ro, vec3 rd, float tLimit)
{
    const int STEPS = 32;

    vec3 normal = uSaturnRotation[1];
    float thickness = uRingHazeThickness;
    float slab = 3.0 * thickness;
    float height = dot(ro - uSaturnCenter, normal);
    float climb = dot(rd, normal);

    // Clip the ray to the slab...
    float t0 = 0.0;
    float t1 = tLimit;
    if (abs(climb) > 1e-6) {
        float ta = (-slab - height) / climb;
        float tb = (slab - height) / climb;
        t0 = max(t0, min(ta, tb));
        t1 = min(t1, max(ta, tb));
    } else if (abs(height) > slab) {
        return vec4(0.0);
    }

    // ...and to the sphere enclosing the rings.
    vec3 oc = ro - uSaturnCenter;
    float b = dot(oc, rd);
    float discriminant = b * b - (dot(oc, oc) - A_RING_OUTER * A_RING_OUTER);
    if (discriminant < 0.0)
        return vec4(0.0);

    float s = sqrt(discriminant);
    t0 = max(t0, -b - s);
    t1 = min(t1, -b + s);
    if (t1 <= t0)
        return vec4(0.0);

    // Chosen so that looking straight through the rings only adds a faint glow (optical depth of 0.12 x opacity).
    float density = 0.12 / (thickness * sqrt(PI));
    float dt = (t1 - t0) / float(STEPS);
    float jitter = hash(gl_FragCoord.xy);  // Hides the banding of the fixed step count.

    vec3 light = vec3(0.0);
    float transmittance = 1.0;

    for (int i = 0; i < STEPS; i++) {
        vec3 p = ro + rd * (t0 + (float(i) + jitter) * dt);
        vec3 offset = p - uSaturnCenter;
        float h = dot(offset, normal);
        float r = length(offset - normal * h);

        float extinction = density * ringOpacity(r) * exp(-(h * h) / (thickness * thickness));
        float alpha = 1.0 - exp(-extinction * dt);
        if (alpha <= 0.0)
            continue;

        vec3 scattered = ringAlbedo(r) * (AMBIENT + 0.6 * sunVisibility(p, BODY_RINGS));
        light += transmittance * alpha * scattered;
        transmittance *= 1.0 - alpha;
    }

    return vec4(light, 1.0 - transmittance);
}

// The Sun's disk plus the glare around it. From Saturn the disk is smaller than a pixel, so it's drawn at least a
// few pixels wide, and the glare (a bright halo plus a wide faint one) makes it read as far brighter than a star.
vec3 sunLight(vec3 rd)
{
    float angle = 2.0 * asin(clamp(length(rd - uSunDir) * 0.5, 0.0, 1.0));  // Accurate for tiny angles.
    float radius = max(uSunAngularRadius, 3.0 * uPixelAngle);

    float disk = 1.0 - smoothstep(radius - uPixelAngle, radius + uPixelAngle, angle);
    float glare = 0.5 * exp(-angle / 0.01) + 0.12 * exp(-angle / 0.06);

    return vec3(1.0, 0.96, 0.9) * (disk * 20.0 + glare);
}

float depthOf(vec3 p)
{
    vec4 clip = uViewProj * vec4(p, 1.0);
    return clamp((clip.z / clip.w) * 0.5 + 0.5, 0.0, 1.0);
}

void main()
{
    vec2 ndc = (gl_FragCoord.xy / uResolution) * 2.0 - 1.0;
    vec4 nearPoint = uInvViewRotProj * vec4(ndc, -1.0, 1.0);

    vec3 ro = uCameraPos;
    vec3 rd = normalize(nearPoint.xyz / nearPoint.w);

    vec3 titanLocal;
    vec3 saturnLocal;
    float ringRadius;

    float tTitan = intersectEllipsoid(ro, rd, uTitanCenter, uTitanRadii, uTitanRotation, titanLocal);
    float tSaturn = intersectEllipsoid(ro, rd, uSaturnCenter, uSaturnRadii, uSaturnRotation, saturnLocal);
    float tRings = intersectRings(ro, rd, ringRadius);

    if (!uShowSaturn) {
        tSaturn = NO_HIT;
        tRings = NO_HIT;
    }

    // Sampled outside of any branches so that the screen-space derivatives are well defined.
    vec3 titanAlbedo = toLinear(sampleEquirect(uTitanTexture, bodyMapUv(titanLocal)));
    vec3 saturnAlbedo = toLinear(sampleEquirect(uSaturnTexture, bodyMapUv(saturnLocal)));
    vec3 sky = (uShowSky ? sampleEquirect(uSkyTexture, skyMapUv(rd)) * uSkyExposure : vec3(0.0)) + sunLight(rd);

    vec3 color = sky;
    float depth = 1.0;
    vec3 titanNormal = vec3(0.0);
    vec3 saturnNormal = vec3(0.0);
    float tOpaque = min(tTitan, tSaturn);

    if (tTitan < tSaturn) {
        vec3 p = ro + rd * tTitan;
        titanNormal = ellipsoidNormal(titanLocal, uTitanRadii, uTitanRotation);
        color = shadeSurface(titanAlbedo, titanNormal, p, BODY_TITAN);
        depth = depthOf(p);
    } else if (tSaturn < NO_HIT) {
        vec3 p = ro + rd * tSaturn;
        saturnNormal = ellipsoidNormal(saturnLocal, uSaturnRadii, uSaturnRotation);
        color = shadeSurface(saturnAlbedo, saturnNormal, p, BODY_SATURN);
        depth = depthOf(p);
    }

    if (uShowSaturn) {
        color += limbHaze(ro, rd, tSaturn, saturnNormal, tTitan, uSaturnCenter, uSaturnRadii, uSaturnRotation,
                          uSaturnHazeScaleHeight, vec3(0.85, 0.78, 0.6) * 0.35);

        vec4 haze = ringHaze(ro, rd, tOpaque);
        color = color * (1.0 - haze.a) + haze.rgb;
    }

    if (tRings < tOpaque) {
        vec3 p = ro + rd * tRings;
        vec3 normal = uSaturnRotation[1];

        // The side facing away from the Sun only gets the light that is scattered through the rings.
        bool litSide = sign(dot(normal, uSunDir)) == sign(dot(normal, -rd));
        float lighting = (litSide ? 0.9 : 0.3) * sunVisibility(p, BODY_RINGS);
        float opacity = ringOpacity(ringRadius);

        color = mix(color, ringAlbedo(ringRadius) * (AMBIENT + lighting), opacity);
        if (opacity > 0.5)
            depth = depthOf(p);
    }

    color += limbHaze(ro, rd, tTitan, titanNormal, tOpaque, uTitanCenter, uTitanRadii, uTitanRotation,
                      uHazeScaleHeight, vec3(0.9, 0.55, 0.2) * 0.6);

    FragColor = vec4(toSrgb(color), 1.0);
    gl_FragDepth = depth;
}
