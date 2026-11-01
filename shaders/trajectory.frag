#version 330 core

in float vTime;
in float vAcross;

out vec4 FragColor;     // Premultiplied alpha.

uniform float uWidth;           // framebuffer pixels
uniform vec2 uTimeRange;        // The first and last record's time (s)
uniform float uShownUntil;      // Only the part of the trajectory up to this time (s) is drawn
uniform vec3 uStartColor;
uniform vec3 uEndColor;

void main()
{
    if (vTime > uShownUntil)
        discard;

    // The quad is a pixel wider than the line, so its edges can fade out smoothly.
    float halfWidth = 0.5 * uWidth;
    float distance = abs(vAcross) * (halfWidth + 0.5);
    float alpha = 1.0 - smoothstep(halfWidth - 0.5, halfWidth + 0.5, distance);

    // Coloured by time, so the direction of travel can be seen.
    float progress = clamp((vTime - uTimeRange.x) / max(uTimeRange.y - uTimeRange.x, 1e-6), 0.0, 1.0);
    vec3 color = mix(uStartColor, uEndColor, progress);

    FragColor = vec4(color * alpha, alpha);
}
