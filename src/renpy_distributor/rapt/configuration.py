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

import json
import re

from typing import Any, Literal
from pathlib import Path

from ..machinery import Interface

# Taken from https://docs.oracle.com/javase/tutorial/java/nutsandbolts/_keywords.html
JAVA_KEYWORDS = """
abstract    continue    for    new    switch
assert***    default    goto*    package    synchronized
boolean    do    if    private    this
break    double    implements    protected    throw
byte    else    import    public    throws
case    enum****    instanceof    return    transient
catch    extends    int    short    try
char    final    interface    static    void
class    finally    long    strictfp**    volatile
const*    float    native    super    while
true false null
""".replace("*", "").split()

ScreenOrientationKind = Literal['sensorLandscape', 'sensorPortrait', 'fullSensor']
StoreKind = Literal['play', 'amazon', 'all', 'none']


class Configuration(object):

    def __init__(self):

        self._package: str | None = None
        self.name: str | None = None
        self.icon_name: str | None = None
        self._version: str | None = None
        self.numeric_version: int = 1
        self.orientation: ScreenOrientationKind = "sensorLandscape"
        self._permissions: list[str] = ["VIBRATE"]

        self.include_pil = False
        self.include_sqlite = False
        self.layout = None
        self.source = False
        self.expansion = False

        self.google_play_key = None
        self.google_play_salt = None

        self.store: StoreKind = "none"
        self.update_icons = True
        self.update_always = True
        self._heap_size: str | None = None

    @property
    def package(self):
        return self._package

    @package.setter
    def package(self, value: str):
        value = value.strip().lower()

        if not value:
            raise ValueError("The package name may not be empty.")

        if " " in value:
            raise ValueError("The package name may not contain spaces.")

        if "." not in value:
            raise ValueError("The package name must contain at least one dot.")

        for part in value.split('.'):
            if not part:
                raise ValueError("The package name may not contain two dots in a row, or begin or end with a dot.")

            if not re.match(r"[a-zA-Z_]\w*$", part):
                raise ValueError(
                    "Each part of the package name must start with a letter, and contain only letters, numbers, and underscores.")

            if part in JAVA_KEYWORDS:
                raise ValueError(f"{part!r} is a Java keyword, and can't be used as part of a package name.")

        self._package = value

    @property
    def version(self):
        return self._version

    @version.setter
    def version(self, value: str):
        if not re.match(r'^[\d\.]+$', value):
            raise ValueError("The version number must contain only numbers and dots.")

        self._version = value

    @property
    def heap_size(self):
        return self._heap_size

    @heap_size.setter
    def heap_size(self, value: str):
        if not re.match(r'^[\d]+$', value):
            raise ValueError("The RAM size must contain only numbers and be positive.")

        self._heap_size = value

    @property
    def permissions(self):
        return self._permissions

    @permissions.setter
    def permissions(self, value: list[str]):
        value = [i for i in value if i not in ["INTERNET"]]
        value.append("INTERNET")
        self._permissions = value

    def read(self, directory: Path):
        if (jsonf := (directory / ".android.json")).exists():
            with jsonf.open("r", encoding="utf-8")as f:
                data = json.load(f)
        else:
            return

        if data.get("orientation") == "landscape":
            data["orientation"] = "sensorLandscape"

        for key, value in data.items():
            setattr(self, key, value)

    def save(self, directory: Path):
        with (directory / ".android.json").open("w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, sort_keys=True, indent=4)


def _set_or_fail(config: Configuration, iface: Interface, field: str, value: Any):
    try:
        setattr(config, field, value)
    except ValueError as e:
        iface.fail(e.args[0])


def configure(config: Configuration, interface: Interface,
              default_name: str | None = None,
              default_version: str | None = None):

    if config.name is None:
        config.name = default_name

    config.name = interface.input(
        "What is the full name of your application? This name will appear in the list of installed applications.",
        config.name)

    if config.icon_name is None:
        config.icon_name = config.name

    config.icon_name = interface.input(
        "What is the short name of your application? This name will be used in the launcher, and for application shortcuts.",
        config.icon_name)

    _set_or_fail(config, interface, "package", interface.input(
        "What is the name of the package?\nThis is usually of the form com.domain.program or com.domain.email.program. It may only contain ASCII letters and dots. It must contain at least one dot.",
        config.package))

    version = config.version or default_version

    _set_or_fail(config, interface, "version", interface.input(
        "What is the application's version?\nThis should be the human-readable version that you would present to a person. It must contain only numbers and dots.",
        version))

    heap_size = config.heap_size or "3"

    _set_or_fail(config, interface, "heap_size", interface.input(
        "How much RAM (in GB) do you want to allocate to Gradle?\nThis must be a positive integer number.",
        heap_size))

    config.orientation = interface.choice("How would you like your application to be displayed?", [
        ("sensorLandscape", "In landscape orientation."),
        ("sensorPortrait", "In portrait orientation."),
        ("fullSensor", "In the user's preferred orientation."),
    ], config.orientation)

    config.store = interface.choice("Which app store would you like to support in-app purchasing through?", [
        ("play", "Google Play."),
        ("amazon", "Amazon App Store."),
        ("all", "Both, in one app."),
        ("none", "Neither."),
    ], config.store)

    config.update_always = interface.choice(
        "Do you want to automatically update the Java source code?", [
            (True, "Yes. This is the best choice for most projects."),
            (False, "No. This may require manual updates when Ren'Py or the project configuration changes.")
        ], config.update_always)


def set_config(iface: Interface, directory: Path, var: str, value: Any):

    config = Configuration()

    config.read(directory)

    if var == "permissions":
        value = value.split()
    elif hasattr(config, var):
        _set_or_fail(config, iface, var, value)
    else:
        iface.fail(f"Unknown configuration variable: {var!r}")

    config.save(directory)
