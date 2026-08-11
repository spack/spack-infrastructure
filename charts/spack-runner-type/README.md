# spack-runner-type

One chart release per *runner type* — a microarchitecture we build on. Each
release renders:

* the Karpenter `NodePool` that provisions nodes for that microarch, and
* the `public` and `protected` GitLab runners that schedule onto it,

from a single set of values. Before this chart, those three objects lived in
three files that were ~85% identical to the three files for every other runner
type.

## Layout

| | |
|---|---|
| `templates/_runner-config.tpl` | the `config.toml`, written once for all types |
| `templates/nodepool.yaml` | the Karpenter NodePool |
| `values.yaml` | defaults; per-type values live in `k8s/production/runners/types/` |

Values split into two scopes:

* **`global.spack.*`** — shared by the whole type (microarch label, node
  affinity, instance families, NodePool limits). `global` is the only way to
  get values into both `gitlab-runner` subcharts.
* **`<visibility>.spack.*`** — differs between the public and protected runner
  (`cpuLimitMax`, `protected`, `oidcOptional`).

Everything the two runners share is written once in `values.yaml` behind the
`&managerCommon` / `&runnersCommon` YAML anchors and merged into both aliases
with `<<:`.

## Two things that look like magic

**The `config.toml` is shared via `tpl`.** The `gitlab-runner` chart renders
`.Values.runners.config` through `tpl` before writing its ConfigMap, and Helm
shares named templates between a chart and its subcharts. So `values.yaml` only
needs `config: '{{ include "spack.runnerConfig" . }}'`, and the template is
evaluated against the *subchart's* values. That is what lets one template serve
both visibilities without duplicating the TOML per alias.

**One comment in `values.yaml` is load-bearing.** The `gitlab-runner` chart
regex-matches the *raw* text of `runners.config` to decide whether to inject a
`KUBERNETES_NAMESPACE` env var. Our real config does not exist until the
`include` is rendered, so the chart cannot see the `namespace = "pipeline"`
inside it. Without the literal `namespace = "pipeline"` comment at the top of
`runners.config`, the chart injects the release namespace and job pods get
created in `gitlab` instead of `pipeline`.

## Adding a runner type

Copy the closest file in `k8s/production/runners/types/` and adjust
`global.spack`. A type needs, at minimum: `description`, `nodeLabelKey`,
`nodeLabelValue`, `schedulesOn`, `nodeAffinityComment`, and `nodePool.name` /
`nodePool.arch` / `nodePool.instanceFamilies`. Leave `instanceFamilies` empty to
accept any family for the architecture.

`fullnameOverride` must keep the `-gitlab-runner` suffix: it is what the
upstream chart would have generated on its own, and changing it renames (and so
recreates) the live Deployment.

## Changing the chart

**Bump `version` in `Chart.yaml` for any change under this directory.** The
HelmReleases source this chart from the `flux-system` GitRepository using the
default `reconcileStrategy: ChartVersion`, so source-controller only rebuilds
the artifact when the version changes. Values changes in the HelmReleases take
effect without a bump.

To check a change before pushing:

```
helm dependency build charts/spack-runner-type
helm template runner-x86-v3 charts/spack-runner-type -n gitlab \
  -f <(sed -n '/^  values:/,$p' k8s/production/runners/types/x86_64-v3.yaml | tail -n +2 | sed 's/^    //')
```

## Not covered by this chart

The Windows runners (`k8s/production/runners/{public,protected}/x86_64/v2-win/`)
and the signing runner (`k8s/production/runners/signing/`) are still standalone
HelmReleases with their own NodePools. Their `config.toml` differs from the
Linux one in most of its body — PowerShell pre-build, different executor and
feature flags for Windows; notary service account and image allowlist for
signing — so folding them in would mean a template that is mostly conditionals.
They can be added later as alternate config templates if that changes.
