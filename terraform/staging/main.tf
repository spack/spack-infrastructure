terraform {
  required_version = "~> 1.4.6"

  backend "s3" {
    bucket         = "spack-terraform-state-staging"
    key            = "terraform.tfstate"
    region         = "us-west-1"
    dynamodb_table = "spack-terraform-state-locks-staging"
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
  region = "us-west-2"
}

provider "helm" {
  kubernetes {
    host                   = module.staging_cluster.cluster_endpoint
    cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args = [
        "eks",
        "get-token",
        "--region", "us-west-2",
        "--cluster-name", module.staging_cluster.cluster_name,
        "--role", module.staging_cluster.cluster_access_role_arn
      ]
    }
  }
}

provider "kubectl" {
  host                   = module.staging_cluster.cluster_endpoint
  cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--region", "us-west-2",
      "--cluster-name", module.staging_cluster.cluster_name,
      "--role", module.staging_cluster.cluster_access_role_arn
    ]
  }
}

provider "kubernetes" {
  host                   = module.staging_cluster.cluster_endpoint
  cluster_ca_certificate = module.staging_cluster.cluster_ca_certificate
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args = [
      "eks",
      "get-token",
      "--region", "us-west-2",
      "--cluster-name", module.staging_cluster.cluster_name,
      "--role", module.staging_cluster.cluster_access_role_arn
    ]
  }
}


provider "github" {
  owner = "spack"
  token = jsondecode(data.aws_secretsmanager_secret_version.flux_github_token.secret_string).flux_github_token
}


module "staging_cluster" {
  source = "../modules/spack"

  deployment_name = "staging"

  kubernetes_version = "1.27"

  availability_zones = ["us-west-2a", "us-west-2b", "us-west-2c", "us-west-2d"]

  vpc_cidr = "192.168.0.0/16"
  public_subnets = [
    "192.168.0.0/19",
    "192.168.32.0/19",
    "192.168.64.0/19",
    "192.168.96.0/19",
  ]
  private_subnets = [
    "192.168.128.0/19",
    "192.168.160.0/19",
    "192.168.192.0/19",
    "192.168.224.0/19",
  ]

  flux_repo_name   = "spack-infrastructure"
  flux_repo_owner  = "spack"
  flux_branch      = "main"
  flux_target_path = "k8s/staging/"

  # Use cheap DB instances for staging deployment
  cdash_db_instance_class = "db.t3.small"

  gitlab_db_instance_class            = "db.t3.small"
  gitlab_db_master_credentials_secret = "arn:aws:secretsmanager:us-west-2:588562868276:secret:gitlab-staging-master-credentials-q5Fynz"

  provision_opensearch_cluster = false

  ses_email_domain = "staging.spack.io"
}
