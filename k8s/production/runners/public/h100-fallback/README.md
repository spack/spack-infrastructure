# H100 EC2 Fallback Runner

Manual EC2 fallback for the `illyad` GitLab runner (hosted at the University
of Oregon).

Provides at most one on-demand `p5.48xlarge` (8x H100 80GB), tagged
`hpsf-gpu`, `nvidia-h100`, `x86_64-nvidiagpu`. Registered as a GitLab
**instance runner** (available instance-wide on gitlab.spack.io), not a
spack group runner.

Uses `p5.48xlarge` rather than the originally-intended single-GPU
`p5.4xlarge`: Karpenter can't provision `p5.4xlarge` due to an AWS EC2 API
bug where `DescribeInstanceTypes` intermittently reports it as having 0
GPUs, so Karpenter filters it out for any GPU-requesting workload (see
[aws/karpenter-provider-aws#8368](https://github.com/aws/karpenter-provider-aws/issues/8368),
open with no fix timeline as of this writing). `p5.48xlarge` isn't affected.
The runner's `concurrent` setting is 8 (one job per GPU) to make use of the
larger instance.

Registration and the `spack-instance-runner-secret` it authenticates with
are both Terraform-managed (`terraform/modules/spack_gitlab/h100_fallback_runner.tf`)
- no manual GitLab UI step or secret sealing required. `terraform apply`
creates the instance runner via `gitlab_user_runner` and writes its auth
token straight into the cluster as a Secret. Applies in both prod and
staging.

## Enable

1. Open a PR changing `values.replicas` from `0` to `1` in
   [`release.yaml`](./release.yaml).
2. Get it reviewed and merged. Flux applies it within a few minutes.
3. The runner starts polling GitLab for matching jobs. The first matching
   job triggers Karpenter to provision the `p5.48xlarge` node, which takes
   several minutes (GPU instances boot slower than CPU-only ones) - this is
   expected, not a broken runner.

## Disable

1. Open a PR reverting `values.replicas` back to `0`.
2. Get it reviewed and merged.
3. Karpenter drains and terminates the node once any in-flight job finishes
   and no new job pods land (standard empty-node consolidation - no manual
   node cleanup needed).

## Staging

This runner also exists in staging (`gitlab.staging.spack.io`, `us-west-2`),
wired in via `k8s/staging/karpenter/kustomization.yaml` and
`k8s/staging/runners/kustomization.yaml` rather than duplicated files. It
exists to validate the whole chain end to end before enabling this for real
in prod.

Staging's enable/disable toggle is independent of prod's: it's controlled by
the `replicas` patch on the `runner-h100-fallback-pub` `HelmRelease` in
`k8s/staging/runners/kustomization.yaml`, not by editing `release.yaml`
directly (editing that file would also affect prod, since staging
references it as-is). Flip that patch's `value` between `0` and `1` via PR
to enable or disable the runner in staging.
