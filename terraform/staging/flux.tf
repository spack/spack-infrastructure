provider "flux" {
  config_path = "~/.kube/configs/spack-staging"
}

resource "flux_bootstrap_git" "this" {
  url = "https://github.com/spack/spack-infrastructure"
  path = "k8s/staging/"
  http = {
    username = "spackbot"
    password = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
  }
}
