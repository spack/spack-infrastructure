from __future__ import annotations

import json
import logging
import os
import re
import tarfile
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import boto3
import requests
from botocore import UNSIGNED
from botocore.client import Config

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

    def _convert_booleans_to_strings(obj):
        if isinstance(obj, bool):
            return str(obj).lower()
        if isinstance(obj, (list, tuple)):
            return [_convert_booleans_to_strings(item) for item in obj]
        if isinstance(obj, dict):
            return {
                key: _convert_booleans_to_strings(value) for key, value in obj.items()
            }
        return obj

    res = requests.post(
        f"{OPENSEARCH_ENDPOINT}/pipeline-logs-{TODAY.strftime('%Y.%m.%d')}/_doc",
        data=json.dumps(_convert_booleans_to_strings(log_data)),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    res.raise_for_status()


def upload_to_opensearch(
    build_hash: str,
    spec_json: dict,
    install_times_json: dict,
    spack_build_out: dict[str, str],
):
    """
    Given a spec.json, install_times.json, and spack-build-out files, package them all
    into a single JSON document and POSTs them to the OpenSearch API.
    """
    # Check if a document with this hash already exists, and if so don't upload it.
    res = requests.get(
        f"{OPENSEARCH_ENDPOINT}/pipeline-logs*/_search",
        data=json.dumps({"query": {"match": {"hash": build_hash}}}),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    res.raise_for_status()

    if res.json()["hits"]["total"]["value"] > 0:
        logging.info(
            f"Skipping upload of record with build hash {build_hash} - already exists."
        )
        return

    document: dict[str, Any] = {}

    document["hash"] = build_hash
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
        data=json.dumps(
            {
                "mappings": {
                    "date_detection": False,
                    "properties": {
                        "spec.nodes.arch.target": {
                            "enabled": False,
                            "type": "object",
                        },
                    },
                }
            }
        ),
        headers={"Content-Type": "application/json"},
        auth=(OPENSEARCH_USERNAME, OPENSEARCH_PASSWORD),
    )
    if res.status_code >= 400:
        logging.error(
            f'Failed to create opensearch index "{index_name}", server responded with status {res.status_code}'
        )
        try:
            logging.error(res.json())
        except json.JSONDecodeError:
            logging.error(res.text)


def fetch_and_upload_tarball(spec_json_sig_key: str):
    logging.info(f'Fetching and uploading "{spec_json_sig_key}"...')

    # Extract metadata from *.spec.json.sig filename
    (os_arch, compiler, package, build_hash) = re.findall(
        rf"{PREFIX}/(.+)-(.+-[\d+\.]+)-(.+)-(.+).spec.json.sig",
        spec_json_sig_key,
    )[0]

    binary_prefix = f"{PREFIX}/{os_arch}/{compiler}/{package}"
    file_path = f"{binary_prefix}/{os_arch}-{compiler}-{package}-{build_hash}.spack"

    try:
        # Download the tarball, extract it to a temp directory, parse the build logs we're
        # interested in, and POST them to the OpenSearch cluster.
        with NamedTemporaryFile("rb+") as f:
            s3.download_fileobj(BUCKET, file_path, f)
            with tarfile.open(
                f.name, mode="r:gz"
            ) as tar, TemporaryDirectory() as temp_dir:
                tar.extract(f"{package}-{build_hash}/.spack/spec.json", path=temp_dir)
                tar.extract(
                    f"{package}-{build_hash}/.spack/install_times.json", path=temp_dir
                )

                spec_json = json.loads(
                    (
                        Path(temp_dir)
                        / f"{package}-{build_hash}"
                        / ".spack"
                        / "spec.json"
                    ).read_text()
                )
                install_times = json.loads(
                    (
                        Path(temp_dir)
                        / f"{package}-{build_hash}"
                        / ".spack"
                        / "install_times.json"
                    ).read_text()
                )

                spack_build_out: dict[str, str] = {}

                # Find all files with name in format of
                # `spack-build-<phase-name>-<phase-number>-out.txt`
                spack_build_out_paths = re.findall(
                    rf"{package}-{build_hash}/.spack/spack-build-(\d+)-(.+)-out.txt",
                    "\n".join(tar.getnames()),
                )

                # Extract all spack-build-<phase-name>-<phase-number>-out.txt files from the tarball
                # and add them as seperate entries in the spack_build_out JSON object.
                for phase_number, phase_name in spack_build_out_paths:
                    tar.extract(
                        f"{package}-{build_hash}/.spack/spack-build-{phase_number}-{phase_name}-out.txt",
                        path=temp_dir,
                    )
                    spack_build_out[f"{phase_number}-{phase_name}"] = (
                        Path(temp_dir)
                        / f"{package}-{build_hash}"
                        / ".spack"
                        / f"spack-build-{phase_number}-{phase_name}-out.txt"
                    ).read_text()

                upload_to_opensearch(
                    build_hash, spec_json, install_times, spack_build_out
                )
    except Exception as e:
        # Catch all exceptions and log error instead of crashing script
        logging.error(f'Error occurred while processing Key "{spec_json_sig_key}"')
        logging.error(f"Tarball S3 Key = {file_path}")
        logging.error(str(e))
        if isinstance(e, requests.HTTPError):
            try:
                logging.error(str(e.response.json()) + "\n")
            except json.JSONDecodeError:
                logging.error(str(e.response.content) + "\n")
        return


def main():
    """Iterate over the entire S3 bucket and send any new build logs to OpenSearch."""
    create_opensearch_index()

    all_pages = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=PREFIX):
        contents = [
            key["Key"]
            for key in page["Contents"]
            if key["Key"].endswith(".spec.json.sig")
        ]
        all_pages.extend(contents)

    with Pool(processes=os.cpu_count()) as pool:
        pool.map(fetch_and_upload_tarball, all_pages)
        pool.close()
        pool.join()


if __name__ == "__main__":
    main()
