#! /usr/bin/env bash

cd "$( dirname "$0" )"

set -e

kubectl apply -f flux.yaml

helm repo add fluxcd https://charts.fluxcd.io

helm upgrade -i flux fluxcd/flux \
    -f flux-chart.yaml \
    --namespace flux

helm upgrade -i helm-operator fluxcd/helm-operator \
    -f helm-operator-chart.yaml \
    --namespace flux

echo 'Generated Deployment Key:'
kubectl -n flux logs deployment/flux | grep identity.pub | cut -d '"' -f2
