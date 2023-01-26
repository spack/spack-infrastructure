terraform {
  required_version = "~> 1.3.6"

  backend "s3" {
    bucket         = "spack-terraform-state"
    key            = "terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "spack-terraform-state-locks"
    encrypt        = true
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 4.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.5"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
    }
    flux = {
      source  = "fluxcd/flux"
      version = "~> 0.22.2"
    }
    github = {
      source  = "integrations/github"
      version = "~> 5.13.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

provider "helm" {
  kubernetes {
    host                   = data.aws_eks_cluster.default.endpoint
    cluster_ca_certificate = base64decode(data.aws_eks_cluster.default.certificate_authority[0].data)
    token                  = data.aws_eks_cluster_auth.default.token
  }
}

data "aws_eks_cluster" "default" {
  name = module.eks.cluster_name

  depends_on = [
    module.eks.cluster_name
  ]
}

data "aws_eks_cluster_auth" "default" {
  name = module.eks.cluster_name

  depends_on = [
    module.eks.cluster_name
  ]
}

provider "kubectl" {
  host                   = data.aws_eks_cluster.default.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.default.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.default.token
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.default.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.default.certificate_authority[0].data)
  token                  = data.aws_eks_cluster_auth.default.token
}


provider "github" {
  owner = "mvandenburgh" # TODO: change this
  token = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
}

locals {
  cluster_name = "spack-${terraform.workspace}"
  vpc_cidr     = "10.0.0.0/16"
  azs          = terraform.workspace == "production" ? ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"] : ["us-east-1a", "us-east-1b"]
}
