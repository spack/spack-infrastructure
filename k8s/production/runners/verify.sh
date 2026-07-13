#!/bin/sh
# Verify each release.jsonnet is semantically equivalent to its release.yaml:
# same Kubernetes objects (key order/quoting/comments ignored) and same parsed
# TOML runner config (indentation and blank lines in embedded scripts ignored).
cd "$(dirname "$0")" || exit 1
rc=0
for j in $(find . -name release.jsonnet); do
  jsonnet -S "$j" | python3 verify.py "${j%.jsonnet}.yaml" || { echo "DIFF: $j"; rc=1; }
done
[ $rc -eq 0 ] && echo "all equivalent"
exit $rc
