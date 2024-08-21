resource "flux_bootstrap_git" "this" {
  path            = var.flux_path
  toleration_keys = ["CriticalAddonsOnly"]
}
