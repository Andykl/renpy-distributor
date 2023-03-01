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

import sys
import renpy.script

from typing import Any, cast

from .archiver import KNOWN_ARCHIVERS, register_archiver_type as register_archiver_type
from .packager import register_packager_type as register_packager_type, KNOWN_PACKAGERS
from .types import KNOWN_PLATFORMS, ArchiveKind, FileListKind, FileListName, FilesPattern, PlatfromSetKind
from .buildinfo import Package, Archive


packages: dict[str, Package] = {}


def package(
    name: str,
    format: str,
    file_lists: list[FileListName],
    description: str | None = None,
    update: bool = True,
    dlc: bool = False,
    hidden: bool = False,
    ignore_archives: bool = False,
    platform: str = "win linux mac android ios web"
):
    """
    Declares a package that can be built by the packaging
    tool.

    `name`
        The name of the package.

    `format`
        The format of the package. A string containing a space separated
        list of:

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

        The empty string will not build any package formats (this
        makes dlc possible).

    `platform`
        The platform this package targets to. A string containing a space
        separated list of - "win", "linux", "mac", "android", "ios", "web".

    `file_lists`
        A list containing the file lists that will be included
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
        If true, this will be hidden from the list of packages in
        the launcher.
    """

    formats = format.split()

    for i in formats:
        if i not in KNOWN_PACKAGERS:
            raise ValueError(f"Format {i!r} not known.")

    platforms = cast(PlatfromSetKind, set(platform.split()))
    for i in platforms:
        if i not in KNOWN_PLATFORMS:
            raise Exception(f"Platform {i!r} not known.")

    packages[name] = Package(
        name, formats, platforms, ignore_archives,
        file_lists, description, update, dlc, hidden)


archives: dict[str, Archive] = {}


def archive(name: str, file_list: list[FileListName] | FileListName = "all",
            filename: str | None = None, archive_kind: ArchiveKind = "rpa",
            *archiver_args: Any):
    """
    Declares the existence of an archive, whose `name` is added to the
    list of available archive names, which can be passed to
    :func:`build.classify`.

    If one or more files are classified with `name`, `name`.rpa is
    built as an archive, and then distributed in packages including
    the `file_list` given here. ::

        build.archive("secret", "windows")

    If any file is included in the "secret" archive using the
    :func:`build.classify` function, the file will be included inside
    the secret.rpa archive in the windows builds.

    As with the :func:`build.classify` function, if the name given as
    `file_list` doesn't exist as a file list name, it is created and
    added to the set of valid file lists.
    """

    if not isinstance(file_list, list):
        file_list = [file_list]

    if filename is None:
        filename = name

    if archive_kind not in KNOWN_ARCHIVERS:
        raise Exception(f"Archiver {archive_kind!r} not known.")

    archives[name] = Archive(name, filename, file_list, archive_kind, list(archiver_args))


# Documentation patterns.
documentation_patterns: list[FilesPattern] = ["*.html", "*.txt"]


def documentation(pattern: FilesPattern):
    """
    Declares a pattern that matches documentation. In a mac app build,
    files matching the documentation pattern are stored twice - once
    inside the app package, and again outside of it.
    """

    documentation_patterns.append(pattern)


xbit_patterns = [
    "**.sh",

    "lib/py*-linux-*/*",
    "lib/py*-mac-*/*",

    "**.app/Contents/MacOS/*",
]


def executable(pattern: FilesPattern):
    """
    Adds a pattern marking files as executable on platforms that support it.
    (Linux and Macintosh)
    """

    xbit_patterns.append(pattern)


game_patterns: list[tuple[FilesPattern, FileListKind]] = []


def classify(pattern: FilesPattern, file_list: Any):
    """
    Classifies files that match `pattern` into `file_list`, which can
    also be an archive name.

    If the name given as `file_list` doesn't exist as an archive or file
    list name, it is created and added to the set of valid file lists.
    """

    if file_list is None:
        rfile_list = None
    elif isinstance(file_list, list):
        rfile_list = tuple(cast(list[str], file_list))
    elif isinstance(file_list, str):
        rfile_list = tuple(file_list.split())
    else:
        raise ValueError(f"Expected a string, list of strings, or None, got {file_list!r}.")

    game_patterns.append((pattern, rfile_list))


# Data that we expect the user to set.
# A base name that's used to create the other names.
name: str

# A verbose version to include in the update.
version: str

# The name of directories in the archives.
directory_name: str = ""

# The name of executables.
executable_name: str = ""

# A verbose name to include in package info.
display_name: str = ""

# Should we include update information into the archives?
include_update: bool = False

# The key used for google play.
google_play_key: str | None = None

# The salt used for google play.
google_play_salt: str | None = None

# A list of additional android permission names.
android_permissions: list[str] = []

# The destination things are built in.
destination = "{directory_name}-dists"

# The itch.io project name.
itch_project: str | None = None

# The identity used for codesigning and dmg building.
mac_identity: str | None = None

# The command used for mac codesigning.
mac_codesign_command: list[str] = [
    "/usr/bin/codesign", "--entitlements={entitlements}", "--options=runtime", "--timestamp", "-s", "{identity}",
    "-f", "--deep", "--no-strict", "{app}"]

# The command used to build a dmg.
mac_create_dmg_command: list[str] = ["/usr/bin/hdiutil", "create", "-format", "UDBZ",
                                     "-volname", "{volname}", "-srcfolder", "{sourcedir}", "-ov", "{dmg}"]

# The command used to sign a dmg.
mac_codesign_dmg_command: list[str] = ["/usr/bin/codesign", "--timestamp", "-s", "{identity}", "-f", "{dmg}"]

# Additional or Override keys to add to the Info.plist.
mac_info_plist: dict[str, Any] = {}


package("pc", "zip", ["windows", "linux", "renpy", "all"], "PC: Windows and Linux", platform="win linux")
package("linux", "tar.bz2", ["linux", "linux_arm", "renpy", "all"], "Linux", platform="linux")
package("win", "zip", ["windows", "renpy", "all"], "Windows", platform="win")
package("mac", "app-zip app-dmg", ["mac", "renpy", "all"], "Macintosh", platform="mac")
package("market", "bare-zip", ["windows", "linux", "mac", "renpy", "all"],
        "Windows, Mac, Linux for Markets", platform="win linux mac")
package("steam", "zip", ["windows", "linux", "mac", "renpy", "all"], hidden=True, platform="win linux mac")

package("android-bundle", "android-bundle", ["android", "all"], update=False,
        hidden=True, dlc=True, platform="android", ignore_archives=True)
package("android-apk", "android-apk", ["android", "all"], update=False,
        hidden=True, dlc=True, platform="android", ignore_archives=True)
package("ios", "ios", ["ios", "all"], update=False,
        hidden=True, dlc=True, platform="ios", ignore_archives=True)
package("web", "web", ["web", "renpy", "all"], update=False,
        hidden=True, dlc=True, platform="web", ignore_archives=True)

archive("archive", "all")


def _make_patterns_list(plist: list[tuple[FilesPattern, Any]]):
    rv: list[tuple[FilesPattern, FileListKind]] = []
    for p, file_list in plist:
        if file_list is None:
            rfile_list = None
        elif isinstance(file_list, list):
            rfile_list = tuple(cast(list[str], file_list))
        elif isinstance(file_list, str):
            rfile_list = tuple(file_list.split())
        else:
            raise ValueError(f"Expected a string, list of strings, or None, got {file_list!r}.")
        rv.append((p, rfile_list))
    return rv


def remove_pattern(lst: list[tuple[FilesPattern, FileListKind]], what: tuple[FilesPattern, Any]):
    if what[1] is None:
        rfile_list = None
    elif isinstance(what[1], list):
        rfile_list = tuple(cast(list[str], what[1]))
    elif isinstance(what[1], str):
        rfile_list = tuple(what[1].split())
    else:
        raise ValueError(f"Expected a string, list of strings, or None, got {what[1]!r}.")

    search_w = (what[0], rfile_list)
    lst[:] = [i for i in lst if i != search_w]


# Patterns that are used to classify Ren'Py.
renpy_patterns = _make_patterns_list([
    (f"renpy/**__pycache__/**.{sys.implementation.cache_tag}.pyc", "all"),
    ("renpy/**__pycache__", "all"),

    ("**~", None),
    ("**/#*", None),
    ("**/.*", None),
    ("**.old", None),
    ("**.new", None),
    ("**.rpa", None),

    ("**/steam_appid.txt", None),

    ("renpy.py", "all"),

    ("renpy/", "all"),
    ("renpy/**.py", "renpy"),

    # Ignore Cython source files.
    ("renpy/**.pxd", None),
    ("renpy/**.pxi", None),
    ("renpy/**.pyx", None),

    # Ignore legacy Python bytcode files (unless allowed above).
    ("renpy/**.pyc", None),
    ("renpy/**.pyo", None),

    ("renpy/common/", "all"),
    ("renpy/common/_compat/**", None),
    ("renpy/common/_roundrect/**", None),
    ("renpy/common/_outline/**", None),
    ("renpy/common/_theme**", None),
    ("renpy/common/**.rpy", "renpy"),
    ("renpy/common/**.rpym", "renpy"),
    ("renpy/common/**", "all"),
    ("renpy/**", "all"),

    # Ignore Ren'Py and renpy.exe.
    ("lib/*/renpy", None),
    ("lib/*/renpy.exe", None),
    ("lib/*/pythonw.exe", None),

    # Ignore the wrong Python.
    ("lib/py2-*/", None),

    # Windows patterns.
    ("lib/py*-windows-i686/**", None),
    ("lib/py*-windows-x86_64/**", "windows"),

    # Linux patterns.
    ("lib/py*-linux-i686/**", None),
    ("lib/py*-linux-aarch64/**", "linux_arm"),
    ("lib/py*-linux-armv7l/**", "linux_arm"),
    ("lib/py*-linux-*/**", "linux"),

    # Mac patterns.
    ("lib/py*-mac-*/**", "mac"),

    # Old Python library.
    ("lib/python2.*/**", None),

    # Shared patterns.
    ("lib/**", "windows linux mac android ios"),
    ("renpy.sh", "linux mac"),
])

early_game_patterns = _make_patterns_list([
    ("*.py", None),
    ("*.sh", None),
    ("*.app/", None),
    ("*.dll", None),
    ("*.manifest", None),

    ("lib/", None),
    ("renpy/", None),
    ("update/", None),
    ("common/", None),
    ("update/", None),

    ("old-game/", None),

    ("icon.ico", None),
    ("icon.icns", None),
    ("project.json", None),

    ("log.txt", None),
    ("errors.txt", None),
    ("traceback.txt", None),
    ("image_cache.txt", None),
    ("text_overflow.txt", None),
    ("dialogue.txt", None),
    ("dialogue.tab", None),
    ("profile_screen.txt", None),

    ("files.txt", None),
    ("memory.txt", None),

    ("tmp/", None),
    ("game/saves/", None),
    ("game/bytecode.rpyb", None),

    ("archived/", None),
    ("launcherinfo.py", None),
    ("android.txt", None),

    ("game/presplash*.*", "all"),

    (".android.json", "android"),
    ("android-*.png", "android"),
    ("android-*.jpg", "android"),
    ("ouya_icon.png", None),

    ("ios-presplash.*", "ios"),
    ("ios-launchimage.png", None),
    ("ios-icon.png", None),

    ("web-presplash.png", "web"),
    ("web-presplash.jpg", "web"),
    ("web-presplash.webp", "web"),
    ("progressive_download.txt", "web"),

    ("steam_appid.txt", None),

    (f"game/{renpy.script.BYTECODE_FILE}", "all"),
    ("game/cache/bytecode-311.rpyb", "web"),
    ("game/cache/bytecode-*.rpyb", None),

])

late_game_patterns = _make_patterns_list([
    (".*", None),
    ("**", "all")
])
