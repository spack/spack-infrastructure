terraform {
  required_version = "~> 1.11.3"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.17.0"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "2.1.3"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "2.16.1"
    }
    flux = {
      source  = "fluxcd/flux"
      version = "1.7.3"
    }
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "17.6.1"
    }
  }

  backend "s3" {
    bucket       = "spack-terraform-state"
    key          = "staging/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
