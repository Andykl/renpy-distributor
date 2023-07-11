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
import time
import enum
import types
import collections

from pathlib import Path
from typing import (
    Any, Callable, Union, Final, Generic,
    Iterable, Literal, NoReturn, TypeVar,
)

from .interface import Interface
from .types import PlatfromSetKind, KNOWN_PLATFORMS

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

    # Path to the RenPy interpreter executable.
    renpy_python: Path

    # Path to the root directory of the project.
    project_dir: Path

    # Path to the Ren'Py SDK directory.
    sdk_dir: Path

    # Path to the directory where temporary files can be stored.
    tmp_dir: Path

    # Log file path. If None, log to devnull.
    log_file: Path

    # Set of platform names to invoke the command for.
    platforms: set[str]

    # Command that the distributor was invoked with.
    command: str

    # Interface-related options.
    silent: bool = False
    verbose: bool = True

    def __init__(self, log_file: str | None, **kwargs: Any):
        if log_file is None:
            log_file = os.devnull
        self.log_file = Path(log_file)
        self.platforms = set()

        self.__dict__.update(kwargs)

    def check_kind(self, kind: PlatfromSetKind):
        build_platforms = self.platforms
        if not build_platforms:
            return True

        return bool(kind.intersection(build_platforms))

    def sdk_path(self, *parts: str):
        """
        Returns a filename in the SDK directory.
        """

        return self.sdk_dir.joinpath(*parts)

    def project_path(self, *parts: str):
        """
        Returns a filename in the project directory.
        """

        return self.project_dir.joinpath(*parts)

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
        cmd.append(str(self.renpy_python))
        cmd.append(str(self.sdk_dir / "renpy.py"))

        cmd.append(str(self.project_dir))
        cmd.extend(args)

        cmd.append("--errors-in-editor")

        return cmd


_ContextT_co = TypeVar("_ContextT_co", bound=Context, covariant=True)


class Runner(Generic[_ContextT_co]):
    def __init__(self, context: _ContextT_co, interface: Interface):
        self._context = context
        self._interface = interface

        self._registered_tasks: dict[str, Task] = {}

    def register_task(self, name: str, task: Task):
        """
        Register a task with the given name.
        """
        if name in self._registered_tasks:
            raise ValueError(f"{name!r} already registered as a task. Unregister it first to replace.")

        self._registered_tasks[name] = task

    def unregister_task(self, name: str):
        """
        Unregister a task with the given name.
        """
        if name not in self._registered_tasks:
            raise ValueError(f"{name!r} does not registered as a task.")
        del self._registered_tasks[name]

    def register_tasks_from(self, module: types.ModuleType):
        """
        Register all tasks from the given module.
        """

        for name, value in vars(module).items():
            if isinstance(value, Task):
                self.register_task(name, value)

    def _compute(self) -> Iterable[Task]:
        all_tasks = self._registered_tasks.copy()

        # For each task, the list of tasks it needs.
        forward = collections.defaultdict[str, list[str]](list)

        # For each task, the list of tasks that needs it.
        reverse = collections.defaultdict[str, list[str]](list)

        for name, task in all_tasks.items():
            for rname in task.requires:
                try:
                    all_tasks[rname]
                except KeyError:
                    raise ValueError(f"Task {name!r} requires unknown task {rname!r}.")
                else:
                    if rname not in forward[name]:
                        forward[name].append(rname)
                    if name not in reverse[rname]:
                        reverse[rname].append(name)

            for dname in task.dependencies:
                try:
                    all_tasks[dname]
                except KeyError:
                    raise ValueError(f"Task {name!r} depends on unknown task {dname!r}.")
                else:
                    if name not in forward[dname]:
                        forward[dname].append(name)
                    if dname not in reverse[name]:
                        reverse[name].append(dname)

        # Actual dependencies of the tasks.
        tasks_dependencies: dict[str, tuple[str]] = {}
        for name in all_tasks:
            depends = tuple(forward.get(name, ()))
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
            cycle_tasks = ', '.join(repr(n) for n in use_cycle)
            raise Exception(
                f"The following tasks use each other in a loop: {cycle_tasks}."
                "This is not allowed.")

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

        self._context.log_file.parent.mkdir(parents=True, exist_ok=True)
        log_f = self._context.log_file.open("w", encoding="utf-8")

        tasks_queue = self._compute()

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
    """
    A task is a wrapper around a function that can be run by the build system.
    """

    def __init__(
        self,
        description: str,
        function: TaskFunction,
        kind: PlatfromSetKind,
        dependencies: Iterable[str] = (),
        requires: Iterable[str] = (),
    ) -> None:
        self.name = function.__name__
        self.description = description
        self.kind = kind
        self.function = function
        self.dependencies = tuple(dependencies)
        self.requires = tuple(requires)

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


def create_task(
    description: str,
    function: TaskFunction, /, *,
    kind: Literal["all"] | str = "all",
    requires: str | None = None,
    dependencies: str | None = None,
):
    """
    Create and return Task instance from task function.
    `description`
        A string description of the task purpose, that will be printed just before the task
        execution (if it was not skipped).
    `function`
        A function with (Context, Interface) -> TaskResult signature, that will be executed
        when the task is run.
    `kind`
        If it is "all" (default), then the task will be run on all platforms.
        Otherwise it should be space-separated list of platforms that the task should be run on.
        If that strings starts with a minus, then it only lists platfroms from where that should be
        excluded.
    `requires`
        If not None, should be a name or space-separated list of names of Tasks this Task needs to be done
        before it.
    `dependencies`
        If not None, should be a name or space-separated list of names of Tasks this Task will precede.
    """

    rkind: PlatfromSetKind
    if kind == "all":
        rkind = KNOWN_PLATFORMS
    else:
        if kind.startswith("-"):
            kind = kind[1:]
            negative = True
        else:
            negative = False

        bad_kinds = set()
        rkind = set()
        for p in kind.split():
            if p not in KNOWN_PLATFORMS:
                bad_kinds.add(p)
            else:
                rkind.add(p)

        if bad_kinds:
            bad_kind = ", ".join(repr(k) for k in bad_kinds)
            raise ValueError(f"Unknown kind(s) {bad_kind!r} in task {function.__name__!r}")

        if negative:
            rkind = {p for p in KNOWN_PLATFORMS if p not in rkind}

    if requires is None:
        rrequires = ()
    else:
        rrequires = requires.split()

    if dependencies is None:
        rdependencies = ()
    else:
        rdependencies = dependencies.split()

    return Task(
        description,
        function,
        rkind,
        rdependencies,
        rrequires,
    )


def task(
    description: str, /, *,
    kind: Literal["all"] | str = "all",
    requires: str | None = None,
    dependencies: str | None = None,
) -> Callable[[TaskFunction], Task]:
    """
    Decorator kind of create_task function.

    `description`
        A string description of the task purpose, that will be printed just before the task
        execution (if it was not skipped).
    `function`
        A function with (Context, Interface) -> TaskResult signature, that will be executed
        when the task is run.
    `kind`
        If it is "all" (default), then the task will be run on all platforms.
        Otherwise it should be space-separated list of platforms that the task should be run on.
        If that strings starts with a minus, then it only lists platfroms from where that should be
        excluded.
    `requires`
        If not None, should be a name or space-separated list of names of Tasks this Task needs to be done
        before it.
    `dependencies`
        If not None, should be a name or space-separated list of names of Tasks this Task will precede.
    """

    def deco(function: TaskFunction):
        return create_task(
            description,
            function,
            kind=kind,
            requires=requires,
            dependencies=dependencies,
        )
    return deco
