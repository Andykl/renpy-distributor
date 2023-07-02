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

import pathlib

from ..machinery import Interface, task, TaskResult
from .. import BuildContext as Context


# Init phase - populate build properties before actual build.
def check_path(
    arg: str | pathlib.Path, name: str, *,
    should_exist: bool = False,
    should_writible: bool = False,
):
    path = pathlib.Path(arg).resolve()
    if should_exist and not path.exists():
        raise FileNotFoundError(f"{name} does not exists.")
    if path.is_file():
        raise NotADirectoryError(f"{name} can not refer to a file.")

    if should_writible:
        path.mkdir(parents=True, exist_ok=True)
        try:
            (path / "test.txt").open("w").close()
            (path / "test.txt").open("r").close()
            (path / "test.txt").unlink()
        except OSError:
            raise Exception(f"{name} is not writable.")

    return path


@task("Checking build properties...", kind="system")
def check_properties(context: Context, interface: Interface):
    context.project_dir = check_path(context.project_dir,
                                     "project-dir", should_exist=True)

    context.sdk_dir = check_path(context.sdk_dir,
                                 "sdk-dir", should_exist=True)

    if not context.tmp_dir:
        context.tmp_dir = context.sdk_path("tmp", context.project_dir.name)

    context.tmp_dir = check_path(context.tmp_dir,
                                 "tmp-dir", should_writible=True)

    if context.fresh and context.tmp_dir.exists():
        import shutil

        # Since LOG-FILE can be in TMP-DIR we can not rmtree it.
        for p in context.tmp_dir.iterdir():
            if p.is_dir():
                shutil.rmtree(p)
            elif p != context.log_file.resolve():
                p.unlink()

    return True


@task(kind="system")
def renpy_to_syspath(context: Context, interface: Interface):
    import sys
    import os

    if pathlib.Path(sys.executable).is_relative_to(context.sdk_dir):
        return TaskResult.SKIPPED

    interface.info("Adding RenPy paths...")

    if str(context.sdk_dir) not in sys.path:
        sys.path.append(str(context.sdk_dir))

    if str(context.sdk_dir / "lib" / "python3.9") not in sys.path:
        sys.path.append(str(context.sdk_dir / "lib" / "python3.9"))

    # Find the python executable to run.
    if os.name == 'nt':
        lib = "py3-windows-x86_64"
    elif sys.platform == "darwin":
        lib = "py3-mac-universal"
    else:
        lib = "py3-linux-x86_64"

    if str(context.sdk_dir / "lib" / lib) not in sys.path:
        sys.path.append(str(context.sdk_dir / "lib" / lib))

    return True


@task("Retrieving build info...", kind="system")
def update_dump(context: Context, interface: Interface):
    from ..machinery import BuildInfo
    import os

    if not context.legacy_build:
        # Common path.
        from importlib.util import spec_from_file_location, module_from_spec
        from ..machinery import default_buildinfo

        buildinfo_py = context.project_path("buildinfo.py")
        modulespec = spec_from_file_location(
            "buildinfo", buildinfo_py)
        if (not buildinfo_py.exists()) or modulespec is None or modulespec.loader is None:
            interface.fail("Could not find 'buildinfo.py' module. "
                           "Check if it exists or run with --legacy-build option.")

        buildinfo = module_from_spec(modulespec)
        for key, value in vars(default_buildinfo).items():
            if not hasattr(buildinfo, key):
                setattr(buildinfo, key, value)

        modulespec.loader.exec_module(buildinfo)
        context.build_info = BuildInfo.from_module(buildinfo)

    else:
        # Legacy path.
        import json

        dump_filename = context.temp_path("dump.json")

        cmd = ["--json-dump", str(dump_filename)]
        if context.force_recompile:
            cmd = ["compile", "--keep-orphan-rpyc"] + cmd
        else:
            cmd = ["quit"] + cmd

        env = os.environ | {"RENPY_LOG_BASE": str(context.tmp_dir)}

        def get_dump():
            return interface.run_subprocess(*context.get_launch_args(*cmd), env=env)

        rv = interface.background("Launching the game", get_dump)
        if (not rv) and dump_filename.exists():
            try:
                with dump_filename.open("r", encoding="utf-8") as f:
                    with f:
                        data = json.load(f)["build"]

                    context.build_info = BuildInfo.from_dump(data)
                rv = 0

            except Exception:
                interface.exception("While reading dump.json...")
                rv = -1
        else:
            rv = -1

        if rv != 0:
            interface.fail("Could not get build data from the project. Please ensure the project runs.")

    output_dir = context.output_dir
    if not output_dir:
        destination = context.build_info.destination
        if not destination:
            interface.fail("Neither OUTPUT-DIR nor destination is set - there is nowhere to write.")
        output_dir = context.project_dir / ".." / destination

    context.output_dir = check_path(output_dir, "output-dir", should_writible=True)
    return True


@task("Checking chosen packages...", kind="system")
def check_package(context: Context, interface: Interface):
    all_packages = list(context.build_info.packages)

    def check_packages(chosen: set[str]):
        if extra := chosen.difference(all_packages):
            interface.info(
                "Selected packages does not exist: "
                f"{', '.join(extra)}. Choose from: {', '.join(all_packages)}.")
            return False
        return True

    chosen: set[str] = context.build_packages
    if chosen and not check_packages(context.build_packages):
        chosen = set()

    if not chosen:
        while True:
            result = interface.input(
                f"Input space-separated packges from {', '.join(all_packages)}:", empty="")

            chosen = set(result.split())
            if check_packages(chosen):
                break

    context.build_packages = chosen
    if not context.build_packages:
        interface.fail("No packages are selected, so there's nothing to do.")
    return True


@task("Initialising build platforms...", kind="system")
def init_build_platforms(context: Context, interface: Interface):
    from ..machinery import PlatfromSetKind

    kinds: PlatfromSetKind = set()
    for name in context.build_packages:
        package = context.build_info.packages[name]
        kinds.update(package.platforms)
    context.build_platforms = kinds
    return True


@task("Initialising clasifier file lists...", kind="system")
def init_classifier_file_lists(context: Context, interface: Interface):
    from ..machinery import FileList

    # TODO: Probably add some cache.
    # Возможно лучше вообще не обрабатывать списки файлов которые не нужны для текущей сборки.
    # Это можно сделать фильтруя [context.build_info.packages[i] for i in context.packages]
    context.classifier_file_lists = {fln: FileList() for fln in context.build_info.file_lists}
    return True
