import argparse
from contextlib import closing
from datetime import datetime
import sqlite3
import sys

DB_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def get_total_time_and_split(job_list):
    total_time = 0
    uo_jobs = 0
    cluster_jobs = 0
    dev_jobs = 0
    pr_jobs = 0

    for job in job_list:
        pr_num = job[0]
        runner = job[1]
        duration = job[2]
        status = job[3]

        if status == 'success' or status == 'failed':
            total_time += duration

            if runner.startswith('uo-'):
                uo_jobs += 1
            else:
                cluster_jobs += 1

            if pr_num != 'None':
                pr_jobs += 1
            else:
                dev_jobs += 1

    return total_time, uo_jobs, cluster_jobs, pr_jobs, dev_jobs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="""Query pipelines database""")
    parser.add_argument('--db-path', type=str, default=None, help="""Absolute path to sqlite3 database
file to open for querying.""")
    args = parser.parse_args()

    if not args.db_path:
        print('Error: no db path provided')
        sys.exit(1)

    with closing(sqlite3.connect(args.db_path)) as db_connection:
        with closing(db_connection.cursor()) as db_cursor:
            # Get information about generate jobs
            generate_jobs_times = db_cursor.execute("""
                SELECT
                    pipelines.pr_number,
                    runner,
                    duration,
                    status
                FROM generates
                INNER JOIN pipelines ON generates.pipeline_id == pipelines.pipeline_id
            ;""").fetchall()

            total, uo, cluster, pr, dev = get_total_time_and_split(generate_jobs_times)

            print('Time spent in generate jobs: {0} min'.format(total / 60.0))
            print('  UO: {0}'.format(uo))
            print('  Cluster: {0}'.format(cluster))
            print('  PR: {0}'.format(pr))
            print('  develop: {0}'.format(dev))

            # Get the same information for build jobs
            build_jobs_times = db_cursor.execute("""
                SELECT
                    pipelines.pr_number,
                    runner,
                    duration,
                    status
                FROM builds
                INNER JOIN pipelines ON builds.pipeline_id == pipelines.pipeline_id
            ;""").fetchall()

            total, uo, cluster, pr, dev = get_total_time_and_split(build_jobs_times)

            print('Time spent in build jobs: {0} min'.format(total / 60.0))
            print('  UO: {0}'.format(uo))
            print('  Cluster: {0}'.format(cluster))
            print('  PR: {0}'.format(pr))
            print('  develop: {0}'.format(dev))

            # Report any full hashes built multiple times and the number of builds
            rebuilds = db_cursor.execute("""
                SELECT
                    SUM(duration) l,
                    COUNT(*) c
                FROM builds
                WHERE status == 'success'
                GROUP BY full_hash HAVING c > 2
                ORDER BY c DESC
            ;""").fetchall()

            time_spent_rebuilding = sum([d[0] for d in rebuilds])
            num_rebuilds = sum([d[1] for d in rebuilds])
            print('number of full hashes built more than twice: {0}'.format(num_rebuilds))
            print('total time spent rebuilding full hashes: {0} min'.format(time_spent_rebuilding / 60.0))

            # A more nuanced assessment of redundant builds
            builds = db_cursor.execute("""
                SELECT
                    pipelines.pipeline_id,
                    pipelines.pr_number,
                    pipelines.branch,
                    pkg_name,
                    status,
                    duration,
                    runner,
                    full_hash
                FROM builds
                INNER JOIN pipelines ON builds.pipeline_id == pipelines.pipeline_id
            ;""").fetchall()

            full_hashes = {}

            for p_id, pr, br, name, status, dur, run, h in builds:
                if status == 'success' or status == 'failed':
                    name_hash_key = '{0} / {1}'.format(name, h)

                    if name_hash_key not in full_hashes:
                        full_hashes[name_hash_key] = []

                    full_hashes[name_hash_key].append((p_id, pr, name, br, status, dur, run))

            all_builds = {
                'count': 0,
                'time': 0.0
            }

            redundant_builds = {
                'count': 0,
                'time': 0.0
            }

            for name_hash_key, builds in full_hashes.items():
                # Ordering the buils by pipeline id orders them in time
                ordered_builds = sorted(builds, key=lambda b: b[0])

                # Get the number of the PR that introduced this hash (the number
                # of the PR associated with the first pipeline that built this
                # hash)
                first_pr_num = ordered_builds[0][1]
                for b in ordered_builds:

                    p_id, pr_num, name, branch, status, duration, runner = b
                    if pr_num == 'None':
                        tested_branch = 'github/develop'
                    else:
                        tested_branch = 'github/pr{0}_{1}'.format(pr_num, branch)

                    all_builds['count'] += 1
                    all_builds['time'] += duration

                    if pr_num != first_pr_num and pr_num != 'None':
                        # This build was not done as a part of the PR that introduced the
                        # hash, and it was not done on "develop", we can probably avoid
                        # doing this build in the future.
                        redundant_builds['count'] += 1
                        redundant_builds['time'] += duration

            print('\nSlightly more nuanced view of redundant builds:')
            print('  {0} total builds took {1} min'.format(all_builds['count'], all_builds['time'] / 60.0))
            print('  {0} redundant builds took {1} min'.format(redundant_builds['count'], redundant_builds['time'] / 60.0))

            # Count rebuild pipelines and rebuilds in the last week
            all_pipelines = db_cursor.execute("""
                SELECT
                    create_time
                FROM pipelines
            ;""").fetchall()

            pipelines_last_7_days = 0

            zulu_now = datetime.utcnow()

            for p in all_pipelines:
                pipeline_time = datetime.strptime(p[0], DB_TIMESTAMP_FORMAT)
                how_long_ago = zulu_now - pipeline_time
                if how_long_ago.days < 7:
                    pipelines_last_7_days += 1

            print('\nFound {0} pipelines total, {1} from the last 7 days'.format(
                len(all_pipelines), pipelines_last_7_days))

            rebuilds_total = 0
            rebuilds_last_7_days = 0
            pkg_bins = {}

            all_build_jobs = db_cursor.execute("""
                SELECT
                    pkg_name,
                    create_time,
                    duration
                FROM builds
            ;""").fetchall()

            for b_job in all_build_jobs:
                pkg_name = b_job[0]
                created_str = b_job[1]
                duration = b_job[2]

                if not duration:
                    continue

                rebuilds_total += 1

                b_job_time = datetime.strptime(b_job[1], DB_TIMESTAMP_FORMAT)
                how_long_ago = zulu_now - b_job_time

                if how_long_ago.days < 7:
                    rebuilds_last_7_days += 1

                if pkg_name not in pkg_bins:
                    pkg_bins[pkg_name] = {
                        'count': 0,
                        'time': 0
                    }

                pkg_bins[pkg_name]['count'] += 1
                pkg_bins[pkg_name]['time'] += duration

            print('\nFound {0} build jobs total, {1} from the last 7 days'.format(
                rebuilds_total, rebuilds_last_7_days))

            bins = [(name, stats['count'], stats['time']) for name, stats in pkg_bins.items()]
            bins = sorted(bins, key=lambda item: item[1], reverse=True)

            print('  {0} pkgs were rebuilt in the last 7 days'.format(len(bins)))

            show_top_n = 30

            print('  The {0} pkgs getting rebuilt the most were:'.format(show_top_n))

            for i in range(show_top_n):
                name, count, time_spent = bins[i]
                print('    {0}: {1} ({2:.1f} hrs)'.format(name, count, time_spent / 60.0 / 60.0))

            """
                SELECT
                    pkg_name,
                    full_hash,
                    duration,
                    COUNT(*) c
                FROM builds
                GROUP BY full_hash HAVING c > 1
                ORDER BY c DESC
            """

            # # Report total number of rebuilds for each PR
            # pr_rebuilds = db_cursor.execute("""
            #     SELECT
            #         pipelines.pr_number,
            #         COUNT(*) c
            #     FROM builds
            #     INNER JOIN pipelines ON builds.pipeline_id == pipelines.pipeline_id
            #     WHERE pipelines.pr_number != 'None'
            #     GROUP BY pipelines.pr_number
            #     ORDER BY c DESC
            # ;""").fetchall()
            # print('PR Rebuilds:')
            # for pr_num, pkg_name in pr_rebuilds:
            #     print('    {0} -> {1}'.format(pr_num, pkg_name))

            # # Print all generation jobs on non uo runners
            # gen_jobs = db_cursor.execute("""
            #     SELECT *
            #     FROM generates
            #     WHERE NOT runner LIKE 'uo%'
            # ;""").fetchall()
            # print('All generation jobs')
            # for gen_job in gen_jobs:
            #     print(gen_job)

