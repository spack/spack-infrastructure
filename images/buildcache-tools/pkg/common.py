import contextlib
import hashlib
import json
import logging
import os
import re
import requests
import shutil
import stat
import subprocess
import tempfile
from collections import defaultdict
from concurrent.futures import as_completed, ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

import boto3
import boto3.session
from boto3.s3.transfer import TransferConfig

try:
    import sentry_sdk
    sentry_sdk.init(
        # This cron job only runs once weekly,
        # so just record all transactions.
        traces_sample_rate=1.0,
    )
except ImportError:
    print("Sentry Disabled")


SPACK_REPO = "https://github.com/spack/spack"
PACKAGES_REPO = "https://github.com/spack/spack-packages"

TIMESTAMP_AND_SIZE = r"^[\d]{4}-[\d]{2}-[\d]{2}\s[\d]{2}:[\d]{2}:[\d]{2}\s+\d+\s+"
TIMESTAMP_PATTERN = "%Y-%m-%d %H:%M:%S"

SPACK_PUBLIC_KEY_LOCATION = "https://spack.github.io/keys"
SPACK_PUBLIC_KEY_NAME = "spack-public-binary-key.pub"
TARBALL_MEDIA_TYPE = "application/vnd.spack.install.v2.tar+gzip"
SPEC_METADATA_MEDIA_TYPE = "application/vnd.spack.spec.v5+json"

REGEX_LISTING_DATA = r"^([\d]{4}-[\d]{2}-[\d]{2}\s[\d]{2}:[\d]{2}:[\d]{2})\s+(\d+)\s+(.+)"

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

SNAPSHOT_TAG_REGEXES = [
    re.compile(r"^develop-[\d]{4}-[\d]{2}-[\d]{2}$"),
    re.compile(r"^v([\d]+)\.([\d]+)\.[\d]+$"),
]

PROTECTED_BRANCH_REGEXES = [
    re.compile(r"^develop$"),
    re.compile(r"^releases/v[\d]+\.[\d]+$"),
]


LOGGER = logging.getLogger(__name__)


def download_and_import_key(gpg_home: str, tmpdir: str, force: bool) -> str | None:
    """Download spack public signing key and import it"""
    if os.path.isdir(gpg_home):
        if force is True:
            shutil.rmtree(gpg_home)
        else:
            return None

    mode_owner_rwe = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
    os.makedirs(gpg_home, mode=mode_owner_rwe)

    public_key_url = f"{SPACK_PUBLIC_KEY_LOCATION}/{SPACK_PUBLIC_KEY_NAME}"
    public_key_id = "2C8DD3224EF3573A42BD221FA8E0CA3C1C2ADA2F"

    # Fetch the public key and write it to a file to be imported
    tmp_key_path = os.path.join(tmpdir, SPACK_PUBLIC_KEY_NAME)
    response = requests.get(public_key_url)
    with open(tmp_key_path, "w") as f:
        f.write(response.text)

    # Also write an ownertrust file to be imported
    ownertrust_path = os.path.join(tmpdir, "trustfile")
    with open(ownertrust_path, "w") as f:
        f.write(f"{public_key_id}:6:\n")

    env = {"GNUPGHOME": gpg_home}

    # Import the key
    subprocess.run(["gpg", "--no-tty", "--import", tmp_key_path], env=env, check=True)

    # Trust it ultimately
    subprocess.run(
        ["gpg", "--no-tty", "--import-ownertrust", ownertrust_path],
        env=env,
        check=True,
    )

    return tmp_key_path


def tag_source_branch(tag):
    """Parse a tag and return the source branch
    """
    m = SNAPSHOT_TAG_REGEXES[0].match(tag)
    if m:
        return "develop"

    m = SNAPSHOT_TAG_REGEXES[1].match(tag)
    if m:
        major, minor = m.groups()
        return f"releases/v{major}.{minor}"

    return None


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
        manifest_prefix: Optional[str] = None,
        manifest_path: Optional[str] = None,
    ):
        self.hash = hash
        self.stack = stack
        self.prefix = prefix
        self.meta = meta
        self.archive = archive
        self.manifest_prefix = manifest_prefix
        self.manifest_path = manifest_path


################################################################################
#
def bucket_name_from_s3_url(url):
    m = REGEX_S3_BUCKET.search(url)
    if m:
        return m.group(1)
    return ""


################################################################################
#
def spec_catalogs_from_listing_v2(bucket: str, ref: str) -> Dict[str, Dict[str, BuiltSpec]]:
    """Return a complete catalog of all the built specs in the listing

    Return a complete catalog of all the built specs for every prefix in the
    listing.  The returned dictionary of catalogs is keyed by unique prefix.
    """
    list_url = f"s3://{bucket}/{ref}/"
    listing_path = list_prefix_contents(list_url)
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
def spec_catalogs_from_listing_v3(bucket: str, ref: str) -> Dict[str, Dict[str, BuiltSpec]]:
    list_url = f"s3://{bucket}/{ref}/"
    listing_path = list_prefix_contents(list_url)
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
                spec.manifest_prefix = f"{prefix}{middle_bit}{hash}{end_bit}"
                continue

    return all_catalogs


################################################################################
#
def generate_spec_catalogs_v2(
    bucket: str, ref: str, exclude: List[str] = [], listing_path: Optional[str] = None
) -> tuple[Dict[str, Dict[str, BuiltSpec]], Dict[str, BuiltSpec]]:
    """Return information about specs in stacks and at the root

    Read the listing file, populate and return a tuple of dicts indicating which
    specs exist in stacks, and which exist in the top-level buildcache. Stacks
    appearing in the ``exclude`` list are ignoreed.

    Returns a tuple like the following:

        (
            # First element of tuple is the stack specs
            {
                <hash>: {
                    <stack>: <BuiltSpec>,
                    ...
                },
                ...
            },
            # Followed by specs at the top level
            {
                <hash>: <BuiltSpec>,
                ...
            }
        )
    """
    stack_prefix_regex = re.compile(rf"{ref}/(.+)")
    stack_specs: Dict[str, Dict[str, BuiltSpec]] = defaultdict(
        lambda: defaultdict(BuiltSpec)
    )
    all_catalogs = spec_catalogs_from_listing_v2(bucket, ref)
    top_level_specs = all_catalogs[ref]

    for prefix in all_catalogs:
        m = stack_prefix_regex.search(prefix)
        if not m:
            continue

        stack = m.group(1)
        if stack in exclude:
            continue

        for spec_hash, built_spec in all_catalogs[prefix].items():
            stack_specs[stack][spec_hash] = built_spec

    return stack_specs, top_level_specs


def format_blob_url(prefix: str, blob_record: Dict[str, str]) -> str:
    """Use prefix and algorithm/checksum from record to build full prefix"""
    hash_algo = blob_record.get("checksumAlgorithm", None)
    checksum = blob_record.get("checksum", None)

    if not hash_algo:
        raise MalformedManifestError("Missing 'checksumAlgorithm'")

    if not checksum:
        raise MalformedManifestError("Missing 'checksum'")

    return f"{prefix}/blobs/{hash_algo}/{checksum[:2]}/{checksum}"


def find_data_with_media_type(
    data: List[Dict[str, str]], mediaType: str
) -> Dict[str, str]:
    """Return data element with matching mediaType, or else raise"""
    for elt in data:
        if elt["mediaType"] == mediaType:
            return elt
    raise NoSuchMediaTypeError(mediaType)


################################################################################
#
def generate_spec_catalogs_v3(
    bucket: str,
    ref: str,
    exclude: List[str] = [],
    include: List[str] = [],
    parallel: int = 8,
    workdir: Optional[str] = None,
) -> tuple[Dict[str, Dict[str, BuiltSpec]], Dict[str, BuiltSpec]]:
    """Return information about specs in stacks and at the root"""
    stack_prefix_regex = re.compile(rf"{ref}/(.+)")
    stack_specs: Dict[str, Dict[str, BuiltSpec]] = defaultdict(
        lambda: defaultdict(BuiltSpec)
    )
    all_catalogs = spec_catalogs_from_listing_v3(bucket, ref)
    top_level_specs = all_catalogs[ref]

    task_list = []
    delete_on_exit = False
    if not workdir:
        delete_on_exit = True
        workdir = tempfile.mkdtemp()

    tmpdir = workdir

    for prefix in all_catalogs:
        m = stack_prefix_regex.search(prefix)
        if not m:
            continue

        stack = m.group(1)
        if stack in exclude:
            continue

        if include and stack not in include:
            continue

        stack_manifests_dir = os.path.join(tmpdir, stack)
        os.makedirs(stack_manifests_dir, exist_ok=True)
        stack_manifest_sync_cmd = [
            "aws",
            "s3",
            "sync",
            "--exclude",
            "*",
            "--include",
            "*.spec.manifest.json",
            f"s3://{bucket}/{prefix}/v3/manifests/spec",
            stack_manifests_dir,
        ]

        start_time = datetime.now()

        try:
            print(f"Downloading manifests for stack {stack}")
            subprocess.run(
                stack_manifest_sync_cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError as cpe:
            error_msg = getattr(cpe, "message", cpe)
            print(f"Failed to download manifests for {stack} due to: {error_msg}")
            continue

        end_time = datetime.now()
        elapsed = end_time - start_time
        print(f"Downloaded manifests for stack {stack}, elapsed time: {elapsed}")

        for spec_hash, built_spec in all_catalogs[prefix].items():
            stack_specs[stack][spec_hash] = built_spec
            task_list.append((built_spec.hash, stack))

    def _process_manifest_fn(spec_hash, stack):
        download_dir = os.path.join(tmpdir, stack)
        LOGGER.debug(f"searching {download_dir} for spec /{spec_hash}")
        find_cmd = ["find", download_dir, "-type", "f", "-name", f"*{spec_hash}*"]
        find_result = subprocess.run(
            find_cmd,
            capture_output=True,
        )

        # Check for an error searching for the spec
        manifest_path = find_result.stdout.decode("utf-8").strip()
        if not manifest_path or find_result.returncode != 0:
            LOGGER.error(f"[{find_cmd}] failed to find manifest for /{spec_hash} in {stack}")
            return (None, None, None, None)

        manifest_dict = extract_json_from_clearsig(manifest_path)
        return (spec_hash, stack, manifest_dict, manifest_path)

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [executor.submit(_process_manifest_fn, *task) for task in task_list]
        for future in as_completed(futures):
            try:
                spec_hash, stack, manifest_dict, manifest_path = future.result()
                if not spec_hash or not stack or not manifest_dict or not manifest_path:
                    continue

                stack_specs[stack][spec_hash].stack = stack
                stack_specs[stack][spec_hash].manifest_path = manifest_path
                stack_specs[stack][spec_hash].meta = format_blob_url(
                    f"{ref}/{stack}",
                    find_data_with_media_type(
                        manifest_dict["data"], SPEC_METADATA_MEDIA_TYPE
                    ),
                )
                stack_specs[stack][spec_hash].archive = format_blob_url(
                    f"{ref}/{stack}",
                    find_data_with_media_type(
                        manifest_dict["data"], TARBALL_MEDIA_TYPE
                    ),
                )
            except Exception as exc:
                LOGGER.error(f"Exception processing manifests: {exc}")

    # Cleanup the tmpdir
    if delete_on_exit:
        shutil.rmtree(tmpdir)
    return stack_specs, top_level_specs


################################################################################
# If the cli didn't provide a working directory, we will create (and clean up)
# a temporary directory.
def get_workdir_context(workdir: Optional[str] = None):
    if not workdir:
        return tempfile.TemporaryDirectory()

    return contextlib.nullcontext(workdir)


listing_prefix = os.environ.get("LISTING_CACHE_PREFIX", ".")
################################################################################
# Given a url and a file path to use for writing, get a recursive listing of
# everything under the prefix defined by the url, and write it to disk using the
# supplied path.
def list_prefix_contents(url: str, output_prefix: Optional[str] = None, force: bool = False, iterator: bool = False):

    # Auto caching of listing file
    global listing_prefix
    if not output_prefix:
        if not listing_prefix:
            listing_prefix = tempfile.mkdtemp()
        output_prefix = listing_prefix

    # Store the listing has the checksum of the url
    h = hashlib.sha256()
    h.update(url.encode())
    output_file = os.path.join(output_prefix, h.hexdigest())

    if not os.path.isfile(output_file) or force:
        if iterator:
            client = s3_create_client()
            purl = urllib.parse.urlparse(url)
            prefix = re.sub("^/*", "/")
            list_args = dict(Bucket=url.netloc, Prefix=prefix)
            # Local buffer of objects to cache to a file
            all_objects = []
            while True:
                resp = client.list_objects_v2(**list_args)

                all_objects.extend(resp.get("Contents", []))
                obj = None
                for obj in resp.get("Contents", []):
                    yield obj["Key"]

                if resp.get("IsTruncated", False) and obj:
                    list_args.update({
                        "StartAfter": obj
                    })
                else:
                    break

            # Write the listing in the same format used by "aws s3 ls"
            dt_format = "%Y-%m-%d %H:%M:%S"
            msize = max([obj["Size"] for obj in all_objects])
            msize = math.ceil(math.log(msize) / math.log(10)) + 1
            with open(output_file, "w", encoding="utf=8") as fd:
                for obj in all_objects:
                    date_time = obj["LastModified"].strftime(dt_format)
                    size = obj["Size"]
                    key = obj["Key"]
                    fd.write(f"{date_time} {size:msize} {key}\n")

        else:
            LOGGER.info(f"Writing cached listfile for {url} to {output_file}")
            list_cmd = ["aws", "s3", "ls", "--recursive", url]
            with open(output_file, "w") as f:
                subprocess.run(list_cmd, stdout=f, stderr=subprocess.DEVNULL, check=True)
    elif iterator:
        with open(output_file, "r", encoding="utf-8") as fd:
            for line in fd
                m = REGEX_LISTING_DATA.search(line)
                if m:
                    yield m.group(3).strip()

    if not iterator:
        return output_file


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
def clone_spack(spack_ref: str = "develop", packages_ref: str = "develop", spack_repo: str = SPACK_REPO, packages_repo: str = PACKAGES_REPO, clone_dir: str = "/"):
    spack_path = f"{clone_dir}/spack"
    packages_path = f"{clone_dir}/spack-packages"

    if os.path.isdir(spack_path):
        shutil.rmtree(spack_path)

    if os.path.isdir(packages_path):
        shutil.rmtree(packages_path)

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
                f"{spack_ref}",
                f"{spack_repo}",
                spack_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                f"{packages_ref}",
                f"{packages_repo}",
                packages_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        # Configure the repo destination
        subprocess.run(
            [
                "spack/bin/spack",
                "repo",
                "set",
                "builtin",
                "--destination",
                packages_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
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
# Create and return a new s3 client by first creating a Session, using that to
# create a new "s3" resource, and return the client stored within the resources
# metadata.
def s3_create_client():
    session = boto3.session.Session()
    s3_resource = session.resource("s3")
    return s3_resource.meta.client

################################################################################
# Copy objects between s3 buckets/prefixes
def s3_copy_file(copy_source: Dict[str, str], bucket: str, dest_prefix: str, client=None):
    if client:
        s3_client = client
    else:
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
def s3_upload_file(file_path: str, bucket: str, prefix: str, client=None):
    if client:
        s3_client = client
    else:
        session = boto3.session.Session()
        s3_resource = session.resource("s3")
        s3_client = s3_resource.meta.client

    with open(file_path, "rb") as fd:
        s3_client.upload_fileobj(fd, bucket, prefix)


def s3_object_exists(bucket: str, key: str, client=None):
    """Check if an s3 object exists"""

    if client:
        s3_client = client
    else:
        s3_client = s3_create_client()

    try:
        _ = s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


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
