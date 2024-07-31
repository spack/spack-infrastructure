provider "flux" {
  kubernetes = {
    host                   = module.production_cluster.cluster_endpoint
    cluster_ca_certificate = module.production_cluster.cluster_ca_certificate
    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--region", "us-east-1",
        "--cluster-name", module.production_cluster.cluster_name,
        "--role", module.production_cluster.cluster_access_role_arn
      ]
    }
  }
  git = {
    url = "https://github.com/spack/spack-infrastructure"
    http = {
      username = "spackbot"
      password = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
    }
  }
}

resource "flux_bootstrap_git" "this" {
  path            = "k8s/production/"
  toleration_keys = ["CriticalAddonsOnly"]
}
