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
import argparse

if __name__ == "__main__" and not __package__:
    if str(pathlib.Path(__file__).parents[2]) not in sys.path:
        sys.path.append(str(pathlib.Path(__file__).parents[2]))
    __package__ = "build.distributor"

from . import machinery, BuildContext, CLIInterface

parser = argparse.ArgumentParser(
    "-m distributor",
    description="Distributor of RenPy games.",
    epilog="Use COMMAND -h to get help for needed command.")

# Paths that are required for all commands.
parser.add_argument(
    "--project-dir", type=pathlib.Path, required=True,
    help="Path to the root of project to build.")
parser.add_argument(
    "--sdk-dir", type=pathlib.Path, required=True,
    help="Path to the root of RenPy SDK.")
parser.add_argument(
    "--tmp-dir", type=pathlib.Path,
    help="Path to the tmp directory."
    "If ommitted, defaults to SDK-DIR/tmp.")
parser.add_argument(
    "--log-file", type=pathlib.Path,
    help="The name of the log file to write build progress. "
    " If ommitted, only prints to the console.")

# Switches that are expected to be used by all commands.
parser.add_argument(
    "--legacy-build", action="store_true",
    help="Compiles the game to retrieve dump with build info."
    " If ommitted, buildinfo.toml file in PROJECT-DIR is expected to exist.")
parser.add_argument(
    "--silent", action="store_true",
    help="Prints only error or success messages to the console"
    " (but the log output remains unchanged).")
parser.add_argument(
    "--verbose", action="store_true",
    help="Prints a more verbous output in the console and log.")

_subparsers = parser.add_subparsers(
    required=True, dest="command", metavar="COMMAND", title="subcommands")


# Build parser.
build_parser = _subparsers.add_parser("build", help="Build the game.")
build_parser.add_argument("build_packages", nargs="*")
build_parser.add_argument(
    "--output-dir", type=pathlib.Path,
    help="Path to the directory in where result packages will be placed. "
    "If omitted, it is computed based on data from build info."
)
build_parser.add_argument(
    "--fresh", action="store_true",
    help="Prevents build to use the cached data from previous build.")
build_parser.add_argument(
    "--force-recompile", action="store_true",
    help="Forces all .rpy scripts to be recompiled during build.")
build_parser.add_argument(
    "--no-update", action="store_false", dest="build_update",
    help="Prevents updates from being built.")


if __name__ == "__main__":
    from .tasks import system, classify, prepare_build, build
    from .web import tasks as web_tasks
    from .rapt import tasks as rapt_tasks

    args = parser.parse_args()
    context = BuildContext(**args.__dict__)
    interface = CLIInterface(context.verbose, context.silent)
    runner = machinery.Runner(context, interface)

    # Register all system tasks.
    runner.register_tasks_from(system)
    runner.register_tasks_from(classify)
    runner.register_tasks_from(prepare_build)
    runner.register_tasks_from(build)
    runner.register_tasks_from(web_tasks)
    runner.register_tasks_from(rapt_tasks)

    sys.exit(runner.run())
