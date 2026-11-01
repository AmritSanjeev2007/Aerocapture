#version 330 core

// The cone of the burn's arrow (see display/burn.py), lit by the Sun.

in vec3 in_position;    // km, display frame
in vec3 in_normal;

uniform mat4 uViewProj;

out vec3 vNormal;

void main()
{
    vNormal = in_normal;
    gl_Position = uViewProj * vec4(in_position, 1.0);
}
