#! /usr/bin/env sh

img="$1"

if [ -z "$img" ] ; then
    echo "Usage:"
    echo "  $0 <image>"
    exit 1
fi >&2

new_tag="k8s.internal/$( echo "$img" | tr '/' '-' )"

script="docker pull \"$img\""
script="${script} && docker tag \"$img\" \"$new_tag\""
script="${script} && docker push \"$new_tag\""

exec kubectl exec -t -n spack deployments/docker-shell -- sh -c "$script"
