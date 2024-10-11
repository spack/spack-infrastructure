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
  * `graviton2`
  * `graviton3`

### Special Variables

* `CI_OIDC_REQUIRED`: available to be set for runners with the `service` tag.
  This variable can be used to skip OIDC configuration.

## Signing Runners

The `signing` runners use either `x86_64_v3` or `x86_64_v4` Linux machines.
