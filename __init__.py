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

import os
import sys
import time
import pathlib
import platform
import textwrap
import traceback
import webbrowser
import subprocess
import typing as t

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

    def __init__(self, build_packages: t.Iterable[str] = (), **kwargs: t.Any):
        super().__init__(**kwargs)
        self.build_packages = tuple(build_packages)

    # Path to the output directory.
    output_dir: pathlib.Path = None  # type: ignore

    # Should we clean tmp directory before build?
    fresh: bool = True

    # Should we force recompilation of all files?
    force_recompile: bool = True

    legacy_build: bool = False
    build_update: bool = True

    # Set of names of packages to build.
    build_packages: tuple[str]

    build_info: machinery.BuildInfo
    classifier_file_lists: dict[machinery.FileListName, machinery.FileList]

    packagers: dict[tuple[str, machinery.FormatKind], machinery.Packager]
    archivers: dict[str, machinery.Archiver]


class CLIInterface(machinery.Interface):
    """
    Displays progress on the command line.
    """

    progress_bar: machinery.interface.ProgressBar[str] | None

    def __init__(self, verbose: bool, silent: bool):
        super().__init__(verbose, silent)
        self.current_progress: str | None = None
        self.progress_delta: bool = False

    def _write(self, s: str, add_interaction: bool, verbose: bool, wrap: bool = True):
        if not s:
            return

        # Special case for \n or \n\n
        elif set(s) == {"\n"}:
            wrap = False

        if wrap:
            wrapped = "\n".join(
                textwrap.fill(i, width=160) for i in s.split("\n\n"))
        else:
            wrapped = s

        # In silent mode print to stdout only if we really need it.
        if (not self.silent) or verbose:
            print(wrapped, file=sys.__stdout__)

        if add_interaction:
            self.interactions.append(wrapped)

    def info(self, prompt: str, verbose: bool = False):
        if verbose and not self.verbose:
            return

        self._write(prompt, True, verbose)

    def success(self, prompt: str):
        self.info(prompt, verbose=True)

    def final_success(self, prompt: str):
        self._write(prompt, True, True)
        super().final_success(prompt)

    def exception(self, prompt: str, exception: BaseException | None = None):
        exc = exception
        if exc is None:
            exc = sys.exc_info()[1]

        if exc is None:
            return

        self._write(f"{prompt} - {exc!r}", True, True, False)
        self.interactions.extend(
            traceback.format_exception(type(exc), exc, exc.__traceback__))

    def fail(self, prompt: str):
        self.pause(prompt)
        super().fail(prompt)

    # Interaction methods
    def pause(self, prompt: str):
        self._write(prompt, True, True)

        if platform.system() == "Windows":
            os.system("pause")
        else:
            os.system("/bin/bash -c 'read -s -n 1 -p \"Press any key to continue...\"'")
            sys.__stdout__.write("\n")

    def input(self, prompt: str, empty: str | None = None):
        orig_prompt = prompt

        if empty:
            prompt += f" [{empty}]> "
        else:
            prompt += " > "

        rv = ""
        while True:
            try:
                rv = input(prompt).strip()
            except BaseException:
                self._write("\n", False, True)
                raise

            if rv:
                break

            if empty is not None:
                rv = empty
                break

        self.interactions.append(f"{orig_prompt} - {rv or 'NO INPUT'}")
        return rv

    def choice(self, prompt: str, choices: list[tuple[t.Any, str]], default: t.Any | None = None):

        default_choice = None

        self._write(prompt, True, True)
        for i, (value, label) in enumerate(choices, start=1):
            if value == default:
                default_choice = i

            self._write(f"{i}) {label}", True, True)

        if default_choice is not None:
            prompt = f"1-{len(choices)} [{default_choice}]> "
        else:
            prompt = f"1-{len(choices)}> "

        while True:
            try:
                choice_s = input(prompt).strip()
            except BaseException:
                self._write("\n", False, True)
                raise

            if choice_s:
                try:
                    choice = int(choice_s)
                except Exception:
                    continue
            elif default_choice is None:
                continue
            else:
                choice = default_choice

            if choice <= 0 or choice > len(choices):
                continue

            choice -= 1
            self.interactions.append(f"Choice result - {choice + 1}")
            return choices[choice][0]

    def yesno(self, prompt: str):
        return self.yesno_choice(prompt)

    def yesno_choice(self, prompt: str, default: bool | None = None):
        orig_prompt = prompt

        if default is True:
            prompt += " yes/no [yes]> "
        elif default is False:
            prompt += " yes/no [no]> "
        else:
            prompt += " yes/no> "

        while True:
            try:
                rv = input(prompt).strip().lower()
            except BaseException:
                self._write("\n", False, True)
                raise

            if rv in ("yes", "y"):
                result = True
            elif rv in ("no", "n"):
                result = False
            elif rv == "" and default is not None:
                result = default
            else:
                continue
            break

        self.interactions.append(f"{orig_prompt} - {'yes' if result else 'no'}")
        return result

    # Other methods
    def terms(self, prompt: str, url: str):
        self.info(f"Opening {url} in a web browser.", True)

        webbrowser.open_new(url)
        time.sleep(.5)

        if not self.yesno(prompt):
            self.fail("You must accept the terms and conditions to proceed.")

    def open_directory(self, prompt: str, directory: pathlib.Path):
        self.info(prompt, True)
        if os.name == 'nt':
            os.startfile(directory)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])

    def start_progress_bar(self, *entities_prompt: str):
        progress_bar = super().start_progress_bar(*entities_prompt)
        self._write(self._progress_bar_string(progress_bar), False, False, False)
        return progress_bar

    def _progress_bar_string(self, bar: machinery.interface.ProgressBar[str]):
        rv: list[str] = []
        for caption, value, status in bar.iter_entities():
            if value is None:
                value = "?"

            extra = ""
            if status == "error":
                extra = " - ERROR"
            elif status == "done":
                extra = " - DONE"
            elif status == "halted":
                extra = " - HALT"
            rv.append(f"{caption}: {value}{extra}")

        return "\n".join(rv)

    def update_progress_bar(self, *entities_progress: str) -> None:
        super().update_progress_bar(*entities_progress)
        progress_bar = t.cast('machinery.interface.ProgressBar[str]', self.progress_bar)

        rv = self._progress_bar_string(progress_bar)
        self._write(f"\033[{progress_bar.length}F{rv}", False, False, False)

    def end_progress_bar(self) -> None:
        if self.progress_bar is None:
            return

        self._write(f"\033[{self.progress_bar.length + 1}F", False, False, False)
        self._write(self._progress_bar_string(self.progress_bar), True, False, False)
        super().end_progress_bar()
