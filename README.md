# Spack Infrastructure

This contains code and configuration for Spack's various infrastructure
services, including:

* Kubernetes: [k8s.spack.io](https://k8s.spack.io)
* CDash: [cdash.spack.io](https://cdash.spack.io)
* GitLab: [gitlab.spack.io](https://gitlab.spack.io)

## Restoring from Backup

- Delete the persistent volume (PV) and persistent volume claim (PVC) for the old volume that's being replaced.
   - `kubectl delete -f pv.yaml -f pvc.yaml`
- Create a new volume from a snapshot in the [AWS web console](https://console.aws.amazon.com)
- Update `pv.yaml` to reference the newly created volumeId.
- Recreate the PV and PVC
   - `kubectl apply -f pv.yaml -f pvc.yaml`

License
----------------

Spack is distributed under the terms of both the MIT license and the
Apache License (Version 2.0). Users may choose either license, at their
option.

All new contributions must be made under both the MIT and Apache-2.0
licenses.

See [LICENSE-MIT](https://github.com/spack/spack-infrastructure/blob/master/LICENSE-MIT),
[LICENSE-APACHE](https://github.com/spack/spack-infrastructure/blob/master/LICENSE-APACHE),
[COPYRIGHT](https://github.com/spack/spack-infrastructure/blob/master/COPYRIGHT), and
[NOTICE](https://github.com/spack/spack-infrastructure/blob/master/NOTICE) for details.

SPDX-License-Identifier: (Apache-2.0 OR MIT)

LLNL-CODE-647188
