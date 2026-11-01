#version 330 core

// Each instance is one segment of the trajectory, drawn as a quad of 4 vertices (a triangle strip) which is
// widened in screen space, since OpenGL's own lines can only be 1 pixel wide in the core profile.

in vec4 in_start;   // xyz: the segment's start (km, display frame), w: its time (s)
in vec4 in_end;

uniform mat4 uViewProj;
uniform vec2 uResolution;   // framebuffer pixels
uniform float uWidth;       // framebuffer pixels

out float vTime;
out float vAcross;  // -1 to 1 across the line, for anti-aliasing its edges

void main()
{
    float along = float(gl_VertexID / 2);           // 0, 0, 1, 1
    vAcross = float(gl_VertexID % 2) * 2.0 - 1.0;   // -1, 1, -1, 1

    vec4 clipStart = uViewProj * vec4(in_start.xyz, 1.0);
    vec4 clipEnd = uViewProj * vec4(in_end.xyz, 1.0);

    // Segments crossing behind the camera are skipped (the quad collapses to nothing).
    if (clipStart.w <= 0.0 || clipEnd.w <= 0.0) {
        gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
        vTime = 0.0;
        return;
    }

    vec2 screenStart = clipStart.xy / clipStart.w * uResolution;
    vec2 screenEnd = clipEnd.xy / clipEnd.w * uResolution;
    vec2 direction = screenEnd - screenStart;
    direction = length(direction) > 1e-6 ? normalize(direction) : vec2(1.0, 0.0);
    vec2 normal = vec2(-direction.y, direction.x);

    vec4 clip = mix(clipStart, clipEnd, along);
    // One pixel is 2 / resolution in normalized device coordinates, and clip space is scaled by w.
    clip.xy += normal * vAcross * (uWidth + 1.0) / uResolution * clip.w;

    gl_Position = clip;
    vTime = mix(in_start.w, in_end.w, along);
}
