#!/usr/bin/env bash
#
# Prove that charts/spack-runner-type renders the same Kubernetes objects the
# per-runner HelmReleases used to. Renders both sides and diffs them.
#
#   ./verify_render.sh [before-ref]     # default: main
#
# Requires PyYAML for the NodePool comparison; set PYTHON=/path/to/python if
# your default python3 lacks it.
#
# Expected result: every runner ConfigMap differs by exactly one line (the
# deliberate `namespace = "pipeline"` marker comment), every Deployment differs
# by exactly one line (checksum/configmap, a consequence of that comment), and
# every NodePool is semantically identical.

set -euo pipefail

BEFORE="${1:-main}"
REPO="$(git rev-parse --show-toplevel)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CHART="$REPO/charts/spack-runner-type"
GLR="$CHART/charts/gitlab-runner-0.91.0.tgz"
[ -f "$GLR" ] || helm dependency build "$CHART" >/dev/null

mkdir -p "$WORK/old" "$WORK/new"

# Pull the `values:` block out of a HelmRelease and dedent it.
extract_values() {
  awk '
    /^  values:[[:space:]]*$/ { inblock=1; next }
    inblock {
      if ($0 ~ /^[[:space:]]*$/) { print ""; next }
      if ($0 !~ /^    /) { exit }
      sub(/^    /, ""); print
    }'
}

for spec in \
  "public/x86_64/v2:runner-x86-v2-pub"       "protected/x86_64/v2:runner-x86-v2-prot" \
  "public/x86_64/v3:runner-x86-v3-pub"       "protected/x86_64/v3:runner-x86-v3-prot" \
  "public/x86_64/v4:runner-x86-v4-pub"       "protected/x86_64/v4:runner-x86-v4-prot" \
  "public/graviton/3:runner-graviton3-pub"   "protected/graviton/3:runner-graviton3-prot" \
  "public/graviton/4:runner-graviton4-pub"   "protected/graviton/4:runner-graviton4-prot" ; do
  path="${spec%%:*}"; rel="${spec##*:}"
  git -C "$REPO" show "$BEFORE:k8s/production/runners/$path/release.yaml" \
    | extract_values > "$WORK/$rel.values.yaml"
  helm template "$rel" "$GLR" -n gitlab -f "$WORK/$rel.values.yaml" > "$WORK/old/$rel.yaml"
done

for t in x86_64-v2 x86_64-v3 x86_64-v4 graviton3 graviton4; do
  rel="runner-${t/x86_64-/x86-}"
  extract_values < "$REPO/k8s/production/runners/types/$t.yaml" > "$WORK/$t.values.yaml"
  helm template "$rel" "$CHART" -n gitlab -f "$WORK/$t.values.yaml" > "$WORK/new/$t.yaml"
done

# Split into one file per object, keyed by kind+name.
split_docs() {
  awk -v dest="$2" '
    /^---$/ { doc++; next }
    { docs[doc] = docs[doc] $0 "\n" }
    END {
      for (i in docs) {
        body = docs[i]; kind = ""; name = ""
        n = split(body, lines, "\n")
        for (j = 1; j <= n; j++) {
          if (kind == "" && lines[j] ~ /^kind: /)   kind = substr(lines[j], 7)
          if (name == "" && lines[j] ~ /^  name: /) name = substr(lines[j], 9)
        }
        if (kind == "" || name == "") continue
        gsub(/"/, "", name)
        f = dest "/" kind "." name ".yaml"
        printf "%s", body > f
        close(f)
      }
    }' "$1"
}
mkdir -p "$WORK/split/old" "$WORK/split/new"
for f in "$WORK"/old/*.yaml; do split_docs "$f" "$WORK/split/old"; done
for f in "$WORK"/new/*.yaml; do split_docs "$f" "$WORK/split/new"; done

# Two runners now share one Helm release, so the `chart` and `release` labels
# necessarily change. Normalize those; everything else must match.
normalize() {
  sed -E -e '/^# Source:/d' \
         -e 's/^([[:space:]]+)(chart|release): .*/\1\2: NORMALIZED/' "$1"
}

status=0
for f in $(ls "$WORK/split/old"); do
  if diff -q <(normalize "$WORK/split/old/$f") <(normalize "$WORK/split/new/$f") >/dev/null; then
    echo "  identical: $f"
  else
    echo "  DIFFERS:   $f"
    # `diff` exits non-zero here by construction; pipefail would abort the loop.
    { diff -u <(normalize "$WORK/split/old/$f") <(normalize "$WORK/split/new/$f") \
      | grep -E '^[+-][^+-]' | sed 's/^/      /'; } || true
    status=1
  fi
done

echo
echo "NodePools (compared against the deleted provisioner manifests at $BEFORE):"
for spec in \
  "glr-x86-64-v2:x86_64/v2" "glr-x86-64-v3:x86_64/v3" "glr-x86-64-v4:x86_64/v4" \
  "glr-graviton3:graviton/3" "glr-graviton4:graviton/4" ; do
  name="${spec%%:*}"; path="${spec##*:}"
  git -C "$REPO" show \
    "$BEFORE:k8s/production/karpenter/provisioners/runners/$path/provisioners.yaml" \
    > "$WORK/$name.old.yaml"
  # Compare the fields that matter, ignoring key order, list order within a
  # requirement, and the annotations Helm adds.
  "${PYTHON:-python3}" - "$WORK/$name.old.yaml" "$WORK/split/new/NodePool.$name.yaml" "$name" <<'PY' || status=1
import sys, json, yaml
def canon(doc):
    doc = json.loads(json.dumps(doc))
    doc["metadata"].pop("annotations", None)
    reqs = doc["spec"]["template"]["spec"].get("requirements", [])
    for r in reqs:
        if isinstance(r.get("values"), list):
            r["values"] = sorted(r["values"])
    doc["spec"]["template"]["spec"]["requirements"] = sorted(reqs, key=lambda r: r["key"])
    return doc
old = canon([d for d in yaml.safe_load_all(open(sys.argv[1])) if d][0])
new = canon(yaml.safe_load(open(sys.argv[2])))
if old == new:
    print(f"  identical: NodePool/{sys.argv[3]}")
else:
    import difflib
    print(f"  DIFFERS:   NodePool/{sys.argv[3]}")
    for line in difflib.unified_diff(
            json.dumps(old, indent=2, sort_keys=True).splitlines(),
            json.dumps(new, indent=2, sort_keys=True).splitlines(),
            "committed", "rendered", lineterm="", n=1):
        print("     ", line)
    sys.exit(1)
PY
done

exit $status
