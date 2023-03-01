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
import pathlib

if __name__ == "__main__" and not __package__:
    if str(pathlib.Path(__file__).parents[2]) not in sys.path:
        sys.path.append(str(pathlib.Path(__file__).parents[2]))
    __package__ = "build.distributor"

from . import machinery

# Missing parts are dmg and codesign, RenIOS, distributor of renpy launcher,
# updates creation, documentation, GUI interface.


class BuildContext(machinery.Context):
    """
    Namespace created once per build representing properties of build process.
    """

    output_dir: pathlib.Path

    fresh: bool
    force_recompile: bool
    legacy_build: bool
    build_update: bool

    build_packages: set[str]
    build_platforms: set[str]

    build_info: machinery.BuildInfo
    classifier_file_lists: dict[machinery.FileListName, machinery.FileList]

    packagers: dict[tuple[str, machinery.FormatKind], machinery.Packager]
    archivers: dict[str, machinery.Archiver]


def import_tasks_from(runner: machinery.Runner[machinery.Context], name: str):
    from importlib import reload, import_module

    if name.startswith('.'):
        depth = name.split(".").count("")
        package_parts = __package__.split(".")

        if depth > len(package_parts):
            raise ImportError("attempted relative import beyond top-level package")

        for _ in range(depth - 1):
            package_parts.pop()

        name = f"{'.'.join(package_parts)}.{name[depth:]}"

    if name in sys.modules:
        mod = reload(sys.modules[name])
    else:
        mod = import_module(name)

    runner.get_tasks_from(name)
    return mod


def build_game(context: BuildContext, interface: machinery.Interface, *tasks_source: str):
    runner = machinery.Runner(context, interface)

    machinery.clear_tasks()
    import_tasks_from(runner, ".tasks.system")
    import_tasks_from(runner, ".tasks.classify")
    import_tasks_from(runner, ".tasks.prepare_build")
    import_tasks_from(runner, ".tasks.build")
    import_tasks_from(runner, ".web.tasks")
    import_tasks_from(runner, ".rapt.tasks")
    for source in tasks_source:
        import_tasks_from(runner, source)
    return runner.run()


def get_build_info(context: BuildContext, interface: machinery.Interface):
    runner = machinery.Runner(context, interface)

    machinery.clear_tasks()
    import_tasks_from(runner, ".tasks.system")
    import_tasks_from(runner, ".web.tasks")
    import_tasks_from(runner, ".rapt.tasks")

    def _(context: BuildContext, interface: machinery.Interface):
        return machinery.TaskResult.SUCCESS_EXIT

    runner.register("exit", machinery.create_task(None, _), ["update_dump"], ["check_package"])

    if runner.run():
        raise Exception("Could not get build info.")

    return context.build_info
