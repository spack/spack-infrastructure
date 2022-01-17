#!/usr/bin/env python3

import os
import re
import sys
import click
import requests
import psycopg2
from psycopg2.extras import RealDictCursor

GH_PR_RE = re.compile(r'^github/pr(\d+)_')

def _gh_pr_num(branch):
    match = GH_PR_RE.match(branch)
    return int(match.group(1)) if match else 0


class DBAndAPIAccess(object):
    """Dead simple object that provides DB and API access to the gitlab instance.

    """
    def _envvar_or_error(self, envvar):
        """Raise Runtime error if envvar is not set.

        """
        var = os.environ.get(envvar, None)
        if var is None:
            raise RuntimeError(f'{envvar} must be set for script to work!')
        return var

    def __init__(self):
        self.token = self._envvar_or_error('GITLAB_API_TOKEN')
        self._pg_params = {
            "host": self._envvar_or_error('GITLAB_PG_HOST'),
            "port": self._envvar_or_error('GITLAB_PG_PORT'),
            "dbname": self._envvar_or_error('GITLAB_PG_DBNAME'),
            "user": self._envvar_or_error('GITLAB_PG_USER'),
            "password": self._envvar_or_error('GITLAB_PG_PASS')
        }

    def __enter__(self):
        self.conn = psycopg2.connect(**self._pg_params)
        return self

    def __exit__(self, exc_type,exc_value, exc_traceback):
        self.conn.close()

    def get(self, url):
        """get JSON from an API endpoint"""
        response = requests.get(url, headers={'PRIVATE-TOKEN': self.token})
        # TODO Status code check?
        return response.json()

    def execute(self, sql, args=()):
        """Execute SQL against the Database"""
        try:
            cur = self.conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(sql, args)
            return [dict(r) for r in cur.fetchall()]
        finally:
            if cur:
                cur.close()

    def close(self):
        self.conn.close()


@click.command()
@click.option('-p', '--project-id', default=2)
@click.option('-t', '--threshold', default=28000)
def cli(project_id, threshold):
    _exit = 0
    with DBAndAPIAccess() as dbapi:
        branches = set([
            r['name'] for r in
            dbapi.get(f'https://gitlab.spack.io/api/'
                      f'v4/projects/{project_id}/repository/branches')
        ])

        pipelines = set([
            r['ref'] for r in
            dbapi.execute("SELECT DISTINCT(ref) FROM ci_pipelines "
                          "WHERE project_id = %s", (project_id,))
        ])

        for b in branches:
            if b not in pipelines and _gh_pr_num(b) > threshold:
                click.echo(click.style(b, fg='red'))
                # TODO - manually force pipeline trigger!
                _exit = 1

    sys.exit(_exit)

if __name__ == "__main__":
    cli()
