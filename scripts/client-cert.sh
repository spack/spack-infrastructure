#!/usr/bin/env bash
set -euo pipefail

NAME=${1:-client}
TEMPDIR=$(mktemp -d)

#trap 'rm -rf ${TEMPDIR}' EXIT

kubectl get secret client-ca -n ingress-nginx -o jsonpath='{.data.ca\.crt}' | base64 -d > $TEMPDIR/ca.crt
kubectl get secret client-ca -n ingress-nginx -o jsonpath='{.data.ca\.key}' | base64 -d > $TEMPDIR/ca.key

# Generate client private key
openssl ecparam -name prime256v1 -genkey -noout -out $NAME.key

# Geneate client CSR
openssl req -new -sha256 -key $NAME.key -out $NAME.csr

# Geneate client certificate
openssl x509 -req -in $NAME.csr \
    -CA $TEMPDIR/ca.crt \
    -CAkey $TEMPDIR/ca.key \
    -CAcreateserial \
    -out $NAME.crt -days 1000 -sha256

# Bundle client key and crt into pkcs12 file
openssl pkcs12 -export -in $NAME.crt \
    -inkey $NAME.key \
    -out $NAME.p12

rm $NAME.key $NAME.csr $NAME.crt
