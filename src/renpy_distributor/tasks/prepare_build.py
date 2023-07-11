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

from ..machinery import Interface, task
from .. import BuildContext as Context


# Prepare build phase - merge file lists and make all files ready to read and write.
@task("Initialising archivers...")
def create_archivers(context: Context, interface: Interface):
    from ..machinery import init_archiver, Archiver

    classifier_file_lists = context.classifier_file_lists
    archives = context.build_info.archives
    result: dict[str, Archiver] = {}

    for name, archive in archives.items():
        file_list = classifier_file_lists[name].copy()
        # Archives are expected to be in game directory only, so remove
        # the prefix from added files.
        file_list.reprefix("game/", "")

        file_list.filter_empty()
        file_list.add_missing_directories()
        file_list.filter_none()

        if not file_list:
            continue

        outfile = context.temp_path("archives", archive.filename)
        result[name] = init_archiver(
            archive.archiver_kind, outfile, *archive.archiver_args)

        result[name].file_list = file_list

    context.archivers = result
    return True


@task("Initialising packagers and its file lists...")
def create_packagers_and_file_lists(context: Context, interface: Interface):
    from ..machinery import init_packager, Packager, FormatKind, FileList

    directory_name = context.build_info.directory_name
    classifier_file_lists = context.classifier_file_lists
    archives = context.build_info.archives
    archivers = context.archivers
    result: dict[tuple[str, FormatKind], Packager] = {}

    # For each package we want to build and each format in it, merge needed file lists into one.
    for pname in context.build_packages:
        package = context.build_info.packages[pname]

        for format in package.formats:
            file_lists: dict[str, FileList] = {}
            for name in package.file_lists:
                file_list = classifier_file_lists[name]
                file_list.filter_empty()
                file_list.add_missing_directories()
                if not file_list:
                    continue
                file_lists[name] = file_list.copy()

            for name, archive in archives.items():
                if name not in archivers:
                    interface.info(f"Ignore {name} archive in {pname} {format}, empty file list.", verbose=True)
                    continue

                # We need to add archive only once and only if package
                # need it.
                for fl in archive.file_lists:
                    if fl in package.file_lists:
                        add_list = fl
                        break
                else:
                    interface.info(f"Ignore {name} archive in {pname} {format}, no matching file list.", verbose=True)
                    continue

                archiver = archivers[name]
                if package.ignore_archives:
                    for f in archiver.file_list:
                        # Add game/ prefix back.
                        file_lists[add_list].add(f.copy(name=f"game/{f.name}"))
                    interface.info(
                        f"Ignore {name} archive in {pname} {format}, package ignores archives.", verbose=True)

                else:
                    # This is not created yet.
                    file_lists[add_list].add_file(
                        f"game/{archiver.filename.name}", archiver.filename)
                    archiver.build_request = True
                    interface.info(f"Add {name} archive in {pname} {format}.", verbose=True)

            outfile = context.output_dir / f"{directory_name}-{pname}"

            packager = init_packager(
                format, context.build_info, outfile)
            if packager is None:
                continue

            packager.file_list = FileList.merge(*file_lists.values())
            result[pname, format] = packager

    context.packagers = result
    return True


@task("Prepending directory...")
def prepend_directory(context: Context, interface: Interface):
    from ..machinery import get_packager_modifiers

    directory_name = context.build_info.directory_name
    for (pname, format), packager in context.packagers.items():
        if "prepend" not in get_packager_modifiers(format):
            continue

        packager.file_list.prepend_directory(f"{directory_name}-{pname}")
    return True


@task("Signing the app...", kind="mac")
def transform_and_sign_app(context: Context, interface: Interface):
    from ..machinery import file_match_pattern, get_packager_modifiers, FileList, FilesPattern

    def mac_transform(fl: FileList, documentation: set[FilesPattern]):
        """
        Creates a new file list that has the mac transform applied to it.

        The mac transform places all files that aren't already in <app> in
        <app>/Contents/Resources/autorun. If it matches one of the documentation
        patterns, then it appears both inside and outside of the app.
        """

        rv = FileList()

        for f in fl:

            # Already in the app.
            if f.name == app or f.name.startswith(f"{app}/"):
                rv.add(f)
                continue

            # If it's documentation, keep the file. (But also make
            # a copy.)
            for pattern in documentation:
                if file_match_pattern(f.name, pattern):
                    rv.add(f)

            # Make a copy.
            rv.add(f.copy(name=f"{autorun}/{f.name}"))

        rv.add_directory(autorun, None)
        rv.sort()

        return rv

    def sign_app(fl: FileList, appzip: bool):
        """
        Signs the mac app contained in appzip.
        """

        if (identity := context.build_info.mac_identity) is None:
            return fl

        raise Exception("Not yet implemented")

        if self.macapp:
            return self.rescan(fl, self.macapp)

        # Figure out where it goes.
        if appzip:
            dn = "sign.app-standalone"
        else:
            dn = "sign.app-crossplatform"

        dn = context.temp_path(dn)

        if dn.exists():
            import shutil
            shutil.rmtree(dn)

        # Unpack the app.
        from ..machinery import packager
        with packager.DirectoryPackage(dn) as pkg:
            fllen = len(fl)
            for i, f in enumerate(fl):
                interface.progress("Unpacking the Macintosh application for signing...", i, fllen)

                if f.directory:
                    pkg.add_directory(f.name, f.path)
                else:
                    pkg.add_file(f.name, f.path, f.executable)

            interface.progress_done()

        # Sign the mac app.
        interface.info("Signing the Macintosh application...\n(This may take a long time.)")
        context.run(
            context.build_info.mac_codesign_command,
            identity=identity,
            app=os.path.join(dn, self.app),
            entitlements=os.path.join(config.gamedir, "entitlements.plist"),
        )

        # Rescan the signed app.
        return self.rescan(fl, dn)

    app = f"{context.build_info.executable_name}.app"
    autorun = f"{app}/Contents/Resources/autorun"
    for (_, format), packager in context.packagers.items():
        macapp = "app" in get_packager_modifiers(format)
        fl = packager.file_list
        if macapp:
            fl = mac_transform(fl, context.build_info.documentation_patterns)

        appfl, rest = fl.split_by_prefix(app)

        if appfl:
            appfl = sign_app(appfl, macapp)
            fl = FileList.merge(appfl, rest)
            fl.filter_empty()
            fl.add_missing_directories()

        else:
            continue

        packager.file_list = fl
    return True


@task("Workaround mac notarization...", kind="mac")
def workaround_mac_notarization(context: Context, interface: Interface):
    """
    This works around mac notarization by compressing the unsigned,
    un-notarized, binaries in lib/py3-mac-universal.
    """
    from ..machinery import get_packager_modifiers, FileList

    for (_, format), packager in context.packagers.items():
        if "dmg" not in get_packager_modifiers(format):
            continue

        fl = FileList()
        for f in packager.file_list:
            if "/lib/py3-mac-universal/" in f.name and f.path is not None:
                with open(f.path, "rb") as inf:
                    data = inf.read()

                *parts, name = f.name.split("/")
                tempfile = context.temp_path(*parts, name + ".macho")

                with open(tempfile, "wb") as outf:
                    outf.write(b"RENPY" + data)

                fl.add_file(f.name + ".macho", tempfile, f.executable)
            else:
                fl.add(f)

        packager.file_list = fl

    return True
