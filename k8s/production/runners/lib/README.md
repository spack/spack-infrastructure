# Runner HelmReleases in Jsonnet

`runners.libsonnet` is a shared library that generates the GitLab runner
`HelmRepository` + `HelmRelease` pairs. Each runner has a small `release.jsonnet`
next to its `release.yaml` that supplies only what differs (name, tier, tags,
architecture, affinity).

## Status: source, not yet applied

Flux's kustomize-controller only renders YAML/JSON, **not** Jsonnet. The
committed `release.yaml` files are still the source of truth that Flux applies;
the `.jsonnet` files are an equivalent, deduplicated re-expression of them.
`.jsonnet`/`.libsonnet` are ignored by the recursive manifest scan, so their
presence does not affect what Flux deploys.

To make Jsonnet authoritative, a render step (Makefile / pre-commit / CI) would
need to compile each `release.jsonnet` to its `release.yaml`.

## Rendering

```sh
jsonnet -S protected/x86_64/v2/release.jsonnet   # emits the two-document YAML stream
```

`-S` (string output) is required because each file ends in
`std.manifestYamlStream(...)`, which returns the rendered YAML as a string.

## Verified equivalence

Each rendered release parses to the same HelmRelease structure and the same TOML
tables as the current `release.yaml`, with these deliberate normalizations:

- graviton runners gain an empty `helpers: {}` (matching the x86 runners).
- both Windows runners share one config template, so the public runner's
  pre-build log wording matches the protected runner's.
