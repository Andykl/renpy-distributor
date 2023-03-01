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

parser = argparse.ArgumentParser(
    "-m distributor",
    description="Distributor of RenPy games.",
    epilog="Use COMMAND -h to get help for needed command.")
_subparsers = parser.add_subparsers(
    required=True, dest="command", metavar="COMMAND", title="subcommands")


def _add_paths(parser: argparse.ArgumentParser):
    # Paths that needed regardless of command.
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


# Get build info parser.
build_info_parser = _subparsers.add_parser(
    "buildinfo", help="Update and return build info.")
_add_paths(build_info_parser)
build_info_parser.add_argument(
    "--legacy-build", action="store_true",
    help="Compiles the game to retrieve dump with build info."
    " If ommitted, buildinfo.toml file in PROJECT-DIR is expected to exist.")

# Build parser.
build_parser = _subparsers.add_parser("build", help="Build the game.")
build_parser.add_argument("build_packages", nargs="*")
_add_paths(build_parser)
build_parser.add_argument(
    "--output-dir", type=pathlib.Path,
    help="Path to the directory in where result packages will be placed. "
    "If omitted, it is computed based on data from build info."
)

# Switches
build_parser.add_argument(
    "--silent", action="store_true",
    help="Prints only error or success messages to the console"
    " (but the log output remains unchanged).")
build_parser.add_argument(
    "--verbose", action="store_true",
    help="Prints a more verbous output in the console and log.")
build_parser.add_argument(
    "--fresh", action="store_true",
    help="Prevents build to use the cached data from previous build.")
build_parser.add_argument(
    "--force-recompile", action="store_true",
    help="Forces all .rpy scripts to be recompiled during build.")
build_parser.add_argument(
    "--legacy-build", action="store_true",
    help="Compiles the game to retrieve dump with build info."
    " If ommitted, buildinfo.toml file in PROJECT-DIR is expected to exist.")
build_parser.add_argument(
    "--no-update", action="store_false", dest="build_update",
    help="Prevents updates from being built.")


if __name__ == "__main__":
    from .machinery.interface import CLIInterface
    from . import build_game, get_build_info, BuildContext

    args = parser.parse_args()
    if args.command == "build":
        # Convert list to set so we do not lie about our type.
        args.build_packages = set(args.build_packages)

        context = BuildContext(**args.__dict__)
        sys.exit(build_game(context, CLIInterface(context.verbose, context.silent)))

    elif args.command == "buildinfo":
        context = BuildContext(**args.__dict__, silent=True, verbose=True)
        interface = CLIInterface(context.verbose, context.silent)
        print(get_build_info(context, interface))
        sys.exit(0)
