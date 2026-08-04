#!/usr/bin/env bash
# Seal a single secret value for the current kubectl context.
#
# Reads the plaintext on stdin and prints the sealed ciphertext on stdout, ready to
# paste into a `spec.encryptedData` entry. Trailing newlines are stripped (matching
# `spack-secrets update`); use --keep-newline to preserve them.
#
#   echo -n 'hunter2' | seal-value.sh --namespace gitlab --name gitlab-postgresql-secrets
#   seal-value.sh -n monitoring -s metabase-postgresql-password < /path/to/value
#
set -euo pipefail

namespace=""
name=""
keep_newline=0

usage() {
    cat >&2 <<'EOF'
usage: seal-value.sh --namespace NS --name SECRET_NAME [--keep-newline]

Reads plaintext on stdin, prints the strict-scoped sealed value on stdout.
NS and SECRET_NAME must exactly match the SealedSecret's metadata.namespace
and metadata.name, or the controller will not be able to decrypt it.
EOF
    exit 2
}

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--namespace) namespace="${2:-}"; shift 2 ;;
        -s|--name) name="${2:-}"; shift 2 ;;
        --keep-newline) keep_newline=1; shift ;;
        -h|--help) usage ;;
        *) echo "unknown argument: $1" >&2; usage ;;
    esac
done

[ -n "$namespace" ] && [ -n "$name" ] || usage

command -v kubeseal >/dev/null 2>&1 || {
    echo "kubeseal not found. Install it: https://github.com/bitnami-labs/sealed-secrets#kubeseal" >&2
    exit 1
}
command -v kubectl >/dev/null 2>&1 || { echo "kubectl not found" >&2; exit 1; }

echo "Sealing for namespace=$namespace name=$name on context $(kubectl config current-context)" >&2

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
cert="$tmpdir/sealing-cert.pem"

# Newest active key pair is the one the controller currently seals with.
kubectl get secrets -n kube-system \
    -l sealedsecrets.bitnami.com/sealed-secrets-key=active \
    --sort-by=.metadata.creationTimestamp \
    -o jsonpath='{.items[-1:].data.tls\.crt}' | base64 -d > "$cert"
[ -s "$cert" ] || { echo "could not fetch sealing cert from kube-system" >&2; exit 1; }

if [ -t 0 ]; then
    echo "Enter the secret value (input hidden), then press Enter:" >&2
    IFS= read -rs value
    echo >&2
else
    # $(cat) drops trailing newlines, which is what we want by default.
    value="$(cat)"
fi

[ -n "$value" ] || { echo "refusing to seal an empty value" >&2; exit 1; }

if [ "$keep_newline" -eq 1 ]; then
    printf '%s\n' "$value"
else
    printf '%s' "$value"
fi | kubeseal --raw --scope strict --namespace "$namespace" --name "$name" --cert "$cert"

echo >&2
echo "Paste the value above into spec.encryptedData.<key> as a single unwrapped line." >&2
