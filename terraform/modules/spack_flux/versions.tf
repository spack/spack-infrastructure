terraform {
  required_providers {
    flux = {
      source = "fluxcd/flux"
    }
  }
}

provider "flux" {
  kubernetes = {
    host                   = data.aws_eks_cluster.spack.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.spack.certificate_authority[0].data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      # This requires the awscli to be installed locally where Terraform is executed
      args = [
        "eks",
        "get-token",
        "--cluster-name",
        data.aws_eks_cluster.spack.name,
        "--role",
        data.aws_iam_role.eks_cluster_access.arn
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


data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
