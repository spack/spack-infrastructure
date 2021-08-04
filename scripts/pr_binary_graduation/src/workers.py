import asyncio
import logging


async def run_in_subprocess(cmd_string):
    proc = await asyncio.create_subprocess_shell(
        cmd_string,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    logging.info(f'[{cmd_string!r} exited with {proc.returncode}]')
    if stdout:
        logging.info(f'[stdout]\n{stdout.decode()}')
    if stderr:
        logging.info(f'[stderr]\n{stderr.decode()}')


async def copy_mirror_entries(src_mirror, dest_mirror):
    """ Use aws cli to copy recursively from one bucket to another """
    logging.info('Copying binaries from {0} to {1}'.format(src_mirror, dest_mirror))

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
    logging.info('Updating binary index at {0}'.format(mirror_url))

    cmd_elements = [
        "spack", "-d", "buildcache", "update-index", "--mirror-url", '"{0}"'.format(mirror_url)
    ]

    await run_in_subprocess(' '.join(cmd_elements))


async def test_worker():
    logging.info('Inside test_worker method')

    cmd_elements = [
        'ls', '-alt'
    ]

    await run_in_subprocess(' '.join(cmd_elements))
