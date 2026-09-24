locals {
  suffix     = var.deployment_name != "prod" ? "-${var.deployment_name}" : ""
  gitlab_url = "https://gitlab${var.deployment_name == "prod" ? "" : ".${var.deployment_name}"}.spack.io"

  # The host GitLab advertises in SSH clone URLs. Must match global.hosts.ssh
  # in k8s/*/gitlab/.
  gitlab_ssh_host = "ssh.gitlab${var.deployment_name == "prod" ? "" : ".${var.deployment_name}"}.spack.io"
}
