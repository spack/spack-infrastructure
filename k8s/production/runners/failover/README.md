# On-prem failover runner

`runner-onprem-failover` is a gitlab-runner deployment that stands in for the
on-prem (`uo-*`) runners when they go down. It is registered in GitLab with
the **same tags** as the on-prem runners but is kept **paused**, so it
receives no jobs while the on-prem fleet is healthy. GitLab has no runner
priority mechanism — an active runner with matching tags would share load with
the on-prem runners — so the paused flag is the failover switch.

The switch is operated manually. Karpenter needs no toggling: the
`glr-onprem-failover` NodePool
(`k8s/production/karpenter/provisioners/runners/onprem-failover/`) sits at
zero nodes while the runner is paused, provisions nodes when unpausing lets
job pods through, and consolidates back to zero ~5 minutes after the last job
pod exits.

## Failover on

Unpause the runner in the GitLab admin UI (Admin Area → Runners →
`failover-…` → Resume), or on one line:

    curl -s -X PUT -H "PRIVATE-TOKEN: $GITLAB_ADMIN_TOKEN" "https://gitlab.spack.io/api/v4/runners/<RUNNER_ID>" --data paused=false

## Failover off

Re-pause the same runner (Pause in the UI, or the same call with
`paused=true`). In-flight jobs on EC2 finish normally; nothing is
interrupted.

## Setup (required before unsuspending the HelmRelease)

1. **Fill in the TODOs** in `release.yaml` (tags comment, `concurrent`) and in
   the NodePool (`instance-type` list, `limits`) to match the on-prem runner
   hardware and capacity. The on-prem tag list is visible in the GitLab Admin
   Area under Runners (runners with description starting `uo-`).

2. **Create the runner in GitLab**: Admin Area → Runners → New instance runner
   (or a group runner on the `spack` group, matching how the on-prem runners
   are scoped). Set:
   - *Tags*: exactly the on-prem runners' tag list
   - *Paused*: **checked** — this is the failsafe default
   - *Protected*: only if the on-prem runners serve protected refs
   - description prefixed `failover-` so it is easy to find

   Copy the `glrt-…` authentication token.

3. **Seal the runner token** into `spack-onprem-failover-runner-secret`
   (namespace `gitlab`, same shape as `spack-group-runner-secret` in
   `k8s/production/runners/sealed-secrets.yaml`, i.e. keys `runner-token` and
   `runner-registration-token` — the latter may be an empty string), and commit
   the SealedSecret as `sealed-secrets.yaml` in this directory.

4. **Unsuspend**: remove `spec.suspend: true` from `release.yaml`. The manager
   pod is a single ~1G pod on the `base` pool; while the runner is paused it
   polls GitLab and does nothing else.
