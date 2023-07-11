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

import abc

from pathlib import Path
from typing import Final, Any, Iterator

from .file_utils import FileList
from .types import ArchiveKind


_registry: dict[ArchiveKind, tuple[type[Archiver], str, dict[str, Any]]] = {}
KNOWN_ARCHIVERS: set[ArchiveKind] = set()


def register_archiver_type(name: str, type: type[Archiver], extension: str, **extra_kwargs: Any):
    _registry[name] = type, extension, extra_kwargs
    KNOWN_ARCHIVERS.add(name)


def init_archiver(name: ArchiveKind, filename: Path, **extra_kwargs: Any) -> Archiver:
    type, extension, default_extra_kwargs = _registry[name]
    filename = filename.parent / (filename.name + extension)
    return type(filename, **default_extra_kwargs, **extra_kwargs)


class Archiver(abc.ABC):
    # TODO: Make sure we have header and we write it
    # so this is in sync with renpy.loader.archive_handlers
    # That way it is easer to add correct new archive types.

    file_list: FileList

    @abc.abstractmethod
    def __init__(self, filename: Path):
        # A path this archive will be written to.
        self.filename = filename

        self.files: dict[str, Path] = {}

        # This is set to True if there is a package which need this archive.
        self.build_request = False

    def add(self, name: str, path: Path):
        """
        Adds a file to the archive.

        `name`
            A filename as it is stored inside the archive.
            Can not startswith or endswith backslash.

        `path`
            A path to actual file on the disk to be written into.
            The path should be absolute and link to existing file.
        """

        assert not name.startswith("/"), f"Archive file `name` can not starts with /, passed: {name!r}."
        assert not name.endswith("/"), f"Archive file `name` can not ends with /, passed: {name!r}."
        assert path.is_absolute(), f"Archive file {path!r} is relative."
        assert path.exists(), f"Archive file {path!r} does not exist."

        if name in self.files:
            raise Exception(f"Duplicate file {name!r} in archive {self.filename}.")

        self.files[name] = path

    def write_length(self):
        return len(self.files)

    @abc.abstractmethod
    def write(self) -> Iterator[None]:
        ...


class RenPyRPA3Archiver(Archiver):
    """
    Adds files from disk to a .rpa archive.
    """

    def __init__(self, filename: Path):
        super().__init__(filename)

        # The index to the file.
        self.index: dict[str, list[tuple[int, int, bytes]]] = dict()

        # A fixed key minimizes difference between archive versions.
        self.key: Final = 0x42424242
        self.padding: Final = b"RPA-3.0 XXXXXXXXXXXXXXXX XXXXXXXX\n"
        self.file_padding: Final = b"Made with Ren'Py."

    def write_length(self):
        return len([p for p in self.files.values() if p.is_file()]) + 2

    def write(self):
        from zlib import compress
        from pickle import dumps, HIGHEST_PROTOCOL

        with self.filename.open("wb") as f:
            f.write(self.padding)
            yield

            files = self.files.items()
            files = ((n, p) for n, p in files if p.is_file())
            files = sorted(files, key=lambda x: x[0])
            for name, path in files:
                self.index[name] = list()

                try:
                    with path.open("rb") as df:
                        fdata = df.read()
                        dlen = len(fdata)
                except Exception as e:
                    raise Exception(f"Can not read file: {path!s}") from e

                # Pad.
                f.write(self.file_padding)

                offset = f.tell()

                f.write(fdata)

                self.index[name].append((offset ^ self.key, dlen ^ self.key, b""))
                yield

            indexoff = f.tell()

            data: dict[str, list[tuple[int, int, bytes]]] = {
                k: v for k, v in sorted(self.index.items(), key=lambda x: x[0])}
            f.write(compress(dumps(data, HIGHEST_PROTOCOL)))

            f.seek(0)
            f.write(b"RPA-3.0 %016x %08x\n" % (indexoff, self.key))
            yield
