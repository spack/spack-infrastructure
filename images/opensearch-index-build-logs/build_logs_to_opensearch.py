from __future__ import annotations

import json
import logging
import os
import re
import tarfile
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import boto3
import requests
from botocore import UNSIGNED
from botocore.client import Config
from botocore.exceptions import ClientError

# Authenticate the boto3 client with AWS.
# Since the spack build cache is a public S3 bucket, we don't need credentials
s3 = boto3.client(
    "s3", config=Config(signature_version=UNSIGNED), region_name="us-east-1"
)

logging.basicConfig(level=logging.ERROR)  # Only log ERROR messages

BUCKET = "spack-binaries"
PREFIX = "develop/build_cache"

OPENSEARCH_ENDPOINT = os.environ["OPENSEARCH_ENDPOINT"]
OPENSEARCH_USERNAME = os.environ["OPENSEARCH_USERNAME"]
OPENSEARCH_PASSWORD = os.environ["OPENSEARCH_PASSWORD"]

TODAY = datetime.today()


def post_logs(log_data):
    """Post the given JSON log data to OpenSearch."""
    res = requests.post(
        f"{OPENSEARCH_ENDPOINT}/pipeline-logs-{TODAY.strftime('%Y.%m.%d')}/_doc",
        data=json.dumps(log_data),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    if res.status_code >= 400:
        logging.error(f"Failed to POST logs to OpenSearch. Log dump: {log_data}")


def upload_to_opensearch(
    spec_json: dict, install_times_json: dict, spack_build_out: dict[str, str]
):
    """
    Given a spec.json, install_times.json, and spack-build-out files, package them all
    into a single JSON document and POSTs them to the OpenSearch API.
    """
    document = {}
    document["spec"] = spec_json["spec"]
    document["install_times"] = install_times_json
    document["spack-build-out"] = spack_build_out

    post_logs(document)


def create_opensearch_index():
    """
    Create an opensearch index for the current date.

    This operation is idempotent; if an index already exists for the current date, the server will
    not create a new one.
    """
    index_name = f"pipeline-logs-{TODAY.strftime('%Y.%m.%d')}"
    res = requests.put(
        f"{OPENSEARCH_ENDPOINT}/{index_name}",
        # Disable date_detection. OpenSearch thinks the `version` field in spec.json is a date
        # for some reason.
        data=json.dumps({"mappings": {"date_detection": False}}),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    if res.status_code >= 400:
        logging.error(
            f'Failed to create opensearch index "{index_name}", server responded with status {res.status_code}'
        )


def fetch_and_upload_tarball(spec_json_sig_key: str):
    logging.info(f'Fetching and uploading "{spec_json_sig_key}"...')

    # Extract metadata from *.spec.json.sig filename
    (os_arch, compiler, package, hash) = re.findall(
        rf"{PREFIX}/(.+)-(.+-[\d+\.]+)-(.+)-(.+).spec.json.sig",
        spec_json_sig_key,
    )[0]

    binary_prefix = f"{PREFIX}/{os_arch}/{compiler}/{package}"

    # Download the tarball, extract it to a temp directory, parse the build logs we're
    # interested in, and POST them to the OpenSearch cluster.
    with NamedTemporaryFile("rb+") as f:
        file_path = f"{binary_prefix}/{os_arch}-{compiler}-{package}-{hash}.spack"
        try:
            s3.download_fileobj(BUCKET, file_path, f)
        except ClientError as e:
            logging.error(e)
            return
        with tarfile.open(f.name, mode="r:gz") as tar, TemporaryDirectory() as temp_dir:
            tar.extract(f"{package}-{hash}/.spack/spec.json", path=temp_dir)
            tar.extract(f"{package}-{hash}/.spack/install_times.json", path=temp_dir)

            spec_json = json.loads(
                (
                    Path(temp_dir) / f"{package}-{hash}" / ".spack" / "spec.json"
                ).read_text()
            )
            install_times = json.loads(
                (
                    Path(temp_dir)
                    / f"{package}-{hash}"
                    / ".spack"
                    / "install_times.json"
                ).read_text()
            )

            spack_build_out: dict[str, str] = {}

            # Find all files with name in format of
            # `spack-build-<phase-name>-<phase-number>-out.txt`
            spack_build_out_paths = re.findall(
                rf"{package}-{hash}/.spack/spack-build-(\d+)-(.+)-out.txt",
                "\n".join(tar.getnames()),
            )

            # Extract all spack-build-<phase-name>-<phase-number>-out.txt files from the tarball
            # and add them as seperate entries in the spack_build_out JSON object.
            for phase_number, phase_name in spack_build_out_paths:
                tar.extract(
                    f"{package}-{hash}/.spack/spack-build-{phase_number}-{phase_name}-out.txt",
                    path=temp_dir,
                )
                spack_build_out[f"{phase_number}-{phase_name}"] = (
                    Path(temp_dir)
                    / f"{package}-{hash}"
                    / ".spack"
                    / f"spack-build-{phase_number}-{phase_name}-out.txt"
                ).read_text()

            upload_to_opensearch(spec_json, install_times, spack_build_out)


def main():
    """Iterate over the entire S3 bucket and send any new build logs to OpenSearch."""
    create_opensearch_index()
    paginator = s3.get_paginator("list_objects_v2")
    for result in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        for obj in result["Contents"]:
            # Ignore files that don't end in spec.json.sig
            if not obj.get("Key", "").endswith(".spec.json.sig"):
                continue
            # Ignore files that aren't from today
            if obj["LastModified"].date() != TODAY.date():
                continue
            fetch_and_upload_tarball(obj["Key"])


if __name__ == "__main__":
    main()
