#! /usr/bin/env sh

exec kubectl exec -ti -n spack deployments/docker-shell -- sh -il
