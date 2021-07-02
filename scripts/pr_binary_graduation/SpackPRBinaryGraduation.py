#!/usr/bin/env python3

import argparse
import asyncio
import hmac

import aiohttp.web as aiohttp_web

import llnl.util.tty as tty
import spack.main as spack_main
import spack.util.url as url_util
import spack.util.web as web_util


PR_MIRROR_BASE_URL = 's3://spack-binaries-prs'


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


async def webhook_handler(request):
    if request.content_type != 'application/json':
        print('Ignoring non-JSON request')
        return

    payload = await request.json()

    if payload['action'] == 'closed' and payload['pull_request']['merged'] == True:
        pr_number = payload['number']
        pr_branch = payload['pull_request']['head']['ref']

        pr_mirror_url = '{0}/github/pr{1}_{2}'.format(PR_MIRROR_BASE_URL, pr_number, pr_branch)
        shared_mirror_url = '{0}/shared_pr_mirror'.format(PR_MIRROR_BASE_URL)

        print('this is a merged PR')
        print('Copying binaries from {0} to {1}'.format(pr_mirror_url, shared_mirror_url))

        # await copy_mirror_entries(pr_mirror_url, shared_mirror_url)
        # await update_mirror_index(shared_mirror_url)


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Start PR binary graduation webservice")
    args = parser.parse_args()

    print('Spack version:')
    print(spack_main.get_version())

    # src = 's3://spack-binaries-prs/github/pr24637_pipelines-add-broken-spec-details'
    # dest = 's3://spack-binaries-prs/shared-pr-mirror/test'

    # asyncio.run(test_methods(src, dest))

    app = aiohttp_web.Application()
    app.add_routes([aiohttp_web.post('/payload', webhook_handler)])
    aiohttp_web.run_app(app, port=4567)
