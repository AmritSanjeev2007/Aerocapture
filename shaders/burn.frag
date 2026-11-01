#version 330 core

in vec3 vNormal;

out vec4 FragColor;

uniform vec3 uColor;
uniform vec3 uSunDirection;     // Towards the Sun, display frame
uniform float uAmbient;         // The brightness of the side facing away from the Sun, so it never goes black

void main()
{
    float light = max(dot(normalize(vNormal), uSunDirection), 0.0);
    FragColor = vec4(uColor * mix(uAmbient, 1.0, light), 1.0);
}
