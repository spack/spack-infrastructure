#!/bin/bash
set -euo pipefail

UNIQUE_ID=$(whoami | sed 's/\.//g')

export LOCALPORT=9999
export PORT=5432
export ADDR=$REMOTE_DB_HOST
export PODNAME="pg-bastion-$UNIQUE_ID"

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
