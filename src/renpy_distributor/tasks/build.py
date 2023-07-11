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


# Build phase - actually copy and write files.
@task("Sorting and eliminating empty directories...")
def sort_and_clear_empty(context: Context, interface: Interface):
    for packager in context.packagers.values():
        packager.finish_file_list()
    return True


@task("Writing archives...")
def write_archives(context: Context, interface: Interface):
    from ..machinery import Archiver

    if not context.archivers:
        interface.info("No archives to write.")
        return True

    def write(name: str, archiver: Archiver):
        for f in archiver.file_list:
            if f.path is None:
                raise Exception(
                    "Archiver files should be set or filtered before 'write_archives' "
                    f"task run. File with path=None: {f.name!r}")
            archiver.add(f.name, f.path)

        write_length = archiver.write_length()
        yield from ((i, write_length) for i, _ in enumerate(archiver.write(), start=1))

    future_prompts: list[str] = []
    future_args: list[tuple[str, Archiver]] = []
    for name, archiver in context.archivers.items():
        if not archiver.build_request:
            continue

        future_prompts.append(f"Writing the {name} archive")
        future_args.append((name, archiver))

    interface.execute_in_thread_pool(write, future_prompts, future_args)
    return True


@task("Writing packages...")
def write_packages(context: Context, interface: Interface):
    from ..machinery import Packager, FormatKind

    def write(pname: str, format: FormatKind, packager: Packager):

        write_length = packager.write_length()
        yield from ((i, write_length) for i, _ in enumerate(packager.write(), start=1))

    future_prompts: list[str] = []
    future_args: list[tuple[str, str, Packager]] = []
    for (pname, format), packager in context.packagers.items():
        future_prompts.append(f"Writing the {pname} {format} package")
        future_args.append((pname, format, packager))

    interface.execute_in_thread_pool(write, future_prompts, future_args)
    return True


# End phase.
@task("Open distribte directory.")
def open_output_dir(context: Context, interface: Interface):
    from ..machinery import TaskResult

    interface.open_directory(
        "All packages have been built.\n\nDue to the presence of permission information, "
        "unpacking and repacking the Linux and Macintosh distributions on Windows is not supported.",
        context.output_dir)
    return TaskResult.SUCCESS_EXIT
