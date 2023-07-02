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
import re
import os
import json
import shutil
import time
from zipfile import ZipFile

from .utils import WebContext as Context
from ..machinery import CONVERT_LIB, task, Interface, File, FileList, TaskResult

if CONVERT_LIB == "PIL":
    import PIL.Image
    import PIL.ImageChops
else:
    import pygame_sdl2

WEB_PATH = Path(__file__).parent


@task("Updating WEB static files...", kind="web",
      requires="init_build_platforms", dependencies="init_classifier_file_lists")
def update_web_static_files(context: Context, interface: Interface):
    """
    This downloading libraries from the (
        https://nightly.renpy.org/
        http://update.renpy.org/
    )
    """
    from renpy import version_tuple, nightly

    if nightly:
        name = ".".join(str(i) for i in version_tuple)
        name = f"{name}+nightly"
        url = f"https://nightly.renpy.org/{name}/renpy-{name}-web.zip"
    else:
        name = ".".join(str(i) for i in version_tuple[:-1])
        url = f"http://update.renpy.org/{name}/renpy-{name}-web.zip"

    try:
        with (WEB_PATH / "current_version.txt").open("r", encoding="utf-8") as f:
            current_version = f.read().strip()
    except FileNotFoundError:
        current_version = None

    if current_version == name:
        interface.info(f"WEB static files are up-to-date.")
        return TaskResult.SKIPPED

    archive = WEB_PATH / f"web_{name}.zip"

    if not archive.exists():
        interface.download(f"I'm downloading the WEB", url, archive)

    assert archive.exists()

    interface.info(f"I'm extracting the WEB.")

    old_cwd = os.getcwd()
    os.chdir(WEB_PATH)

    if Path("web").exists():
        shutil.rmtree("web")

    with ZipFile(archive) as zip:
        zip.extractall()

    # Remove old core_files directory, so we don't have to worry about
    # renamed or deleted files.
    shutil.rmtree(WEB_PATH / "core_files", ignore_errors=True)
    (WEB_PATH / "core_files").mkdir()

    for m in (WEB_PATH / "web").rglob("*"):
        if m.name in (
            "index.html", "web-icon.png", "web-presplash.jpg",
        ):
            shutil.copy2(m, WEB_PATH / m.name)
        else:
            shutil.copy2(m, WEB_PATH / "core_files" / m.name)

    if Path("web").exists():
        shutil.rmtree("web")

    os.chdir(old_cwd)

    with (WEB_PATH / "current_version.txt").open("w", encoding="utf-8") as f:
        f.write(name)

    interface.success(f"I've finished unpacking the WEB.")

    return True


@task("Initialising web rules...", kind="web",
      requires="init_build_platforms", dependencies="init_classifier_file_lists")
def init_web_rules(context: Context, interface: Interface):
    from .utils import ProgressiveRules

    # Type- and path-based filtering, following
    # progressive_download.txt rules (created with default rules if
    # not there already). Assumes prior filtering based on
    # hard-coded list of file extensions.

    rules_path = context.project_dir / 'progressive_download.txt'
    if not rules_path.exists():
        with rules_path.open('w', encoding="utf-8") as f:
            f.write(
                "# RenPyWeb progressive download rules - first match applies\n"
                "# '+' = progressive download, '-' = keep in game.zip (default)\n"
                "# See https://www.renpy.org/doc/html/build.html#classifying-and-ignoring-files for matching\n"
                "#\n"
                "# +/- type path\n"
                '- image game/gui/**\n'
                '+ image game/**\n'
                '+ music game/audio/**\n'
                '+ voice game/voice/**\n'
            )

    # Parse rules
    rules = ProgressiveRules()
    with rules_path.open('r', encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if line.startswith('#') or line.strip() == '':
                continue

            try:
                (f_rule, f_type, f_pattern) = line.rstrip("\r\n").split(' ', 2)
            except ValueError:
                raise RuntimeError(f"Missing element at progressive_download.txt:{line_no}")

            try:
                f_rule = {'+': True, '-': False}[f_rule]
            except KeyError:
                raise RuntimeError(f"Invalid rule {f_rule!r} at progressive_download.txt:{line_no}")

            if f_type not in ('image', 'music', 'voice'):
                raise RuntimeError(f"Invalid type {f_type!r} at progressive_download.txt:{line_no}")

            rules.add_rule(f_type, f_rule, f_pattern)

    context.progressive_download_rules = rules
    return True


@task("Classifying progressive download files...", kind="web",
      requires="create_packagers_and_file_lists", dependencies="prepend_directory")
def classify_progressive_download(context: Context, interface: Interface):
    from .utils import ProgressiveRules, WebPackager

    rules: ProgressiveRules = context.progressive_download_rules
    main_py_file = "renpy.py"

    with (WEB_PATH / "index.html").open("r", encoding='utf-8') as f:
        html_content = f.read()

    for packager in context.packagers.values():
        if not isinstance(packager, WebPackager):
            continue

        presplash_f = None
        file_list = FileList()
        for file in packager.file_list:
            name = file.name

            # Entry point to the game should be called main.py.
            if name == main_py_file:
                file = file.copy(name="main.py")

            # Find the presplash to copy it over.
            elif name in ("web-presplash.png", "web-presplash.jpg", "web-presplash.webp"):
                assert file.path is not None and file.path.exists()
                presplash_f = file

            # This should be some system file.
            elif file.path is None or not (ext := file.path.suffix.lower()):
                pass

            # Images
            elif (ext in ('.jpg', '.jpeg', '.png', '.webp') and rules.filters_match(name, 'image')):
                file_list.add(file)

                # Add image to list to generate placeholder later
                assert file.name.startswith("game/")
                name = "_placeholders/" + file.name[len("game/"):]
                ppath = context.temp_path("web_placeholders", file.name)
                packager.gamezip_file_list.add_file(name, ppath)
                packager.placeholders_files[file] = packager.gamezip_file_list[name]
                continue

            # For now it just sit in game forlder and is missing in game.zip.

            # Musics (but not SFX - no placeholders for short, non-looping sounds)
            elif (ext in ('.wav', '.mp2', '.mp3', '.ogg', '.opus') and rules.filters_match(name, 'music')):
                packager.remote_files[file] = 'music -'
                file_list.add(file)
                continue

            # Voices
            elif (ext in ('.wav', '.mp2', '.mp3', '.ogg', '.opus') and rules.filters_match(name, 'voice')):
                packager.remote_files[file] = 'voice -'
                file_list.add(file)
                continue

            # Videos are never included.
            elif (ext in ('.ogv', '.webm', '.mp4', '.mkv', '.avi')):
                file_list.add(file)
                continue

            # At this point we should have all the files that should be in game.zip as
            # single file list, so prepend directory to zip it later when placeholders
            # are created.
            packager.gamezip_file_list.add(file)

        for file in (WEB_PATH / "core_files").iterdir():
            file_list.add_file(file.name, file)

        if presplash_f is not None:
            html_content = html_content.replace("web-presplash.jpg", presplash_f.name)
        else:
            file_list.add_file("web-presplash.jpg", WEB_PATH / "web-presplash.jpg")

        # Copy over index.html.
        index_f = context.temp_path("index.html")
        with index_f.open("w", encoding='utf-8') as f:
            f.write(html_content.replace("Ren'Py Web Game", context.build_info.display_name))
        file_list.add_file("index.html", index_f)

        packager.file_list = file_list

    return True


@task("Writing progressive download placeholder images...", kind="web",
      requires="sort_and_clear_empty", dependencies="write_packages")
def write_progressive_download(context: Context, interface: Interface):
    from . import generate_placeholder
    from .utils import WebPackager

    if generate_placeholder.CONVERT_LIB == "pygame":
        manager = generate_placeholder.execute_in_pygame()
    else:
        from contextlib import nullcontext
        manager = nullcontext()

    prefix = "game/"
    with manager:
        for (pname, format), packager in context.packagers.items():
            if not isinstance(packager, WebPackager):
                continue

            leni = len(packager.placeholders_files)
            interface.start_progress_bar(
                f"Converting progressive download placeholder for {format}")

            for i, (source_f, game_f) in enumerate(packager.placeholders_files.items(), start=1):
                interface.update_progress_bar(f"{i}/{leni}")

                assert source_f.path is not None
                assert game_f.path is not None

                w, h = generate_placeholder.generate_image_placeholder(source_f.path, game_f.path)

                packager.remote_files[source_f] = f'image {w},{h}'
            interface.progress_bar.done_enitity(0)  # type: ignore
            interface.end_progress_bar()

            # A list of remote files for renpy.loader.
            remote_files: dict[File, str] = packager.remote_files
            temp_file = context.temp_path(f"{pname}-{format}_remote_files.txt")
            with temp_file.open("w", encoding="utf-8") as file:
                for f in sorted(remote_files, key=lambda f: f.name):
                    print(f.name[len(prefix):], file=file)
                    print(remote_files[f], file=file)

            packager.gamezip_file_list.add_file('game/renpyweb_remote_files.txt', temp_file)
    return True


@task("Finishing web packagers...", kind="web",
      requires="write_progressive_download", dependencies="write_packages")
def zip_game(context: Context, interface: Interface):
    from .utils import WebPackager

    for (pname, format), packager in context.packagers.items():
        if not isinstance(packager, WebPackager):
            continue

        packager.gamezip_outfile = context.temp_path(f"{pname}-{format}_game.zip")
        packager.gamezip_file_list.filter_empty()
        packager.gamezip_file_list.add_missing_directories()

        packager.file_list.add_file("game.zip", packager.gamezip_outfile)
        packager.file_list.filter_empty()
        packager.file_list.add_missing_directories()

    return True
