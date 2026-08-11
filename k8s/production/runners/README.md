# Gitlab runners

There are three types of runners with increasing levels of access to cluster secrets.

1. `public`
2. `protected`
3. `signing`

## Public & Protected runners

The `public` and `protected` runners provide multiple architectures and base OSs that run across a range of AWS nodes.

* Windows
  * `x86_64_v2`
* Linux
  * `x86_64_v2`
  * `x86_64_v3`
  * `x86_64_v4`
  * `neoverse_v1`

### Layout

The Linux runners are defined one file per *runner type* in [`types/`](types/).
Each of those HelmReleases uses [`charts/spack-runner-type`](../../../charts/spack-runner-type),
which renders three objects from one set of values:

* the type's Karpenter `NodePool` (so it is no longer under
  `k8s/production/karpenter/provisioners/runners/`), and
* the type's `public` and `protected` runners.

Day-to-day changes — tags, replicas, instance families, resource ceilings — are
values edits in `types/` and need no chart change. Editing the chart itself
requires bumping its `version`; see the chart's README for why.

The Windows and signing runners are still standalone HelmReleases with their own
NodePools, for the reasons given at the end of the chart README.

### Special Variables

* `CI_OIDC_REQUIRED`: available to be set for runners with the `service` tag.
  This variable can be used to skip OIDC configuration. Enabled per runner with
  `<visibility>.spack.oidcOptional`.

## Signing Runners

The `signing` runners use either `x86_64_v3` or `x86_64_v4` Linux machines.
