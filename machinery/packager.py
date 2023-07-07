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
import time
import zipfile
import shutil
import tarfile

from typing import Any, Iterator, cast, TYPE_CHECKING
from pathlib import Path

from .file_utils import FileList
from .buildinfo import BuildInfo
from .types import FormatKind

# Values are:
# 1. Subclass of Package to use.
# 2. Extention of that format.
# 3. Extra arguments used to init the Package.
# 4. List of build modifiers.
_registry: dict[FormatKind, tuple[type[Packager], str, dict[str, Any], set[str]]] = {}
KNOWN_PACKAGERS: set[FormatKind] = set()


def register_packager_type(name: str, type: type[Packager], extension: str, /, *,
                           extra_kwargs: dict[str, Any] | None = None,
                           modifiers: set[str] | None = None):
    """
    Default modifiers are:
        'app' - Makes this format make a Mac app.
        'dmg' - Makes this format make a dmg.
        'prepend' - Makes this format prepends package name to added file list.
    """

    _registry[name] = type, extension, (extra_kwargs or {}), (modifiers or set())
    KNOWN_PACKAGERS.add(name)


def get_packager_modifiers(name: FormatKind) -> set[str]:
    return _registry[name][3]


def init_packager(name: FormatKind, build_info: BuildInfo, outfile: Path, /, **extra_kwargs: Any) -> Packager | None:
    type, extension, default_extra_kwargs, _ = _registry[name]

    filename = outfile.parent / (outfile.name + extension)
    return type.init_package(build_info, filename, **default_extra_kwargs, **extra_kwargs)


class Packager(abc.ABC):
    """
    TODO
    """

    file_list: FileList

    def __init__(self, outpath: Path, /):
        assert outpath.is_absolute(), f"Package `outpath` should be absolute Path, got {outpath}."

        self.outpath = outpath

    @classmethod
    @abc.abstractmethod
    def init_package(cls, build_info: BuildInfo, outfile: Path, /) -> Packager | None:
        ...

    def finish_file_list(self):
        self.file_list.filter_empty()
        self.file_list.add_missing_directories()

    @abc.abstractmethod
    def write_file(self, name: str, path: Path, xbit: bool):
        ...

    @abc.abstractmethod
    def write_directory(self, name: str, path: Path):
        ...

    def write_length(self):
        return len(self.file_list)

    @abc.abstractmethod
    def write(self) -> Iterator[None]:
        for f in self.file_list:
            # Some paths can still be None but it is up to packager to
            # allow or disallow that.
            if TYPE_CHECKING:
                f.path = cast(Path, f.path)

            if f.directory:
                self.write_directory(f.name, f.path)
            else:
                self.write_file(f.name, f.path, f.executable)

            yield


class ZipFile(zipfile.ZipFile):
    def write_with_info(self, zinfo: zipfile.ZipInfo, filename: Path):
        if zinfo.filename.endswith("/"):
            data = b''
        else:
            with open(filename, "rb") as f:
                data = f.read()

        self.writestr(zinfo, data)


class ZipPackager(Packager):
    """
    A class that creates a zip file.
    """

    zipfile: ZipFile

    @classmethod
    def init_package(cls, build_info: BuildInfo, outfile: Path, /):
        return cls(outfile)

    def get_date_time(self, path: Path):
        """
        Gets the datetime for a file. If the time doesn't exist or is
        weird, use the current time instead.
        """

        try:
            s = path.stat()
            rv = time.gmtime(s.st_mtime)[:6]

            # Check that the time is sensible.
            if rv[0] < 2000:
                rv = None
        except Exception:
            rv = None

        if rv is None:
            rv = time.gmtime()[:6]

        return rv

    def write_file(self, name: str, path: Path, xbit: bool):
        if path is None:  # type: ignore
            raise Exception(f"path for {name!r} must not be None.")

        zi = zipfile.ZipInfo(name)
        zi.date_time = self.get_date_time(path)
        zi.compress_type = zipfile.ZIP_DEFLATED
        zi.create_system = 3

        if xbit:
            zi.external_attr = int(0o100755) << 16
        else:
            zi.external_attr = int(0o100644) << 16

        self.zipfile.write_with_info(zi, path)

    def write_directory(self, name: str, path: Path):
        if path is None:  # type: ignore
            return

        zi = zipfile.ZipInfo(name + "/")
        zi.date_time = self.get_date_time(path)
        zi.compress_type = zipfile.ZIP_STORED
        zi.create_system = 3
        zi.external_attr = (int(0o040755) << 16) | 0x10

        self.zipfile.write_with_info(zi, path)

    def write(self):
        self.zipfile = ZipFile(self.outpath, "w", zipfile.ZIP_DEFLATED, True)
        with self.zipfile:
            yield from super().write()


class DirectoryPackager(Packager):
    def __init__(self, path: Path):
        super().__init__(path)
        self.path = path

        if path.exists():
            shutil.rmtree(path)

        path.mkdir(0o755, parents=True, exist_ok=True)

    @classmethod
    def init_package(cls, build_info: BuildInfo, outfile: Path, /) -> DirectoryPackager | None:
        return cls(outfile)

    def write_file(self, name: str, path: Path, xbit: bool):
        if path is None:  # type: ignore
            raise Exception(f"path for {name!r} must not be None.")

        assert path.is_file()

        fn = self.path / name

        # If this is not a directory, ensure all parent directories
        # have been created
        fn.parent.mkdir(0o755, parents=True, exist_ok=True)
        shutil.copy(path, fn)

        if xbit:
            fn.chmod(0o755)
        else:
            fn.chmod(0o644)

    def write_directory(self, name: str, path: Path):
        if path is None:  # type: ignore
            return

        assert path.is_dir()

        fn = self.path / name
        fn.mkdir(0o755, parents=True, exist_ok=True)

    def write(self):
        yield from super().write()


class TarPackager(Packager):

    tarfile: tarfile.TarFile

    def __init__(self, filename: Path, mode: str, notime: bool = False):
        """
        notime
            If true, times will be forced to the epoch.
        """

        super().__init__(filename)
        self.mode = mode
        self.notime = notime

    @classmethod
    def init_package(cls, build_info: BuildInfo, outfile: Path, /, mode: str):
        return cls(outfile, mode=mode)

    def write_file(self, name: str, path: Path, xbit: bool):
        if path is not None:  # type: ignore
            info = self.tarfile.gettarinfo(path, name)
        else:
            info = tarfile.TarInfo(name)
            info.size = 0
            info.mtime = int(time.time())
            info.type = tarfile.DIRTYPE

        if xbit:
            info.mode = 0o755
        else:
            info.mode = 0o644

        info.uid = 1000
        info.gid = 1000
        info.uname = "renpy"
        info.gname = "renpy"

        if self.notime:
            info.mtime = 0

        if info.isreg():
            with open(path, "rb") as f:
                self.tarfile.addfile(info, f)
        else:
            self.tarfile.addfile(info)

    def write_directory(self, name: str, path: Path):
        self.write_file(name, path, True)

    def write(self):
        self.tarfile = tarfile.open(self.outpath, self.mode)
        self.tarfile.dereference = True

        with self.tarfile:
            yield from super().write()


class DMGPackager(DirectoryPackager):
    @classmethod
    def init_package(cls, build_info: BuildInfo, outfile: Path, /):
        if build_info.mac_identity is None:
            return None

        return cls(outfile)
