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

from pathlib import Path
from typing import Literal

from .. import machinery, BuildContext
from ..machinery import packager
from ..machinery import FilesPattern, File, FileList

RuleKind = Literal["image", "music", "voice"]


class WebContext(BuildContext):
    progressive_download_rules: ProgressiveRules


class WebPackager(packager.ZipPackager):

    gamezip_outfile: Path

    def __init__(self, outpath: Path, /):
        super().__init__(outpath)

        self.remote_files: dict[File, str] = {}
        self.placeholders_files: dict[File, File] = {}

        self.gamezip_file_list = FileList()

    def write_length(self):
        return super().write_length() + len(self.gamezip_file_list)

    def write(self):
        gamezip_packager = packager.ZipPackager(
            self.gamezip_outfile)
        gamezip_packager.file_list = self.gamezip_file_list

        yield from gamezip_packager.write()
        yield from super().write()


machinery.register_packager_type("web", WebPackager, ".zip")


class ProgressiveRules:
    def __init__(self):
        self.image: list[tuple[bool, FilesPattern]] = []
        self.music: list[tuple[bool, FilesPattern]] = []
        self.voice: list[tuple[bool, FilesPattern]] = []

    def _get_container(self, kind: RuleKind):
        if kind == "image":
            return self.image
        elif kind == "music":
            return self.music
        elif kind == "voice":
            return self.voice

    def add_rule(self, kind: RuleKind, rule: bool, pattern: FilesPattern):

        self._get_container(kind).append((rule, pattern))

    def filters_match(self, path: str, path_type: RuleKind):
        """
        Returns whether path matches a progressive download rule.
        """
        for (f_rule, f_pattern) in self._get_container(path_type):
            if machinery.file_match_pattern(path, f_pattern):
                return f_rule
        return False
