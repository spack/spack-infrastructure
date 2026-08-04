# GitLab Orphaned Job Canceller

## Overview

This CronJob detects and cancels GitLab CI jobs that GitLab still reports as `Running`,
but whose backing Kubernetes pod has disappeared (or already reached a terminal phase)
out from under them, and then automatically retries them.

## Problem

GitLab jobs using the Kubernetes executor can occasionally lose their backing pod without
GitLab ever being told the job failed. One situation where this occurs is when Karpenter's
disruption controller incorrectly deletes a node it believes is empty while a build pod is
still actively running on it
(see [kubernetes-sigs/karpenter#2916](https://github.com/kubernetes-sigs/karpenter/issues/2916)).
When this happens, the job is permanently stuck showing `Running` with no work actually
happening behind it.

## How it Works

1. For each configured project, query GitLab for jobs with `status=running`.
2. Only jobs picked up by one of our cloud-based Kubernetes runners are considered.
   These are identified by their description:
   `runner-*-{pub,prot,signing}[-windows]-gitlab-runner-*` .
3. Runner pods are annotated `gitlab/ci_job_id: "$CI_JOB_ID"` by the gitlab-runner Kubernetes
   executor. Every pod in the `pipeline` namespace is listed once and indexed by this
   annotation.
4. For each relevant running job older than the grace period, look up its pod via that index.
5. If no matching pod exists, or the matching pod has already reached a terminal phase
   (`Succeeded`/`Failed`), the job is considered orphaned and is canceled via the GitLab API.
6. Retry the canceled job hasn't already been retried `MAX_RETRIES` times.

## Scope

This tool cancels orphaned jobs and automatically retries them, up to `MAX_RETRIES` (currently
`2`) times per job. If a job has been retried that many times and still ends up orphaned
again, it's left canceled for a human to investigate, rather than being retried indefinitely.
This caps the impact if a job (or its runner pool) has a persistent, unrelated problem.

## Configuration

- `--projects`: comma-separated list of GitLab project ids or paths to check
  (default: `spack/spack,spack/spack-packages`)
- `--grace-period-minutes`: skip jobs started more recently than this, to avoid racing normal
  pod-scheduling delays (default: `30`)

`MAX_RETRIES` (currently `2`) is not a CLI flag - it's a constant in `main.py`.
