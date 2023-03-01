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

from ..machinery import Interface, task
from .. import BuildContext as Context


# Classyfy phase - populate all file lists, add additional files, etc.
@task("Compiling renpy folder...")
def compile_renpy(context: Context, interface: Interface):
    # This should run before `scan_renpy` so we classify all Python compiled files.
    from ..machinery import TaskResult

    import compileall
    with interface.catch_std(stdout=True, stderr=True, verbose=True):
        return TaskResult(compileall.compile_dir(
            str(context.sdk_dir / "renpy"),
            ddir="renpy/",
            workers=0,
            quiet=(not context.verbose) + context.silent,
            force=True,
        ))


@task("Scanning renpy files...")
def scan_renpy(context: Context, interface: Interface):
    from contextlib import redirect_stdout
    from ..machinery import classify_directory

    p = context.temp_path("renpy_patterns_match.txt")
    with p.open("w", encoding="utf-8") as f, redirect_stdout(f):
        classify_directory(
            "SDK-DIR", context.sdk_dir,
            context.classifier_file_lists,
            context.build_info.renpy_patterns)
    return True


@task("Scanning project files...")
def scan_project(context: Context, interface: Interface):
    from contextlib import redirect_stdout
    from ..machinery import classify_directory

    p = context.temp_path("project_patterns_match.txt")
    with p.open("w", encoding="utf-8") as f, redirect_stdout(f):
        classify_directory("PROJECT-DIR", context.project_dir,
                           context.classifier_file_lists,
                           context.build_info.game_patterns)
    return True


@task("Adding linux files...", kind="linux")
def add_linux_files(context: Context, interface: Interface):
    prefix = f"lib/py3-linux-"
    pattern = f"{prefix}{{}}/{context.build_info.executable_name}"

    # Linux executable files.
    for arch, file_list in {"x86_64": "linux", "armv7l": "linux_arm", "aarch64": "linux_arm"}.items():
        archfn = context.sdk_dir / f"{prefix}{arch}/renpy"
        if archfn.exists():
            context.classifier_file_lists[file_list].add_file(
                pattern.format(arch), archfn, True)

    return True


@task("Adding mac files...", kind="mac")
def add_mac_files(context: Context, interface: Interface):
    """
    Add mac-specific files to the distro.
    """
    import time
    import plistlib

    executable = context.build_info.executable_name
    contents = f"{executable}.app/Contents"
    macos = f"{contents}/MacOS"
    resources = f"{contents}/Resources"
    maclib = f"lib/py3-mac-universal"
    mac_fl = context.classifier_file_lists['mac']

    # Mac executable files.
    mac_fl.add_file(f"{maclib}/{executable}", context.sdk_dir / f"{maclib}/renpy", True)
    mac_fl.add_file(f"{macos}/{executable}", context.sdk_dir / f"{maclib}/renpy", True)

    # Info.plist file.
    plist = {
        "CFBundleDevelopmentRegion": "English",
        "CFBundleDisplayName": context.build_info.display_name,
        "CFBundleExecutable": executable,
        "CFBundleIconFile": "icon",
        "CFBundleIdentifier": "com.domain.game",
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": context.build_info.display_name,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": context.build_info.version,
        "CFBundleVersion": time.strftime("%Y.%m%d.%H%M%S"),
        "LSApplicationCategoryType": "public.app-category.simulation-games",
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeOSTypes": ["****", "fold", "disk"],
                "CFBundleTypeRole": "Viewer",
            },
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeConformsTo": ["public.python-script"],
                "UTTypeDescription": "Ren'Py Script",
                "UTTypeIdentifier": "org.renpy.rpy",
                "UTTypeTagSpecification": {"public.filename-extension": ["rpy"]}
            },
        ],
        "NSHighResolutionCapable": True,
        "NSSupportsAutomaticGraphicsSwitching": True,
        **context.build_info.mac_info_plist,
    }

    with (plist_fn := context.temp_path("Info.plist")).open("wb") as f:
        plistlib.dump(plist, f)
    mac_fl.add_file(f"{contents}/Info.plist", plist_fn)

    # Icon file.
    custom_fn = context.project_dir / "icon.icns"
    default_fn = context.sdk_dir / "launcher/icon.icns"
    if custom_fn.exists():
        icon_fn = custom_fn
    else:
        icon_fn = default_fn
    mac_fl.add_file(f"{resources}/icon.icns", icon_fn)

    # Update mac file list that has lib/py3-mac-universal and lib/python3
    # copied into the mac app.
    python_lib = "lib/python3"
    maclib_len = len(maclib) + 1
    for f in list(mac_fl):
        name = None
        if f.name.startswith(python_lib):
            if fname := f.name:
                name = f"{resources}/{f.name}"

        elif f.name.startswith(maclib):
            if fname := f.name[maclib_len:]:
                name = f"{macos}/{fname}"

        if name is None:
            continue

        mac_fl.add(f.copy(name=name))
        mac_fl.remove(f)

    return True


@task("Adding windows files...", kind="win")
def add_windows_files(context: Context, interface: Interface):
    """
    Adds windows-specific files.
    """

    from .change_icon import change_icons

    icon_fn = context.project_dir / "icon.ico"

    def write_exe(isrc: str, dst: str, itmp: str):
        """
        Write the exe found at `src` (taken as relative to renpy-base)
        as `dst` (in the distribution). `tmp` is the name of a tempfile
        that is written if one is needed.
        """

        src = context.sdk_dir / isrc

        if icon_fn.exists() and src.exists():
            outfile = context.temp_path(itmp)

            with open(outfile, "wb") as f:
                f.write(change_icons(str(src), str(icon_fn)))

        else:
            outfile = src

        if outfile.exists():
            context.classifier_file_lists["windows"].add_file(dst, outfile)

    exe = f"{context.build_info.executable_name}.exe"
    write_exe("lib/py3-windows-x86_64/renpy.exe", exe, exe)
    write_exe("lib/py3-windows-x86_64/pythonw.exe",
              "lib/py3-windows-x86_64/pythonw.exe", "pythonw-64.exe")
    return True


@task("Adding RenPy files...")
def add_renpy_game_files(context: Context, interface: Interface):
    """
    Add Ren'Py file to the game.
    """

    if (license_txt := context.sdk_dir / "LICENSE.txt").exists():
        context.classifier_file_lists["renpy"].add_file("renpy/LICENSE.txt", license_txt)

    if not (context.project_path("game/script_version.rpy").exists() or
            context.project_path("game/script_version.rpyc").exists()):
        import renpy
        from typing import cast

        script_version_txt = context.temp_path("script_version.txt")
        with script_version_txt.open("w", encoding="utf-8") as f:
            f.write(repr(cast(tuple[str, str, str], renpy.version_tuple[:-1])))

        context.classifier_file_lists["all"].add_file("game/script_version.txt", script_version_txt)
    return True


@task("Marking executables...", kind="linux mac")
def mark_executable(context: Context, interface: Interface):
    """
    Marks files as executable.
    """
    from ..machinery import file_match_pattern

    xbit_patterns = context.build_info.xbit_patterns
    for fl in context.classifier_file_lists.values():
        for f in fl:
            for pat in xbit_patterns:
                if file_match_pattern(f.name, pat):
                    f.executable = True
    return True


@task("Renaming files...")
def rename(context: Context, interface: Interface):
    """
    Rename files in all lists to match the executable names.
    """

    from ..machinery import FileList

    def rename_one(fn: str):
        parts = fn.split('/')
        p = parts[0]

        if p == "renpy.sh":
            p = f"{context.build_info.executable_name}.sh"
        elif p == "renpy.py":
            p = f"{context.build_info.executable_name}.py"

        parts[0] = p
        return "/".join(parts)

    for k, fl in context.classifier_file_lists.items():
        context.classifier_file_lists[k] = FileList(
            *(f.copy(name=rename_one(f.name)) for f in fl))
    return True


@task()
def move_sdk_fonts(context: Context, interface: Interface):
    if (
            context.project_dir == context.sdk_dir / "the_question" or
            context.project_dir == context.sdk_dir / "tutorial"):
        interface.info("Moving SDK fonts...")
        for fl in context.classifier_file_lists.values():
            fl.reprefix("sdk-fonts/", "game/")
    return True
