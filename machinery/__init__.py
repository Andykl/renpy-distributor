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

from . import (
    file_utils as file_utils,
    interface as interface,
    archiver as archiver,
    packager as packager,
    buildinfo as buildinfo,
)

# Export all typing helpers.
from .types import *

# Export file utils.
from .file_utils import (
    File as File,
    FileList as FileList,
    classify_directory as classify_directory,
    hash_file as hash_file,
    match as file_match_pattern,  # type: ignore
)

# Export abstract types to extend by third party.
from .interface import Interface as Interface
from .archiver import Archiver as Archiver
from .packager import Packager as Packager

# Export build info types.
from .buildinfo import (
    BuildInfo as BuildInfo,
    Package as Package,
    Archive as Archive
)


# Export functions to register and init packager and archiver types.
from .archiver import (
    init_archiver as init_archiver,
    register_archiver_type as register_archiver_type
)
from .packager import (
    init_packager as init_packager,
    register_packager_type as register_packager_type,
    get_packager_modifiers as get_packager_modifiers,
)

# Export all the needed stuff from model.
from .model import (
    TaskResult as TaskResult,
    Context as Context,
    Runner as Runner,
    task as task,
    create_task as create_task,
    clear_tasks as clear_tasks,
)

import os
from typing import cast

CONVERT_LIB: Literal["PIL", "pygame"] = cast(
    Literal["PIL", "pygame"],
    os.environ.get("RENPY_DISTRIBUTOR_CONVERT_LIB", "pygame"))

del os, cast

if True:
    from . import packager

    # Register base formats
    register_packager_type("zip", packager.ZipPackager, ".zip", modifiers={"prepend"})
    register_packager_type("app-zip", packager.ZipPackager, ".zip", modifiers={"app"})
    register_packager_type("bare-zip", packager.ZipPackager, ".zip")
    register_packager_type("directory", packager.DirectoryPackager, "")
    register_packager_type("app-directory", packager.DirectoryPackager, "-app", modifiers={"app"})
    register_packager_type("tar.bz2", packager.TarPackager, ".tar.bz2", extra_args=["w:bz2"], modifiers={"prepend"})
    register_packager_type("dmg", packager.DMGPackager, "-dmg", modifiers={"dmg", "prepend"})
    register_packager_type("app-dmg", packager.DMGPackager, "-app-dmg", modifiers={"app", "dmg"})
    register_packager_type("bare-tar.bz2", packager.TarPackager, ".tar.bz2", extra_args=["w:bz2"])

    # Special packagers used in other systems.
    register_packager_type("android-bundle", packager.RaisePackager, "", extra_args=[
                           "Could not build android package because RAPT is not installed."])
    register_packager_type("android-apk", packager.RaisePackager, "", extra_args=[
                           "Could not build android package because RAPT is not installed."])
    register_packager_type("web", packager.RaisePackager, "", extra_args=[
                           "Could not build web package because web support is not installed."])
    register_packager_type("ios", packager.RaisePackager, "", extra_args=["RENIOS"])

    del packager

if True:
    from . import archiver

    register_archiver_type("rpa", archiver.RenPyRPA3Archiver, ".rpa")

    del archiver
