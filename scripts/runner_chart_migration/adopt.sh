#!/usr/bin/env bash
#
# One-time migration for moving the Linux GitLab runners and their Karpenter
# NodePools into charts/spack-runner-type.
#
# RUN THIS BEFORE MERGING THE PR, against the cluster being migrated.
#
# Why it is needed
# ----------------
# The refactor changes who owns three sets of live objects:
#
#   * the runner ConfigMaps/Deployments move from ten Helm releases (one per
#     runner) to five (one per runner type), so their
#     `meta.helm.sh/release-name` annotation has to be repointed;
#   * the NodePools move from kustomize-controller to Helm;
#   * the old HelmReleases and NodePool manifests disappear from git, so
#     kustomize-controller will prune them.
#
# Without this script, merging would: prune the NodePools (Karpenter then
# deletes their NodeClaims and drains every build node), uninstall the ten old
# Helm releases (deleting the runner Deployments), and only then install the new
# releases. That is a full CI outage with killed jobs, for a change that is
# otherwise a no-op.
#
# With this script, the merge is an in-place adoption: Helm finds the objects
# already carrying the right ownership metadata and updates them in place.
#
# It is idempotent, and it only adds/removes metadata -- no spec is touched.

set -euo pipefail

NS=gitlab
DRY_RUN="${DRY_RUN:-1}"

kc() {
  if [ "$DRY_RUN" = "1" ]; then
    echo "  would run: kubectl $*"
  else
    kubectl "$@"
  fi
}

# runner name -> the new (per-type) Helm release that will own it
RUNNERS="
runner-x86-v2-pub:runner-x86-v2
runner-x86-v2-prot:runner-x86-v2
runner-x86-v3-pub:runner-x86-v3
runner-x86-v3-prot:runner-x86-v3
runner-x86-v4-pub:runner-x86-v4
runner-x86-v4-prot:runner-x86-v4
runner-graviton3-pub:runner-graviton3
runner-graviton3-prot:runner-graviton3
runner-graviton4-pub:runner-graviton4
runner-graviton4-prot:runner-graviton4
"

# NodePool -> the new Helm release that will own it
NODEPOOLS="
glr-x86-64-v2:runner-x86-v2
glr-x86-64-v3:runner-x86-v3
glr-x86-64-v4:runner-x86-v4
glr-graviton3:runner-graviton3
glr-graviton4:runner-graviton4
"

if [ "$DRY_RUN" = "1" ]; then
  echo "DRY RUN -- set DRY_RUN=0 to apply."
  echo "Context: $(kubectl config current-context 2>/dev/null || echo '<none>')"
  echo
fi

echo "== 1. Protect the runner ConfigMaps/Deployments from the old releases' uninstall"
# kustomize-controller prunes the old HelmRelease objects, which makes
# helm-controller uninstall the old Helm releases. `resource-policy: keep` makes
# that uninstall skip the resources instead of deleting them. Removed again in
# step 4 once the new releases own them.
for entry in $RUNNERS; do
  name="${entry%%:*}"
  for kind in configmap deployment; do
    kc -n "$NS" annotate --overwrite "$kind/$name-gitlab-runner" \
      helm.sh/resource-policy=keep
  done
done

echo
echo "== 2. Repoint the runner ConfigMaps/Deployments at their new Helm release"
for entry in $RUNNERS; do
  name="${entry%%:*}"; rel="${entry##*:}"
  for kind in configmap deployment; do
    kc -n "$NS" annotate --overwrite "$kind/$name-gitlab-runner" \
      meta.helm.sh/release-name="$rel" \
      meta.helm.sh/release-namespace="$NS"
  done
done

echo
echo "== 3. Hand the NodePools from kustomize-controller to Helm"
# Dropping the kustomize.toolkit.fluxcd.io labels takes the NodePools out of
# Flux's prune set, so removing their manifests from git no longer deletes them.
for entry in $NODEPOOLS; do
  name="${entry%%:*}"; rel="${entry##*:}"
  kc label "nodepool/$name" \
    kustomize.toolkit.fluxcd.io/name- \
    kustomize.toolkit.fluxcd.io/namespace- || true
  kc label --overwrite "nodepool/$name" app.kubernetes.io/managed-by=Helm
  kc annotate --overwrite "nodepool/$name" \
    meta.helm.sh/release-name="$rel" \
    meta.helm.sh/release-namespace="$NS" \
    helm.sh/resource-policy=keep
done

echo
echo "== 4. AFTER the PR is merged and all five HelmReleases report Ready:"
echo "   Drop the temporary keep policy from the runner workloads, so a future"
echo "   rename or uninstall does not silently orphan them. (The NodePools keep"
echo "   theirs -- that one is set by the chart on purpose.)"
for entry in $RUNNERS; do
  name="${entry%%:*}"
  echo "  kubectl -n $NS annotate configmap/$name-gitlab-runner deployment/$name-gitlab-runner helm.sh/resource-policy-"
done
