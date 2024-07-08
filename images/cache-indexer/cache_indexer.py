#!/usr/bin/env python

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


def get_label(subref):
    if subref == "build_cache":
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
                json_data[ref].append({
                    "label": mirror_label,
                    "url": f"s3://{bucket_name}/{p}",
                })

    return json_data


def query_bucket(bucket_name):
    client = boto3.client("s3")
    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name)
    results = []
    for page in pages:
        for obj in page["Contents"]:
            if obj["Key"].endswith("/build_cache/index.json"):
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
