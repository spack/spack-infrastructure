# Purpose

The purpose of this cronjob is to find and cancel gitlab pipelines that have become mystyeriously "stuck" as well as to run a new pipeline on the affected branch.

## Background

This [issue](https://github.com/spack/spack-infrastructure/issues/239) describes the problem.

## Cause

At the moment we are investigating whether an overloaded ingress controller has correlation with this behavior, but so far have found no concrete evidence of any cause.

## Mitigation

Run a cronjob that periodically looks for pipelines older than some threshold, and cancel them (dynamic child pipelines must be found and canceled specifically as well).  Also, blindly attempt to run a new pipeline on the affected branch (i.e. do not first check whether the branch still exists in gitlab or has been deleted by the gh-gl-sync cronjob).
