# Gitlab runners

There are three types of runners with increasing levels of access to cluster secrets.

1. `public`
2. `protected`
3. `signing`

## Isolation

`protected` runners and the build pods they spawn are kept off the same hardware, and out of
the same namespace, as `public` ones. Nothing is shared between the two tiers except the
GitLab runner registration secret.

| | `public` (and `signing`) | `protected` |
| --- | --- | --- |
| Runner manager namespace | `gitlab` | `gitlab` |
| Runner manager SA | `runner` | `runner-protected` |
| Build pod namespace | `pipeline` | `pipeline-protected` |
| Build pod SA | `pipeline/runner` | `pipeline-protected/runner` |
| Node pools | `glr-*`, `x86-64-v2-win` | `glr-prot-*`, `x86-64-v2-win-prot` |
| Node taint | `spack.io/runner-taint` (`spack.io/notary-taint` for `signing`) | `spack.io/protected-runner-taint` |
| Node label | — | `spack.io/protected=true` |

The separation is enforced in three independent places, so no single misconfiguration
collapses it:

* **Taints.** Protected build pods only tolerate `spack.io/protected-runner-taint` and public
  build pods only tolerate `spack.io/runner-taint`, so neither tier can schedule onto the
  other's nodes.
* **Node affinity.** Protected pods additionally *require* `spack.io/protected=true`; public
  and signing pods require that the label be absent.
* **RBAC.** Each manager SA is bound to a namespaced `Role` (not a `ClusterRole`) in the one
  namespace its own build pods run in. `gitlab/runner` cannot read Secrets or exec into pods
  in `pipeline-protected`, and `gitlab/runner-protected` cannot do so in `pipeline`.

`spack-intermediate-ci-signing-key` is mounted only by protected build pods and therefore
lives only in `pipeline-protected` (see `protected/sealed-secrets.yaml`). SealedSecret
ciphertext is bound to its namespace, so moving that secret between namespaces requires
re-sealing it against the cluster's current public key.

The `signing` runners are a separate tier again, with their own node pool (`glr-notary`),
taint (`spack.io/notary-taint`) and service account (`pipeline/notary`), but their build pods
still share the `pipeline` namespace with public jobs.

## Public & Protected runners

The `public` and `protected` runners provide multiple architectures and base OSs that run across a range of AWS nodes.

* Windows
  * `x86_64_v2`
* Linux
  * `x86_64_v2`
  * `x86_64_v3`
  * `x86_64_v4`
  * `neoverse_v1`

### Special Variables

* `CI_OIDC_REQUIRED`: available to be set for runners with the `service` tag.
  This variable can be used to skip OIDC configuration.

## Signing Runners

The `signing` runners use either `x86_64_v3` or `x86_64_v4` Linux machines.
