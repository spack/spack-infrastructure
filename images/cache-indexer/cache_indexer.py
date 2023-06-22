#!/usr/bin/env python

import json
import re
import subprocess


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


def build_json(root_url, index_paths):
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
                    "url": f"{root_url}/{p}",
                })

    return json_data


def query_bucket(root_url):
    cmd = f"aws s3 ls {root_url} --recursive | grep -E \"build_cache\/index\.json$\""
    task = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    data = task.stdout.read()
    assert task.wait() == 0

    lines = [s.strip() for s in data.decode("utf-8").split("\n") if s]
    regex = re.compile(f"([^\s]+)$")
    results = []

    for line in lines:
        m = regex.search(line)
        if m:
            results.append(m.group(1))

    return results


if __name__ == "__main__":
    root_url = "s3://spack-binaries"

    results = query_bucket(root_url)
    json_data = build_json(root_url, results)

    # with open("results.txt") as fd:
    #     results = [l.strip() for l in fd]
    # json_data = build_json(root_url, results)

    with open("output.json", "w") as fd:
        fd.write(json.dumps(json_data))

    cmd = ["aws", "s3", "cp", "output.json", "s3://spack-binaries/cache_spack_io_index.json"]
    proc = subprocess.run(cmd, capture_output=True)
    print(" ".join(cmd))
    print(proc.stdout)
    print(proc.stderr)
