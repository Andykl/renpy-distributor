# Copyright 2023 Andrej Klychin <klyuchin.a@gmail.com>
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation files
# (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge,
# publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from ..machinery import CONVERT_LIB


def generate_image_placeholder(src: Path, dst: Path) -> tuple[int, int]:
    """
    Creates size-efficient 1/32 thumbnail for use as download preview.
    Pixellate first for better graphic results.
    Will be stretched back when playing.
    """

    if CONVERT_LIB == "PIL":
        return pil_generate_image_placeholder(src, dst)
    elif CONVERT_LIB == "pygame":
        return pygame_generate_image_placeholder(src, dst)
    else:
        raise RuntimeError("Can not import PIL nor pygame to make thumbnail.")


def pil_generate_image_placeholder(src: Path, dst: Path):
    import PIL.Image
    with PIL.Image.open(src) as im:
        width, height = im.size

        if width > 32 and height > 32:
            im.thumbnail((width // 32, height // 32))

        # optimize True uses best compression regardless compress_level.
        im.save(dst, "png", optimize=True)
    return (width, height)


@contextmanager
def execute_in_pygame():
    import pygame
    if pygame.display.get_surface():
        yield
    else:
        pygame.display.init()
        pygame.display.hint("PYGAME_SDL2_AVOID_GL", "1")  # type: ignore
        pygame.display.set_mode((640, 480))
        pygame.event.pump()
        try:
            yield
        finally:
            pygame.display.quit()


def pygame_generate_image_placeholder(src: Path, dst: Path):
    import os
    import pygame

    os.environ["RENPY_NO_REDIRECT_STDIO"] = "1"

    import renpy.object  # type: ignore
    import renpy.style  # type: ignore
    import renpy.display.render  # type: ignore
    import renpy.display.accelerator  # type: ignore
    from renpy.display.module import pixellate
    from renpy.display.pgrender import transform_scale

    surface = pygame.image.load(str(src))
    width: int = surface.get_width()
    height: int = surface.get_height()

    if width > 32 and height > 32:
        pixellate(surface, surface, 32, 32, 32, 32)
        thumbnail = transform_scale(surface, (width / 32, height / 32))
    else:
        # avoid unsupported 0-width or 0-height picture
        thumbnail = surface

    best_compression = 9
    pygame.image.save(thumbnail, str(dst), best_compression)  # type: ignore

    return (width, height)
