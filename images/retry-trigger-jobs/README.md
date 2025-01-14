# Purpose

The purpose of this script is to retry child pipelines whose generate job initially failed, but succeeded upon retry.

## Background

This [issue](https://github.com/spack/spack-infrastructure/issues/1031) describes the problem in more detail.

## Mitigation

Periodically search for recent child pipelines that match this failure condition and retry them using the GitLab API.
