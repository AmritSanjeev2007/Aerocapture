#version 330 core

in vec2 in_position;    // The corners of a [-1, 1] quad.

uniform vec4 uRect;     // x, y of the bottom left corner, width, height (normalized device coordinates)

out vec2 vUv;

void main()
{
    vUv = in_position * 0.5 + 0.5;
    gl_Position = vec4(uRect.xy + vUv * uRect.zw, 0.0, 1.0);
}
