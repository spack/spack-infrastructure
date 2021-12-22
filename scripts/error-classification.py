#!/usr/bin/env python3

import csv
import logging
import os
import re

import click
from click_loglevel import LogLevel
import requests_cache

class JobLogScraper(object):
    """Scrape job logs from GitLab API.

    This uses requests_cache to save requests to a sqlite cache file reducing
    the load on the GitLab API.

    """

    link_regex = re.compile(
        r'https://gitlab.spack.io/api/v4/projects/(?P<project>\d+)/jobs/(?P<job_id>\d+)/trace')

    def __init__(self, token,
                 session_name='error_log',
                 out_dir='error_logs'):
        self.session = requests_cache.CachedSession(session_name)
        self.out_dir = out_dir
        self.token = token

    def scrape(self, api_link):
        logging.debug(f'Getting {api_link}')
        match = self.link_regex.match(api_link)
        if match is None:
            logging.warning(f'API link {api_link} is not valid. Skipping!')
            return

        job_id = int(match.group('job_id'))

        response = self.session.get(
            api_link, headers={'PRIVATE-TOKEN': self.token})

        text = response.text

        if response.status_code != 200:
            logging.warning('Got {response.status_code} for {api_link}')
            text = f'ERROR: Got {response.status_code} for {api_link}.'

        with open(f'{self.out_dir}/{job_id}.log', 'w') as f:
            f.write(text)

        logging.debug(f'Log saved to {self.out_dir}/{job_id}.log')
        return

    def process_csv(self, dict_reader):
        for i, row in enumerate(dict_reader):
            logging.info(f'{i}: Getting {row["api_link"]}')
            self.scrape(row['api_link'])

class ErrorLogCSVType(click.File):
    """Given a CSV file, validate columns and return a csv.DictReader

    """
    name = "error_log_csv"
    required_fields = set([
        'id', 'name', 'created_at', 'duration', 'runner',
        'stage', 'ref', 'project_name', 'job_link', 'api_link'])

    def convert(self, value, param, ctx):
        fh = super().convert(value, param, ctx)
        reader = csv.DictReader(fh)
        if not self.required_fields <= set(reader.fieldnames):
            self.fail(f'CSV does not contain the following columns: '
                      f'{self.required_fields - set(reader.fieldnames)}')
        return reader

@click.group()
@click.option('-t', '--token', required=True,
              default=lambda: os.environ.get('API_TOKEN'),
              help='Spack GitLab API Token (or API_TOKEN environment variable)')
@click.option('-c', '--cache', default='error_log',
              help='Requests cache log-file name')
@click.option("-l", "--log-level", type=LogLevel(), default=logging.WARNING)
@click.pass_context
def cmd(ctx, token, cache, log_level):
    logging.basicConfig(level=log_level)
    ctx.obj = JobLogScraper(token, session_name=cache)

@cmd.command()
@click.option('-o', '--output', default='error_logs',
              type=click.Path(file_okay=False),
              help="Output directory for error logs.")
@click.argument('error_csv', type=ErrorLogCSVType(mode='r'))
@click.pass_obj
def get_logs(scraper, error_csv, output):
    os.makedirs(output, exist_ok=True)
    scraper.out_dir = output
    scraper.process_csv(error_csv)

if __name__ == '__main__':
    cmd()
