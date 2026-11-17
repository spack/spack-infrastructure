resource "flux_bootstrap_git" "this" {
  path = var.flux_path

  # The Flux version to install. Terraform generates
  # k8s/*/flux-system/gotk-components.yaml from this, so upgrade Flux by
  # changing this value, never by editing that file. Renovate bumps it via the
  # custom manager in .github/renovate.json5.
  version = "v2.10.0"

  toleration_keys = ["CriticalAddonsOnly"]
}
