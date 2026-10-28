#version 330 core

out vec4 FragColor;

uniform vec2 uResolution;
uniform float uProgress;    // [0, 1]
uniform float uTime;        // seconds
uniform vec3 uFillColor;

const vec3 BACKGROUND = vec3(0.012, 0.012, 0.018);
const vec3 TRACK_COLOR = vec3(0.10, 0.09, 0.09);

// Signed distance (in pixels) to a rounded rectangle centred on the origin.
float roundedRect(vec2 p, vec2 halfSize, float radius)
{
    vec2 q = abs(p) - halfSize + radius;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
}

void main()
{
    vec2 pixel = gl_FragCoord.xy;
    vec2 center = uResolution * 0.5;

    vec2 halfSize = vec2(min(uResolution.x * 0.3, 360.0), 4.0);
    vec2 p = pixel - center;

    // A faint vignette so the screen isn't a flat black.
    float vignette = 1.0 - 0.6 * length((pixel - center) / uResolution);
    vec3 color = BACKGROUND * vignette;

    float track = roundedRect(p, halfSize, halfSize.y);
    color = mix(color, TRACK_COLOR, 1.0 - smoothstep(-0.5, 0.5, track));

    // The filled part, with a soft highlight sweeping along it.
    float fillRight = -halfSize.x + 2.0 * halfSize.x * clamp(uProgress, 0.0, 1.0);
    float inFill = 1.0 - smoothstep(-0.5, 0.5, max(track, p.x - fillRight));
    float shimmer = 0.85 + 0.15 * sin((p.x - uTime * 160.0) * 0.03);
    color = mix(color, uFillColor * shimmer, inFill);

    // A glow around the leading edge.
    float glow = exp(-length(vec2(p.x - fillRight, p.y * 2.0)) / 18.0) * step(0.001, uProgress);
    color += uFillColor * glow * 0.35;

    FragColor = vec4(color, 1.0);
}
