import contextlib
import subprocess
import os
import re
import shutil
import tempfile
from collections import defaultdict
from typing import  Dict, Optional


SPACK_REPO = "https://github.com/spack/spack"

TIMESTAMP_AND_SIZE = r"^[\d]{4}-[\d]{2}-[\d]{2}\s[\d]{2}:[\d]{2}:[\d]{2}\s+\d+\s+"

# 2023-05-14 01:23:32      50105 develop-2023-05-14/aws-ahug-aarch64/build_cache/linux-amzn2-aarch64-gcc-7.3.1-adios2-2.9.0-hxjtlz7dy3ayuory4vtfsaxhwnt44pt4.spec.json.sig
REGEX_V2_SIGNED_SPECFILE_RELATIVE = re.compile(rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(.spec.json.sig)$")
# 2023-05-14 01:23:32    5068680 develop-2023-05-14/aws-ahug-aarch64/build_cache/linux-amzn2-aarch64/gcc-7.3.1/adios2-2.9.0/linux-amzn2-aarch64-gcc-7.3.1-adios2-2.9.0-hxjtlz7dy3ayuory4vtfsaxhwnt44pt4.spack
REGEX_V2_ARCHIVE_RELATIVE = re.compile(rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(.spack)$")


################################################################################
# Encapsulate information about a built spec in a mirror
class BuiltSpec:
    def __init__(
        self,
        hash: Optional[str] = None,
        stack: Optional[str] = None,
        prefix: Optional[str] = None,
        meta: Optional[str] = None,
        archive: Optional[str] = None,
    ):
        self.hash = hash
        self.stack = stack
        self.prefix = prefix
        self.meta = meta
        self.archive = archive


################################################################################
# Return a complete catalog of all the built specs for every prefix in the
# listing.  The returned dictionary of catalogs is keyed by unique prefix.
def spec_catalogs_from_listing(listing_path: str) -> Dict[str, Dict[str, BuiltSpec]]:
    all_catalogs: Dict[str, Dict[str, BuiltSpec]] = defaultdict(lambda: defaultdict(BuiltSpec))

    # line_count = 0
    # max_lines = 10

    with open(listing_path) as f:
        for line in f:

            # line_count += 1
            # if line_count > max_lines:
            #     break

            # print(line)

            # import pdb
            # pdb.set_trace()

            m = REGEX_V2_SIGNED_SPECFILE_RELATIVE.search(line)
            if m:
                # print("matched a specfile")
                prefix = m.group(1)
                middle_bit = m.group(2)
                hash = m.group(3)
                end_bit = m.group(4)
                spec = all_catalogs[prefix][hash]
                spec.hash = hash
                spec.meta = f"{prefix}{middle_bit}{hash}{end_bit}"
                continue

            m = REGEX_V2_ARCHIVE_RELATIVE.search(line)
            if m:
                # print("matched an archive file")
                prefix = m.group(1)
                middle_bit = m.group(2)
                hash = m.group(3)
                end_bit = m.group(4)
                spec = all_catalogs[prefix][hash]
                spec.hash = hash
                spec.archive = f"{prefix}{middle_bit}{hash}{end_bit}"
                continue

            # else it must be a public key, an index, or a hash of an index

    return all_catalogs


################################################################################
# If the cli didn't provide a working directory, we will create (and clean up)
# a temporary directory.
def get_workdir_context(workdir: Optional[str] = None):
    if not workdir:
        return tempfile.TemporaryDirectory()

    return contextlib.nullcontext(workdir)


################################################################################
# Given a url and a file path to use for writing, get a recursive listing of
# everything under the prefix defined by the url, and write it to disk using the
# supplied path.
def list_prefix_contents(url: str, output_file: str):
    list_cmd = ["aws", "s3", "ls", "--recursive", url]

    with open(output_file, "w") as f:
        subprocess.run(list_cmd, stdout=f, check=True)


################################################################################
# Each mirror we might publish was built with a particular version of spack, and
# in order to be able update the index for one of those mirrors, we need to
# clone the matching version of spack.
#
# Clones the version of spack specified by ref to the root of the file system
def clone_spack(ref: str):
    if os.path.isdir("/spack"):
        shutil.rmtree("/spack")

    owd = os.getcwd()

    try:
        os.chdir("/")
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                f"{ref}",
                SPACK_REPO,
            ],
            check=True,
        )
    finally:
        os.chdir(owd)
