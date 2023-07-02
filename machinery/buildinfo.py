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

import dataclasses
from types import ModuleType

from typing import Any, ClassVar, Iterable

from .types import ArchiveKind, FileListKind, FileListName, FilesPattern, FormatKind, PlatfromSetKind


@dataclasses.dataclass(init=False, eq=True, frozen=True)
class Package:
    """
    TODO

    `name`
        The name of the package.

    `formats`
        The formats of the package. A dict with pacakge formats
        Package formats registered by default:

        zip
            A zip file.
        tar.bz2
            A tar.bz2 file.
        directory
            A directory containing the files.
        dmg
            A Macintosh DMG containing the files.
        app-zip
            A zip file containing a macintosh application.
        app-directory
            A directory containing the mac app.
        app-dmg
            A macintosh drive image containing a dmg. (Mac only.)
        bare-zip
            A zip file without :var:`build.directory_name`
            prepended.
        bare-tar.bz2
            A zip file without :var:`build.directory_name`
            prepended.

        The empty list will not build any package formats (this
        makes dlc possible).

    `platforms`
        The set of kinds that package wants to build. Can contain only
        "win", "linux", "mac", "android", "ios" or "web".

    `ignore_archvies`
        If true, this package will always ignore archives and build
        add files directly.

    `file_lists`
        A non-empty list containing the file lists that will be included
        in the package.

    `description`
        An optional description of the package to be built.

    `update`
        If true and updates are being built, an update will be
        built for this package.

    `dlc`
        If true, any zip or tar.bz2 file will be built in
        standalone DLC mode, without an update directory.

    `hidden`
        If true, this will be hidden from the list of packages.
    """

    name: str
    formats: list[FormatKind]
    platforms: PlatfromSetKind
    ignore_archives: bool
    file_lists: list[FileListName]
    description: str
    update: bool
    dlc: bool
    hidden: bool

    def __init__(
        self,
        name: str,
        formats: list[FormatKind],
        platforms: PlatfromSetKind,
        ignore_archives: bool,
        file_lists: list[FileListName],
        description: str | None,
        update: bool,
        dlc: bool,
        hidden: bool,
    ):

        if description is None:
            description = name

        assert file_lists, "File lists can not be empty."

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "formats", formats)
        object.__setattr__(self, "platforms", platforms)
        object.__setattr__(self, "ignore_archives", ignore_archives)
        object.__setattr__(self, "file_lists", file_lists)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "update", update)
        object.__setattr__(self, "dlc", dlc)
        object.__setattr__(self, "hidden", hidden)

    def __repr__(self):
        from textwrap import dedent
        from pprint import pformat

        return dedent(f"""\
            Package:
                name: {self.name!r}
                description: {self.description!r}

                formats: {pformat(self.formats, width=120 - 13, compact=True)}
                platforms: {pformat(self.platforms, width=120 - 15, compact=True)}
                file_lists: {pformat(self.file_lists, width=120 - 16, compact=True)}

                ignore_archives: {self.ignore_archives}
                update: {self.update}
                dlc: {self.dlc}
                hidden: {self.hidden}
        """)


@dataclasses.dataclass(init=False, eq=True, frozen=True)
class Archive:
    """
    TODO
    """

    name: str
    filename: str
    file_lists: list[FileListName]

    archiver_kind: ArchiveKind
    archiver_args: list[Any]

    def __init__(self, name: str, filename: str, file_lists: list[str],
                 archiver_kind: ArchiveKind, archiver_args: list[Any]):

        assert file_lists, "File lists can not be empty."

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "file_lists", file_lists)

        object.__setattr__(self, "archiver_kind", archiver_kind)
        object.__setattr__(self, "archiver_args", archiver_args)

    def __repr__(self):
        from textwrap import dedent
        from pprint import pformat

        return dedent(f"""\
            Archive:
                name: {self.name!r}
                filename: {self.filename!r}

                file_lists: {pformat(self.file_lists, width=120 - 16, compact=True)}

                archiver_kind: {self.archiver_kind!r}
                archiver_args: {pformat(self.archiver_args, width=120 - 19, compact=True)}
        """)


@dataclasses.dataclass(frozen=True)
class BuildInfo:
    """
    TODO
    """

    SPECIAL_PACKAGES: ClassVar = {
        "android-bundle": Package(
            "android-bundle", ["android-bundle"], {"android"}, True,
            ["android", "all"], None, False, False, True),
        "android-apk": Package(
            "android-apk", ["android-apk"], {"android"}, True,
            ["android", "all"], None, False, False, True),
        "ios": Package(
            "ios", ["ios"], {"ios"}, True,
            ["ios", "all"], None, False, False, True),
        "web": Package(
            "web", ["web"], {"web"}, True,
            ["web", "renpy", "all"], None, False, False, True),
    }

    # The name of directories in the archives.
    directory_name: str

    # The destination things are built in.
    destination: str

    # The name of .exe, .sh and .app files.
    executable_name: str

    # Should we include update information into the archives?
    include_update: bool

    # A verbose name to include in package info.
    display_name: str

    # A string version of the game.
    version: str

    # Additional or Override keys to add to the Info.plist.
    mac_info_plist: dict[str, Any]

    # The identity used for codesigning and dmg building.
    # TODO: Ask Tom how it should actually work.
    mac_identity: None

    # Set of file patterns of documentation files.
    # In a mac app build,
    # files matching the documentation pattern are stored twice - once
    # inside the app package, and again outside of it.
    documentation_patterns: set[FilesPattern]

    # Set of file patterns to make them executable on platforms that support it.
    # (Linux and Macintosh)
    xbit_patterns: set[FilesPattern]

    game_patterns: dict[FilesPattern, FileListKind]
    renpy_patterns: dict[FilesPattern, FileListKind]

    # The names of all possible filelists.
    file_lists: set[FileListName]

    # All the known packages.
    packages: dict[str, Package]

    # All the known archives.
    archives: dict[str, Archive]

    # Do we still need those fields?

    # Should we exclude empty directories from the zip and tar files?
    # exclude_empty_directories: bool

    # Do we want to add the script_version file?
    # script_version: bool

    # Should we include the old Ren'Py themes?
    # include_old_themes: bool

    # Should we allow the use of an integrated GPU on platforms that support
    # both discrete and integrated GPUs?
    # allow_integrated_gpu: bool

    # Should the sdk-fonts directory be renamed to game?
    # _sdk_fonts: bool

    def __post_init__(self):
        if {" ", ":", ";"}.intersection(self.directory_name):
            raise ValueError(
                "Building distributions failed:\n\n"
                "`directory_name` value may not include the space, colon, or semicolon characters.")

    def __repr__(self) -> str:
        from textwrap import dedent
        from pprint import pformat

        idt = str.maketrans({'\n': "\n" + "    " * 4})

        def format_obj(obj: Any, extra_width: int):
            rv = pformat(obj, width=120 - extra_width)
            return rv.translate(idt)

        slash_n = "\n" + "    " * 4
        return dedent(f"""\
            BuildInfo:
                # The name of directories in the archives.
                directory_name: {self.directory_name!r}

                # The destination things are built in.
                destination: {self.destination!r}

                # The name of .exe, .sh and .app files.
                executable_name: {self.executable_name!r}

                # Should we include update information into the archives?
                include_update: {self.include_update}

                # A verbose name to include in package info.
                display_name: {self.display_name!r}

                # A string version of the game.
                version: {self.version!r}

                # The names of all possible filelists.
                file_lists: {format_obj(self.file_lists, 12)}

                # Additional or Override keys to add to the Info.plist.
                mac_info_plist: {format_obj(self.mac_info_plist, 20)}

                # The identity used for codesigning and dmg building.
                # TODO: Ask Tom how it should actually work.
                mac_identity: {self.mac_identity}

                {slash_n.join([format_obj(p, 0) for p in self.packages.values()])}
                {slash_n.join([format_obj(p, 0) for p in self.archives.values()])}
                # Set of file patterns of documentation files.
                # In a mac app build,
                # files matching the documentation pattern are stored twice - once
                # inside the app package, and again outside of it.
                documentation_patterns: {format_obj(self.documentation_patterns, 28)}

                # Set of file patterns to make them executable on platforms that support it.
                # (Linux and Macintosh)
                xbit_patterns: {format_obj(self.xbit_patterns, 19)}

                game_patterns: {format_obj(self.game_patterns, 19)}
                renpy_patterns: {format_obj(self.renpy_patterns, 20)}

        """)

    @classmethod
    def from_dump(cls, data: dict[str, Any], /):
        directory_name = data.pop("directory_name")
        destination = data.pop("destination")
        executable_name: str = data.pop("executable_name")
        include_update: bool = data.pop("include_update")
        display_name: str = data.pop("display_name")
        version: str = data.pop("version")
        mac_info_plist: dict[str, Any] = data.pop("mac_info_plist")
        documentation_patterns: list[str] = data.pop("documentation_patterns")
        xbit_patterns: list[str] = data.pop("xbit_patterns")

        rpackages: dict[str, Package] = cls.SPECIAL_PACKAGES.copy()
        packages: list[dict[str, Any]] = data.pop("packages")
        builtin_packages: dict[str, PlatfromSetKind] = {
            "pc": {"win", "linux"},
            "linux": {"linux"},
            "mac": {"mac"},
            "win": {"win"},
            "market": {"win", "linux", "mac"},
            "steam": {"win", "linux", "mac"},
        }
        for package in packages:
            if package["name"] in ("android", "ios", "web"):
                continue

            assert package["name"] not in rpackages, f"Duplicate package: {package['name']!r}"

            if package["name"] not in builtin_packages:
                # TODO: Write down migration path.
                raise Exception("It is not supported to have any except default packages in legacy mode."
                                " Please migrate to build.toml.")

            platforms = builtin_packages[package["name"]]
            ignore_archives = package["name"] in ("android", "ios", "web")
            rpackages[package["name"]] = Package(**package,
                                                 platforms=platforms,
                                                 ignore_archives=ignore_archives)

        rarchives: dict[str, Archive] = {}
        archives: list[tuple[str, list[str]]] = data.pop("archives")
        for arcname, file_lists in archives:
            assert arcname not in rarchives, f"Duplicate archive: {arcname!r}"

            # All legacy archives assumed to be RenPy RPA3 archives.
            rarchives[arcname] = Archive(arcname, arcname, file_lists, "rpa", [])

        base_patterns: list[tuple[str, None | list[str]]] = data.pop("base_patterns")
        rgame_patterns = cls._process_patterns_list(base_patterns)
        renpy_patterns: list[tuple[str, None | list[str]]] = data.pop("renpy_patterns")
        rrenpy_patterns = cls._process_patterns_list(renpy_patterns)

        # Not Yet Implemented.
        data.pop("google_play_key", None)
        data.pop("google_play_salt", None)
        data.pop("android_permissions", None)

        if mac_identity := data.pop("mac_identity", None):
            data.pop("mac_codesign_command", None)
            data.pop("mac_create_dmg_command", None)
            data.pop("mac_codesign_dmg_command", None)

        data.pop("itch_project", None)
        data.pop("itch_channels", None)

        # All fields below are ignored.
        # Either it has a replacement in the model or it is obsolete.
        data.pop("_sdk_fonts")
        data.pop("script_version")
        data.pop("exclude_empty_directories")
        data.pop("allow_integrated_gpu")
        data.pop("renpy")
        data.pop("merge")
        data.pop("include_i686")
        data.pop("change_icon_i686")
        assert not data, f"dump.json has unexpected fields: {', '.join(data)}"

        all_file_lists = cls._check_filelists(
            rpackages, rarchives, rgame_patterns, rrenpy_patterns)

        return cls(
            directory_name=directory_name,
            destination=destination,
            executable_name=executable_name,
            include_update=include_update,
            display_name=display_name,
            mac_info_plist=mac_info_plist,
            mac_identity=mac_identity,
            version=version,
            documentation_patterns=set(documentation_patterns),
            xbit_patterns=set(xbit_patterns),
            file_lists=all_file_lists,
            packages=rpackages,
            archives=rarchives,
            game_patterns=rgame_patterns,
            renpy_patterns=rrenpy_patterns,
        )

    @classmethod
    def from_module(cls, mod: ModuleType, /):
        try:
            name: str = getattr(mod, "name")
        except NameError:
            raise RuntimeError("`name` is not defined in buildinfo.py")

        try:
            version: str = getattr(mod, "version")
        except NameError:
            raise RuntimeError("`version` is not defined in buildinfo.py")

        directory_name = mod.directory_name
        if not directory_name:
            directory_name = name

            if version:
                directory_name += f"-{version}"

        executable_name = mod.executable_name
        if not executable_name:
            executable_name = name

        display_name = mod.display_name
        if not display_name:
            display_name = name or executable_name

        destination = mod.destination
        destination = destination.format(
            directory_name=directory_name,
            executable_name=executable_name,
            display_name=display_name,
            version=version or directory_name,
        )

        game_patterns = cls._process_patterns_list(
            mod.early_game_patterns +
            mod.game_patterns +
            mod.late_game_patterns)
        renpy_patterns = cls._process_patterns_list(
            mod.renpy_patterns)

        all_file_lists = cls._check_filelists(
            mod.packages, mod.archives, game_patterns, renpy_patterns)

        return cls(
            directory_name=directory_name,
            destination=destination,
            executable_name=executable_name,
            include_update=mod.include_update,
            display_name=display_name,
            mac_info_plist=mod.mac_info_plist,
            mac_identity=mod.mac_identity,
            version=version,
            documentation_patterns=set(mod.documentation_patterns),
            xbit_patterns=set(mod.xbit_patterns),
            file_lists=all_file_lists,
            packages=mod.packages,
            archives=mod.archives,
            game_patterns=game_patterns,
            renpy_patterns=renpy_patterns,
        )

    @staticmethod
    def _process_patterns_list(patterns: list[tuple[str, None | list[str]]]):
        rv: dict[FilesPattern, FileListKind] = {}
        for files_p, file_lists in patterns:
            if file_lists is not None:
                file_lists = tuple(file_lists)

            # If pattern already exists we should not overwrite it.
            if files_p not in rv:
                rv[files_p] = file_lists

        return rv

    @staticmethod
    def _check_filelists(
            packages: dict[str, Package], archives: dict[str, Archive],
            game_patterns: dict[FilesPattern, FileListKind],
            renpy_patterns: dict[FilesPattern, FileListKind],
    ):
        # The set of file list names that can be classified.
        file_lists_to_use: set[str] = set()

        def check_used(file_list: Iterable[FileListName], what: str):
            if not (extra := set(file_list) - file_lists_to_use):
                return

            raise Exception(
                f"{what} uses a file list(s) that are not one of"
                f" valid package lists or archive name: {', '.join(extra)}.")

        for package in packages.values():
            file_lists_to_use.update(package.file_lists)

        for archive in archives.values():
            check_used(archive.file_lists, f"Archive {archive.name!r}")

        for archive in archives.values():
            file_lists_to_use.add(archive.name)

        for pattern, file_lists in game_patterns.items():
            if file_lists is not None:
                check_used(file_lists, f"Game pattern {pattern!r}")

        for pattern, file_lists in game_patterns.items():
            if file_lists is not None:
                check_used(file_lists, f"RenPy pattern {pattern!r}")

        return file_lists_to_use
