#!/usr/bin/env -S uv run
"""
GitLab Orphaned Job Canceller

Cancels GitLab CI jobs that GitLab still reports as "running" but whose
backing Kubernetes pod has disappeared.
"""

import argparse
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

import requests
import sentry_sdk
from kubernetes import client, config

sentry_sdk.init(traces_sample_rate=0.1)

GITLAB_API_ROOT = "https://gitlab.spack.io/api/v4"
GITLAB_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
AUTH_HEADER = {"PRIVATE-TOKEN": os.environ.get("GITLAB_TOKEN", None)}
PIPELINE_NAMESPACE = "pipeline"
TERMINAL_POD_PHASES = {"Succeeded", "Failed"}

# All of our own Kubernetes-executor runners are registered as group-level
# runners, which GitLab reports as runner_type "group_type". Shared on-prem/
# external runners (UO) show up as "instance_type" instead - those jobs never
# have a pod in this cluster by design, so they must never be checked or
# canceled here.
KUBERNETES_RUNNER_TYPE = "group_type"


def project_api_url(project):
    """Build the API base URL for a project, given as either a numeric id
    or a namespaced path like 'spack/spack-packages'."""
    encoded = urllib.parse.quote_plus(str(project))
    return f"{GITLAB_API_ROOT}/projects/{encoded}"


def get_running_jobs(project_url):
    """Return all jobs GitLab currently reports as running for a project."""
    results = []
    url = f"{project_url}/jobs?scope[]=running&per_page=100"

    while url:
        resp = requests.get(url, headers=AUTH_HEADER)
        if resp.status_code in (401, 403):
            raise RuntimeError(
                f"{resp.status_code} requesting {url} - check GITLAB_TOKEN permissions"
            )
        resp.raise_for_status()

        results.extend(resp.json())
        url = resp.links.get("next", {}).get("url")

    return results


def cancel_job(project_url, job_id):
    """Cancel a single job by id. Returns True on success."""
    cancel_url = f"{project_url}/jobs/{job_id}/cancel"
    resp = requests.post(cancel_url, headers=AUTH_HEADER)
    print(f"    cancel response: {resp.status_code} {resp.text}")
    return resp.ok


def index_pods_by_job_id(v1):
    """List every pod in the pipeline namespace once and index them by the
    gitlab/ci_job_id annotation the gitlab-runner Kubernetes executor sets.
    This is checked as an annotation rather than a label selector because
    at least one runner fleet (the Windows public/protected runners) is
    missing this key from its pod_labels config, even though every fleet
    consistently sets it as a pod annotation - and annotations aren't
    queryable via the Kubernetes API's label selectors, so we have to list
    and filter client-side instead."""
    index = {}
    for pod in v1.list_namespaced_pod(PIPELINE_NAMESPACE).items:
        annotations = pod.metadata.annotations or {}
        job_id = annotations.get("gitlab/ci_job_id")
        if job_id:
            index.setdefault(job_id, []).append(pod)
    return index


def is_kubernetes_executor_job(job):
    """Only jobs picked up by one of our own group-level Kubernetes-executor
    runners can ever have a backing pod in this cluster."""
    runner = job.get("runner")
    if not runner:
        return False
    return runner.get("runner_type") == KUBERNETES_RUNNER_TYPE


def is_orphaned(pod_index, job, grace_period):
    """A running job is orphaned if it's running on one of our own
    Kubernetes-executor runners, has been running longer than the grace
    period (to avoid racing normal pod-scheduling delays), and its backing
    pod either no longer exists, or has already reached a terminal phase
    without GitLab having found out."""
    if not is_kubernetes_executor_job(job):
        return False

    started_at = job.get("started_at")
    if not started_at:
        return False

    started = datetime.strptime(started_at, GITLAB_TIME_FORMAT).replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - started < grace_period:
        return False

    pods = pod_index.get(str(job["id"]), [])
    if not pods:
        return True

    return all(
        (pod.status.phase if pod.status else None) in TERMINAL_POD_PHASES
        for pod in pods
    )


def cancel_orphaned_jobs(v1, project, grace_period_minutes):
    project_url = project_api_url(project)
    grace_period = timedelta(minutes=grace_period_minutes)

    running_jobs = get_running_jobs(project_url)
    print(f"Checking {len(running_jobs)} running job(s) in {project}")

    pod_index = index_pods_by_job_id(v1)

    canceled = []
    for job in running_jobs:
        job_id = job["id"]
        job_name = job.get("name", "?")

        orphaned = is_orphaned(pod_index, job, grace_period)

        if orphaned:
            print(f"  job {job_id} ({job_name}): no live pod found, canceling")
            if cancel_job(project_url, job_id):
                canceled.append(job_id)
        else:
            print(f"  job {job_id} ({job_name}): pod still present or within grace period, leaving alone")

    return canceled


def main():
    if "GITLAB_TOKEN" not in os.environ:
        raise SystemExit("GITLAB_TOKEN environment is not set")

    parser = argparse.ArgumentParser(
        description="Cancel GitLab CI jobs whose backing pod has disappeared out from under them"
    )
    parser.add_argument(
        "--projects",
        default="spack/spack,spack/spack-packages",
        help="Comma-separated list of project ids or paths to check",
    )
    parser.add_argument(
        "--grace-period-minutes",
        default=30,
        type=int,
        help="Ignore jobs started more recently than this many minutes ago",
    )
    args = parser.parse_args()

    try:
        config.load_incluster_config()
    except config.ConfigException:
        # Not running inside a pod - fall back to the local kubeconfig
        # (e.g. ~/.kube/config) so this can be run locally too.
        config.load_kube_config()
    v1 = client.CoreV1Api()

    projects = [p.strip() for p in args.projects.split(",") if p.strip()]

    failed_projects = []
    for project in projects:
        try:
            cancel_orphaned_jobs(v1, project, args.grace_period_minutes)
        except Exception as exc:
            print(f"Caught unhandled exception processing project '{project}':")
            print(exc)
            failed_projects.append(project)

    if failed_projects:
        print(f"Failed to fully process project(s): {', '.join(failed_projects)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
