#! /usr/bin/env bash

template="{{ range .items }}{{ with .metadata.labels }}\
{{ index . \"topology.kubernetes.io/zone\" }} \
{{ index . \"spack.io/node-pool\" }}
{{ end }}{{ end }}"

exec kubectl get nodes -o go-template="$template" | sort | uniq -c
