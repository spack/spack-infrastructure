import argparse
import io
import json
import re
import sys
from datetime import datetime

import botocore.exceptions
import boto3.session
import sentry_sdk

sentry_sdk.init(traces_sample_rate=1.0)


################################################################################
#
def validate_mirror_index(index_data):
    installs = index_data["database"]["installs"]

    total_count = 0
    missing = []

    for hash, install_obj in installs.items():
        spec_obj = install_obj["spec"]
        if "external" not in spec_obj and not install_obj["in_buildcache"]:
            name = spec_obj["name"]
            missing.append(f"{name}/{hash[:7]}")

        total_count += 1

    present_count = total_count - len(missing)

    print(
        f"There are {total_count} specs in the index, {present_count} "
        f"are present, and {len(missing)} are missing"
    )

    if missing:
        print("Missing specs:")
        for item in missing:
            print(f"    {item}")


################################################################################
#
def validate_s3_index(url):
    url_regex = re.compile(r"^s3://([^/]+)/(.+)$")
    m = url_regex.match(url)
    if not m:
        print(f"url {url} could not be understood (s3 urls only)")
        sys.exit(1)

    bucket = m.group(1)
    prefix = f"{m.group(2)}/build_cache/index.json"

    session = boto3.session.Session()
    s3_client = session.client("s3")

    try:
        buf = io.BytesIO()
        s3_client.download_fileobj(bucket, prefix, buf)
        index_data = json.loads(buf.getvalue().decode("utf-8"))
    except botocore.exceptions.ClientError as error:
            error_msg = getattr(error, "message", error)
            error_msg = f"Failed to download {bucket} {prefix} due to {error_msg}"
            sys.exit(1)

    validate_mirror_index(index_data)


################################################################################
#
def validate_file_index(file_path):
    try:
        with open(file_path) as f:
            index_data = json.load(f)
    except Exception as error:
            error_msg = getattr(error, "message", error)
            error_msg = f"Failed to read {file_path} due to {error_msg}"
            sys.exit(1)

    validate_mirror_index(index_data)


################################################################################
#
def main():
    start_time = datetime.now()
    print(f"Validattion script started at {start_time}")

    parser = argparse.ArgumentParser(
        prog="validate_index.py",
        description="Fetch mirror index from S3 or file path and report on any 'holes'",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-u", "--url", default=None, help="URL of S3 mirror to validate"
    )
    group.add_argument(
        "-f", "--file", default=None, help="Absolute path to local index file"
    )

    args = parser.parse_args()

    if not args.url and not args.file:
        print("Either '--file' or '--url' argument required")
        sys.exit(1)

    if args.file:
        validate_file_index(args.file)
    else:
        validate_s3_index(args.url)

    end_time = datetime.now()
    elapsed = end_time - start_time
    print(f"Validation script finished at {end_time}, elapsed time: {elapsed}")


################################################################################
#
if __name__ == "__main__":
    main()
