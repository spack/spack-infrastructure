#!/bin/bash
[ -z "$KUBECONFIG" ] && echo "KUBECONFIG env var must be set" && exit 1;
[ -z "$REMOTE_DB_HOST" ] && echo "REMOTE_DB_HOST env var must be set" && exit 1;

set -euo pipefail

UNIQUE_ID=$(whoami | sed 's/\.//g')

export LOCALPORT=5433
export PORT=5432
export ADDR=$REMOTE_DB_HOST
export PODNAME="gitlab-pg-bastion-$UNIQUE_ID"

# trap for deleting the pod
function cleanup {
  kubectl delete pod --now ${PODNAME} || true
}
trap cleanup 2

if kubectl get pod ${PODNAME} &> /dev/null; then
  kubectl delete pod --now ${PODNAME}
fi

kubectl run --restart=Never --image=alpine/socat ${PODNAME} -- -d -d tcp-listen:${PORT},fork,reuseaddr tcp-connect:${ADDR}:${PORT}
kubectl wait --for=condition=Ready pod/${PODNAME}
kubectl port-forward pod/${PODNAME} ${LOCALPORT}:${PORT}
