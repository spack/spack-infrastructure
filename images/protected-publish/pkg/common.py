import contextlib
import hashlib
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
TIMESTAMP_PATTERN = "%Y-%m-%d %H:%M:%S"

#: regular expressions designed to match "aws s3 ls" output
REGEX_V2_SIGNED_SPECFILE_RELATIVE = re.compile(
    rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(\.spec\.json\.sig)$"
)
REGEX_V2_ARCHIVE_RELATIVE = re.compile(
    rf"{TIMESTAMP_AND_SIZE}(.+)(/build_cache/.+-)([^\.]+)(\.spack)$"
)
REGEX_V3_SIGNED_SPECFILE_RELATIVE = re.compile(
    rf"{TIMESTAMP_AND_SIZE}(.+)(/v3/manifests/spec/.+-)([^-\.]+)(\.spec\.manifest\.json)$"
)

#: Regular expression to pull spec contents out of clearsigned signature
#: file.
CLEARSIGN_FILE_REGEX = re.compile(
    (
        r"^-----BEGIN PGP SIGNED MESSAGE-----"
        r"\s+Hash:\s+[^\s]+\s+(.+)-----BEGIN PGP SIGNATURE-----"
    ),
    re.MULTILINE | re.DOTALL,
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
        manifest: Optional[str] = None,
    ):
        self.hash = hash
        self.stack = stack
        self.prefix = prefix
        self.meta = meta
        self.archive = archive
        self.manifest = manifest


################################################################################
#
def bucket_name_from_s3_url(url):
    m = REGEX_S3_BUCKET.search(url)
    if m:
        return m.group(1)
    return ""


################################################################################
#
def spec_catalogs_from_listing_v2(listing_path: str) -> Dict[str, Dict[str, BuiltSpec]]:
    """Return a complete catalog of all the built specs in the listing

    Return a complete catalog of all the built specs for every prefix in the
    listing.  The returned dictionary of catalogs is keyed by unique prefix.
    """
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
#
def spec_catalogs_from_listing_v3(listing_path: str) -> Dict[str, Dict[str, BuiltSpec]]:
    all_catalogs: Dict[str, Dict[str, BuiltSpec]] = defaultdict(
        lambda: defaultdict(BuiltSpec)
    )

    with open(listing_path) as f:
        for line in f:
            m = REGEX_V3_SIGNED_SPECFILE_RELATIVE.search(line)
            if m:
                prefix = m.group(1)
                middle_bit = m.group(2)
                hash = m.group(3)
                end_bit = m.group(4)
                spec = all_catalogs[prefix][hash]
                spec.hash = hash
                spec.manifest = f"{prefix}{middle_bit}{hash}{end_bit}"
                continue

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
#
def extract_json_from_clearsig(file_path):
    with open(file_path) as fd:
        data = fd.read()

    m = CLEARSIGN_FILE_REGEX.search(data)
    if not m:
        return {}

    return json.loads(m.group(1))


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
    if not os.path.isfile(save_path) or force is True:
        session = boto3.session.Session()
        s3_resource = session.resource("s3")
        s3_client = s3_resource.meta.client

        with open(save_path, "wb") as f:
            s3_client.download_fileobj(bucket, prefix, f)

    return save_path


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


################################################################################
#
def compute_checksum(input_file: str, buf_size: int = 65536) -> str:
    sha256 = hashlib.sha256()

    with open(input_file, 'rb') as f:
        while True:
            data = f.read(buf_size)
            if not data:
                break
            sha256.update(data)

    return sha256.hexdigest()


################################################################################
#
class NoSuchMediaTypeError(Exception):
    pass


class MalformedManifestError(Exception):
    pass


class UnexpectedURLFormatError(Exception):
    pass
