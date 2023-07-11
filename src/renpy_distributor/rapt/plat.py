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

# This sets up various variables and commands based on the platform we're on.

from __future__ import annotations

import traceback
import platform
import os

from pathlib import Path

RAPT_PATH = Path(__file__).parent

##############################################################################
# These are set based on the platform we're on.
windows = False
macintosh = False
linux = False


def set_win32_java_home():
    """
    When run on Win32, this is used to set the JAVA_HOME environment variable.
    """

    if "JAVA_HOME" in os.environ:
        return

    import winreg
    import contextlib

    open_keys = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    javasoft = "SOFTWARE\\JavaSoft"

    for key in (f"{javasoft}\\Java Development Kit", f"{javasoft}\\JDK"):
        try:
            keyobj = winreg.OpenKeyEx(
                winreg.HKEY_LOCAL_MACHINE, key, access=open_keys)
        except FileNotFoundError:
            continue

        result: str | None = None
        with contextlib.suppress(FileNotFoundError), keyobj:
            value, _ = winreg.QueryValueEx(keyobj, "CurrentVersion")
            keyobj = winreg.OpenKeyEx(keyobj, value)

        with contextlib.suppress(FileNotFoundError), keyobj:
            result, _ = winreg.QueryValueEx(keyobj, "JavaHome")

        if result is not None:
            os.environ["JAVA_HOME"] = result
            return


def set_mac_java_home():
    """
    When run on macOS, this is used to set the JAVA_HOME environment variable.
    """

    if "JAVA_HOME" in os.environ:
        return

    import subprocess
    import plistlib
    import contextlib

    with contextlib.suppress(Exception):
        raw_plist = subprocess.check_output(
            "/usr/libexec/java_home -X -v 1.8", shell=True)

        java_home = None
        for d in plistlib.loads(raw_plist):
            if not d.get("JVMEnabled", True):
                continue

            java_home = d["JVMHomePath"]

            if Path(java_home, "bin", "javac").exists():
                os.environ["JAVA_HOME"] = java_home
                return


def maybe_java_home(s: str):
    """
    If JAVA_HOME is in the environ, return $JAVA_HOME/bin/s. Otherwise, return `s`.
    """

    if (java_home := os.environ.get("JAVA_HOME")) is None:
        return s

    if not (path := Path(java_home, "bin", s)).exists():
        return s

    return str(path)


if platform.win32_ver()[0]:
    windows = True

    try:
        set_win32_java_home()
    except:
        traceback.print_exc()

    adb = "platform-tools\\adb.exe"
    sdkmanager = "cmdline-tools\\latest\\bin\\sdkmanager.bat"

    java = maybe_java_home("java.exe")
    javac = maybe_java_home("javac.exe")
    keytool = maybe_java_home("keytool.exe")

    gradlew = "gradlew.bat"

elif platform.mac_ver()[0]:
    macintosh = True

    try:
        set_mac_java_home()
    except:
        traceback.print_exc()

    adb = "platform-tools/adb"
    sdkmanager = "cmdline-tools/latest/bin/sdkmanager"

    java = maybe_java_home("java")
    javac = maybe_java_home("javac")
    keytool = maybe_java_home("keytool")

    gradlew = "gradlew"

else:
    linux = True

    adb = "platform-tools/adb"
    sdkmanager = "cmdline-tools/latest/bin/sdkmanager"

    java = maybe_java_home("java")
    javac = maybe_java_home("javac")
    keytool = maybe_java_home("keytool")

    gradlew = "gradlew"


sdk_version = "7583922_latest"

if (RAPT_PATH / "sdk.txt").exists():
    with (RAPT_PATH / "sdk.txt").open("r", encoding="utf-8") as f:
        sdk = Path(f.read().strip())
else:
    sdk = RAPT_PATH / "Sdk"

adb = str(sdk / adb)
sdkmanager = str(sdk / sdkmanager)
