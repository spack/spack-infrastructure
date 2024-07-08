# Purpose

This script searches GitLab for branches that did not have a pipeline run for the most recent commit. After identifying such a commit, this script also schedules a pipeline to run on the affected branch.

## Background

This [issue](https://github.com/spack/spack-infrastructure/issues/316) describes the problem.

## Cause

Unknown

## Mitigation

Install a cron job to run a Python script that implements the following logic:

```
for each branch:
  get HEAD commit
  check if there is a pipeline for this commit:
    if not, run one
```
