#version 330 core

in vec2 vUv;

out vec4 FragColor;

uniform sampler2D uTexture;     // Premultiplied alpha.
uniform float uOpacity;

void main()
{
    FragColor = texture(uTexture, vUv) * uOpacity;
}
