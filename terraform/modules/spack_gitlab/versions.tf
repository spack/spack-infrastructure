terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    kubectl = {
      source = "alekc/kubectl"
    }
    gitlab = {
      source = "gitlabhq/gitlab"
    }
  }
}

provider "aws" {
  region = var.region

  assume_role {
    role_arn = "arn:aws:iam::588562868276:role/terraform-role"
  }
}


provider "kubectl" {
  host                   = data.aws_eks_cluster.spack.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.spack.certificate_authority[0].data)

  exec {
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

provider "gitlab" {
  base_url = local.gitlab_url
  token    = var.gitlab_token
}
