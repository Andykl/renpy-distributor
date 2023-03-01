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

import re
import hashlib
import functools

from pathlib import Path
from typing import Any, AbstractSet, MutableSet

from .types import FileListKind, FileListName, FilesPattern


def classify_directory(
    where: str, directory: Path,
    file_lists: dict[FileListName, FileList],
    patterns: dict[FilesPattern, FileListKind],
):
    """
    Walks through the `directory`, finds files and directories that
    match the pattern, and assigns them to the appropriate file list.
    Directories are matched with a trailing /, but added to the
    file list with the trailing / removed.
    """

    def walk(name: str, path: Path):

        # Ignore ASCII control characters, like (Icon\r on the mac).
        if re.search('[\x00-\x19]', name):
            return

        is_dir = path.is_dir()

        if is_dir:
            match_name = name + "/"
        else:
            match_name = name

        for pattern, file_list in patterns.items():

            if match(match_name, pattern):

                # When we have ('test/**', None), avoid excluding test.
                if file_list is None and is_dir:
                    new_pattern = pattern.rstrip("*")
                    if (pattern != new_pattern) and match(match_name, new_pattern):
                        continue

                break

        else:
            print(f"'{where}/{match_name}' doesn't match anything.")
            return

        if file_list is None:
            file_list_str = "None"
        else:
            file_list_str = repr(" ".join(file_list))
        print(f"'{where}/{match_name}' matches ({pattern!r}, {file_list_str}).")

        if file_list is None:
            return

        for fl in file_list:
            file_lists[fl].add(File(name, path, is_dir, False))

        if is_dir:
            for fn in path.iterdir():
                walk(f"{name}/{fn.name}", fn)

    for fn in directory.iterdir():
        walk(fn.name, fn)


@functools.cache
def hash_file(fn: Path, method: str = "sha256", chunk_size: int = 8 * 1024 * 1024):
    """
    Returns the hash of content of `fn`.
    """

    hash = hashlib.new(method)

    with fn.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hash.update(chunk)

    return hash.hexdigest()


@functools.cache
def match(s: str, pattern: FilesPattern):
    """
    Matches a glob-style pattern against s. Returns True if it matches,
    and False otherwise.

    ** matches every character.
    * matches every character but /.
    [abc] matches a, b, or c.

    Things are matched case-insensitively.
    """

    # Compile a pattern for use with match.
    regexstr = ""

    while pattern:
        if pattern.startswith("**"):
            regexstr += r'.*'
            pattern = pattern[2:]
        elif pattern[0] == "*":
            regexstr += r'[^/]*/?'
            pattern = pattern[1:]
        elif pattern[0] == '[':
            regexstr += r'['
            pattern = pattern[1:]

            while pattern and pattern[0] != ']':
                regexstr += pattern[0]
                pattern = pattern[1:]

            pattern = pattern[1:]
            regexstr += ']'

        else:
            regexstr += re.escape(pattern[0])
            pattern = pattern[1:]

    regexstr += "$"

    regexp = re.compile(regexstr, re.I)

    if regexp.match(s):
        return True

    if regexp.match("/" + s):
        return True

    return False


def _check_file_name(name: str):
    assert name, f"File's `name` can not be empty string."
    assert "\\" not in name, f"File's `name` can not contain forward slash, passed: {name!r}."
    assert not name.startswith("/"), f"File's `name` can not starts with /, passed: {name!r}."
    assert not name.endswith("/"), f"File's `name` can not ends with /, passed: {name!r}."
    assert "//" not in name, f"File's `name` can not contain two backslashes in a row, passed: {name!r}"
    assert {".", ".."}.isdisjoint(
        name.split("/")), f"File's `name` can not contain '.' or '..', passed: {name!r}"


def _merge_files(first: File, second: File):
    # If it is a directory, ignore even if it is different, first added wins.
    if first.directory and second.directory:
        return first if first.path is not None else second

    assert first == second, f"Can not merge files, {first!r} and {second!r} differs."
    return first


class File(object):
    """
    Represents a file that we can distribute.

    self.name
        The name of the file as it will be stored in the archives.
        This is read-only field to prevent corruption of FileLists.

    self.path
        The path to the file on disk. None if it won't be stored
        on disk.

    self.directory
        True if this is a directory.

    self.executable
        True if this is an executable that should be distributed
        with the xbit set.
    """

    def __init__(self, name: str, path: Path | None, directory: bool, executable: bool):
        _check_file_name(name)

        self._name = name
        self.path = path
        self.directory = directory
        self.executable = executable

    @property
    def name(self):
        return self._name

    def __repr__(self):
        if self.directory:
            extra = " dir"
        elif self.executable:
            extra = " x-bit"
        else:
            extra = ""

        return f"<File {self.name!r} {self.path!r}{extra}>"

    def __lt__(self, other: Any):
        if not isinstance(other, File):
            return NotImplemented

        return self.name < other.name

    def __le__(self, other: Any):
        if not isinstance(other, File):
            return NotImplemented

        return self.name <= other.name

    def __gt__(self, other: Any):
        if not isinstance(other, File):
            return NotImplemented

        return self.name > other.name

    def __ge__(self, other: Any):
        if not isinstance(other, File):
            return NotImplemented

        return self.name >= other.name

    def __eq__(self, other: Any):
        if not isinstance(other, File):
            return NotImplemented

        return self.__dict__ == other.__dict__

    def __hash__(self):
        return (
            hash(type(self)) ^
            hash(self.name) ^
            hash(None if self.path is None else self.path.as_posix()) ^
            hash(self.directory) ^
            hash(self.executable)
        )

    def copy(self, *, name: str | None = None):
        return File(name or self.name, self.path, self.directory, self.executable)

    def hash(self, hash: hashlib.sha3_256):
        """
        Update hash with information about this entry.
        """

        key = (self.name, self.directory, self.executable)

        hash.update(repr(key).encode("utf-8"))

        if self.path is None:
            return

        if self.directory:
            return

        hash.update(hash_file(self.path).encode("utf-8"))

    def digest(self):
        """
        Returns a hex digest representing this file list.
        """

        hash = hashlib.sha256(usedforsecurity=False)
        self.hash(hash)
        return hash.hexdigest()


class FileList(MutableSet[File]):
    """
    This represents a list of files that we know about.
    This implelemts a mutable ordered set interface.
    Additionaly it allows item access with file name.
    """

    # Implementation note.
    # When adding new items to the list we make a copy of the file,
    # so if user creates one instance and adds it to separate file lists
    # modifying one of them does not change the other. Thus, creating a
    # FileList means to make a copy of all used files.
    # But in contrast, all modifying methods (i.e. returns None),
    # should modify File itself, so if user holds the reference to the File
    # of some FileList, that change does not get them out of sync.

    def __init__(self, *files: File):
        self._files: dict[str, File] = {}
        for file in files:
            self.add(file)

    def __repr__(self):
        return f"<FlieList({self._files})>"

    # Implement MutableSet interface.
    def __len__(self):
        return len(self._files)

    def __contains__(self, name: str) -> bool:
        return name in self._files

    def __iter__(self):
        yield from iter(self._files.values())

    def __reversed__(self):
        return reversed(self._files.values())

    # Those methods works with File instances.
    def add(self, value: File):
        self[value.name] = value

    def discard(self, value: File) -> None:
        del self[value.name]

    remove = discard

    # But those methods works with str.
    def __getitem__(self, key: str):
        _check_file_name(key)
        return self._files[key]

    def __setitem__(self, key: str, value: File):
        _check_file_name(key)
        if key in self:
            value = _merge_files(self[key], value)
            if value is self[key]:
                return

        self._files[key] = value.copy()

    def __delitem__(self, key: str):
        _check_file_name(key)
        del self._files[key]

    def __le__(self, other: AbstractSet[Any]):
        if not isinstance(other, FileList):
            return NotImplemented

        return self._files.keys() < other._files.keys()

    def __ge__(self, other: AbstractSet[Any]):
        if not isinstance(other, FileList):
            return NotImplemented

        return self._files.keys() > other._files.keys()

    def __eq__(self, other: Any):
        if not isinstance(other, FileList):
            return NotImplemented

        return self._files == other._files

    def __hash__(self):
        return self._hash()

    def clear(self):
        self._files.clear()

    def copy(self):
        """
        Makes a deep copy of this file list.
        """

        return FileList(*self._files.values())

    def sort(self):
        """
        Sort this file list in such a way that the directories containing
        the files come before these files.
        """

        self._files = {f.name: f for f in sorted(self)}

    def add_file(self, name: str, path: Path | None, executable: bool = False):
        """
        Adds a file to the file list.

        `name`
            The name of the file to be added.

        `path`
            The path to that file on disk.

        `executable`
            True if file is an executable that should be distributed
            with the xbit set.
        """

        self.add(File(name, path, False, executable))

    def add_directory(self, name: str, path: Path | None):
        """
        Adds an empty directory to the file list.

        `name`
            The name of the file to be added.

        `path`
            The path to that file on disk.
        """

        self.add(File(name, path, True, False))

    def filter_none(self):
        """
        Updates this file list in a way that there is no file with path = None.
        """

        self._files = {f.name: f for f in self._files.values() if f.path is not None}

    def filter_empty(self):
        """
        Updates this file list with empty directories omitted.
        """

        rv: list[File] = []
        needed_dirs: set[str] = set()
        for f in sorted(self, reverse=True):
            if (not f.directory) or (f.name in needed_dirs):
                rv.append(f)

                directory = f.name.rpartition("/")[0]
                needed_dirs.add(directory)

        self._files = {f.name: f for f in reversed(rv)}

    def add_missing_directories(self):
        """
        Adds to this file list all directories that are needed by other
        entries in this file list.
        """

        rv: list[File] = []
        seen: set[str] = set()
        required: set[str] = set()
        for i in self:
            name = i.name
            seen.add(name)
            rv.append(i)

            while "/" in name:
                name = name.rpartition("/")[0]
                required.add(name)

        for name in required - seen:
            rv.append(File(name, None, True, False))

        self._files = {f.name: f for f in sorted(rv)}

    @staticmethod
    def merge(*lists: FileList):
        """
        Merges a list of file lists into a single file list with no
        duplicate entries.
        """

        rv: list[File] = []
        seen: dict[str, File] = {}
        for fl in lists:
            for f in fl:
                if f.name in seen:
                    f = _merge_files(seen[f.name], f)
                    if f is seen[f.name]:
                        continue

                rv.append(f := f.copy())
                seen[f.name] = f

        return FileList(*rv)

    def split_by_prefix(self, prefix: str):
        """
        Returns two filelists, one that contains all the files starting with prefix,
        and one tht contains all other files.
        """

        yes = FileList()
        no = FileList()

        for f in self:
            if f.name.startswith(prefix):
                yes.add(f)
            else:
                no.add(f)

        return yes, no

    def reprefix(self, old: str, new: str):
        """
        Updates this file list with all the paths reprefixed.
        Depending on values of old and new this can lead to
        file list with missing or empty directories.
        """

        rv: list[File] = []
        len_old = len(old)
        for f in self:
            name = f.name
            if name.startswith(old):
                name = new + name[len_old:]
                if not name:
                    continue
                _check_file_name(name)
                f._name = name  # type: ignore
            rv.append(f)

        self._files = {f.name: f for f in rv}

    def prepend_directory(self, directory: str):
        """
        Modifies this file list such that every file in it has `directory`
        prepended.
        """

        rv: list[File] = [File(directory, None, True, False)]
        for f in self:
            f._name = f"{directory}/{f.name}"  # type: ignore
            rv.append(f)

        self._files = {f.name: f for f in rv}

    def hash(self):
        """
        Returns a hex digest representing this file list.
        """

        sha = hashlib.sha256(usedforsecurity=False)

        for f in sorted(self, key=lambda a: a.name):
            f.hash(sha)

        return sha.hexdigest()
