terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.5"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = ">= 2.0.0"
    }
    github = {
      source  = "integrations/github"
      version = "~> 5.13.0"
    }
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "16.3.0"
    }
  }
}

# Data source that allows us to dynamically determine the current AWS region
data "aws_region" "current" {}

# Data source that allows us to dynamically determine id of the current "canonical user"
data "aws_canonical_user_id" "current" {}
