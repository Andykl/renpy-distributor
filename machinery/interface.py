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

import io
from math import ceil
import os
import subprocess
import sys
import abc
import time
import textwrap
import platform
import traceback
import contextlib
import threading
import webbrowser
import requests

import concurrent.futures as futures

from pathlib import Path
from typing import (
    Any, Callable, Generator, Generic,
    Iterator, Literal, NoReturn,
    TypeVar, Iterable, cast
)


class InterfaceExit(SystemExit):
    pass


class FutureException(RuntimeError):
    def __init__(self, index: int) -> None:
        super().__init__(index)
        self.index = index


_T = TypeVar("_T")
PoolGenerator = Generator[tuple[int, int], None, _T]


class ProgressBar(Generic[_T]):
    StatusKind = Literal["progress", "done", "halted", "error"]

    _entities_progress: list[_T] | list[None]

    def __init__(self, *entities: str) -> None:
        self.length = len(entities)
        self.entities = entities
        self._entities_progress = [None for _ in entities]
        self._entities_status: list[ProgressBar.StatusKind] = ["progress" for _ in entities]

    @property
    def completed(self):
        return all(i in {"done", "error", "halted"} for i in self._entities_status)

    def update_entity(self, index: int, value: _T):
        if self._entities_status[index] in {"done", "error", "halted"}:
            return

        _entities_progress = cast(list[_T], self._entities_progress)
        _entities_progress[index] = value

    def done_enitity(self, index: int):
        if self._entities_status[index] != "error":
            self._entities_status[index] = "done"

    def halt_entity(self, index: int):
        if self._entities_status[index] != "error":
            self._entities_status[index] = "halted"

    def error_entity(self, index: int, *, halt_others: bool = False):
        if halt_others:
            self._entities_status = ["halted" for _ in self.entities]
        self._entities_status[index] = "error"

    def iter_entities(self):
        for i in range(len(self.entities)):
            yield self.entities[i], self._entities_progress[i], self._entities_status[i]


class Interface(abc.ABC):
    """
    Abstract class representing interface to interact with user.
    """

    @abc.abstractmethod
    def __init__(self, verbose: bool, silent: bool):
        self.verbose = verbose
        self.silent = silent

        self.progress_bar: ProgressBar[Any] | None = None

        # Holds the interactions result.
        self.interactions: list[str] = []

    def system_info(self, prompt: str):
        sys.__stdout__.write(prompt + "\n")

    def log(self, file: io.TextIOWrapper):
        for line in self.interactions:
            print(line, file=file)
            file.flush()
        self.interactions.clear()

    @contextlib.contextmanager
    def catch_std(self, *, stdout: bool = False, stderr: bool = False, verbose: bool = False):
        """
        Context manager which redirects its content `stdout` and/or `stderr`
        into Interface.info with `verbose` flag.
        """

        reporter = self

        class redirector(io.StringIO):
            def write(self, prompt: str):
                if prompt.strip():
                    reporter.info(prompt, verbose=verbose)
                    return len(prompt)
                return 0

        if stdout:
            stdout_m = contextlib.redirect_stdout(redirector())
        else:
            stdout_m = contextlib.nullcontext()

        if stderr:
            stderr_m = contextlib.redirect_stderr(redirector())
        else:
            stderr_m = contextlib.nullcontext()

        with stdout_m, stderr_m:
            yield

    @contextlib.contextmanager
    def try_or_fail(self, prompt: str):
        try:
            yield
        except Exception:
            self.fail(prompt)

    # Information methods
    @abc.abstractmethod
    def info(self, prompt: str, verbose: bool = False) -> None:
        """
        Displays `prompt` as an informational message.
        """

    @abc.abstractmethod
    def success(self, prompt: str) -> None:
        """
        Displays `prompt` as a success message.
        """

    @abc.abstractmethod
    def final_success(self, prompt: str) -> NoReturn:
        """
        Displays `prompt` as the last success message of an operation.
        """
        raise InterfaceExit(0)

    @abc.abstractmethod
    def exception(self, prompt: str, exception: BaseException | None = None) -> None:
        """
        Displays `prompt` as the source of exception and prints
        last occurred exception.
        """

    @abc.abstractmethod
    def fail(self, prompt: str) -> NoReturn:
        """
        Causes the program to terminate with a `prompt` message and error return code code.
        """
        raise InterfaceExit(-1)

    # Interaction methods
    @abc.abstractmethod
    def pause(self, prompt: str) -> None:
        """
        Displays `prompt` to the user and waits for user acknowledgement.
        """

    @abc.abstractmethod
    def input(self, prompt: str, empty: str | None = None) -> str:
        """
        Prompts the user for input. The input is expected to be a string, which
        is stripped of leading and trailing whitespace. If `empty` is not None,
        empty strings are allowed and `empty` is used as result. Otherwise,
        they are not.
        """

    @abc.abstractmethod
    def choice(self, prompt: str, choices: list[tuple[Any, str]], default: Any | None = None) -> Any:
        """
        Prompts the user with prompt, and then presents him with a list of
        choices.

        `choices`
            A list of (value, label) tuples.

        `default`
            If not None, should be one of the values. The value that we use
            return if the user just hits enter.
        """

    @abc.abstractmethod
    def yesno(self, prompt: str) -> bool:
        """
        Prompts the user for a response to a yes or no question.
        """

    @abc.abstractmethod
    def yesno_choice(self, prompt: str, default: bool | None = None) -> bool:
        """
        Prompts the user for a response to a yes or no question.

        This can also take a default, and indicates which of yes or no
        is currently selected, if any.
        """

    # Other methods
    @abc.abstractmethod
    def terms(self, prompt: str, url: str) -> None:
        """
        Displays `url` to the user, and then prompts the user to accept the
        terms and conditions.

        If the user doesn't accept, gives up.
        """

    @abc.abstractmethod
    def open_directory(self, prompt: str, directory: Path) -> None:
        """
        Opens the directory, and display the prompt to explain why.
        """

    def download(self, prompt: str, url: str, outfile: Path) -> None:
        """
        Opens the directory, and display the prompt to explain why.
        """

        response = requests.get(url, stream=True)

        # Error out if the request failed.
        response.raise_for_status()

        total_length = response.headers.get('Content-Length')
        if total_length is None:
            def write_file_background():
                with outfile.open("wb") as f:
                    f.write(response.content)

            self.background(prompt, write_file_background)

        else:
            chunk_size = 4096
            total = ceil(int(total_length) / chunk_size)

            def write_file_chunk():
                with outfile.open("wb") as f:
                    content_iter = response.iter_content(chunk_size)
                    for i, data in enumerate(content_iter, start=1):
                        f.write(data)
                        yield (i, total)

            self.execute_in_thread_pool(write_file_chunk, [prompt], [[]])

    def run_subprocess(self, *args: str,
                       cancel: bool = False, yes: bool = False,
                       **kwargs: Any) -> int:
        """
        Executes `args` as a program. Raises subprocess.CalledProcessError
        if the program fails.

        `cancel`
            If true, this is an expensive call that the user may be offered
            the opportunity to cancel. in some Interfaces could be omitted.

        `yes`
            Repeatedly sends 'y\n' to the command's stdin, and in this case
            `stdin/out/err` keyword can not be used.

        `kwargs`
            Other keywords passed to Popen constructor.
        """

        yes_thread = None
        if yes:
            for key in ("stdin", "stdout", "stderr"):
                if kwargs.get(key) is not None:
                    raise Exception(f"'yes' and '{key}' can not be used at the same time.")

            kwargs["stdin"] = subprocess.PIPE

            def write_n():
                while p.poll() is None:
                    time.sleep(0.33)
                    assert p.stdin is not None
                    try:
                        p.stdin.write(b'y\n')  # type: ignore
                        p.stdin.flush()
                    except:
                        pass

            yes_thread = threading.Thread(target=write_n, daemon=True)

        p = subprocess.Popen(args, **kwargs)
        if yes_thread is not None:
            yes_thread.start()

        return p.wait()

    def background(self, prompt: str, f: Callable[..., _T],
                   *func_args: Any, timeout: float = 0.33,
                   raise_on_exception: bool = True,) -> _T | Exception:
        """
        Runs f in the background, if possible. Returns when f has finished.

        (This is intended to inform user that _something_ happens, and the
        system does not stuck.)
        """

        start = time.perf_counter_ns()
        progress_bar = self.start_progress_bar(prompt)

        def update_progress_bar():
            elapsed = (time.perf_counter_ns() - start) / 1_000_000_000
            self.update_progress_bar(f"{elapsed:.3f}s.")

        with futures.ThreadPoolExecutor() as pool:
            future = pool.submit(f, *func_args)
            while True:
                try:
                    return_value = future.result(timeout)

                except futures.TimeoutError:
                    update_progress_bar()

                except Exception as exc:
                    if raise_on_exception:
                        progress_bar.error_entity(0)
                        update_progress_bar()
                        self.end_progress_bar()
                        raise
                    else:
                        update_progress_bar()
                        self.end_progress_bar()
                        return exc

                except BaseException:
                    update_progress_bar()
                    self.end_progress_bar()
                    raise

                else:
                    progress_bar.done_enitity(0)
                    update_progress_bar()
                    self.end_progress_bar()
                    return return_value

    def execute_in_thread_pool(
            self, func: Callable[..., PoolGenerator[_T]],
            tasks_prompts: Iterable[str],
            tasks_args: Iterable[Iterable[Any]], *,
            timeout: float = 0.33,
            raise_on_exception: bool = True,
    ) -> tuple[tuple[int, FutureException | _T]]:
        return tuple(i for i in self.run_in_thread_pool(
            func, tasks_prompts, tasks_args,
            timeout=timeout, raise_on_exception=raise_on_exception))

    def run_in_thread_pool(
            self, func: Callable[..., PoolGenerator[_T]],
            tasks_prompts: Iterable[str],
            tasks_args: Iterable[Iterable[Any]], *,
            timeout: float = 0.33,
            raise_on_exception: bool = True,
    ) -> Iterator[tuple[int, FutureException | _T]]:
        """
        TODO
        """

        tasks_prompts = list(tasks_prompts)
        tasks_args = list(tasks_args)

        assert len(tasks_prompts) == len(
            tasks_args), "Length of prompts and args mismatch, probably you wanted to use args = [[], ...]."

        progress_bar = self.start_progress_bar(*tasks_prompts)

        def update_func_progress(index: int, func: Callable[..., PoolGenerator[_T]], *args: Any) -> _T:
            func_gen = func(*args)
            while True:
                try:
                    complete, total = next(func_gen)
                except StopIteration as e:
                    return e.value

                progress_bar.update_entity(index, f"{complete}/{total}")

        future_to_i: dict[futures.Future[_T], int] = {}
        with futures.ThreadPoolExecutor() as pool:
            for i, args in enumerate(tasks_args):
                future = pool.submit(update_func_progress, i, func, *args)
                future_to_i[future] = i

            while future_to_i:
                waitr = futures.wait(
                    future_to_i, timeout=timeout, return_when=futures.FIRST_COMPLETED)

                self.update_progress_bar()
                for future in waitr.done:
                    i = future_to_i.pop(future)
                    progress_bar.done_enitity(i)

                    try:
                        data = future.result()

                    except Exception as exc:
                        if raise_on_exception:
                            progress_bar.error_entity(i, halt_others=True)
                            self.end_progress_bar()

                            raise FutureException(i) from exc
                        else:
                            data = FutureException(i)
                            data.__cause__ = exc
                            yield (i, data)

                    except BaseException:
                        self.end_progress_bar()
                        raise

                    else:
                        yield (i, data)

            self.end_progress_bar()

    @abc.abstractmethod
    def start_progress_bar(self, *entities_prompt: str) -> ProgressBar[Any]:
        if self.progress_bar is not None:
            raise RuntimeError("Can not start progress bar with another one in progress.")

        self.progress_bar = ProgressBar(*entities_prompt)
        return self.progress_bar

    @abc.abstractmethod
    def update_progress_bar(self, *entities_progress: Any) -> None:
        if self.progress_bar is None:
            raise RuntimeError("There is no current progress bar to update.")

        if entities_progress:
            assert len(entities_progress) == self.progress_bar.length
            for i, value in enumerate(entities_progress):
                self.progress_bar.update_entity(i, value)

    @abc.abstractmethod
    def end_progress_bar(self) -> None:
        self.progress_bar = None


class CLIInterface(Interface):
    """
    Displays progress on the command line.
    """

    progress_bar: ProgressBar[str] | None

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
        raise InterfaceExit(0)

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
        raise InterfaceExit(-1)

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

    def choice(self, prompt: str, choices: list[tuple[Any, str]], default: Any | None = None):

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

    def open_directory(self, prompt: str, directory: Path):
        self.info(prompt, True)
        if os.name == 'nt':
            os.startfile(directory)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(directory)])
        else:
            subprocess.Popen(["xdg-open", str(directory)])

    def start_progress_bar(self, *entities_prompt: str) -> ProgressBar[str]:
        progress_bar = super().start_progress_bar(*entities_prompt)
        self._write(self._progress_bar_string(progress_bar), False, False, False)
        return progress_bar

    def _progress_bar_string(self, bar: ProgressBar[str]):
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
        progress_bar = cast(ProgressBar[str], self.progress_bar)

        rv = self._progress_bar_string(progress_bar)
        self._write(f"\033[{progress_bar.length}F{rv}", False, False, False)

    def end_progress_bar(self) -> None:
        if self.progress_bar is None:
            return

        self._write(f"\033[{self.progress_bar.length + 1}F", False, False, False)
        self._write(self._progress_bar_string(self.progress_bar), True, False, False)
        super().end_progress_bar()
