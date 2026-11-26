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

### Special Variables

* `CI_OIDC_REQUIRED`: available to be set for runners with the `service` tag.
  This variable can be used to skip OIDC configuration.
* `SPACK_CI_POST_BUILD_PUSH`: a command run by `post_build_script` after the
  job's `script` succeeds. When set, the OIDC token is exchanged for AWS
  credentials only after the build, and the token is never exported to the
  build's processes. When unset, credentials are exported before the build
  as before. Not supported on the `signing` runners. Can't be combined with
  `CI_OIDC_REQUIRED=0`: the job fails because no token was saved.
* `SPACK_CI_CREDENTIALS_DURATION`: lifetime in seconds of the AWS credentials,
  from 900 to 43200. Defaults to 3600 when `SPACK_CI_POST_BUILD_PUSH` is set,
  and to 43200 otherwise.

### Pushing after the build

A build job opts in by building without pushing and naming the push command:

```yaml
script:
  - spack ci rebuild --no-push ...
variables:
  SPACK_CI_POST_BUILD_PUSH: >-
    spack buildcache push --only package --allow-missing --private
    buildcache-destination /$SPACK_JOB_SPEC_DAG_HASH
```

* Set the variable on build jobs only, never pipeline-wide. Other jobs on
  these runners (generate, copy, rebuild-index) need credentials during
  `script`.
* `--allow-missing`: `spack ci rebuild` succeeds without installing anything
  when the spec is already in a mirror, so the push must tolerate that.
* `--private`: without it, `spack buildcache push` skips packages that can't
  be redistributed as binaries. `spack ci rebuild` pushes them.
* Signing: `spack ci rebuild` signs only when exactly one secret key is
  available, while `spack buildcache push` signs by default and fails without
  a key. Add `--unsigned` on runners with no signing key (PR pipelines).
* During the build, spack has no AWS credentials and reads the binary mirrors
  anonymously, so those buckets must keep public `s3:GetObject`. Builds don't
  list buckets; without public `s3:ListBucket`, missing objects return 403
  instead of 404, which spack's read paths treat as "not found".

## Signing Runners

The `signing` runners use either `x86_64_v3` or `x86_64_v4` Linux machines.
