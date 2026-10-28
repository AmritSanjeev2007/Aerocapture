# pyright: standard

""" Renders text into textures, and draws those textures onto the screen.

Text is rasterized on the CPU with Pillow (so any TrueType/OpenType font works), optionally with an outline and a
soft glow, then uploaded as a premultiplied-alpha RGBA texture. Usage::

    text = TextRenderer(renderer.ctx)
    label = text.create("Titan", TextStyle(size=32, glow_radius=8))
    ...
    text.draw(label, position=(20, 20), framebuffer_size=renderer.framebuffer_size)  # Every frame.
"""

import math
import moderngl
import numpy

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from typing import Literal

from .constants import SHADERS_PATH
from .shaders import create_fullscreen_quad, create_shader_program, set_uniform


TEXT_VERTEX_SHADER_PATH = SHADERS_PATH / "text.vert"
TEXT_FRAGMENT_SHADER_PATH = SHADERS_PATH / "text.frag"

DEFAULT_FONT = "segoeui.ttf"
""" Found in the system's font folder by Pillow. Falls back to Pillow's built-in font when missing. """
CACHE_SIZE = 64
""" How many text textures ``TextRenderer.create`` keeps around for reuse. """

Color = tuple[float, float, float] | tuple[float, float, float, float]
""" An RGB(A) colour with channels between 0 and 1. """

@dataclass(frozen=True)
class TextStyle:
    """ How a piece of text looks. Sizes are in pixels. """

    size: float = 24.0
    """ The font size (roughly the height of a capital letter plus descenders). """
    font: str | Path = DEFAULT_FONT
    """ A font file path, or a font file name in the system's font folder (e.g. ``"arial.ttf"``). """
    color: Color = (1.0, 1.0, 1.0, 1.0)
    align: Literal["left", "center", "right"] = "left"
    """ The alignment of multi-line text. """
    line_spacing: float = 4.0
    """ Extra pixels between lines. """
    outline_width: int = 0
    outline_color: Color = (0.0, 0.0, 0.0, 1.0)
    glow_radius: float = 0.0
    """ The blur radius of the glow. ``0`` disables it. """
    glow_color: Color | None = None
    """ The colour of the glow. Defaults to the text's colour. """
    glow_strength: float = 1.0
    """ Multiplies the glow's opacity. Values above 1 make it denser. """
    padding: int = 2
    """ Empty pixels around the text (on top of the room made for the glow). """


@dataclass(frozen=True)
class TextTexture:
    """ A texture containing rendered text. """

    texture: moderngl.Texture
    size: tuple[int, int]
    """ The size (width, height) of the texture in pixels, including padding and glow. """


def _rgba(color: Color) -> numpy.ndarray:
    return numpy.array(color if len(color) == 4 else (*color, 1.0), dtype=numpy.float32)


@lru_cache(maxsize=16)
def _load_font(font: str | Path, size: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(font), size)
    except OSError:
        print(f"Could not load the font '{font}', using Pillow's default font instead.")
        return ImageFont.load_default(size)


def render_text_image(text: str, style: TextStyle = TextStyle()) -> numpy.ndarray:
    """ Rasterizes ``text`` (which may contain newlines) and returns it as a ``(height, width, 4)`` float32 array of
    premultiplied RGBA pixels, with the first row at the top. """

    font = _load_font(style.font, style.size)
    spacing = style.line_spacing
    stroke = style.outline_width

    # Measure first so the canvas fits the text exactly, then leave room for the glow to fade out.
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    left, top, right, bottom = measure.multiline_textbbox(
        (0, 0), text, font=font, spacing=spacing, align=style.align, stroke_width=stroke
    )
    left, top, right, bottom = math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)
    margin = style.padding + math.ceil(style.glow_radius * 2.5)
    width = max(right - left, 1) + 2 * margin
    height = max(bottom - top, 1) + 2 * margin
    origin = (margin - left, margin - top)

    def coverage(stroke_width: int) -> numpy.ndarray:
        """ The text's coverage (0 to 1), with the outline grown by ``stroke_width``. """

        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).multiline_text(
            origin, text, font=font, fill=255, spacing=spacing, align=style.align,
            stroke_width=stroke_width, stroke_fill=255,
        )
        return numpy.asarray(mask, dtype=numpy.float32) / 255.0

    fill = coverage(0)
    color = _rgba(style.color)

    # Layers are composited back to front with the premultiplied "over" operator.
    pixels = numpy.zeros((height, width, 4), dtype=numpy.float32)

    def over(layer_alpha: numpy.ndarray, layer_color: numpy.ndarray) -> None:
        alpha = numpy.clip(layer_alpha * layer_color[3], 0.0, 1.0)[..., None]
        premultiplied = numpy.concatenate([layer_color[:3] * alpha, alpha], axis=-1)
        pixels[:] = premultiplied + pixels * (1.0 - alpha)

    outlined = coverage(stroke) if stroke > 0 else fill

    if style.glow_radius > 0.0:
        shape = Image.fromarray((outlined * 255).astype(numpy.uint8))
        glow = numpy.asarray(shape.filter(ImageFilter.GaussianBlur(style.glow_radius)), dtype=numpy.float32) / 255.0
        over(glow * style.glow_strength, _rgba(style.glow_color or style.color))

    if stroke > 0:
        over(outlined, _rgba(style.outline_color))

    over(fill, color)
    return pixels


class TextRenderer:
    """ Creates text textures and draws them on top of whatever has already been drawn. Created textures are cached
    by their text and style, so calling ``create`` every frame with the same arguments is cheap. """

    def __init__(self, context: moderngl.Context) -> None:

        self._context = context
        self._program = create_shader_program(
            context=context,
            vert_shader_path=TEXT_VERTEX_SHADER_PATH,
            frag_shader_path=TEXT_FRAGMENT_SHADER_PATH,
        )
        self._vao = create_fullscreen_quad(context, self._program)
        self._scope = context.scope(enable_only=moderngl.BLEND)
        self._cache: OrderedDict[tuple[str, TextStyle], TextTexture] = OrderedDict()

    def create(self, text: str, style: TextStyle = TextStyle()) -> TextTexture:
        """ Returns a texture of ``text`` rendered in the given ``style``. """

        key = (text, style)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]

        pixels = render_text_image(text, style)
        height, width = pixels.shape[:2]

        data = numpy.ascontiguousarray(pixels[::-1], dtype=numpy.float32)  # OpenGL wants the bottom row first.
        texture = self._context.texture((width, height), 4, data.tobytes(), dtype="f4")
        texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        texture.repeat_x = False
        texture.repeat_y = False

        result = TextTexture(texture, (width, height))
        self._cache[key] = result
        if len(self._cache) > CACHE_SIZE:
            _, evicted = self._cache.popitem(last=False)
            evicted.texture.release()

        return result

    def draw(self, text: TextTexture, position: tuple[float, float], framebuffer_size: tuple[int, int],
             anchor: tuple[float, float] = (0.0, 0.0), scale: float = 1.0, opacity: float = 1.0) -> None:
        """ Draws ``text`` with its ``anchor`` point at ``position``. Both are measured from the top left: the
        position in framebuffer pixels and the anchor as a fraction of the text's size, so ``(0.5, 0.5)`` centres
        it on ``position``. It's drawn over everything, ignoring the depth buffer. """

        width, height = text.size[0] * scale, text.size[1] * scale
        left = position[0] - anchor[0] * width
        top = position[1] - anchor[1] * height
        fb_width, fb_height = framebuffer_size

        # The rectangle in normalized device coordinates (x, y of the bottom left corner, width, height).
        rect = (
            2.0 * left / fb_width - 1.0,
            1.0 - 2.0 * (top + height) / fb_height,
            2.0 * width / fb_width,
            2.0 * height / fb_height,
        )

        set_uniform(self._program, "uRect", rect)
        set_uniform(self._program, "uOpacity", opacity)
        text.texture.use(location=0)
        set_uniform(self._program, "uTexture", 0)

        # The scope restores the previously enabled flags (e.g. depth testing) afterwards. The blend function can't
        # be read back in moderngl, so it's simply set every time (nothing else in the renderer blends).
        with self._scope:
            self._context.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA  # Premultiplied alpha.
            self._vao.render(mode=moderngl.TRIANGLE_STRIP, vertices=4)
