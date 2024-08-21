locals {
  suffix = var.deployment_name != "prod" ? "-${var.deployment_name}" : ""
  gitlab_url = "https://gitlab${var.deployment_name == "prod" ? "" : ".${var.deployment_name}"}.spack.io"
}
