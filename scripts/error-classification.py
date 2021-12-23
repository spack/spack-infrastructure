#!/usr/bin/env python3

import csv
import glob
import itertools
import logging
import os
from pathlib import Path
import random
import re
import subprocess
import sys

import click
from click_loglevel import LogLevel
import pandas as pd
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
            logging.warning(f'Got {response.status_code} for {api_link}')
            text = f'ERROR: Got {response.status_code} for {api_link}'

        if text == '':
            logging.warning(f'Log File Empty {api_link}')
            text = 'ERROR: Log File Empty'

        with open(f'{self.out_dir}/{job_id}.log', 'w') as f:
            f.write(text)

        logging.debug(f'Log saved to {self.out_dir}/{job_id}.log')
        return

    def process_csv(self, dict_reader):
        for i, row in enumerate(dict_reader):
            logging.info(f'{i}: Getting {row["api_link"]}')
            self.scrape(row['api_link'])


class ErrorClassifier(object):
    def __init__(self, csv_path=None, log_dir='error_logs', taxonomy=None):
        if taxonomy is None:
            self.taxonomy = {
                'no_runner': lambda df: df['runner'].isna(),
                'job_log_missing': ["ERROR: Got [0-9][0-9][0-9] for",
                                    "ERROR: Log File Empty"],
                '5XX': 'HTTP Error 5[00|02|03]',
                'spack_root': 'Error: SPACK_ROOT',
                'setup_env': 'setup-env.sh: No such file or directory',
                'no_spec': 'SpackError: No installed spec matches the hash',
                'build_error': ['error found in build log:',
                                'errors found in build log:'],
                'oom': ['command terminated with exit code 137',
                        'ERROR: Job failed: exit code 137'],
                'gitlab_down': 'fatal: unable to access',
                'module_not_found': 'ModuleNotFoundError: No module named',
                'artifacts': ['ERROR: Uploading artifacts',
                              'ERROR: Downloading artifacts'],
                'dial_backend': 'error dialing backend',
                'pod_cleanup': 'Error cleaning up pod',
                'pod_exec': 'Error response from daemon: No such exec instance',
                'cmd_not_found': 'Command exited with status 127',
                'db_mismatch': 'Error: Expected database version',
                'db_match': 'spack.store.MatchError:',
                'pod_timeout': 'timed out waiting for pod to start',
                'docker_daemon': 'Cannot connect to the Docker daemon',
                'rcp_failure': 'error: RPC failed',
                'spack_error': 'To reproduce this build locally, run:',
                'remote_not_found': ['fatal: Remote branch',
                                     'fatal: couldn\'t find remote ref'],
                'pipeline_generation': 'Error: Pipeline generation failed',
                'killed': 'Killed',
                'remote_discontect': 'http.client.RemoteDisconnected',
                'db_hash': 'Error: Expected database index keyed by',
                'image_pull': ['Job failed (system failure): prepare environment: image pull failed',
                               'ERROR: Job failed (system failure): failed to pull image'],
                'other_errors': self._other_errors
            }
        else:
            self.taxonomy = taxonomy

        if csv_path is not None and log_dir is not None:
            self.init_dataframe(csv_path, log_dir)

    def _verify_df(self):
        log_files = set([int(Path(s).stem) for s
                         in glob.glob(f'{self.log_dir}/*.log')])
        idx = set(self.df.index)

        def _log_file(id):
            return f'  {self.log_dir}/{id}.log'

        if log_files - idx:
            raise RuntimeError(
                f'Log files present which are not in CSV: {os.linesep}'
                f'{os.linesep.join([_log_file(s) for s in log_files - idx])}')

        if idx - log_files:
            raise RuntimeError(
                f'Errors in CSV without job logs (the following are missing): {os.linesep}'
                f'{os.linesep.join([_log_file(s) for s in idx - log_files])}'
                f'{os.linesep}Try running "get-logs" on {self.csv_path}')

    def _kind(self, r):
        if pd.isnull(r):
            return 'None'
        elif r.startswith('uo'):
            return 'UO'
        else:
            return 'AWS'

    def _grep_for_ids(self, match_string):
        _match_group = '1'
        output = subprocess.getoutput(
            f'grep -l "{match_string}" {self.log_dir}/*.log | '
            f'sed -e "s|^.*/\(.*\).log|\\{_match_group}|"')
        return [int(s) for s in output.split('\n')] if output else []

    def _other_errors(self, df):
        target_columns = list(set(self.error_columns) - set(['other_errors']))
        return df[target_columns].apply(lambda row: not any(list(row)), axis=1)

    @property
    def error_columns(self):
        return list(self.taxonomy.keys())

    def init_dataframe(self, csv_path, log_dir):
        self.log_dir = log_dir
        self.csv_path = csv_path

        self.df = pd.read_csv(csv_path,
                              index_col='id',
                              infer_datetime_format=True)
        self._verify_df()

        self.df['created_at'] = pd.to_datetime(self.df['created_at'])
        # Create 'kind' column
        self.df['kind'] = self.df['runner'].apply(self._kind)


    
    def classify(self):
        for col, expr in self.taxonomy.items():
            # If this is a function, just call the function with the data frame
            # and set the column to the values.
            if callable(expr):
                self.df[col] = expr(self.df)

            else:
                # If this is a bare string, convert it to a list with one
                # element (the string).
                if isinstance(expr, str):
                    expr = [expr]

                # Create the column and set to False
                self.df[col] = False
                # Loop through strings in expr and greatp for IDs. Set the
                # column of these ids to True.
                for s in expr:
                    ids = self._grep_for_ids(s)
                    self.df.at[ids, col] = True

            logging.info(f'Processed {col} ({self.df[col].value_counts().loc[True]})')

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

        # Note: We stuff the file_name on the reader in case we want to use it
        # later. This is a non-standard API!
        reader.file_name = value

        if not self.required_fields <= set(reader.fieldnames):
            self.fail(f'CSV does not contain the following columns: '
                      f'{self.required_fields - set(reader.fieldnames)}')
        return reader


@click.group()
@click.option("-l", "--log-level", type=LogLevel(), default=logging.WARNING)
def cmd(log_level):
    logging.basicConfig(level=log_level)

@cmd.command()
@click.option('-o', '--output', default='error_logs',
              type=click.Path(file_okay=False),
              help="Output directory for error logs.")
@click.option('-t', '--token', required=True,
              default=lambda: os.environ.get('API_TOKEN'),
              help='Spack GitLab API Token (or API_TOKEN environment variable)')
@click.option('-c', '--cache', default='error_log',
              help='Requests cache file name')
@click.argument('error_csv', type=ErrorLogCSVType(mode='r'))
def get_logs(error_csv, output, token, cache):
    os.makedirs(output, exist_ok=True)
    scraper = JobLogScraper(token, session_name=cache, out_dir=output)
    scraper.process_csv(error_csv)

@cmd.command()
@click.option('-i', '--input-dir', default='error_logs',
              type=click.Path(exists=True, file_okay=False),
              help="Directory containing job logs")
@click.option('-o', '--output', default=None,
              help="Save annotated CSV to this file name (default [ERROR_CSV]_annotated.csv)")
@click.argument('error_csv', type=ErrorLogCSVType(mode='r'))
def classify(error_csv, input_dir, output):
    if output is None:
        path = Path(error_csv.file_name)
        output = os.path.join(path.parents[0], f'{path.stem}_annotated.csv')

    classifier = ErrorClassifier(error_csv.file_name, log_dir=input_dir)
    classifier.classify()

    logging.info(f'Saving to {output}')
    classifier.df.to_csv(output)


@cmd.command()
@click.option('-i', '--input-dir', default='error_logs',
              type=click.Path(exists=True, file_okay=False),
              help="Directory containing job logs")
@click.argument('annotated_error_csv')
@click.argument('error_class')
def random_log(annotated_error_csv, error_class, input_dir):
    if error_class not in ErrorClassifier().error_columns:
        click.echo(
            f'ERROR: "{error_class}" not one of: {os.linesep}'
            f'{os.linesep.join(["  " + s for s in ErrorClassifier().error_columns])}',
            err=True)
        sys.exit(1)

    df = pd.read_csv(annotated_error_csv,
                     index_col='id')
    idx = random.choice(df[df[error_class]].index)
    with open(f'{input_dir}/{idx}.log', 'r') as fh:
        click.echo(fh.read())

@cmd.command()
@click.argument('error_csv', type=ErrorLogCSVType(mode='r'))
def overlap(error_csv):
    df = pd.read_csv(error_csv.file_name,
                     index_col='id',
                     infer_datetime_format=True)

    columns = ErrorClassifier().error_columns

    def _overlap(columns):
        for (a, b) in itertools.combinations(columns, 2):
            numerator = len(df[(df[a] == True) & (df[b] == True)])
            denominator = len(df[(df[a] == True) | (df[b] == True)])
            if a != b and numerator > 0:
                yield (a, b,
                       numerator,
                       denominator,
                       round((numerator/float(denominator)) * 100, 2))


    o = pd.DataFrame(list(_overlap(columns)),
                     columns=['A', 'B', 'overlap', 'total', 'percent'])
    o.set_index(['A', 'B'], inplace=True)
    o.sort_values('percent', ascending=False, inplace=True)

    print(o)

if __name__ == '__main__':
    cmd()
