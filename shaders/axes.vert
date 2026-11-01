#version 330 core

in vec2 in_position;    // The corners of a [-1, 1] quad.

uniform vec4 uRect;     // x, y of the centre and the half width, half height (normalized device coordinates)

void main()
{
    gl_Position = vec4(uRect.xy + in_position * uRect.zw, 0.0, 1.0);
}
