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

import shutil

from typing import Any, Callable
from contextlib import contextmanager
from pathlib import Path

from .plat import RAPT_PATH
from .configuration import Configuration
from ..machinery import CONVERT_LIB

if CONVERT_LIB == "PIL":
    import PIL.Image
    import PIL.ImageChops
else:
    import pygame_sdl2

_Surface = Any


@contextmanager
def execute_in_pygame():
    if pygame_sdl2.display.get_surface():  # type: ignore
        yield
    else:
        pygame_sdl2.display.init()  # type: ignore
        pygame_sdl2.display.hint("PYGAME_SDL2_AVOID_GL", "1")  # type: ignore
        pygame_sdl2.display.set_mode((640, 480))  # type: ignore
        pygame_sdl2.event.pump()  # type: ignore
        try:
            yield
        finally:
            pygame_sdl2.display.quit()  # type: ignore


class IconMaker:
    def __init__(self, project_dir: Path, project_path: Path, config: Configuration):
        from contextlib import nullcontext

        self.config: Configuration = config
        self.project_dir = project_dir
        self.project_path = project_path

        sizes = [
            ("mdpi", 1),
            ("hdpi", 1.5),
            ("xhdpi", 2),
            ("xxhdpi", 3),
            ("xxxhdpi", 4),
        ]

        if CONVERT_LIB == "PIL":
            manager = nullcontext(None)
        else:
            manager = execute_in_pygame()

        with manager:
            for dpi, scale in sizes:
                self.write_dpi(dpi, scale)

    def scale(self, surf: _Surface, size: int):

        w: int
        h: int
        while True:
            if CONVERT_LIB == "PIL":
                w, h = surf.size
            else:
                w, h = surf.get_size()

            if (w == size) and (h == size):
                break

            w = max(w // 2, size)
            h = max(h // 2, size)

            if CONVERT_LIB == "PIL":
                surf = surf.resize((w, h))
            else:
                surf = pygame_sdl2.transform.smoothscale(surf, (w, h))  # type: ignore

        return surf

    def load_image(self, fn: str):

        for i in [self.project_dir / fn, RAPT_PATH / "templates" / fn]:
            if i.exists():
                if CONVERT_LIB == "PIL":
                    surf = PIL.Image.open(i)
                    surf.load()

                    if surf.mode != "RGBA":
                        surf = surf.convert("RGBA")

                else:
                    surf: _Surface = pygame_sdl2.image.load(str(i))  # type: ignore
                    surf = surf.convert_alpha()
                return surf

        else:
            raise Exception(f"Could not find {fn}.")

    def load_foreground(self, size: int):
        return self.scale(self.load_image("android-icon_foreground.png"), size)

    def load_background(self, size: int):
        return self.scale(self.load_image("android-icon_background.png"), size)

    def make_icon(self, size: int):
        bigsize = int(1.5 * size)
        fg = self.load_foreground(bigsize)
        icon = self.load_background(bigsize)

        offset = int(.25 * size)

        mask = self.scale(self.load_image("android-icon_mask.png"), size)

        if CONVERT_LIB == "PIL":
            icon.paste(fg, (0, 0))

            icon = icon.crop((offset, offset, size, size))

            icon = PIL.ImageChops.multiply(icon, mask)

        else:
            icon.blit(fg, (0, 0))

            icon = icon.subsurface((offset, offset, size, size))

            icon.blit(mask, (0, 0), None, pygame_sdl2.BLEND_RGBA_MULT)  # type: ignore

        return icon

    def write_icon(self, name: str, dpi: str, scale: float, size: int, generator: Callable[[int], _Surface]):

        dst = self.project_path / f"app/src/main/res/mipmap-{dpi}/{name}.png"
        dst.parent.mkdir(parents=True, exist_ok=True)

        # Did the user provide the file?
        src = self.project_dir / f"android-{name}-{dpi}.png"

        if src.exists():
            shutil.copy(src, dst)
            return

        surf = generator(int(scale * size))

        if self.config.update_always or not dst.exists():
            if CONVERT_LIB == "PIL":
                surf.save(dst)
            else:
                pygame_sdl2.image.save(surf, str(dst))  # type: ignore

    def write_dpi(self, dpi: str, scale: float):
        self.write_icon("icon_background", dpi, scale, 108, self.load_background)
        self.write_icon("icon_foreground", dpi, scale, 108, self.load_foreground)
        self.write_icon("icon", dpi, scale, 48, self.make_icon)
