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
import enum
import collections

from pathlib import Path
from typing import (
    Any, Callable, Union, Final, Generic,
    Iterable, Literal, NoReturn, TypeVar, cast,
)

from .interface import Interface
from .types import PlatfromSetKind, TaskKind
from .types import KNOWN_PLATFORMS

DEBUG: Final[bool] = bool(int(os.getenv("RENPY_DISTRIBUTOR_DEBUG", "0")))


class TaskResult(enum.IntEnum):
    KEYBOARD_INTERRUPT = -3
    FAILURE_EXIT = -2
    EXCEPTION = -1
    FAILURE = 0
    SUCCESS = 1
    SKIPPED = 2
    SUCCESS_EXIT = 3

    def __bool__(self):
        return self._value_ > 0


# TODO: typing.dataclass_transform
class Context:
    """
    Namespace created once per programm run and contain fields
    essential for any programm.
    """

    _renpy_python: Path

    project_dir: Path
    sdk_dir: Path
    tmp_dir: Path
    log_file: Path

    command: str

    silent: bool
    verbose: bool

    def __init__(self, **kwargs: Any):
        self.__dict__.update(kwargs)

    def __post_init__(self):
        # Find the python executable to run.
        if os.name == 'nt':
            executable = "python.exe"
            lib = "py3-windows-x86_64"
        elif sys.platform == "darwin":
            executable = "python"
            lib = "py3-mac-universal"
        else:
            executable = "python"
            lib = "py3-linux-x86_64"
        executable_path = self.sdk_dir / "lib" / lib / executable

        if not executable_path.exists():
            raise Exception(f"RenPy interpreter does not exists: {executable_path}")

        self._renpy_python = executable_path

    def check_kind(self, kind: TaskKind):
        if kind == "system":
            return True

        build_platforms: set[str] = self.build_platforms  # type: ignore
        assert build_platforms, "All tasks before build_platfroms is set must be 'system' kind."
        return bool(kind.intersection(build_platforms))

    def sdk_path(self, *parts: str):
        """
        Returns a filename in the SDK directory.
        """

        rv = self.sdk_dir.joinpath(*parts)
        return rv

    def project_path(self, *parts: str):
        """
        Returns a filename in the project directory.
        """

        rv = self.project_dir.joinpath(*parts)
        return rv

    def temp_path(self, *parts: str):
        """
        Returns a filename in the temporary directory.
        """

        rv = self.tmp_dir.joinpath(*parts)
        rv.parent.mkdir(parents=True, exist_ok=True)
        return rv

    def get_launch_args(self, *args: str):
        """
        Construct and return arguments needed to launch project via RenPy.
        """

        # Put together the basic command line.
        cmd: list[str] = []
        cmd.append(str(self._renpy_python))
        cmd.append(str(self.sdk_dir / "renpy.py"))

        cmd.append(str(self.project_dir))
        cmd.extend(args)

        cmd.append("--errors-in-editor")

        return cmd


_ContextT = TypeVar("_ContextT", bound=Context, covariant=True)


class Runner(Generic[_ContextT]):
    def __init__(self, context: _ContextT, interface: Interface):
        self._context = context
        self._interface = interface

        context.__post_init__()

        self.all_tasks: dict[str, tuple[Task, list[str], list[str]]] = {}

    def register(
            self, name: str, task: Task,
            requires: list[str],
            dependencies: list[str]
    ):
        if name in self.all_tasks:
            raise ValueError(f"{name!r} already registered as a task. Unregister it first to replace.")

        self.all_tasks[name] = (task, requires, dependencies)

    def unregister(self, name: str):
        if name not in self.all_tasks:
            raise ValueError(f"{name!r} does not registered as a task.")
        del self.all_tasks[name]

    def get_tasks_from(self, module_name: str):
        for (mod, name), (task, requires, dependencies) in _all_tasks.items():
            if mod == module_name:
                self.register(name, task, requires, dependencies)

    def compute(self) -> Iterable[Task]:
        all_tasks = {k: v[0] for k, v in self.all_tasks.items()}

        # For each task, the list of tasks it needs.
        forward: collections.defaultdict[str, list[str]] = collections.defaultdict(list)

        # For each task, the list of tasks that needs it.
        reverse: collections.defaultdict[str, list[str]] = collections.defaultdict(list)

        # Set of unknown tasks names.
        unknown_depends: set[str] = set()

        for name, (task, requires, dependencies) in self.all_tasks.items():
            for rname in requires:
                try:
                    all_tasks[rname]
                except KeyError:
                    unknown_depends.add(rname)
                else:
                    if rname not in forward[name]:
                        forward[name].append(rname)
                    if name not in reverse[rname]:
                        reverse[rname].append(name)

            for dname in dependencies:
                try:
                    all_tasks[dname]
                except KeyError:
                    unknown_depends.add(dname)
                else:
                    if name not in forward[dname]:
                        forward[dname].append(name)
                    if dname not in reverse[name]:
                        reverse[name].append(dname)

        if unknown_depends:
            raise Exception(f"Task dependencies refers to unknown tasks: {', '.join(unknown_depends)}")

        # Actual dependencies of the tasks.
        tasks_dependencies: dict[str, tuple[str]] = {}
        prev_task = None
        for name in all_tasks:
            depends = tuple(forward.get(name, ()))

            # All tasks implicitly requires previous task
            if not (depends or prev_task is None):
                requires = (prev_task, )

            prev_task = name
            tasks_dependencies[name] = depends

        # But still there could be a cicle of tasks dependencies.
        workset = {k for k in all_tasks if k not in forward}
        while workset:
            name = workset.pop()

            for i in reverse[name]:
                d = forward[i]
                d.remove(name)

                if not d:
                    workset.add(i)

            del reverse[name]

        if use_cycle := sorted(reverse):
            raise Exception(
                f"The following tasks use each other in a loop: {', '.join(use_cycle)}. This is not allowed.")

        # Actually compute tasks order.
        task_indexes: dict[Task, int] = {}
        tasks_order = {n: i for i, n in enumerate(all_tasks)}

        def place_task(name: str, task: Task) -> int:
            if task in task_indexes:
                return task_indexes[task]

            if tasks_dependencies[name]:
                index = 0
                for dname in tasks_dependencies[name]:
                    index = max(index, place_task(dname, all_tasks[dname]) + 1)
            else:
                index = tasks_order[name]

            task_indexes[task] = index
            return index

        for name, task in all_tasks.items():
            place_task(name, task)

        yield from task_indexes

    def run(self) -> int:
        start = time.perf_counter_ns()

        if self._context.log_file is None:  # type: ignore
            self._context.log_file = Path(os.devnull)
        else:
            self._context.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_f = self._context.log_file.open("w", encoding="utf-8")

        tasks_queue = self.compute()

        if DEBUG:
            tasks_queue = list(tasks_queue)
            self._interface.system_info(f"DEBUG: Build tasks:")
            for task in tasks_queue:
                self._interface.system_info(f"    {task}")

        result = 0
        for task in tasks_queue:
            result = task.run(self._context, self._interface)
            self._interface.log(log_f)

            if result == TaskResult.SUCCESS_EXIT:
                result = 0
            elif result == TaskResult.KEYBOARD_INTERRUPT:
                result = 2
            elif result <= 0:
                result = 1
            else:
                continue
            break

        elapsed = (time.perf_counter_ns() - start) / 1_000_000_000
        if result == 0:
            self._interface.info(f"Build has ended successfully, took {elapsed:.3f}s.")
        else:
            self._interface.info(f"Build has ended with failure, took {elapsed:.3f}s.")
        return result


TaskFunction = Callable[..., Union[TaskResult, bool, NoReturn]]


class Task:
    def __init__(
        self, name: str,
        description: str | None,
        kind: TaskKind,
        function: TaskFunction,
    ) -> None:
        self.name = name
        self.description = description
        self.kind: TaskKind = kind
        self.function = function

    def __repr__(self):
        return f"<Task: {self.name}>"

    def run(self, context: Context, interface: Interface) -> TaskResult:
        function = self.function
        if not context.check_kind(self.kind):
            if DEBUG:
                interface.system_info(f"DEBUG: {self!r} skipped.")
            return TaskResult.SKIPPED

        start = time.perf_counter_ns()
        if DEBUG:
            interface.system_info(f"DEBUG: {self!r} has started.")

        if self.description is not None:
            interface.info(self.description)

        try:
            result = function(context, interface)
        except Exception:
            interface.end_progress_bar()
            interface.exception(f"Exception in {self}")
            result = TaskResult.EXCEPTION
        except SystemExit as e:
            if e.code == 0:
                result = TaskResult.SUCCESS_EXIT
            else:
                result = TaskResult.FAILURE_EXIT
        except KeyboardInterrupt:
            result = TaskResult.KEYBOARD_INTERRUPT

        if not isinstance(result, TaskResult):
            if result:
                result = TaskResult.SUCCESS
            else:
                result = TaskResult.FAILURE

        if DEBUG:
            elapsed = (time.perf_counter_ns() - start) / 1_000_000_000
            interface.system_info(
                f"DEBUG: {self!r} has ended with {result._name_}, took {elapsed:.3f}s.")

        return result


_all_tasks: dict[tuple[str, str], tuple[Task, list[str], list[str]]] = {}


def task(
    description: str | None = None, /, *,
    kind: Literal["all", "system"] | str = "all",
    requires: str | None = None,
    dependencies: str | None = None,
):
    """
    This is a decorator that wraps a function (with signature (Context, Reporter) -> bool | TaskResult)
    to define a task.

    `description` is a short declaration of what that task do or None if it is conditional.
    This also takes optional keyword arguments.
    `kind`
        A string giving a kind of that task. It can be "system" to always run.
        Or it can be "all" to run if any platfrom was selected to build.
        Otherwise it should be space-separated list of platforms that the task should be run on.
        If that strings starts with a minus, then it only lists platfroms from where that should be
        excluded.
    `requires`
        If not None, should be a name or space-separated list of names of Tasks this Task needs to be done
        before it.
    `dependencies`
        If not None, should be a name or space-separated list of names of Tasks this Task will precede.
    """

    def register_task(function: TaskFunction):
        task = create_task(description, function, kind=kind)

        if requires is None:
            rrequires = []
        else:
            rrequires = requires.split()

        if dependencies is None:
            rdependencies = []
        else:
            rdependencies = dependencies.split()

        _all_tasks[function.__module__, function.__name__] = (task, rrequires, rdependencies)
        return function

    return register_task


def create_task(
    description: str | None, function: TaskFunction, /, *,
    kind: Literal["all", "system"] | str = "all"
):
    """
    Create and return Task instance without registering it. Arguments meaning is the same
    as in `task` function.
    """

    rkind: TaskKind
    if kind == "system":
        rkind = kind
    elif kind == "all":
        rkind = KNOWN_PLATFORMS
    else:
        if kind.startswith("-"):
            kind = kind[1:]
            negative = True
        else:
            negative = False

        rkind = cast(PlatfromSetKind, set(kind.split()))
        bad_kind = next((p for p in rkind if p not in KNOWN_PLATFORMS), None)
        assert bad_kind is None, f"Unknown kind {bad_kind!r} in task {function.__name__!r}"

        if negative:
            rkind = {p for p in KNOWN_PLATFORMS if p not in rkind}

    return Task(function.__name__, description, rkind, function)


def clear_tasks():
    """
    Resets all defined tasks.
    """
    _all_tasks.clear()
