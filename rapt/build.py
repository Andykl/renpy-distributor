from __future__ import annotations

import jinja2
import tarfile
import shutil
import gzip

from pathlib import Path
from typing import Any


from .plat import RAPT_PATH
from .configuration import Configuration

from .. import BuildContext
from .. import machinery
from ..machinery import packager
from ..machinery.file_utils import match
from ..machinery import FilesPattern, FileList


class AndroidContext(BuildContext):
    android_config: Configuration


class AndroidPackager(packager.Packager):
    """
    This packager holds file list for files that are not a part of
    private.mp3 or assets folders  (i.e. android- icons).
    Also creates and manager private and assets packagers.
    """

    private: AndroidPrivatePackager
    assets: AndroidBundlePackager | AndroidXFilePackager

    def __init__(self, outpath: Path, /, bundle: bool):
        super().__init__(outpath)
        self.bundle = bundle

    @classmethod
    def init_package(cls, build_info: machinery.BuildInfo, outfile: Path, /, bundle: bool):
        return cls(outfile, bundle)

    def finish_file_list(self):
        super().finish_file_list()
        self.private.finish_file_list()
        self.assets.finish_file_list()

    def write_file(self, name: str, path: Path, xbit: bool):
        return super().write_file(name, path, xbit)

    def write_directory(self, name: str, path: Path):
        return super().write_directory(name, path)

    def write_length(self):
        return self.private.write_length() + self.assets.write_length()

    def write(self):
        yield from self.private.write()
        yield from self.assets.write()


machinery.register_packager_type("android-bundle", AndroidPackager, ".aab", extra_args=[True])
machinery.register_packager_type("android-apk", AndroidPackager, ".apk", extra_args=[False])


class AndroidPrivatePackager(packager.Packager):
    """
    This packager is used to write private.mp3 and get its digest.
    Really, a tar file with the private data in it.
    """

    tarfile: tarfile.TarFile

    def __init__(self, outpath: Path, /):
        super().__init__(outpath)
        self.file_list = FileList()

    @classmethod
    def init_package(cls, *_):
        raise RuntimeError("Can not create 'AndroidPrivatePackager' instances via 'init_package'.")

    def write_file(self, name: str, path: Path, xbit: bool):
        self.tarfile.add(path, name, recursive=False)

    def write_directory(self, name: str, path: Path):
        self.write_file(name, path, False)

    def write(self):
        self.outpath.parent.mkdir(0o777, parents=True, exist_ok=True)
        self.tarfile = tarfile.open(self.outpath, "w:gz", format=tarfile.GNU_FORMAT)
        with self.tarfile:
            yield from super().write()


class AndroidBundlePackager(packager.Packager):

    MAX_SIZE = 500000000

    def __init__(self, project_dir: Path, /):
        super().__init__(project_dir)
        self.file_list = FileList()

        self.targets = {
            project_dir / "ff1/src/main/assets": 0,
            project_dir / "ff2/src/main/assets": 0,
            project_dir / "ff3/src/main/assets": 0,
            project_dir / "ff4/src/main/assets": 0,
        }

    @classmethod
    def init_package(cls, *_):
        raise RuntimeError("Can not create 'AndroidBundlePackager' instances via 'init_package'.")

    def _chose_package(self, size: int):
        for target in self.targets:
            if self.targets[target] + size <= self.MAX_SIZE:
                self.targets[target] += size
                return target
        else:
            raise Exception("Game too big for bundle, or single file > 500MB.")

    def write_file(self, name: str, path: Path, xbit: bool):
        if path is None:  # type: ignore
            raise Exception(f"path for {name!r} must not be None.")

        assert path.is_file()

        size = path.stat().st_size
        fn = self._chose_package(size) / name

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

        fn = self._chose_package(0) / name
        fn.mkdir(0o755, parents=True, exist_ok=True)

    def write_length(self):
        return super().write_length() + 4

    def write(self):
        # Write at least one file in each assets directory, to make sure that
        # all exist.
        for p in self.targets:
            if p.exists():
                shutil.rmtree(p)

            p.mkdir(0o777, parents=True, exist_ok=True)

            with (p / "00_pack.txt").open("w", encoding="utf-8") as f:
                print("Shiro was here.", file=f)

            yield

        yield from super().write()


class AndroidXFilePackager(packager.Packager):
    def __init__(self, outpath: Path, /):
        super().__init__(outpath)
        self.file_list = FileList()

    @classmethod
    def init_package(cls, *_):
        raise RuntimeError("Can not create 'AndroidXFilePackager' instances via 'init_package'.")

    # Ren'Py uses a lot of names that don't work as assets. Auto-rename them.
    def _xsify(self, name: str):
        return "/".join([f"x-{p}" for p in name.split("/")])

    def write_file(self, name: str, path: Path, xbit: bool):
        if path is None:  # type: ignore
            raise Exception(f"path for {name!r} must not be None.")

        assert path.is_file()

        fn = self.outpath / self._xsify(name)

        # If this is not a directory, ensure all parent directories
        # have been created
        fn.parent.mkdir(0o755, parents=True, exist_ok=True)
        shutil.copy(path, fn)

        if xbit:
            fn.chmod(0o755)
        else:
            fn.chmod(0o644)

        if fn.suffix != ".gz":
            return

        # AAPT unavoidably gunzips files with a .gz extension.
        # To prevent this we temporarily double gzip such files,
        # leaving AAPT to unpack them back into the original
        # location. /o\

        gzfn = fn.parent / (fn.name + '.gz')
        with fn.open("rb") as src, gzip.open(gzfn, "wb") as out:
            shutil.copyfileobj(src, out)
        fn.unlink()

    def write_directory(self, name: str, path: Path):
        if path is None:  # type: ignore
            return

        assert path.is_dir()

        fn = self.outpath / self._xsify(name)
        fn.mkdir(0o755, parents=True, exist_ok=True)

    def write(self):
        yield from super().write()


class PatternList:
    """
    Used to load in the blocklist and keeplist patterns.
    """

    def __init__(self, fpath: Path):
        self.patterns: list[FilesPattern] = []

        with fpath.open("r") as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue

                if l.startswith("#"):
                    continue

                self.patterns.append(l)

    def match(self, s: str):
        """
        Matches the patterns against s. Returns true if they match, False
        otherwise.
        """

        for p in self.patterns:
            if match(s, p):
                return True

        return False


def should_autoescape(fn: str | None):
    """
    Returnes true if the filename `fn` should be autoescaped.
    """

    if fn is None:
        return False

    return Path(fn).suffix in (".xml", )


# Used by render.
environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(RAPT_PATH), autoescape=should_autoescape)


def render(always: bool, template_name: str, dest: Path, **kwargs: Any):
    """
    Using jinja2, render `template_name` to the `dest`, supplying the keyword
    arguments as template parameters.
    """

    if (not always) and dest.exists():
        return

    template = environment.get_template(template_name)
    text = template.render(**kwargs)

    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        f.write(text.encode("utf-8"))


def get_presplash_src(project_dir: Path, name: str, default: Path):
    """
    Copies the presplash file.
    """

    for ext in [".png", ".jpg"]:

        fn = project_dir / f"{name}{ext}"

        if fn.exists():
            return fn
    else:
        return default
