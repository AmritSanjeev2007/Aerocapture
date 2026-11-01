#version 330 core

// Draws the world axes as a Blender style gizmo: a line and a filled circle for each positive axis, and a faint
// circle for each negative one, sorted back to front by their depth.

out vec4 FragColor;     // Premultiplied alpha.

uniform mat3 uRotation;         // The camera's rotation: world frame -> view frame
uniform vec2 uCenter;           // The centre of the gizmo in framebuffer pixels
uniform float uLength;          // The length of each axis in framebuffer pixels
uniform float uPixelScale;      // Scales the line widths and circles (GUI scale x framebuffer pixels per point)
uniform vec3 uAxisColors[3];    // x, y and z

float segmentDistance(vec2 p, vec2 a, vec2 b)
{
    vec2 ab = b - a;
    float t = clamp(dot(p - a, ab) / max(dot(ab, ab), 1e-6), 0.0, 1.0);
    return length(p - (a + ab * t));
}

// The coverage of a shape whose signed distance (in pixels) is `d`, anti-aliased over one pixel.
float coverage(float d)
{
    return 1.0 - smoothstep(-0.75, 0.75, d);
}

vec4 over(vec4 below, vec3 color, float alpha)
{
    return vec4(color * alpha, alpha) + below * (1.0 - alpha);
}

void main()
{
    vec2 p = gl_FragCoord.xy - uCenter;

    float tipRadius = 8.0 * uPixelScale;
    float lineWidth = 1.25 * uPixelScale;

    // A dark disc behind the gizmo keeps it readable over bright parts of the scene.
    vec4 result = over(vec4(0.0), vec3(0.08), 0.35 * coverage(length(p) - uLength - tipRadius - 6.0 * uPixelScale));

    // The positive axes are 0, 1, 2 and the negative ones 3, 4, 5. In the view frame, +z points at the viewer.
    vec3 tips[6];
    int order[6];
    for (int i = 0; i < 6; i++) {
        vec3 axis = vec3(0.0);
        axis[i % 3] = i < 3 ? 1.0 : -1.0;
        tips[i] = uRotation * axis;
        order[i] = i;
    }

    // Insertion sort, furthest away first.
    for (int i = 1; i < 6; i++) {
        int current = order[i];
        int j = i - 1;
        while (j >= 0 && tips[order[j]].z > tips[current].z) {
            order[j + 1] = order[j];
            j--;
        }
        order[j + 1] = current;
    }

    for (int k = 0; k < 6; k++) {
        int i = order[k];
        vec3 color = uAxisColors[i % 3];
        vec2 tip = tips[i].xy * uLength;
        float circle = length(p - tip) - tipRadius;

        if (i < 3) {
            result = over(result, color, coverage(segmentDistance(p, vec2(0.0), tip) - lineWidth));
            result = over(result, color, coverage(circle));
        } else {
            result = over(result, color * 0.35, 0.6 * coverage(circle));
            result = over(result, color, coverage(abs(circle + lineWidth) - lineWidth * 0.5));  // A thin ring.
        }
    }

    FragColor = result;
}
