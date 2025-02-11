import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from typing import Dict, Optional

import boto3
import boto3.session
from boto3.s3.transfer import TransferConfig


SPACK_REPO = "https://github.com/spack/spack"

TIMESTAMP_AND_SIZE = r"^[\d]{4}-[\d]{2}-[\d]{2}\s[\d]{2}:[\d]{2}:[\d]{2}\s+\d+\s+"

#: regular expressions designed to match "aws s3 ls" output
REGEX_V2_SIGNED_SPECFILE_RELATIVE = re.compile(
    rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(.spec.json.sig)$"
)
REGEX_V2_ARCHIVE_RELATIVE = re.compile(
    rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(.spack)$"
)

#: regex to capture bucket name from an s3 url
REGEX_S3_BUCKET = re.compile(r"s3://([^/]+)/")

#: Values used to config multi-part s3 copies
MB = 1024**2
MULTIPART_THRESHOLD = 100 * MB
MULTIPART_CHUNKSIZE = 20 * MB
MAX_CONCURRENCY = 10
USE_THREADS = True


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
#
def bucket_name_from_s3_url(url):
    bucket_regex = REGEX_S3_BUCKET
    m = bucket_regex.search(url)
    if m:
        return m.group(1)
    return ""


################################################################################
# Return a complete catalog of all the built specs for every prefix in the
# listing.  The returned dictionary of catalogs is keyed by unique prefix.
def spec_catalogs_from_listing_v2(listing_path: str) -> Dict[str, Dict[str, BuiltSpec]]:
    all_catalogs: Dict[str, Dict[str, BuiltSpec]] = defaultdict(
        lambda: defaultdict(BuiltSpec)
    )

    with open(listing_path) as f:
        for line in f:
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
def clone_spack(ref: str = "develop", repo: str = SPACK_REPO, clone_dir: str = "/"):
    spack_path = f"{clone_dir}/spack"

    if os.path.isdir(spack_path):
        shutil.rmtree(spack_path)

    owd = os.getcwd()

    try:
        os.chdir(clone_dir)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                f"{ref}",
                f"{repo}",
            ],
            check=True,
        )
    finally:
        os.chdir(owd)


################################################################################
# Download a file from s3
def s3_download_file(bucket: str, prefix: str, save_path: str, force: bool = False):
    session = boto3.session.Session()
    s3_resource = session.resource("s3")
    s3_client = s3_resource.meta.client

    if not os.path.isfile(save_path) or force is True:
        # First we have to download the file locally
        with open(save_path, "wb") as f:
            s3_client.download_fileobj(bucket, prefix, f)


################################################################################
# Copy objects between s3 buckets/prefixes
def s3_copy_file(copy_source: Dict[str, str], bucket: str, dest_prefix: str):
    session = boto3.session.Session()
    s3_resource = session.resource("s3")
    s3_client = s3_resource.meta.client

    config = TransferConfig(
        multipart_threshold=MULTIPART_THRESHOLD,
        multipart_chunksize=MULTIPART_CHUNKSIZE,
        max_concurrency=MAX_CONCURRENCY,
        use_threads=USE_THREADS,
    )

    s3_client.copy(copy_source, bucket, dest_prefix, Config=config)


################################################################################
#
def s3_upload_file(file_path: str, bucket: str, prefix: str):
    session = boto3.session.Session()
    s3_resource = session.resource("s3")
    s3_client = s3_resource.meta.client

    with open(file_path, "rb") as fd:
        s3_client.upload_fileobj(fd, bucket, prefix)
