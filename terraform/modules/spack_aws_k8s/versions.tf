terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
    }
    kubectl = {
      source = "alekc/kubectl"
    }
    helm = {
      source = "hashicorp/helm"
    }
    flux = {
      source = "fluxcd/flux"
    }
  }
}

locals {
  eks_cluster_role = coalesce(var.eks_cluster_role, aws_iam_role.eks_cluster_access.arn)
}

provider "aws" {
  region = var.region
}


provider "kubectl" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    # This requires the awscli to be installed locally where Terraform is executed
    args = [
      "eks",
      "get-token",
      "--cluster-name",
      module.eks.cluster_name,
      "--role", local.eks_cluster_role,
    ]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      # This requires the awscli to be installed locally where Terraform is executed
      args = [
        "eks",
        "get-token",
        "--cluster-name",
        module.eks.cluster_name,
        "--role", local.eks_cluster_role,
      ]
    }
  }
}

provider "flux" {
  kubernetes = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)

    exec = {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      # This requires the awscli to be installed locally where Terraform is executed
      args = [
        "eks",
        "get-token",
        "--cluster-name",
        module.eks.cluster_name,
        "--role", local.eks_cluster_role,
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
