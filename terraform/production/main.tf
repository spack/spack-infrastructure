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
    host                   = module.production_cluster.cluster_endpoint
    cluster_ca_certificate = module.production_cluster.cluster_ca_certificate
    exec {
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
}

provider "kubectl" {
  host                   = module.production_cluster.cluster_endpoint
  cluster_ca_certificate = module.production_cluster.cluster_ca_certificate
  exec {
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

provider "kubernetes" {
  host                   = module.production_cluster.cluster_endpoint
  cluster_ca_certificate = module.production_cluster.cluster_ca_certificate
  exec {
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


provider "github" {
  owner = "spack"
  token = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
}

module "production_cluster" {
  source = "../modules/spack"

  deployment_name = "production"

  availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]

  vpc_cidr = "10.0.0.0/16"
  public_subnets = [
    "10.0.0.0/19",
    "10.0.32.0/19",
  ]
  private_subnets = [
    "10.0.64.0/19",
    "10.0.96.0/19",
    "10.0.128.0/19",
    "10.0.160.0/19",
  ]
  database_subnets = [
    "10.0.192.0/19",
    "10.0.224.0/19",
  ]

  flux_repo_name   = "spack-infrastructure"
  flux_repo_owner  = "spack"
  flux_branch      = "main"
  flux_target_path = "k8s/production/"

  cdash_db_instance_class  = "db.m6g.large"
  gitlab_db_instance_class = "db.t3.xlarge"

  provision_opensearch_cluster = true
}
