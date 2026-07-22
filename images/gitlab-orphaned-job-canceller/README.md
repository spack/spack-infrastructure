# GitLab Orphaned Job Canceller

## Overview

The GitLab Orphaned Job Canceller is a Kubernetes CronJob that quickly detects and cancels
GitLab CI jobs that GitLab still reports as `Running`, but whose backing Kubernetes pod has
disappeared (or already reached a terminal phase) out from under them.

## Problem

GitLab jobs using the Kubernetes executor can occasionally lose their backing pod without
GitLab ever being told the job failed - for example, when Karpenter's disruption controller
incorrectly deletes a node it believes is empty while a build pod is still actively running
on it (see [kubernetes-sigs/karpenter#2916](https://github.com/kubernetes-sigs/karpenter/issues/2916)).
When this happens, the job is permanently stuck showing `Running` with no work actually
happening behind it.

## How It Works

1. Runner pods are labeled `gitlab/ci_job_id: "$CI_JOB_ID"` by the gitlab-runner Kubernetes
   executor (see the `pod_labels` config in the runner Helm values).
2. For each configured project, query GitLab for jobs with `status=running`.
3. For each running job older than the grace period, look up pods in the `pipeline` namespace
   matching that job's `gitlab/ci_job_id` label.
4. If no matching pod exists, or every matching pod has already reached a terminal phase
   (`Succeeded`/`Failed`), the job is considered orphaned and is canceled via the GitLab API.

## Scope

This tool only cancels orphaned jobs, it doesn't automatically retry them.

## Configuration

- `--projects`: comma-separated list of GitLab project ids or paths to check
  (default: `spack/spack,spack/spack-packages`)
- `--grace-period-minutes`: skip jobs started more recently than this, to avoid racing normal
  pod-scheduling delays (default: `30`)
