# pyright: standard

""" Contains useful functions or objects for dealing with shaders. """

import moderngl

from array import array
from pathlib import Path
from pyglm import glm
from typing import Any

def create_shader_program(context: moderngl.Context, vert_shader_path: Path, frag_shader_path: Path) -> moderngl.Program:
    """ Creates a shader program using the specified vertex and fragment shaders. """

    return context.program(
        vertex_shader=vert_shader_path.read_text(encoding="utf-8"),
        fragment_shader=frag_shader_path.read_text(encoding="utf-8"),
    )

def create_fullscreen_quad(context: moderngl.Context, program: moderngl.Program) -> moderngl.VertexArray:
    """ Creates a quad covering the whole screen for a ``program`` with a ``vec2 in_position`` input. Render it
    with ``mode=moderngl.TRIANGLE_STRIP``. """

    QUAD_VERTICES_ARR = array("f", [
        -1.0, -1.0,
         1.0, -1.0,
        -1.0,  1.0,
         1.0,  1.0,
    ])

    vertices = context.buffer(QUAD_VERTICES_ARR.tobytes())
    return context.vertex_array(program, [(vertices, "2f", "in_position")])

def set_uniform(program: moderngl.Program, name: str, value: Any) -> None:
    """ Sets the uniform ``name`` of the ``program`` to ``value``, which may also be a glm vector or matrix.
    Uniforms which were optimized out by the shader compiler are silently skipped. """

    uniform = program.get(name, None)
    if uniform is None:
        return

    if isinstance(value, (glm.vec3, glm.mat3, glm.mat4)):
        uniform.write(value.to_bytes())
    else:
        uniform.value = value
