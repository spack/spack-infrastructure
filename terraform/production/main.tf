terraform {
  required_version = "~> 1.5.2"

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
      source  = "alekc/kubectl"
      version = ">= 2.0.0"
    }
    flux = {
      source  = "fluxcd/flux"
      version = "1.2.2"
    }
    github = {
      source  = "integrations/github"
      version = "~> 5.13.0"
    }
    gitlab = {
      source  = "gitlabhq/gitlab"
      version = "16.3.0"
    }
    sentry = {
      source  = "jianyuan/sentry"
      version = "0.11.2"
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

data "kubernetes_ingress_v1" "gitlab_webservice" {
  metadata {
    name      = "gitlab-webservice-default"
    namespace = "gitlab"
  }
}

locals {
  gitlab_url = "https://${data.kubernetes_ingress_v1.gitlab_webservice.spec[0].rule[0].host}"
}

provider "gitlab" {
  base_url = local.gitlab_url
  token    = jsondecode(data.aws_secretsmanager_secret_version.gitlab_token.secret_string).gitlab_terraform_provider_access_token
}

module "production_cluster" {
  source = "../modules/spack"

  deployment_name = "prod"

  gitlab_url = local.gitlab_url

  kubernetes_version = "1.27"

  availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d"]

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

  cdash_db_instance_class = "db.m6g.large"

  gitlab_db_instance_class            = "db.t3.xlarge"
  gitlab_db_master_credentials_secret = "arn:aws:secretsmanager:us-east-1:588562868276:secret:gitlab-prod-master-credentials-96P0Cl"

  analytics_db_credentials_secret = "arn:aws:secretsmanager:us-east-1:588562868276:secret:analytics-master-credentials-X2JScV"

  # GitLab docs recommend m class for redis
  # https://docs.gitlab.com/ee/administration/reference_architectures/3k_users.html#cluster-topology
  elasticache_instance_class = "cache.m6g.xlarge"

  opensearch_instance_type = "r6g.xlarge.search"
  opensearch_volume_size   = 500


  ses_email_domain = "spack.io"
}

module "gitlab_runner_configuration" {
  source = "../modules/spack/modules/gitlab_runner_configuration"

  deployment_name = "prod"

  protected_binary_bucket_arn = module.production_cluster.protected_binary_bucket_arn
  pr_binary_bucket_arn        = module.production_cluster.pr_binary_bucket_arn
}
