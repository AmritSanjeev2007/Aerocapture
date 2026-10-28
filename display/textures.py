""" Loads the equirectangular maps that are wrapped around the bodies and the starfield.

Loading is split into decoding (slow, CPU only, so it can run on a background thread) and uploading (which has to
happen on the thread that owns the OpenGL context). """

import moderngl
import numpy
import os

from dataclasses import dataclass
from pathlib import Path
from PIL import Image
Image.MAX_IMAGE_PIXELS = 250_000_000  # To avoid decompression limits

@dataclass(frozen=True)
class MapImage:
    """ A decoded map, ready to be uploaded as a texture. Rows are ordered bottom to top, as OpenGL expects. """

    size: tuple[int, int]
    """ The size (width, height) in pixels. """
    data: bytes
    """ The RGB pixels. """
    dtype: str
    """ The moderngl data type of a single channel, e.g. ``"f1"`` (8-bit) or ``"f2"`` (half-float). """


def decode_map_image(path: Path, max_size: int) -> MapImage:
    """ Decodes an (8-bit) equirectangular map image at the specified ``path``, downsampled to fit ``max_size``. """

    with Image.open(path) as source:
        source.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        image = source.convert("RGB").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return MapImage(image.size, image.tobytes(), "f1")


def decode_hdr_map_image(path: Path, max_width: int) -> MapImage:
    """ Decodes an OpenEXR equirectangular map at the specified ``path`` into half-floats, downsampled to at most
    ``max_width`` pixels wide. """

    os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")  # Must be set before cv2 is imported.
    import cv2

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    assert image is not None, f"Could not read {path}. Is OpenCV built with OpenEXR support?"

    height, width = image.shape[:2]
    if width > max_width:
        image = cv2.resize(image, (max_width, height * max_width // width), interpolation=cv2.INTER_AREA)

    # OpenCV loads channels as BGR with the first row at the top.
    pixels = numpy.ascontiguousarray(image[::-1, :, 2::-1], dtype=numpy.float16)
    height, width = pixels.shape[:2]

    return MapImage((width, height), pixels.tobytes(), "f2")


def upload_map_texture(context: moderngl.Context, image: MapImage) -> moderngl.Texture:
    """ Uploads a decoded map into a mipmapped, horizontally wrapping 2D texture. """

    texture = context.texture(image.size, 3, image.data, dtype=image.dtype, alignment=1)
    texture.build_mipmaps()
    texture.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
    texture.anisotropy = 8.0
    texture.repeat_x = True
    texture.repeat_y = False
    return texture
