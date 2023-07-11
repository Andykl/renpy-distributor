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
import zipfile
import shutil
import stat

from pathlib import Path
from typing import Literal

from . import plat
from .plat import RAPT_PATH
from ..machinery import Interface, Context

JAVA_LINK = "https://adoptium.net/?variant=openjdk8"
ANDROID_KEY_STR = "I can create an application signing key for you. This key is required to create Universal APK for sideloading and stores other than Google Play.\n\nDo you want to create a key?"
BUNDLE_KEY_STR = "I can create a bundle signing key for you. This key is required to build an Android App Bundle (AAB) for upload to Google Play.\n\nDo you want to create a key?"

##############################################################################


##############################################################################

def check_java(interface: Interface):
    """
    Checks for the presence of a minimally useful java on the user's system.
    """

    interface.info("I'm compiling a short test program, to see if you have a working JDK on your system.")

    if interface.run_subprocess(plat.javac, str(RAPT_PATH / "CheckJDK8.java")):
        interface.fail(
            f"I was unable to use javac to compile a test file. If you haven't installed the Java Development Kit yet, please download it from:\n\n{JAVA_LINK}\n\nThe JDK is different from the JRE, so it's possible you have Java without having the JDK. Please make sure you installed the 'JavaSoft (Oracle) registry keys'.\n\nWithout a working JDK, I can't continue.")

    if interface.run_subprocess(plat.java, "-classpath", str(RAPT_PATH), "CheckJDK8"):
        interface.fail(
            "The version of Java on your computer does not appear to be JDK 8, which is the only version supported by the Android SDK. If you need to install JDK 8, you can download it from:\n\n{JAVA_LINK}\n\nYou can also set the JAVA_HOME environment variable to use a different version of Java.")

    interface.success("The JDK is present and working. Good!")
    return True


class FixedZipFile(zipfile.ZipFile):
    """
    A patched version of zipfile.ZipFile that adds support for:

    * Unix permissions bits.
    * Unix symbolic links.
    """

    def _extract_member(self, member: zipfile.ZipInfo | str, targetpath: str, pwd: bytes | None):

        if not isinstance(member, zipfile.ZipInfo):
            member = self.getinfo(member)

        # build the destination pathname, replacing
        # forward slashes to platform specific separators.
        arcname = member.filename.replace('/', os.path.sep)

        if os.path.altsep:
            arcname = arcname.replace(os.path.altsep, os.path.sep)
        # interpret absolute pathname as relative, remove drive letter or
        # UNC path, redundant separators, "." and ".." components.
        arcname = os.path.splitdrive(arcname)[1]
        invalid_path_parts = ('', os.path.curdir, os.path.pardir)
        arcname = os.path.sep.join(x for x in arcname.split(os.path.sep) if x not in invalid_path_parts)

        targetpath = os.path.join(targetpath, arcname)
        targetpath = os.path.normpath(targetpath)

        # Create all upper directories if necessary.
        upperdirs = os.path.dirname(targetpath)
        if upperdirs and not os.path.exists(upperdirs):
            os.makedirs(upperdirs)

        if member.filename[-1] == "/":
            if not os.path.isdir(targetpath):
                os.mkdir(targetpath)
            return targetpath

        attr = member.external_attr >> 16

        if stat.S_ISLNK(attr):

            with self.open(member, pwd=pwd) as source:
                linkto = source.read()

            os.symlink(linkto, targetpath)

        else:

            with self.open(member, pwd=pwd) as source, open(targetpath, "wb") as target:
                shutil.copyfileobj(source, target)

            if attr:
                os.chmod(targetpath, attr)

        return targetpath


def unpack_sdk(interface: Interface):

    if os.path.exists(plat.sdkmanager):
        interface.success("The Android SDK has already been unpacked.")
        return

    if "RAPT_NO_TERMS" not in os.environ:
        interface.terms("Do you accept the Android SDK Terms and Conditions?",
                        "https://developer.android.com/studio/terms")

    if plat.windows:
        archive = "commandlinetools-win-{}.zip".format(plat.sdk_version)
    elif plat.macintosh:
        archive = "commandlinetools-mac-{}.zip".format(plat.sdk_version)
    elif plat.linux:
        archive = "commandlinetools-linux-{}.zip".format(plat.sdk_version)
    else:
        assert False

    url = f"https://dl.google.com/android/repository/{archive}"

    if not (RAPT_PATH / archive).exists():
        interface.download("I'm downloading the Android SDK", url, RAPT_PATH / archive)

    interface.info("I'm extracting the Android SDK.")

    # We have to do this because Python has a small (260?) path length
    # limit on windows, and the Android SDK has very long filenames.
    old_cwd = os.getcwd()
    os.chdir(RAPT_PATH)

    if Path("Sdk").exists():
        shutil.rmtree("Sdk")

    with FixedZipFile(archive) as zip:
        zip.extractall("Sdk")

    # sdkmanager won't run unless we reorganize the unpack.
    os.rename("Sdk/cmdline-tools", "Sdk/latest")
    os.mkdir("Sdk/cmdline-tools")
    os.rename("Sdk/latest", "Sdk/cmdline-tools/latest")

    os.chdir(old_cwd)

    interface.success("I've finished unpacking the Android SDK.")


def get_packages(interface: Interface):

    wanted_packages = [
        ("platform-tools", "platform-tools"),
        ("platforms;android-33", "platforms/android-33"),
    ]

    packages: list[str] = []
    for i, j in wanted_packages:
        if not (plat.sdk / j).exists():
            packages.append(i)

    if packages:

        interface.info("I'm about to download and install the required Android packages. This might take a while.")

        if interface.run_subprocess(str(plat.sdkmanager), "--update", yes=True):
            interface.fail("I was unable to accept the Android licenses.")

        if interface.run_subprocess(str(plat.sdkmanager), "--licenses", yes=True):
            interface.fail("I was unable to accept the Android licenses.")

        if interface.run_subprocess(str(plat.sdkmanager), *packages, yes=True):
            interface.fail("I was unable to install the required Android packages.")

    interface.success("I've finished installing the required Android packages.")


def set_property(properties: Path, key: str, value: str, replace: bool = False):
    """
    Sets the property `key` in local/bundle.properties to `value`. If replace is True,
    replaces the value.
    """

    lines: list[str] = []
    try:
        with properties.open("r", encoding="utf-8") as f:
            for l in f:
                k = l.partition("=")[0].strip()

                if k == key:
                    if not replace:
                        return
                    else:
                        continue

                lines.append(l)

    except:
        pass

    with properties.open("w", encoding="utf-8") as f:
        for l in lines:
            f.write(l)

        f.write("{}={}\n".format(key, value))


def get_property(properties: Path, key: str, default: str | None = None):

    with properties.open("r", encoding="utf-8") as f:
        for l in f:
            k, _, v = l.partition("=")

            if k.strip() == key:
                return v.strip()

    return default


def backup_keys(context: Context, source: Path):
    import time
    import shutil

    keys = context.project_path("game", "saves", "backups", "keys")
    keyfile = keys / f"{source.name}-{int(time.time())}"

    if not keys.exists():
        keys.mkdir(0o700, parents=True, exist_ok=True)

    shutil.copy(source, keyfile)


dname = None


def generate_keys(context: Context, interface: Interface,
                  name: Literal["android", "bundle"],
                  properties: Path):

    set_property(properties, "key.alias", "android")
    set_property(properties, "key.store.password", "android")
    set_property(properties, "key.alias.password", "android")

    default_keystore = (RAPT_PATH / f"{name}.keystore").as_posix()

    if get_property(properties, "key.store", default_keystore) != default_keystore:
        return

    if (RAPT_PATH / f"{name}.keystore").exists():
        set_property(properties, "key.store", default_keystore)
        return

    if not interface.yesno(ANDROID_KEY_STR if name == "android" else BUNDLE_KEY_STR):
        return

    global dname
    if dname is None:
        org_name = interface.input("Please enter your name or the name of your organization.", "A Ren'Py Creator")
        dname = f"CN={org_name}"

    if not interface.yesno(f"I will create the key in the {name}.keystore file.\n\nYou need to back this file up. If you lose it, you will not be able to upgrade your application.\n\nYou also need to keep the key safe. If evil people get this file, they could make fake versions of your application, and potentially steal your users' data.\n\nWill you make a backup of android.keystore, and keep it in a safe place?"):
        return

    if interface.run_subprocess(
            plat.keytool, "-genkey", "-keystore", default_keystore, "-alias", "android", "-keyalg", "RSA", "-keysize",
            "2048", "-keypass", "android", "-storepass", "android", "-dname", dname, "-validity", "20000"):
        interface.fail(f"Could not create {name}.keystore. Is keytool in your path?")

    interface.success(f"I've finished creating {name}.keystore. Please back it up, and keep it in a safe place.")

    backup_keys(context, Path(default_keystore))
    set_property(properties, "key.store", default_keystore)

    return True
