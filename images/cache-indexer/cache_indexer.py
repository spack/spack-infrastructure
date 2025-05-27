#!/usr/bin/env python

import io
import json
import re
import os

import boto3
import sentry_sdk

sentry_sdk.init(
    # This cron job only runs once a day,
    # so just record all transactions.
    traces_sample_rate=1.0,
)

# Describe the spack refs to include in the cache.spack.io website
REF_REGEXES = [
    re.compile(r"^develop-[\d]+-[\d]+-[\d]+$"), # dev snapshot mirrors
    re.compile(r"^develop$"),                   # main develop mirror
    re.compile(r"^v[\d]+\.[\d]+\.[\d]+$"),      # mirrors for point releases
]

# Stacks or other "subdirectories" to ignore under *any* ref
SUBREF_IGNORE_REGEXES = [
    re.compile(r"^deprecated$"),
    re.compile(r"^e4s-mac$"),
]

# Regex and path to find modern index manifest
ROOT_PATTERN = r"v[\d]+"
INDEX_PATH = r"manifests/index/index.manifest.json"

INDEX_MEDIA_TYPE_PREFIX = "application/vnd.spack.db"

ROOT_MATCHER = re.compile(rf"^{ROOT_PATTERN}$")
INDEX_MATCHER = re.compile(rf"/{ROOT_PATTERN}/{INDEX_PATH}$")

class IndexManifestError(Exception):
    pass


def get_label(subref):
    if ROOT_MATCHER.match(subref):
        return "root" # or top-level?
    for regex in SUBREF_IGNORE_REGEXES:
        if regex.match(subref):
            return None
    return subref


def get_matching_ref(ref):
    for regex in REF_REGEXES:
        if regex.match(ref):
            return ref
    return None


def get_index_blob(manifest_data):
    for elt in manifest_data:
        if elt["mediaType"].startswith(INDEX_MEDIA_TYPE_PREFIX):
            return elt
    raise IndexManifestError("Unable to find index blob in manifest")


def get_index_url(bucket_name, prefix):
    # v2 layout: Indices are found directly
    if prefix.endswith("index.json"):
        return f"s3://{bucket_name}/{prefix}"

    # v3 layout: Indices must be found via manifest
    fd = io.BytesIO()
    session = boto3.session.Session()
    s3_resource = session.resource("s3")
    s3_client = s3_resource.meta.client
    s3_client.download_fileobj(bucket_name, prefix, fd)
    manifest_data = json.loads(fd.getvalue().decode("utf-8"))
    index_blob = get_index_blob(manifest_data["data"])
    hash_algo = index_blob["checksumAlgorithm"]
    checksum = index_blob["checksum"]

    m = re.match(rf"^(.+)/{ROOT_PATTERN}/manifests", prefix)
    if not m:
        raise IndexManifestError(f"Unrecognized manifest url pattern: {prefix}")

    return f"s3://{bucket_name}/{m.group(1)}/blobs/{hash_algo}/{checksum[:2]}/{checksum}"


def build_json(bucket_name, index_paths):
    json_data = {}

    for p in index_paths:
        parts = p.split("/")
        ref = get_matching_ref(parts[0])
        if ref:
            if ref not in json_data:
                json_data[ref] = []
            mirror_label = get_label(parts[1])
            if mirror_label:
                try:
                    json_data[ref].append({
                        "label": mirror_label,
                        "url": get_index_url(bucket_name, p),
                    })
                except IndexManifestError as e:
                    print(f"Skipping {p} due to: {e}")
                    continue

    return json_data


def query_bucket(bucket_name):
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name)
    results = []
    for page in pages:
        for obj in page["Contents"]:
            if INDEX_MATCHER.search(obj["Key"]):
                results.append(obj["Key"])

    return results


if __name__ == "__main__":
    bucket_name = os.environ["BUCKET_NAME"]

    results = query_bucket(bucket_name)
    json_data = build_json(bucket_name, results)

    with open("output.json", "w") as fd:
        fd.write(json.dumps(json_data))

    client = boto3.client("s3")
    client.upload_file("output.json", bucket_name, "cache_spack_io_index.json")
