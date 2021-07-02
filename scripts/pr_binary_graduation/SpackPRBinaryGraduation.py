#!/usr/bin/env python3

import argparse
import asyncio

import llnl.util.tty as tty
import spack.main as spack_main
import spack.util.url as url_util
import spack.util.web as web_util


async def run_in_subprocess(cmd_string):
    proc = await asyncio.create_subprocess_shell(
        cmd_string,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd_string!r} exited with {proc.returncode}]')
    if stdout:
        print(f'[stdout]\n{stdout.decode()}')
    if stderr:
        print(f'[stderr]\n{stderr.decode()}')


async def copy_mirror_entries(src_mirror, dest_mirror):
    """ Use aws cli to copy recursively from one bucket to another """
    cmd_elements = [
        "aws", "s3", "cp", src_mirror, dest_mirror,
        "--exclude", '"*"',
        "--include", '"*.cdashid"',
        "--include", '"*.spec.yaml"',
        "--include", '"*.spack"',
        "--recursive"
    ]

    await run_in_subprocess(' '.join(cmd_elements))


async def update_mirror_index(mirror_url):
    """ Use spack buildcache command to update index on remote mirror """
    cmd_elements = [
        "spack", "-d", "buildcache", "update-index", "--mirror-url", '"{0}"'.format(mirror_url)
    ]

    await run_in_subprocess(' '.join(cmd_elements))


async def test_methods(src_mirror, dest_mirror):
    await copy_mirror_entries(src_mirror, dest_mirror)

    await update_mirror_index(dest_mirror)


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Start PR binary graduation webservice")
    args = parser.parse_args()

    print('Spack version:')
    print(spack_main.get_version())

    src = 's3://spack-binaries-prs/github/pr24637_pipelines-add-broken-spec-details'
    dest = 's3://spack-binaries-prs/shared-pr-mirror/test'

    asyncio.run(test_methods(src, dest))
