#!/usr/bin/env python3

import argparse
import asyncio
import logging
import sys

import aiohttp.web as aiohttp_web
from redis import Redis
from rq import Queue

import llnl.util.tty as tty
import spack.main as spack_main
import spack.util.url as url_util
import spack.util.web as web_util

from workers import copy_mirror_entries, update_mirror_index

PR_MIRROR_BASE_URL = 's3://spack-binaries-prs'
PR_EXPECTED_BASE = 'develop'


async def webhook_handler(request):
    if request.content_type != 'application/json':
        logging.debug('Ignoring non-JSON request')
        return aiohttp_web.Response(text="Non-JSON request ignored")

    # TODO: Make sure the request contains the secret token ensuring GitHub sent it

    payload = await request.json()
    action = payload['action']
    base = payload['pull_request']['base']['ref']
    is_merged = payload['pull_request']['merged']

    if action == 'closed' and base == PR_EXPECTED_BASE and is_merged:
        pr_number = payload['number']
        pr_branch = payload['pull_request']['head']['ref']

        pr_mirror_url = '{0}/github/pr{1}_{2}'.format(PR_MIRROR_BASE_URL, pr_number, pr_branch)
        shared_mirror_url = '{0}/shared_pr_mirror'.format(PR_MIRROR_BASE_URL)

        logging.info('PR {0}/{1} merged to develop, graduating binaries'.format(
            pr_number, pr_branch))

        # We need to respond to github within 10 seconds, see here:
        #
        #     https://docs.github.com/en/rest/guides/best-practices-for-integrators#favor-asynchronous-work-over-synchronous
        #
        # So we schedule the work asynchronously

        q = request.app['state']['work_queue']

        copy_job = q.enqueue(copy_mirror_entries, pr_mirror_url, shared_mirror_url)
        logging.info('Copy job queued: {0}'.format(copy_job.id))

        # TODO: Improve scheduling of the update-index job
        update_job = q.enqueue(update_mirror_index, shared_mirror_url, depends_on=copy_job.id)
        logging.info('update-index job queued: {0}'.format(update_job.id))
        return aiohttp_web.Response(text="Request processed")

    logging.info('Ignoring PR {0}, action = {1}, base = {2}, merged = {3}'.format(
        pr_number, action, base, is_merged))
    return aiohttp_web.Response(text="Irrelevant request ignored")


async def test_handler(request):
    logging.info('inside the test_handler')

    q = request.app['state']['work_queue']

    from workers import test_worker

    test_job = q.enqueue(test_worker)
    logging.info('Copy job queued: {0}'.format(test_job.id))

    return aiohttp_web.Response(text="Request processed")


if __name__ == "__main__":
    # Parse command-line arguments.
    parser = argparse.ArgumentParser(description="Start PR binary graduation webservice")
    parser.add_argument('--redis-host', type=str, default='localhost', help="redis server hostname")
    parser.add_argument('--redis-port', type=int, default=6379, help="redis server port")
    parser.add_argument('--work-queue', type=str, default='jobs', help="name of job queue")
    parser.add_argument('--web-server-host', type=str, default='0.0.0.0', help="Host webserver should bind to")
    parser.add_argument('--web-server-port', type=int, default=4567, help="Port webserver should bind to")
    args = parser.parse_args()

    # TODO: Allow cli opts to specify log level and output location
    logging.basicConfig(level=logging.DEBUG)

    logging.debug('Spack version:')
    logging.debug(spack_main.get_version())

    redis_conn = Redis(host=args.redis_host, port=args.redis_port)
    q = Queue(name=args.work_queue, connection=redis_conn)

    app = aiohttp_web.Application()
    app.add_routes([aiohttp_web.post('/payload', webhook_handler)])
    app.add_routes([aiohttp_web.get('/payload', test_handler)])
    app['state'] = {
        'work_queue': q
    }
    aiohttp_web.run_app(app, host=args.web_server_host, port=args.web_server_port)
