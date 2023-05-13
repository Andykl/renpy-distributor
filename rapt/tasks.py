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

import time
import shutil

from pathlib import Path
from typing import Literal

from . import plat
from .plat import RAPT_PATH
from ..machinery import Interface, TaskResult, task
from .build import AndroidContext as Context


RuleKind = Literal["image", "music", "voice"]


@task("Reading .android.json configuration...", kind="android",
      requires="init_build_platforms", dependencies="init_classifier_file_lists")
def init_android_config(context: Context, interface: Interface):
    from .configuration import Configuration, configure

    # Import build so we register our packagers
    from . import build as _

    context.android_config = config = Configuration()
    need_reconfig = False
    try:
        config.read(context.project_dir)
        if config.package is None:
            need_reconfig = True

    except ValueError as e:
        interface.info(f"Error while reading .android.json - {e.args[0]}")
        need_reconfig = True

    if need_reconfig and not interface.yesno("Do you want to configure android now?"):
        interface.fail("Run configure before attempting to build the app.")

    if need_reconfig:
        # This will fail itself in case of bad input.
        configure(config, interface,
                  context.build_info.display_name,
                  context.build_info.version)

        config.save(context.project_dir)

    # Pick the numeric version.
    config.numeric_version = max(int(time.time()), int(config.numeric_version))

    # Annoying fixups.
    assert config.name is not None
    config.name = config.name.replace("'", "\\'")
    assert config.icon_name is not None
    config.icon_name = config.icon_name.replace("'", "\\'")
    return True


@task("Creating android project directory...", kind="android",
      requires="init_build_platforms", dependencies="init_allow_and_block_lists")
def copy_project(context: Context, interface: Interface):
    def snarf(fn: Path):
        if fn.exists():
            return open(fn, "r").read().strip()
        else:
            return None

    prototype = RAPT_PATH / "prototype"
    project = context.temp_path("project")

    if context.android_config.update_always:
        update = True
    elif not project.exists():
        update = True
    elif snarf(project / "build.txt") != snarf(prototype / "build.txt"):
        update = True
    else:
        update = False

    if not update:
        interface.info("Android project directory is up-to-date.")
        return TaskResult.SKIPPED

    lp = snarf(project / "local.properties")
    bp = snarf(project / "bundle.properties")

    if project.exists():
        shutil.rmtree(project)

    shutil.copytree(prototype, project)

    if lp is not None:
        with (project / "local.properties").open("w", encoding="utf-8") as f:
            print(lp, file=f)

    if bp is not None:
        with (project / "bundle.properties").open("w", encoding="utf-8") as f:
            print(bp, file=f)

    return TaskResult.SUCCESS


@task("Checking SDK tools...", kind="android",
      requires="copy_project", dependencies="init_classifier_file_lists")
def check_sdk(context: Context, interface: Interface):
    from . import install_sdk

    install_sdk.check_java(interface)

    install_sdk.unpack_sdk(interface)

    install_sdk.get_packages(interface)

    local_properties = context.temp_path("project", "local.properties")
    bundle_properties = context.temp_path("project", "bundle.properties")

    generated = False
    if install_sdk.generate_keys(context, interface, "android", local_properties):
        generated = True

    if install_sdk.generate_keys(context, interface, "bundle", bundle_properties):
        generated = True

    install_sdk.set_property(local_properties, "sdk.dir", plat.sdk.as_posix(), replace=True)
    install_sdk.set_property(bundle_properties, "sdk.dir", plat.sdk.as_posix(), replace=True)

    if generated:
        interface.open_directory(
            "I've opened the directory containing android.keystore and bundle.keystore. Please back them up, and keep them in a safe place.",
            RAPT_PATH)

    if False:  # TODO
        interface.final_success("It looks like you're ready to start packaging games.")

    return True


@task("Initialising android assets and private packagers...", kind="android",
      requires="create_packagers_and_file_lists", dependencies="prepend_directory")
def init_allow_and_block_lists(context: Context, interface: Interface):
    from . import build

    project = context.temp_path("project")
    assets = project / "app/src/main/assets"
    for packager in context.packagers.values():
        if not isinstance(packager, build.AndroidPackager):
            continue

        if packager.bundle:
            packager.assets = build.AndroidBundlePackager(project)
        else:
            packager.assets = build.AndroidXFilePackager(assets)
        packager.private = build.AndroidPrivatePackager(assets / "private.mp3")
    return True


@task("Eliminating __pycache__...", kind="android",
      requires="create_packagers_and_file_lists", dependencies="prepend_directory")
def eliminate_pycache(context: Context, interface: Interface):
    """
    Eliminates the __pycache__ directory, and moves the files in it up a level,
    renaming them to remove the cache tag.
    """

    import sys
    from ..machinery.file_utils import match, FileList
    from .build import AndroidPackager

    pycache_str = f"**__pycache__/**.{sys.implementation.cache_tag}.pyc"
    for packager in context.packagers.values():
        if not isinstance(packager, AndroidPackager):
            continue

        file_list = FileList()
        for file in packager.file_list:
            if match(file.name, pycache_str):
                name_path = Path(file.name)
                name = name_path.stem.partition(".")[0] + ".pyc"
                name = (name_path.parent.parent / name).as_posix()
                file_list.add(file.copy(name=name))
            else:
                file_list.add(file)

        packager.file_list = file_list

    return True


@task("Splitting private and assets...", kind="android",
      requires="eliminate_pycache", dependencies="sort_and_clear_empty")
def split_renpy(context: Context, interface: Interface):
    """
    Takes a built Ren'Py game, and splits it into the private and assets
    directories. This also renames <game>.py to main.py, and moves common/
    into assets.
    """

    from ..machinery.file_utils import FileList
    from .build import AndroidPackager, PatternList

    main_py_file = f"{context.build_info.executable_name}.py"

    blocklist = PatternList(RAPT_PATH / "blocklist.txt")
    keeplist = PatternList(RAPT_PATH / "keeplist.txt")

    def include(fn: str):
        rv = fn[0] != "."

        if blocklist.match(fn):
            rv = False

        if keeplist.match(fn):
            rv = True

        return rv

    for packager in context.packagers.values():
        if not isinstance(packager, AndroidPackager):
            continue

        file_list = FileList()
        for file in packager.file_list:
            # Keep android files (icons, etc.).
            if file.name.startswith("android-"):
                file_list.add(file)
            elif file.name == ".android.json":
                file_list.add(file)

            # Entry point to the game should be called main.py.
            elif file.name == main_py_file:
                packager.private.file_list.add(file.copy(name="main.py"))

            elif file.name.startswith("renpy/common"):
                if include(file.name):
                    packager.assets.file_list.add(file)
            elif file.name.startswith(("renpy", "lib")):
                packager.private.file_list.add(file)
            elif include(file.name):
                packager.assets.file_list.add(file)

        packager.file_list = file_list

    return True


COPIED = [
    "renpyandroid/src/main/jniLibs",
]


# NOTE: this could not be cached because user could install or delete libs e.g. Live2D
@task("Copying libs...", kind="android",
      requires="split_renpy", dependencies="sort_and_clear_empty")
def copy_libs(context: Context, interface: Interface):
    """
    This copies updated libraries from the prototype to the project each
    time a build occurs.
    """

    for d in COPIED:
        project = context.temp_path("project", d)
        prototype = RAPT_PATH / "prototype" / d

        if project.exists():
            shutil.rmtree(project)

        shutil.copytree(prototype, project)

    return True


@task("Creating android icons...", kind="android",
      requires="split_renpy", dependencies="sort_and_clear_empty")
def create_icons(context: Context, interface: Interface):
    from .build import get_presplash_src

    if context.android_config.update_icons:
        from .iconmaker import IconMaker
        IconMaker(context.project_dir, context.temp_path("project"), context.android_config)

    default_presplash = RAPT_PATH / "templates/renpy-presplash.jpg"
    default_downloading = RAPT_PATH / "templates/renpy-downloading.jpg"

    presplash = get_presplash_src(context.project_dir, "android-presplash", default_presplash)
    downloading = get_presplash_src(context.project_dir, "android-downloading", default_downloading)

    # Copy the presplash files.
    shutil.copy(presplash, context.temp_path("project/app/src/main/assets",
                                             f"android-presplash.{presplash.suffix}"))
    shutil.copy(downloading, context.temp_path("project/app/src/main/assets",
                                               f"android-downloading.{downloading.suffix}"))

    return True


GENERATED = [
    (False, "templates/app-build.gradle", "app/build.gradle"),
    (False, "templates/app-AndroidManifest.xml", "app/src/main/AndroidManifest.xml"),
    (False, "templates/app-strings.xml", "app/src/main/res/values/strings.xml"),
    (False, "templates/renpyandroid-AndroidManifest.xml", "renpyandroid/src/main/AndroidManifest.xml"),
    (False, "templates/renpyandroid-strings.xml", "renpyandroid/src/main/res/values/strings.xml"),
    (False, "templates/Constants.java", "renpyandroid/src/main/java/org/renpy/android/Constants.java"),
    (False, "templates/settings.gradle", "settings.gradle"),
]


@task("Building Android files with Gradle...", kind="android",
      requires="write_packages", dependencies="open_output_dir")
def render_generated(context: Context, interface: Interface):
    import hashlib
    from .build import render, AndroidPackager
    from .configuration import Configuration

    config: Configuration = context.android_config
    for packager in context.packagers.values():
        if not isinstance(packager, AndroidPackager):
            continue

        with packager.private.outpath.open("rb") as f:
            private_version = hashlib.md5(f.read()).hexdigest()

        for always, template, project in GENERATED:
            render(
                always or config.update_always,
                template,
                context.temp_path("project", project),
                private_version=private_version,
                config=config,
                bundle=packager.bundle,
            )

        if packager.bundle:
            name = "bundle"
            apkdir = context.temp_path("project/app/build/outputs/bundle/release")
            command = "bundleRelease"
            ext = ".aab"
        else:
            name = "APK"
            apkdir = context.temp_path("project/app/build/outputs/apk/release")
            command = "assembleRelease"
            ext = ".apk"

        if apkdir.exists():
            for f in os.listdir(apkdir):
                os.unlink(f)

        # Build.
        interface.info(f"I'm using Gradle to build the {name} package.")
        if interface.run_subprocess(
                str(context.temp_path("project", plat.gradlew)),
                "-p", str(context.temp_path("project")), command):
            interface.fail("The build seems to have failed.")

        # Copy result file to output_dir.
        for p in apkdir.glob(f"*{ext}"):
            shutil.copy(p, packager.outpath)

    return True
